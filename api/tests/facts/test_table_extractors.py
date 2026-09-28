"""Deterministic table extractors — synthetic tables + F-05.AC1 demo check."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.facts.extractors import run_extractors
from pine.facts.extractors.bank_statement import BankStatementExtractor
from pine.facts.extractors.base import TableGrid
from pine.facts.extractors.cap_table import CapTableExtractor
from pine.facts.extractors.customer_list import CustomerListExtractor
from pine.facts.extractors.pnl import PnlExtractor
from pine.facts.store import EvidenceStore
from pine.models.deal import Deal
from pine.models.document import (
    Cell,
    DocType,
    Document,
    Page,
    Table,
)
from pine.models.entity import Entity, Relation
from pine.models.evidence import Evidence
from pine.models.fact import ExtractionMethod, Fact

from .conftest import mk_deal, mk_document


def _deal(session: Session, name: str = "Acme Corp") -> Deal:
    return mk_deal(session, name)


def _doc(
    session: Session, deal: Deal, filename: str, doc_type: DocType
) -> Document:
    return mk_document(session, deal, filename, doc_type)


def _mk_table(
    session: Session,
    doc: Document,
    rows: list[list[object]],
    *,
    header_row: int | None = 0,
) -> Table:
    page = Page(document_id=doc.id, page_no=1, text="")
    session.add(page)
    session.flush()
    table = Table(
        page_id=page.id,
        order=0,
        n_rows=len(rows),
        n_cols=max(len(r) for r in rows),
        header_row=header_row,
    )
    session.add(table)
    session.flush()
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            if val is None or val == "":
                continue
            value_num: Decimal | None = None
            value_date: date | None = None
            if isinstance(val, int | float):
                value_num = Decimal(str(val))
            elif isinstance(val, str):
                try:
                    value_date = date.fromisoformat(val)
                except ValueError:
                    value_date = None
            session.add(
                Cell(
                    table_id=table.id,
                    row=r,
                    col=c,
                    text=str(val),
                    value_num=value_num,
                    value_date=value_date,
                )
            )
    session.flush()
    return table


def _facts(session: Session, deal: Deal, metric: str) -> list[Fact]:
    return list(
        session.scalars(
            select(Fact)
            .where(Fact.deal_id == deal.id)
            .where(Fact.metric == metric)
            .order_by(Fact.period_start)
        ).all()
    )


# ----------------------------------------------------------------------
# P&L


def test_pnl_extracts_metrics_with_periods(session: Session) -> None:
    deal = _deal(session)
    doc = _doc(session, deal, "pnl.csv", DocType.financial_statement)
    table = _mk_table(
        session,
        doc,
        [
            ["Metric", "FY2024", "FY2025"],
            ["SaaS revenue", 4_100_000, 9_700_000],
            ["COGS", 1_230_000, 2_522_000],
            ["Gross profit", 2_870_000, 7_178_000],
            ["Sales & marketing", 1_900_000, 3_400_000],
            ["EBITDA", -1_330_000, -122_000],
        ],
    )
    store = EvidenceStore(session, deal.id)
    grid = TableGrid.load(session, table)
    ext = PnlExtractor()
    assert ext.match(grid, doc, deal) >= 0.5
    n = ext.extract(grid, doc, store, deal)
    assert n > 0

    rev = _facts(session, deal, "revenue")
    assert len(rev) == 2
    assert rev[0].value == Decimal("4100000")
    assert rev[0].extraction_method == ExtractionMethod.table.value
    assert (rev[0].period_start, rev[0].period_end) == (
        date(2024, 1, 1),
        date(2024, 12, 31),
    )
    assert rev[1].value == Decimal("9700000")
    # "SaaS revenue" also emits recurring_revenue
    recurring = _facts(session, deal, "recurring_revenue")
    assert {f.value for f in recurring} == {
        Decimal("4100000"),
        Decimal("9700000"),
    }
    assert _facts(session, deal, "cogs")[1].value == Decimal("2522000")
    assert _facts(session, deal, "ebitda")[0].value == Decimal("-1330000")

    # every fact cites ≥1 evidence row pointing at the value cell
    for fact in rev:
        ev = session.scalars(
            select(Evidence)
            .where(Evidence.target_kind == "fact")
            .where(Evidence.target_id == fact.id)
        ).all()
        assert len(ev) >= 1
        assert all(e.cell_id is not None for e in ev)
        assert all(e.document_id == doc.id for e in ev)

    # re-run is a no-op (dedupe)
    assert ext.extract(grid, doc, store, deal) == 0


def test_pnl_point_column(session: Session) -> None:
    deal = _deal(session)
    doc = _doc(session, deal, "balance.csv", DocType.financial_statement)
    table = _mk_table(
        session,
        doc,
        [["Item", "2025-12-31"], ["Cash", 6_200_000], ["Deferred revenue", 1_100_000]],
    )
    store = EvidenceStore(session, deal.id)
    grid = TableGrid.load(session, table)
    PnlExtractor().extract(grid, doc, store, deal)
    cash = _facts(session, deal, "cash_balance")
    assert len(cash) == 1
    assert cash[0].as_of == date(2025, 12, 31)
    assert cash[0].value == Decimal("6200000")


# ----------------------------------------------------------------------
# bank statement


def test_bank_statement_extracts_flows(session: Session) -> None:
    deal = _deal(session)
    doc = _doc(session, deal, "bank.csv", DocType.bank_statement)
    table = _mk_table(
        session,
        doc,
        [
            ["ACCT 4839201156"],
            ["date", "description", "debit", "credit", "balance"],
            ["2025-01-15", "Customer receipts", None, 800_000, 800_000],
            ["2025-01-28", "Operating disbursements", 100_000, None, 700_000],
            ["2025-02-15", "Customer receipts", None, 900_000, 1_600_000],
            ["2025-02-28", "Operating disbursements", 200_000, None, 1_400_000],
        ],
    )
    store = EvidenceStore(session, deal.id)
    grid = TableGrid.load(session, table)
    ext = BankStatementExtractor()
    assert ext.match(grid, doc, deal) >= 0.5
    n = ext.extract(grid, doc, store, deal)
    assert n >= 3

    flows = _facts(session, deal, "bank_inflows")
    monthly = [f for f in flows if f.period_type == "month"]
    yearly = [f for f in flows if f.period_type == "fiscal_year"]
    assert {f.value for f in monthly} == {Decimal("800000"), Decimal("900000")}
    assert len(yearly) == 1 and yearly[0].value == Decimal("1700000")

    cash = _facts(session, deal, "cash_balance")
    assert len(cash) == 1
    assert cash[0].value == Decimal("1400000")
    assert cash[0].as_of == date(2025, 2, 28)

    acct = session.scalar(
        select(Entity).where(
            Entity.deal_id == deal.id, Entity.type == "bank_account"
        )
    )
    assert acct is not None
    assert "4839201156" in acct.canonical_name
    rel = session.scalar(
        select(Relation).where(
            Relation.deal_id == deal.id, Relation.type == "banks_with"
        )
    )
    assert rel is not None
    assert rel.target_entity_id == acct.id


# ----------------------------------------------------------------------
# customer list


def test_customer_list_extracts_entities_and_aggregates(session: Session) -> None:
    deal = _deal(session, "Northwind")
    doc = _doc(session, deal, "customers.csv", DocType.customer_list)
    table = _mk_table(
        session,
        doc,
        [
            [
                "customer_name",
                "contract_start",
                "contract_end",
                "annual_recurring_revenue",
                "segment",
                "region",
            ],
            ["Acme Corporation", "2024-01-01", "2025-01-01", 2_244_000, "enterprise", "NA"],
            ["Helios Logistics", "2024-03-01", "2025-03-01", 480_000, "mid", "EMEA"],
            ["Delta Freight", "2024-06-01", "2025-06-01", 260_000, "smb", "NA"],
        ],
    )
    store = EvidenceStore(session, deal.id)
    grid = TableGrid.load(session, table)
    ext = CustomerListExtractor()
    assert ext.match(grid, doc, deal) >= 0.5
    ext.extract(grid, doc, store, deal)

    customers = session.scalars(
        select(Entity).where(Entity.deal_id == deal.id, Entity.type == "customer")
    ).all()
    assert len(customers) == 3

    company = session.scalar(
        select(Entity).where(Entity.deal_id == deal.id, Entity.type == "company")
    )
    assert company is not None
    rels = session.scalars(
        select(Relation).where(
            Relation.deal_id == deal.id, Relation.type == "has_customer"
        )
    ).all()
    assert len(rels) == 3
    assert all(r.source_entity_id == company.id for r in rels)
    # every edge has evidence
    for rel in rels:
        assert session.scalar(
            select(func.count())
            .select_from(Evidence)
            .where(Evidence.target_kind == "relation")
            .where(Evidence.target_id == rel.id)
        ) == 1

    acme = next(c for c in customers if c.canonical_name == "Acme Corporation")
    cv = _facts(session, deal, "contract_value")
    assert len(cv) == 3
    acme_cv = next(f for f in cv if f.subject_entity_id == acme.id)
    assert acme_cv.value == Decimal("2244000")
    assert (acme_cv.period_start, acme_cv.period_end) == (
        date(2024, 1, 1),
        date(2025, 1, 1),
    )

    rr = _facts(session, deal, "recurring_revenue")
    assert len(rr) == 1 and rr[0].value == Decimal("2984000")
    cc = _facts(session, deal, "customers_count")
    assert len(cc) == 1 and cc[0].value == Decimal("3")
    top = _facts(session, deal, "top_customer_concentration")
    assert len(top) == 1
    assert top[0].value is not None
    assert abs(float(top[0].value) - 75.2) < 0.1  # 2244000/2984000


# ----------------------------------------------------------------------
# cap table


def test_cap_table_extracts_ownership(session: Session) -> None:
    deal = _deal(session, "Northwind")
    doc = _doc(session, deal, "cap.xlsx", DocType.cap_table)
    table = _mk_table(
        session,
        doc,
        [
            ["shareholder", "security_class", "shares", "fully_diluted_pct"],
            ["Founders", "common", 4_500_000, 45.0],
            ["Meridian Ventures", "preferred_series_a", 2_500_000, 25.0],
            ["ESOP", "options", 1_300_000, 13.0],
        ],
    )
    store = EvidenceStore(session, deal.id)
    grid = TableGrid.load(session, table)
    ext = CapTableExtractor()
    assert ext.match(grid, doc, deal) >= 0.5
    ext.extract(grid, doc, store, deal)

    holders = session.scalars(
        select(Entity).where(
            Entity.deal_id == deal.id, Entity.type == "shareholder"
        )
    ).all()
    assert len(holders) == 3
    classes = session.scalars(
        select(Entity).where(
            Entity.deal_id == deal.id, Entity.type == "security_class"
        )
    ).all()
    assert len(classes) == 3

    rels = session.scalars(
        select(Relation).where(
            Relation.deal_id == deal.id, Relation.type == "owns_shares"
        )
    ).all()
    assert len(rels) == 3

    pct_facts = _facts(session, deal, "fully_diluted_pct")
    assert {float(f.value) for f in pct_facts if f.value is not None} == {
        45.0,
        25.0,
        13.0,
    }
    so = _facts(session, deal, "shares_outstanding")
    assert len(so) == 1 and so[0].value == Decimal("8300000")


# ----------------------------------------------------------------------
# discrimination: a bank statement must not match the P&L/customer extractors


def test_extractors_do_not_cross_match(session: Session) -> None:
    deal = _deal(session)
    doc = _doc(session, deal, "bank.csv", DocType.bank_statement)
    table = _mk_table(
        session,
        doc,
        [
            ["date", "description", "debit", "credit", "balance"],
            ["2025-01-15", "Customer receipts", None, 800_000, 800_000],
        ],
    )
    grid = TableGrid.load(session, table)
    assert CustomerListExtractor().match(grid, doc, deal) < 0.5
    assert CapTableExtractor().match(grid, doc, deal) < 0.5
    assert PnlExtractor().match(grid, doc, deal) < 0.5


# ----------------------------------------------------------------------
# F-05.AC1 on the real demo room (demo_deal fixture lives in conftest.py)


def test_demo_room_f05_ac1(session: Session, demo_deal: Deal) -> None:
    deal = demo_deal  # fixture drains the whole chain — facts already exist
    written = run_extractors(session, deal.id)
    session.commit()
    assert written == 0  # idempotent re-run

    # F-05.AC1 — revenue FY2024 + FY2025 from the financials xlsx
    fin = session.scalar(
        select(Document).where(
            Document.deal_id == deal.id,
            Document.filename == "02_Financials_FY2024_FY2025.xlsx",
        )
    )
    assert fin is not None
    rev = (
        session.scalars(
            select(Fact)
            .join(
                Evidence,
                (Evidence.target_id == Fact.id)
                & (Evidence.target_kind == "fact"),
            )
            .where(Fact.deal_id == deal.id)
            .where(Fact.metric == "revenue")
            .where(Fact.extraction_method == ExtractionMethod.table.value)
            .where(Evidence.document_id == fin.id)
        )
        .unique()
        .all()
    )
    by_year = {f.period_start.year: f.value for f in rev if f.period_start}
    assert by_year[2024] == Decimal("4100000")
    assert by_year[2025] == Decimal("9700000")

    # headline aggregates from the other demo tables
    rr = _facts(session, deal, "recurring_revenue")
    assert any(f.value == Decimal("10200000") for f in rr)
    inflows = _facts(session, deal, "bank_inflows")
    assert any(
        f.period_type == "fiscal_year"
        and f.value is not None
        and abs(float(f.value) - 9_900_000) / 9_900_000 <= 0.01
        for f in inflows
    )
    cash = _facts(session, deal, "cash_balance")
    assert any(f.value == Decimal("6200000") for f in cash)
    top = _facts(session, deal, "top_customer_concentration")
    assert any(
        f.value is not None and abs(float(f.value) - 22.0) / 22.0 <= 0.01
        for f in top
    )
    headcount = _facts(session, deal, "headcount")
    assert any(f.value == Decimal("84") for f in headcount)

    customers = session.scalar(
        select(func.count())
        .select_from(Entity)
        .where(Entity.deal_id == deal.id)
        .where(Entity.type == "customer")
    )
    assert customers == 40
    rels = session.scalar(
        select(func.count())
        .select_from(Relation)
        .where(Relation.deal_id == deal.id)
        .where(Relation.type == "has_customer")
    )
    assert rels == 40

    # no fact exists without evidence
    orphans = session.scalar(
        select(func.count())
        .select_from(Fact)
        .where(Fact.deal_id == deal.id)
        .where(Fact.extraction_method != "derived")
        .where(
            ~Fact.id.in_(
                select(Evidence.target_id).where(Evidence.target_kind == "fact")
            )
        )
    )
    assert orphans == 0
