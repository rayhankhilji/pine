"""Hybrid retrieval tests — F-03.AC1/AC2 on a small synthetic room."""

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

import pine.index.jobs  # noqa: F401 — registers index_deal
from pine.index.retrieval import SearchFilters, hybrid_search
from pine.jobs.queue import enqueue
from pine.jobs.worker import _HANDLERS
from pine.models.deal import Deal
from pine.models.document import (
    Blob,
    Block,
    BlockKind,
    Cell,
    DocStatus,
    DocType,
    Document,
    Page,
    Table,
)
from pine.models.job import JobKind


@pytest.fixture(autouse=True)
def _hash_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "hash")
    from pine.config import get_settings

    get_settings.cache_clear()


def _text_doc(
    session: Session,
    deal: Deal,
    name: str,
    text: str,
    doc_type: DocType = DocType.other,
    doc_date: date | None = None,
    ext: str = "txt",
) -> Document:
    blob = Blob(sha256=uuid.uuid4().hex * 2, size_bytes=1, mime="text/plain", path=name)
    session.add(blob)
    session.flush()
    doc = Document(
        deal_id=deal.id,
        blob_id=blob.id,
        filename=name,
        path=name,
        ext=ext,
        doc_type=doc_type,
        status=DocStatus.parsed,
        page_count=1,
        doc_date=doc_date,
    )
    session.add(doc)
    session.flush()
    page = Page(document_id=doc.id, page_no=1, text=text)
    session.add(page)
    session.flush()
    session.add(
        Block(
            page_id=page.id,
            order=0,
            kind=BlockKind.paragraph,
            text=text,
            char_start=0,
            char_end=len(text),
        )
    )
    session.flush()
    return doc


def _table_doc(
    session: Session,
    deal: Deal,
    name: str,
    header: list[str],
    rows: list[list[str]],
    doc_type: DocType = DocType.other,
    doc_date: date | None = None,
) -> Document:
    blob = Blob(sha256=uuid.uuid4().hex * 2, size_bytes=1, mime="text/csv", path=name)
    session.add(blob)
    session.flush()
    doc = Document(
        deal_id=deal.id,
        blob_id=blob.id,
        filename=name,
        path=name,
        ext="csv",
        doc_type=doc_type,
        status=DocStatus.parsed,
        page_count=1,
        doc_date=doc_date,
    )
    session.add(doc)
    session.flush()
    page = Page(document_id=doc.id, page_no=1, text="")
    session.add(page)
    session.flush()
    table = Table(
        page_id=page.id, order=0, n_rows=len(rows) + 1, n_cols=len(header), header_row=0
    )
    session.add(table)
    session.flush()
    for c, text in enumerate(header):
        session.add(Cell(table_id=table.id, row=0, col=c, text=text))
    for r, row in enumerate(rows, start=1):
        for c, text in enumerate(row):
            session.add(Cell(table_id=table.id, row=r, col=c, text=text))
    session.flush()
    return doc


def _room(session: Session) -> tuple[Deal, dict[str, Document]]:
    """Synthetic mini-room: deck-ish prose, customer table, contract, filler."""
    deal = Deal(name="D", company_name="C")
    session.add(deal)
    session.flush()
    docs = {
        "deck": _text_doc(
            session, deal, "deck.txt",
            "Growth metrics. Annual recurring revenue reached $12.0M in Q4 2025, "
            "up 3x year over year. Net revenue retention 118%.",
            doc_type=DocType.deck, doc_date=date(2026, 1, 1),
        ),
        "customers": _table_doc(
            session, deal, "customers.csv",
            ["customer_name", "annual_recurring_revenue", "segment"],
            [[f"Customer {i}", str(1000 * i), "smb"] for i in range(1, 31)],
            doc_type=DocType.customer_list, doc_date=date(2026, 1, 2),
        ),
        "contract": _text_doc(
            session, deal, "msa.txt",
            "Master Services Agreement between Northwind and Acme. "
            "Section 7.2 — Termination for Change of Control: Customer may "
            "terminate upon a change of control with thirty days notice. "
            "Governing law: Delaware.",
            doc_type=DocType.contract, doc_date=date(2025, 6, 1),
        ),
        "filler": _text_doc(
            session, deal, "lorem.txt",
            "lorem ipsum dolor sit amet consectetur adipiscing elit sed do "
            "eiusmod tempor incididunt ut labore et dolore magna aliqua",
            doc_type=DocType.other, doc_date=date(2024, 1, 1),
        ),
    }
    job = enqueue(session, JobKind.index_deal, {"deal_id": deal.id})
    _HANDLERS[JobKind.index_deal](session, job)
    session.commit()
    return deal, docs


