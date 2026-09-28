"""LLM prose extraction — FakeLLM heuristic + scripted fixtures (F-05.AC2/AC3)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.facts.extractors import run_extractors
from pine.facts.llm_extract import extract_facts
from pine.llm.fake import FakeLLM
from pine.models.chunk import ChunkKind
from pine.models.deal import Deal
from pine.models.document import DocType, Document
from pine.models.entity import Entity
from pine.models.evidence import Evidence
from pine.models.fact import ExtractionMethod, Fact
from pine.models.llm_call import LLMCall

from .conftest import mk_chunk, mk_deal, mk_document


def _facts(session: Session, deal: Deal, metric: str) -> list[Fact]:
    return list(
        session.scalars(
            select(Fact)
            .where(Fact.deal_id == deal.id)
            .where(Fact.metric == metric)
            .order_by(Fact.created_at)
        ).all()
    )


def _prose_doc(
    session: Session, deal: Deal, text: str, filename: str, doc_type: DocType
) -> Document:
    doc = mk_document(session, deal, filename, doc_type)
    mk_chunk(session, doc, text, kind=ChunkKind.prose)
    return doc


def test_llm_extracts_arr_fact(session: Session) -> None:
    """F-05.AC2 — 'ARR reached $12M in Q4 2025' produces an arr fact."""
    deal = mk_deal(session, "Northwind")
    _prose_doc(
        session,
        deal,
        "ARR reached $12.0M in Q4 2025, up 3x YoY",
        "deck.pptx",
        DocType.deck,
    )
    stats = extract_facts(session, deal.id)
    assert stats.evidence_mismatches == 0
    arr = _facts(session, deal, "arr")
    assert len(arr) == 1
    fact = arr[0]
    assert fact.value == Decimal("12000000")
    assert fact.extraction_method == ExtractionMethod.llm.value
    assert (fact.period_start, fact.period_end) == (
        date(2025, 10, 1),
        date(2025, 12, 31),
    )
    ev = session.scalars(
        select(Evidence)
        .where(Evidence.target_kind == "fact")
        .where(Evidence.target_id == fact.id)
    ).all()
    assert len(ev) == 1
    assert ev[0].chunk_id is not None
    assert ev[0].quote == "ARR reached $12.0M in Q4 2025, up 3x YoY"

    # an LLMCall row recorded the call
    call = session.scalar(select(LLMCall).where(LLMCall.purpose == "extract_facts"))
    assert call is not None
    assert call.request_hash and not call.cache_hit


def test_invalid_quote_logged_not_persisted(session: Session) -> None:
    """F-05.AC3 — a quote that is not in the chunk yields no Fact + EVIDENCE_MISMATCH."""
    deal = mk_deal(session, "Northwind")
    _prose_doc(session, deal, "The company is doing well.", "d.txt", DocType.deck)
    fake = FakeLLM(
        scripts=[
            {
                "purpose": "extract_facts",
                "match": "doing well",
                "response": {
                    "facts": [
                        {
                            "metric": "arr",
                            "value": 12000000,
                            "unit": "currency",
                            "currency": "USD",
                            "period_label": "Q4 2025",
                            "evidence_quote": "ARR reached $12M in Q4 2025",
                        }
                    ]
                },
            }
        ]
    )
    stats = extract_facts(session, deal.id, llm=fake)
    assert stats.evidence_mismatches == 1
    assert stats.facts_written == 0
    assert not _facts(session, deal, "arr")


def test_unknown_metric_rejected_by_schema(session: Session) -> None:
    deal = mk_deal(session, "Northwind")
    _prose_doc(session, deal, "Waffle index is high", "d.txt", DocType.deck)
    fake = FakeLLM(
        scripts=[
            {
                "purpose": "extract_facts",
                "match": "Waffle",
                "response": {
                    "facts": [
                        {
                            "metric": "waffle_index",
                            "value": 3,
                            "unit": "count",
                            "evidence_quote": "Waffle index is high",
                        }
                    ]
                },
            }
        ]
    )
    # schema validation fails → the call raises inside _extract_chunk → error
    stats = extract_facts(session, deal.id, llm=fake)
    assert stats.facts_written == 0
    assert stats.errors


def test_llm_cache_hit_skips_provider(session: Session) -> None:
    deal = mk_deal(session, "Northwind")
    _prose_doc(
        session, deal, "Cash on hand $6.2M as of December 31, 2025.", "d.pdf",
        DocType.board_deck,
    )
    first = extract_facts(session, deal.id)
    assert first.facts_written == 1

    # identical call again → second LLMCall row is a cache hit, no new fact
    extract_facts(session, deal.id)
    calls = session.scalars(
        select(LLMCall)
        .where(LLMCall.purpose == "extract_facts")
        .order_by(LLMCall.created_at)
    ).all()
    assert len(calls) == 2
    assert calls[1].cache_hit is True
    cash = _facts(session, deal, "cash_balance")
    assert len(cash) == 1
    assert cash[0].value == Decimal("6200000")
    assert cash[0].as_of == date(2025, 12, 31)


def test_yaml_script_fixture(tmp_path: Path, session: Session) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "demo.yaml").write_text(
        """
