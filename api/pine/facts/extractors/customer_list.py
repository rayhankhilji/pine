"""Customer-list extractor (F-04/F-05).

Headers: {customer|account|name, arr|annual_recurring_revenue|acv,
contract_start|start, contract_end|end, segment, region}.

Per row: a Customer entity, a `has_customer` edge from the deal Company and a
`contract_value` fact (subject = the customer). Aggregates on the Company:
`recurring_revenue` (sum), `customers_count`, `top_customer_concentration`.
"""

from datetime import date
from decimal import Decimal

from pine.facts.extractors.base import (
    TableGrid,
    ensure_company,
    evidence_for_cell,
    fact_exists,
    find_header_row,
    parse_number,
)
from pine.facts.periods import PeriodSpec, fiscal_year_bounds, parse_period
from pine.facts.store import EvidenceSpec, EvidenceStore
from pine.models.deal import Deal
from pine.models.document import DocType, Document
from pine.models.entity import Entity
from pine.schemas.entities import EntityType, RelationType
from pine.schemas.metrics import MetricId
from pine.schemas.units import PeriodType, Unit

_ROLES: dict[str, tuple[str, ...]] = {
    "name": ("customer", "account", "name", "customer_name", "company"),
    "arr": ("annual_recurring_revenue", "arr", "acv", "recurring"),
    "start": ("contract_start", "start_date", "start", "since"),
    "end": ("contract_end", "end_date", "end", "renewal"),
    "segment": ("segment", "tier"),
    "region": ("region", "geo", "country"),
}
_REQUIRED = {"name", "arr"}


def _cell_date(grid: TableGrid, row: int, col: int | None) -> date | None:
    if col is None:
        return None
    cell = grid.cell(row, col)
    if cell is None:
        return None
    if cell.value_date is not None:
        return cell.value_date
    spec = parse_period(cell.text)
    return spec.as_of if spec and spec.as_of else None


class CustomerListExtractor:
    name = "customer_list"

    def _header(self, grid: TableGrid) -> tuple[int, dict[str, int]] | None:
        return find_header_row(grid, _ROLES, _REQUIRED)

    def match(self, grid: TableGrid, document: Document, deal: Deal) -> float:
        if self._header(grid) is None:
            return 0.0
        score = 0.8
        if document.doc_type == DocType.customer_list:
            score += 0.2
        return min(score, 1.0)

    def extract(
        self,
        grid: TableGrid,
        document: Document,
        store: EvidenceStore,
        deal: Deal,
    ) -> int:
        found = self._header(grid)
        assert found is not None
        header_row, cols = found
        company = ensure_company(store, deal)

        written = 0
        arr_cells: list[tuple[Decimal, EvidenceSpec]] = []
        ends: list[date] = []

        for row in grid.row_ids:
            if row <= header_row:
                continue
            name_cell = grid.cell(row, cols["name"])
            arr_cell = grid.cell(row, cols["arr"])
            if name_cell is None or not name_cell.text.strip():
                continue
            arr = parse_number(arr_cell) if arr_cell is not None else None

            customer = store.add_entity(
                type=EntityType.customer,
                canonical_name=name_cell.text.strip(),
                attrs=self._row_attrs(grid, row, cols),
                evidence=[evidence_for_cell(grid, document, name_cell)],
                source_document_id=document.id,
            )
            store.add_relation(
                type=RelationType.has_customer,
                source_entity_id=company.id,
                target_entity_id=customer.id,
                evidence=[evidence_for_cell(grid, document, name_cell)],
            )

            start = _cell_date(grid, row, cols.get("start"))
            end = _cell_date(grid, row, cols.get("end"))
            if end is not None:
                ends.append(end)
            if arr is not None and arr_cell is not None:
                arr_cells.append((arr, evidence_for_cell(grid, document, arr_cell)))
                spec = PeriodSpec(
                    period_type=PeriodType.custom,
                    period_start=start,
                    period_end=end,
                )
                if not fact_exists(
                    store,
                    subject_entity_id=customer.id,
                    metric=MetricId.contract_value.value,
                    value=arr,
                    spec=spec,
                    document_id=document.id,
                ):
                    evidence = [evidence_for_cell(grid, document, arr_cell)]
                    if name_cell is not arr_cell:
                        evidence.append(
                            evidence_for_cell(grid, document, name_cell)
                        )
                    store.add_fact(
                        subject_entity_id=customer.id,
                        metric=MetricId.contract_value,
                        value=arr,
                        unit=Unit.currency,
                        currency=deal.currency,
                        period_type=spec.period_type,
                        period_start=spec.period_start,
                        period_end=spec.period_end,
                        source_kind=document.doc_type,
                        extraction_method="table",
                        confidence=0.95,
                        evidence=evidence,
                    )
                    written += 1

        written += self._aggregates(
            store, deal, document, company, arr_cells, ends
        )
        return written

    def _row_attrs(
        self, grid: TableGrid, row: int, cols: dict[str, int]
    ) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for key in ("segment", "region"):
            if key in cols:
                text = grid.text(row, cols[key])
                if text:
                    attrs[key] = text
        return attrs

    def _aggregates(
        self,
        store: EvidenceStore,
        deal: Deal,
        document: Document,
        company: Entity,
        arr_cells: list[tuple[Decimal, EvidenceSpec]],
        ends: list[date],
    ) -> int:
        if not arr_cells:
            return 0
        written = 0
        total = sum(v for v, _ in arr_cells)
        # the book is reported for the fiscal year of the latest contract end
        anchor = max(ends) if ends else None
        if anchor is not None:
            fye = deal.fiscal_year_end_month
            fy = anchor.year + 1 if anchor.month > fye else anchor.year
            start, end = fiscal_year_bounds(fy, fye)
            spec = PeriodSpec(
                period_type=PeriodType.fiscal_year,
                period_start=start,
                period_end=end,
            )
        else:
            spec = PeriodSpec(period_type=PeriodType.custom)
        evidence = [e for _, e in arr_cells]

        aggregates = [
            (MetricId.recurring_revenue, total, Unit.currency),
            (MetricId.customers_count, Decimal(len(arr_cells)), Unit.count),
            (
                MetricId.top_customer_concentration,
                (max(v for v, _ in arr_cells) / total * 100),
                Unit.percent,
            ),
        ]
        for metric, value, unit in aggregates:
            if fact_exists(
                store,
                subject_entity_id=company.id,
                metric=metric.value,
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
                currency=deal.currency if unit == Unit.currency else None,
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
