"""Cap-table extractor (F-04/F-05).

Headers: {shareholder|investor|name, shares, %|pct|percent|fully_diluted,
security_class|class|type}.

Per row: Shareholder entity, SecurityClass entity, `owns_shares` relation
(shareholder → company, security class in attrs) and a `fully_diluted_pct`
fact on the shareholder. Aggregate: `shares_outstanding` on the Company.
"""

from decimal import Decimal

from pine.facts.extractors.base import (
    TableGrid,
    ensure_company,
    evidence_for_cell,
    fact_exists,
    find_header_row,
    parse_number,
)
from pine.facts.periods import PeriodSpec
from pine.facts.store import EvidenceSpec, EvidenceStore
from pine.models.deal import Deal
from pine.models.document import DocType, Document
from pine.schemas.entities import EntityType, RelationType
from pine.schemas.metrics import MetricId
from pine.schemas.units import PeriodType, Unit

_ROLES: dict[str, tuple[str, ...]] = {
    "name": ("shareholder", "investor", "holder", "name"),
    "shares": ("shares", "share_count", "shares_outstanding", "number"),
    "pct": ("fully_diluted_pct", "pct", "percent", "%", "ownership"),
    "class": ("security_class", "class", "type", "security", "series"),
}
_REQUIRED = {"name"}


class CapTableExtractor:
    name = "cap_table"

    def _header(self, grid: TableGrid) -> tuple[int, dict[str, int]] | None:
        found = find_header_row(grid, _ROLES, _REQUIRED)
        if found is None:
            return None
        _, cols = found
        if "pct" not in cols and "shares" not in cols:
            return None
        return found

    def match(self, grid: TableGrid, document: Document, deal: Deal) -> float:
        if self._header(grid) is None:
            return 0.0
        score = 0.8
        if document.doc_type == DocType.cap_table:
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
        total_shares = Decimal(0)
        share_evidence: list[EvidenceSpec] = []

        for row in grid.row_ids:
            if row <= header_row:
                continue
            name_cell = grid.cell(row, cols["name"])
            if name_cell is None or not name_cell.text.strip():
                continue
            shareholder = store.add_entity(
                type=EntityType.shareholder,
                canonical_name=name_cell.text.strip(),
                evidence=[evidence_for_cell(grid, document, name_cell)],
                source_document_id=document.id,
            )

            shares_cell = grid.cell(row, cols["shares"]) if "shares" in cols else None
            pct_cell = grid.cell(row, cols["pct"]) if "pct" in cols else None
            class_cell = grid.cell(row, cols["class"]) if "class" in cols else None
            shares = parse_number(shares_cell) if shares_cell is not None else None
            pct = parse_number(pct_cell) if pct_cell is not None else None

            relation_evidence = [
                e
                for e in (
                    evidence_for_cell(grid, document, shares_cell)
                    if shares_cell is not None and shares_cell.text.strip()
                    else None,
                    evidence_for_cell(grid, document, pct_cell)
                    if pct_cell is not None and pct_cell.text.strip()
                    else None,
                )
                if e is not None
            ] or [evidence_for_cell(grid, document, name_cell)]
            store.add_relation(
                type=RelationType.owns_shares,
                source_entity_id=shareholder.id,
                target_entity_id=company.id,
                attrs={
                    "shares": str(shares) if shares is not None else None,
                    "pct": str(pct) if pct is not None else None,
                    "security_class": class_cell.text.strip()
                    if class_cell is not None
                    else None,
                },
                evidence=relation_evidence,
            )

            if class_cell is not None and class_cell.text.strip():
                store.add_entity(
                    type=EntityType.security_class,
                    canonical_name=class_cell.text.strip(),
                    evidence=[evidence_for_cell(grid, document, class_cell)],
                    source_document_id=document.id,
                )

            if shares is not None:
                total_shares += shares
                if shares_cell is not None and shares_cell.text.strip():
                    share_evidence.append(
                        evidence_for_cell(grid, document, shares_cell)
                    )

            if pct is not None and pct_cell is not None and pct_cell.text.strip():
                spec = PeriodSpec(period_type=PeriodType.point)
                if not fact_exists(
                    store,
                    subject_entity_id=shareholder.id,
                    metric=MetricId.fully_diluted_pct.value,
                    value=pct,
                    spec=spec,
                    document_id=document.id,
                ):
                    store.add_fact(
                        subject_entity_id=shareholder.id,
                        metric=MetricId.fully_diluted_pct,
                        value=pct,
                        unit=Unit.percent,
                        period_type=PeriodType.point,
                        source_kind=document.doc_type,
                        extraction_method="table",
                        confidence=0.95,
                        evidence=[evidence_for_cell(grid, document, pct_cell)],
                    )
                    written += 1

        if total_shares and share_evidence:
            spec = PeriodSpec(period_type=PeriodType.point)
            if not fact_exists(
                store,
                subject_entity_id=company.id,
                metric=MetricId.shares_outstanding.value,
                value=total_shares,
                spec=spec,
                document_id=document.id,
            ):
                store.add_fact(
                    subject_entity_id=company.id,
                    metric=MetricId.shares_outstanding,
                    value=total_shares,
                    unit=Unit.count,
                    period_type=PeriodType.point,
                    source_kind=document.doc_type,
                    extraction_method="table",
                    confidence=0.95,
                    evidence=share_evidence,
                )
                written += 1
        return written
