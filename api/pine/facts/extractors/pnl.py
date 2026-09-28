"""P&L / financial-statement table extractor (F-05.AC1).

Row labels are matched case-insensitively against a synonym map; each period
column ("FY2024", "Q1 2025", "Dec-25", …) yields one fact per metric row.
Every fact cites the label cell and the value cell.
"""

import re

from pine.facts.extractors.base import (
    TableGrid,
    cell_period,
    ensure_company,
    evidence_for_cell,
    fact_exists,
    parse_number,
)
from pine.facts.periods import PeriodSpec
from pine.facts.store import EvidenceStore
from pine.models.deal import Deal
from pine.models.document import DocType, Document
from pine.schemas.metrics import MetricId
from pine.schemas.units import Unit

# (synonyms, metric, unit). First match wins — order long/specific first.
_ROW_MAP: list[tuple[tuple[str, ...], str, str]] = [
    (("gross profit",), MetricId.gross_profit.value, Unit.currency.value),
    (("cogs", "cost of revenue", "cost of goods", "cost of sales"),
     MetricId.cogs.value, Unit.currency.value),
    (("sales and marketing", "sales & marketing", "s&m"),
     MetricId.sm_spend.value, Unit.currency.value),
    (("research and development", "r&d", "r & d"),
     MetricId.rnd_spend.value, Unit.currency.value),
    (("general and administrative", "g&a", "g & a"),
     MetricId.ga_spend.value, Unit.currency.value),
    (("ebitda",), MetricId.ebitda.value, Unit.currency.value),
    (("net income", "net loss"), MetricId.net_income.value, Unit.currency.value),
    (("net burn",), MetricId.net_burn.value, Unit.currency.value),
    (("cash and equivalents", "cash & equivalents", "cash on hand", "cash"),
     MetricId.cash_balance.value, Unit.currency.value),
    (("accounts receivable", "a/r", "ar"),
     MetricId.accounts_receivable.value, Unit.currency.value),
    (("deferred revenue",), MetricId.deferred_revenue.value, Unit.currency.value),
    (("annual recurring revenue", "arr"),
     MetricId.arr.value, Unit.currency.value),
    (("monthly recurring revenue", "mrr"),
     MetricId.mrr.value, Unit.currency.value),
    (("revenue", "total revenue", "net sales", "sales"),
     MetricId.revenue.value, Unit.currency.value),
    (("headcount", "head count", "employees", "fte"),
     MetricId.headcount.value, Unit.count.value),
    (("customers", "customer count", "logos"),
     MetricId.customers_count.value, Unit.count.value),
    (("nrr", "net revenue retention"),
     MetricId.net_revenue_retention.value, Unit.percent.value),
    (("grr", "gross revenue retention"),
     MetricId.gross_revenue_retention.value, Unit.percent.value),
    (("gross margin",), MetricId.gross_margin.value, Unit.percent.value),
    (("runway",), MetricId.runway_months.value, Unit.months.value),
    (("tam",), MetricId.tam.value, Unit.currency.value),
    (("sam",), MetricId.sam.value, Unit.currency.value),
    (("som",), MetricId.som.value, Unit.currency.value),
    (("contract value", "tcv"), MetricId.contract_value.value, Unit.currency.value),
]

# revenue-like rows with a recurring flavour also emit recurring_revenue
_RECURRING_HINT = re.compile(r"recurring|saas|subscription", re.IGNORECASE)


def _label_metrics(label: str) -> list[tuple[str, str]]:
    """(metric, unit) pairs for a row label — may emit recurring_revenue too."""
    text = label.lower()
    out: list[tuple[str, str]] = []
    for synonyms, metric, unit in _ROW_MAP:
        if any(
            re.search(rf"(?<!\w){re.escape(s)}(?!\w)", text) for s in synonyms
        ):
            out.append((metric, unit))
            if (
                metric == MetricId.revenue.value
                and _RECURRING_HINT.search(text)
            ):
                out.append((MetricId.recurring_revenue.value, unit))
            break
    return out


def _period_columns(grid: TableGrid, fye: int) -> dict[int, PeriodSpec]:
    """Columns of the most period-dense early row → parsed PeriodSpec."""
    best: dict[int, PeriodSpec] = {}
    for row in grid.row_ids[:5]:
        cols: dict[int, PeriodSpec] = {}
        for col in grid.col_ids:
            cell = grid.cell(row, col)
            if cell is None:
                continue
            spec = cell_period(cell, fye)
            if spec is not None:
                cols[col] = spec
        if len(cols) > len(best):
            best = cols
    return best


class PnlExtractor:
    name = "pnl"

    def match(self, grid: TableGrid, document: Document, deal: Deal) -> float:
        period_cols = _period_columns(grid, deal.fiscal_year_end_month)
        if not period_cols:
            return 0.0
        rows = sum(
            1
            for r in grid.row_ids
            if _label_metrics(grid.row_label(r)) and grid.row_numbers(r)
        )
        if rows == 0:
            return 0.0
        score = 0.4 + 0.15 * rows
        if document.doc_type == DocType.financial_statement:
            score += 0.2
        return min(score, 1.0)

    def extract(
        self,
        grid: TableGrid,
        document: Document,
        store: EvidenceStore,
        deal: Deal,
    ) -> int:
        company = ensure_company(store, deal)
        period_cols = _period_columns(grid, deal.fiscal_year_end_month)
        written = 0
        for row in grid.row_ids:
            label = grid.row_label(row)
            metrics = _label_metrics(label)
            if not metrics:
                continue
            label_cell = next(
                (c for c in grid.row_cells(row) if c.text.strip()), None
            )
            for col, spec in period_cols.items():
                cell = grid.cell(row, col)
                if cell is None or not cell.text.strip():
                    continue
                value = parse_number(cell)
                if value is None:
                    continue
                evidence = [evidence_for_cell(grid, document, cell)]
                if label_cell is not None and label_cell is not cell:
                    evidence.append(evidence_for_cell(grid, document, label_cell))
                for metric, unit in metrics:
                    currency = deal.currency if unit == Unit.currency.value else None
                    if fact_exists(
                        store,
                        subject_entity_id=company.id,
                        metric=metric,
                        value=value,
                        spec=spec,
                        document_id=document.id,
                    ):
                        continue
                    store.add_fact(
                        subject_entity_id=company.id,
                        metric=metric,
                        value=value,
                        unit=unit,
                        currency=currency,
                        period_type=spec.period_type,
                        period_start=spec.period_start,
                        period_end=spec.period_end,
                        as_of=spec.as_of,
                        source_kind=document.doc_type,
                        extraction_method="table",
                        confidence=0.95,
                        evidence=evidence,
                    )
                    written += 1
        return written