def test_ac1_annual_recurring_revenue(session: Session) -> None:
    deal, room = _room(session)
    hits = hybrid_search(session, deal.id, "annual recurring revenue", k=10)
    assert hits
    top3_docs = {h.document_id for h in hits[:3]}
    assert room["deck"].id in top3_docs
    assert room["customers"].id in top3_docs
    # customer table chunk carries kind + header line
    cust_hit = next(h for h in hits[:3] if h.document_id == room["customers"].id)
    assert "annual_recurring_revenue" in cust_hit.text


def test_ac2_literal_section_clause(session: Session) -> None:
    deal, room = _room(session)
    hits = hybrid_search(session, deal.id, "Section 7.2", k=10)
    assert hits
    top3_docs = {h.document_id for h in hits[:3]}
    assert room["contract"].id in top3_docs
    contract_hit = next(h for h in hits[:3] if h.document_id == room["contract"].id)
    assert "Section 7.2" in contract_hit.text
    assert contract_hit.bm25_rank is not None


def test_hit_fields(session: Session) -> None:
    deal, room = _room(session)
    hits = hybrid_search(session, deal.id, "annual recurring revenue", k=5)
    for h in hits:
        assert h.chunk_id
        assert h.filename
        assert h.page_no >= 1
        assert h.score > 0
        assert h.bm25_rank is not None or h.dense_rank is not None


def test_filters_doc_type(session: Session) -> None:
    deal, room = _room(session)
    hits = hybrid_search(
        session, deal.id, "annual recurring revenue", k=10,
        filters=SearchFilters(doc_types=("customer_list",)),
    )
    assert hits
    assert all(h.document_id == room["customers"].id for h in hits)


def test_filters_document_ids(session: Session) -> None:
    deal, room = _room(session)
    hits = hybrid_search(
        session, deal.id, "termination change control", k=10,
        filters=SearchFilters(document_ids=(room["contract"].id,)),
    )
    assert hits
    assert all(h.document_id == room["contract"].id for h in hits)


def test_filters_date_range(session: Session) -> None:
    deal, room = _room(session)
    hits = hybrid_search(
        session, deal.id, "annual recurring revenue", k=10,
        filters=SearchFilters(date_from=date(2025, 12, 1), date_to=date(2026, 1, 3)),
    )
    assert hits
    # only the deck (Jan 1) and customers (Jan 2) fall inside the window
    assert {h.document_id for h in hits} <= {room["deck"].id, room["customers"].id}


def test_no_match_returns_bm25_empty_but_dense_hits(session: Session) -> None:
    deal, room = _room(session)
    hits = hybrid_search(session, deal.id, "xyzzy nothing matches", k=3)
    # dense path still returns ranked candidates; bm25_rank is None for those
    assert all(h.bm25_rank is None for h in hits if h.dense_rank is not None)


def test_empty_deal(session: Session) -> None:
    deal = Deal(name="E", company_name="E")
    session.add(deal)
    session.flush()
    assert hybrid_search(session, deal.id, "anything") == []


def test_table_row_chunks_rank(session: Session) -> None:
    deal, room = _room(session)
    hits = hybrid_search(session, deal.id, "customer_name segment", k=10)
    cust = [h for h in hits if h.document_id == room["customers"].id]
    assert cust
