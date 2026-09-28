"""Bank-statement table extractor (F-05, feeds contradiction rule R7).

Matches a header row covering {date, description, debit|withdrawal,
credit|deposit, balance}. Emits:

- `cash_balance` point fact from the last row's balance (evidenced by the
  balance cell + its date cell)
- `bank_inflows` facts: monthly credit sums plus per-fiscal-year aggregates
  (evidenced by every contributing credit cell)
- the account's `bank_account` entity + `banks_with` relation when an
  "ACCT …" style account cell is present
"""

import re
from collections import defaultdict
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
from pine.facts.periods import (
    PeriodSpec,
    fiscal_year_bounds,
    month_bounds,
    parse_period,
)
from pine.facts.store import EvidenceSpec, EvidenceStore, whitespace_normalize
from pine.models.deal import Deal
from pine.models.document import DocType, Document
from pine.schemas.entities import EntityType, RelationType
from pine.schemas.metrics import MetricId
from pine.schemas.units import PeriodType, Unit

_ROLES: dict[str, tuple[str, ...]] = {
    "date": ("date", "posted", "txn date"),
    "description": ("description", "memo", "details", "narrative", "payee"),
    "debit": ("debit", "withdrawal", "withdrawals", "paid out"),
    "credit": ("credit", "deposit", "deposits", "paid in"),
    "balance": ("balance", "running balance"),
}
_REQUIRED = {"date", "balance"}
_ACCOUNT_RE = re.compile(r"\b(?:acct|account|a/c)\b|\d{6,}", re.IGNORECASE)


def _date_of_cell(grid: TableGrid, row: int, col: int) -> date | None:
    cell = grid.cell(row, col)
    if cell is None:
        return None
    if cell.value_date is not None:
        return cell.value_date
    spec = parse_period(cell.text)
    if spec is not None and spec.as_of is not None:
        return spec.as_of
    if (
        spec is not None
        and spec.period_type == PeriodType.point
        and spec.period_start is not None
    ):
        return spec.period_start
    return None


class BankStatementExtractor:
    name = "bank_statement"

    def _header(self, grid: TableGrid) -> tuple[int, dict[str, int]] | None:
        return find_header_row(grid, _ROLES, _REQUIRED)

    def match(self, grid: TableGrid, document: Document, deal: Deal) -> float:
        found = self._header(grid)
        if found is None:
            return 0.0
        _, cols = found
        if "credit" not in cols and "debit" not in cols:
            return 0.0
        score = 0.8
        if document.doc_type == DocType.bank_statement:
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

        # optional "ACCT 1234" account cell above the header → bank_account
        account_entity_id = self._account_entity(
            grid, document, store, header_row, company.id
        )

        written = 0
        monthly: dict[tuple[int, int], list[tuple[Decimal, EvidenceSpec]]] = (
            defaultdict(list)
        )
        last_balance: tuple[Decimal, list[EvidenceSpec], date] | None = None

        for row in grid.row_ids:
            if row <= header_row:
                continue
            day = (
                _date_of_cell(grid, row, cols["date"]) if "date" in cols else None
            )
            credit_cell = grid.cell(row, cols["credit"]) if "credit" in cols else None
            balance_cell = (
                grid.cell(row, cols["balance"]) if "balance" in cols else None
            )
            credit = parse_number(credit_cell) if credit_cell is not None else None
            balance = (
                parse_number(balance_cell) if balance_cell is not None else None
            )
            if (
                credit is not None
                and credit > 0
                and day is not None
                and credit_cell is not None
                and credit_cell.text.strip()
            ):
                monthly[(day.year, day.month)].append(
                    (credit, evidence_for_cell(grid, document, credit_cell))
                )
            if (
                balance is not None
                and balance_cell is not None
                and balance_cell.text.strip()
                and day is not None
            ):
                evidence = [evidence_for_cell(grid, document, balance_cell)]
                date_cell = grid.cell(row, cols["date"])
                if date_cell is not None and date_cell.text.strip():
                    evidence.append(evidence_for_cell(grid, document, date_cell))
                last_balance = (balance, evidence, day)

        subject = account_entity_id or company.id
        if last_balance is not None:
            balance, evidence, day = last_balance
            spec = PeriodSpec(
                period_type=PeriodType.point,
                period_start=day,
                period_end=day,
                as_of=day,
            )
            if not fact_exists(
                store,
                subject_entity_id=subject,
                metric=MetricId.cash_balance.value,
                value=balance,
                spec=spec,
                document_id=document.id,
            ):
                store.add_fact(
                    subject_entity_id=subject,
                    metric=MetricId.cash_balance,
                    value=balance,
                    unit=Unit.currency,
                    currency=deal.currency,
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

        written += self._inflow_facts(
            store, deal, document, company.id, monthly
        )
        return written

    def _inflow_facts(
        self,
        store: EvidenceStore,
        deal: Deal,
        document: Document,
        subject_id: str,
        monthly: dict[tuple[int, int], list[tuple[Decimal, EvidenceSpec]]],
    ) -> int:
        """Monthly `bank_inflows` facts + fiscal-year aggregates."""
        written = 0
        yearly: dict[int, tuple[Decimal, list[EvidenceSpec]]] = {}
        fye = deal.fiscal_year_end_month
        for (year, month), items in sorted(monthly.items()):
            total = sum(v for v, _ in items)
            evidence = [e for _, e in items]
            start, end = month_bounds(year, month)
            spec = PeriodSpec(
                period_type=PeriodType.month, period_start=start, period_end=end
            )
            if not fact_exists(
                store,
                subject_entity_id=subject_id,
                metric=MetricId.bank_inflows.value,
                value=total,
                spec=spec,
                document_id=document.id,
            ):
                store.add_fact(
                    subject_entity_id=subject_id,
                    metric=MetricId.bank_inflows,
                    value=total,
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
            # fiscal year label = calendar year the FY ends in
            fy = year + 1 if month > fye else year
            prev_total, prev_ev = yearly.get(fy, (Decimal(0), []))
            yearly[fy] = (prev_total + total, prev_ev + evidence)

        for fy, (total, evidence) in sorted(yearly.items()):
            start, end = fiscal_year_bounds(fy, fye)
            spec = PeriodSpec(
                period_type=PeriodType.fiscal_year,
                period_start=start,
                period_end=end,
            )
            if fact_exists(
                store,
                subject_entity_id=subject_id,
                metric=MetricId.bank_inflows.value,
                value=total,
                spec=spec,
                document_id=document.id,
            ):
                continue
            store.add_fact(
                subject_entity_id=subject_id,
                metric=MetricId.bank_inflows,
                value=total,
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
        return written

    def _account_entity(
        self,
        grid: TableGrid,
        document: Document,
        store: EvidenceStore,
        header_row: int,
        company_id: str,
    ) -> str | None:
        """Create a bank_account entity when a pre-header row names the account."""
        for row in grid.row_ids:
            if row >= header_row:
                break
            for cell in grid.row_cells(row):
                text = whitespace_normalize(cell.text)
                if text and _ACCOUNT_RE.search(text):
                    entity = store.add_entity(
                        type=EntityType.bank_account,
                        canonical_name=text[:120],
                        attrs={},
                        evidence=[evidence_for_cell(grid, document, cell)],
                        source_document_id=document.id,
                    )
                    store.add_relation(
                        type=RelationType.banks_with,
                        source_entity_id=company_id,
                        target_entity_id=entity.id,
                        evidence=[evidence_for_cell(grid, document, cell)],
                    )
                    return entity.id
        return None