- purpose: extract_facts
  match: "record revenue of"
  response:
    facts:
      - metric: revenue
        value: 99000
        unit: currency
        currency: USD
        period_label: FY2025
        evidence_quote: "record revenue of $99,000"
"""
    )
    deal = mk_deal(session, "Northwind")
    _prose_doc(
        session, deal, "We booked record revenue of $99,000 last year.",
        "note.txt", DocType.email,
    )
    fake = FakeLLM(fixtures_dir=fixture_dir)
    stats = extract_facts(session, deal.id, llm=fake)
    assert stats.facts_written == 1
    rev = _facts(session, deal, "revenue")
    assert rev[0].value == Decimal("99000")


def test_table_chunks_are_skipped(session: Session) -> None:
    deal = mk_deal(session, "Northwind")
    doc = mk_document(session, deal, "t.csv", DocType.financial_statement)
    mk_chunk(
        session, doc, "FY2024 revenue, 4100000", kind=ChunkKind.table_rows
    )
    stats = extract_facts(session, deal.id)
    assert stats.chunks == 0
    assert stats.calls == 0


def test_demo_room_llm_extraction(session: Session, demo_deal: Deal) -> None:
    """Prose facts from the demo room (deck, board deck, contracts, emails)."""
    deal = demo_deal
    run_extractors(session, deal.id)  # entities + reference FY exist first
    stats = extract_facts(session, deal.id)
    session.commit()
    assert stats.evidence_mismatches == 0
    assert stats.errors == []

    def found(metric: str, value: Decimal, in_doc: str) -> bool:
        return bool(
            session.scalar(
                select(func.count())
                .select_from(Fact)
                .join(
                    Evidence,
                    (Evidence.target_id == Fact.id)
                    & (Evidence.target_kind == "fact"),
                )
                .join(Document, Evidence.document_id == Document.id)
                .where(Fact.deal_id == deal.id)
                .where(Fact.metric == metric)
                .where(Fact.value == value)
                .where(Document.filename == in_doc)
            )
        )

    assert found("arr", Decimal("12000000"), "01_Northwind_SeriesB_Deck.pptx")
    assert found("tam", Decimal("40000000000"), "01_Northwind_SeriesB_Deck.pptx")
    assert found("net_burn", Decimal("450000"), "07_Board_Deck_Q4_2025.pdf")
    assert found("runway_months", Decimal("14"), "07_Board_Deck_Q4_2025.pdf")
    assert found(
        "net_revenue_retention", Decimal("118"), "07_Board_Deck_Q4_2025.pdf"
    )
    assert found(
        "contract_value", Decimal("6700000"), "MSA_Acme_Corporation.pdf"
    )

    # subject resolution: the Acme MSA fact attaches to the customer entity
    # (the customer-list extractor also wrote a 2,244,000 contract_value for
    # Acme — so scope to the MSA document + llm method)
    acme = session.scalar(
        select(Entity).where(
            Entity.deal_id == deal.id, Entity.canonical_name == "Acme Corporation"
        )
    )
    assert acme is not None
    msa = session.scalar(
        select(Document).where(
            Document.deal_id == deal.id,
            Document.filename == "MSA_Acme_Corporation.pdf",
        )
    )
    assert msa is not None
    cv = session.scalar(
        select(Fact)
        .join(
            Evidence,
            (Evidence.target_id == Fact.id)
            & (Evidence.target_kind == "fact"),
        )
        .where(Fact.deal_id == deal.id)
        .where(Fact.metric == "contract_value")
        .where(Fact.subject_entity_id == acme.id)
        .where(Fact.extraction_method == ExtractionMethod.llm.value)
        .where(Evidence.document_id == msa.id)
    )
    assert cv is not None and cv.value == Decimal("6700000")
