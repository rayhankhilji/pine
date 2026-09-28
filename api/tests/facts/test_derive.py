"""Derived facts — FactLink lineage, pairing rules, idempotency (F-05.AC4)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.facts.derive import derive_facts
from pine.facts.extractors import run_extractors
from pine.facts.extractors.base import ensure_company
from pine.facts.llm_extract import extract_facts
from pine.facts.store import EvidenceSpec, EvidenceStore
from pine.models.deal import Deal
from pine.models.document import DocType
from pine.models.entity import Entity
from pine.models.evidence import Evidence
from pine.models.fact import ExtractionMethod, Fact, FactLink

from .conftest import mk_chunk, mk_deal, mk_document


def _ev(document_id: str, chunk_id: str, quote: str) -> list[EvidenceSpec]:
    return [
        EvidenceSpec(
            document_id=document_id, page_no=1, chunk_id=chunk_id, quote=quote
        )
    ]


def _setup(session: Session, deal: Deal) -> tuple[EvidenceStore, Entity, list[EvidenceSpec]]:
    doc = mk_document(session, deal, "deck.pdf", DocType.deck)
    chunk = mk_chunk(session, doc, "Revenue $9.7M and COGS $2.5M for FY2025.")
    store = EvidenceStore(session, deal.id)
    company = ensure_company(store, deal)
    return store, company, _ev(doc.id, chunk.id, "Revenue $9.7M")


def _fact(
    store: EvidenceStore,
    subject: Entity,
    metric: str,
    value: int | str,
    evidence: list[EvidenceSpec],
    *,
    period_type: str = "fiscal_year",
    period_start: date | None = None,
    period_end: date | None = None,
    as_of: date | None = None,
) -> Fact:
    return store.add_fact(
        subject_entity_id=subject.id,
        metric=metric,
        value=Decimal(str(value)),
        unit="currency",
        currency="USD",
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        source_kind="deck",
        extraction_method="table",
        evidence=evidence,
    )


def _parents(session: Session, fact: Fact) -> dict[str, str]:
    links = session.scalars(
        select(FactLink).where(FactLink.fact_id == fact.id)
    ).all()
    return {link.parent_fact_id: link.role for link in links}


def test_runway_derived_ac4(session: Session) -> None:
    """F-05.AC4 — cash + net_burn → derived runway_months with parents."""
    deal = mk_deal(session)
    store, company, ev = _setup(session, deal)
    cash = _fact(
        store, company, "cash_balance", 6_200_000, ev,
        period_type="point", period_start=date(2025, 12, 31),
        period_end=date(2025, 12, 31), as_of=date(2025, 12, 31),
    )
    burn = _fact(
        store, company, "net_burn", 450_000, ev,
        period_type="quarter", period_start=date(2025, 10, 1),
        period_end=date(2025, 12, 31),
    )
    stats = derive_facts(session, deal.id)
    assert stats.facts_written == 1
    runway = session.scalar(
        select(Fact)
        .where(Fact.metric == "runway_months")
        .where(Fact.extraction_method == ExtractionMethod.derived.value)
    )
    assert runway is not None
    assert runway.value == Decimal("13.78")  # 6.2M / 450k
    assert runway.as_of == date(2025, 12, 31)
    parents = _parents(session, runway)
    assert parents[cash.id] == "numerator"
    assert parents[burn.id] == "denominator"
    # derived facts carry no direct evidence
    assert not session.scalars(
        select(Evidence)
        .where(Evidence.target_kind == "fact")
        .where(Evidence.target_id == runway.id)
    ).all()


def test_gross_profit_and_margin(session: Session) -> None:
    deal = mk_deal(session)
    store, company, ev = _setup(session, deal)
    rev = _fact(
        store, company, "revenue", 9_700_000, ev,
        period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
    )
    cogs = _fact(
        store, company, "cogs", 2_522_000, ev,
        period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
    )
    derive_facts(session, deal.id)
    gp = session.scalar(
        select(Fact).where(
            Fact.metric == "gross_profit",
            Fact.extraction_method == "derived",
        )
    )
    assert gp is not None and gp.value == Decimal("7178000")
    links = _parents(session, gp)
    assert links[rev.id] == "addend"
    assert links[cogs.id] == "subtrahend"
    margin = session.scalar(
        select(Fact).where(
            Fact.metric == "gross_margin", Fact.extraction_method == "derived"
        )
    )
    assert margin is not None and margin.value == Decimal("74.00")


def test_margin_uses_existing_gross_profit(session: Session) -> None:
    deal = mk_deal(session)
    store, company, ev = _setup(session, deal)
    rev = _fact(
        store, company, "revenue", 10_000_000, ev,
        period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
    )
    gp = _fact(
        store, company, "gross_profit", 7_500_000, ev,
        period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
    )
    derive_facts(session, deal.id)
    margin = session.scalar(
        select(Fact).where(
            Fact.metric == "gross_margin", Fact.extraction_method == "derived"
        )
    )
    assert margin is not None and margin.value == Decimal("75.00")
    links = _parents(session, margin)
    assert links[gp.id] == "numerator"
    assert links[rev.id] == "denominator"
    # no derived gross_profit written — the stated one was used
    assert not session.scalar(
        select(Fact).where(
            Fact.metric == "gross_profit",
            Fact.extraction_method == "derived",
        )
    )


def test_concentration_derived(session: Session) -> None:
    deal = mk_deal(session)
    store, company, _ = _setup(session, deal)
    # contract_value cohort must be evidenced from a customer_list document
    cl = mk_document(session, deal, "customers.csv", DocType.customer_list)
    cl_chunk = mk_chunk(session, cl, "customer,arr\nA,80\nB,15\nC,5")
    ev = _ev(cl.id, cl_chunk.id, "customer,arr")
    for i, val in enumerate((80, 15, 5)):
        cust = store.add_entity(
            type="customer",
            canonical_name=f"Customer {i}",
            evidence=ev,
        )
        _fact(
            store, cust, "contract_value", val, ev,
            period_type="custom",
            period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
        )
    derive_facts(session, deal.id)
    conc = session.scalar(
        select(Fact).where(
            Fact.metric == "top_customer_concentration",
            Fact.extraction_method == "derived",
        )
    )
    assert conc is not None
    assert conc.value == Decimal("80.00")
    assert conc.subject_entity_id == company.id
    links = _parents(session, conc)
    roles = sorted(links.values())
    assert roles.count("numerator") == 1
    assert roles.count("denominator") == 2  # top parent is numerator-only


def test_nrr_consecutive_periods(session: Session) -> None:
    deal = mk_deal(session)
    store, company, ev = _setup(session, deal)
    start = _fact(
        store, company, "recurring_revenue", 10_000_000, ev,
        period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
    )
    end = _fact(
        store, company, "recurring_revenue", 11_800_000, ev,
        period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
    )
    derive_facts(session, deal.id)
    nrr = session.scalar(
        select(Fact).where(
            Fact.metric == "net_revenue_retention",
            Fact.extraction_method == "derived",
        )
    )
    assert nrr is not None and nrr.value == Decimal("118.00")
    links = _parents(session, nrr)
    assert links[end.id] == "numerator"
    assert links[start.id] == "denominator"


def test_derive_idempotent(session: Session) -> None:
    deal = mk_deal(session)
    store, company, ev = _setup(session, deal)
    _fact(
        store, company, "cash_balance", 6_200_000, ev,
        period_type="point", period_start=date(2025, 12, 31),
        period_end=date(2025, 12, 31), as_of=date(2025, 12, 31),
    )
    _fact(
        store, company, "net_burn", 450_000, ev,
        period_type="quarter", period_start=date(2025, 10, 1),
        period_end=date(2025, 12, 31),
    )
    first = derive_facts(session, deal.id)
    second = derive_facts(session, deal.id)
    assert first.facts_written == 1
    assert second.facts_written == 0
    assert second.skipped_existing == 1


def test_derive_demo_room(session: Session, demo_deal: Deal) -> None:
    deal = demo_deal  # fixture drains the whole chain — facts already derived
    run_extractors(session, deal.id)
    extract_facts(session, deal.id)
    stats = derive_facts(session, deal.id)
    session.commit()
    # explicit re-run is idempotent: everything below already exists
    assert stats.facts_written == 0
    assert stats.skipped_existing > 0

    def value(metric: str) -> Decimal | None:
        f = session.scalar(
            select(Fact)
            .where(Fact.deal_id == deal.id)
            .where(Fact.metric == metric)
            .where(Fact.extraction_method == "derived")
        )
        return f.value if f else None

    # cash 6.2M ÷ net burn 450k (Oct–Dec 2025 contains the Dec-31 as-of)
    assert value("runway_months") == Decimal("13.78")
    # customer-list snapshot: 2,244,000 / 10,200,000
    assert value("top_customer_concentration") == Decimal("22.00")
    margins = session.scalars(
        select(Fact.value)
        .where(Fact.deal_id == deal.id)
        .where(Fact.metric == "gross_margin")
        .where(Fact.extraction_method == "derived")
        .order_by(Fact.period_start)
    ).all()
    # FY2024 from revenue−cogs; FY2025 prefers the stated gross profit
    # (7.2M — deliberately ≠ 9.7M − 2.522M in the demo fixture)
    assert Decimal("70.00") in margins and Decimal("74.23") in margins
