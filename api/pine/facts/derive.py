"""Derived facts (F-05.AC4, ARCHITECTURE §10).

Derived facts are computed from existing `Fact` rows and written through
`EvidenceStore.add_fact` with `extraction_method = derived`. They carry no
direct `Evidence` — provenance is the `FactLink` chain to their parents
(`numerator`/`denominator`/`addend`/`subtrahend` roles), which bottoms out
in evidence-backed facts.

Derivations (all same-subject unless noted):

- `gross_profit` = revenue − cogs — when a period has both but no
  gross_profit (roles: addend / subtrahend)
- `gross_margin` = gross_profit ÷ revenue × 100 — same period
- `runway_months` = cash_balance ÷ net_burn — cash as-of paired with the
  burn period containing it, else the latest burn ending before it
- `top_customer_concentration` = max per-customer contract_value ÷
  Σ contract_value × 100 — per period bucket (subject = deal company)
- `net_revenue_retention` = recurring_revenue[end] ÷
  recurring_revenue[start] × 100 — consecutive same-subject periods

Idempotent: an identical derived fact (same subject/metric/value/period)
is not written twice.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.facts.extractors.base import ensure_company
from pine.facts.periods import fiscal_year_bounds
from pine.facts.store import EvidenceStore
from pine.models.deal import Deal
from pine.models.document import DocType, Document
from pine.models.entity import Entity
from pine.models.evidence import Evidence
from pine.models.fact import ExtractionMethod, Fact
from pine.schemas.entities import EntityType
from pine.schemas.metrics import MetricId
from pine.schemas.units import PeriodType, Unit

logger = logging.getLogger(__name__)

_PCT = Decimal("100")
_TWO_DP = Decimal("0.01")


class PeriodKey(NamedTuple):
    period_type: str
    period_start: date | None
    period_end: date | None
    as_of: date | None


def _period_key(f: Fact) -> PeriodKey:
    return PeriodKey(f.period_type, f.period_start, f.period_end, f.as_of)


@dataclass
class DeriveStats:
    facts_written: int = 0
    skipped_existing: int = 0
    details: list[str] = field(default_factory=list)


def _pct(a: Decimal, b: Decimal) -> Decimal | None:
    if b == 0:
        return None
    return (a / b * _PCT).quantize(_TWO_DP)


def _derived_exists(
    session: Session,
    deal_id: str,
    *,
    subject_entity_id: str,
    metric: str,
    value: Decimal,
    key: PeriodKey,
) -> bool:
    stmt = (
        select(func.count())
        .select_from(Fact)
        .where(Fact.deal_id == deal_id)
        .where(Fact.subject_entity_id == subject_entity_id)
        .where(Fact.metric == metric)
        .where(Fact.value == value)
        .where(Fact.extraction_method == ExtractionMethod.derived.value)
        .where(Fact.period_type == key.period_type)
    )
    for col, val in (
        (Fact.period_start, key.period_start),
        (Fact.period_end, key.period_end),
        (Fact.as_of, key.as_of),
    ):
        stmt = stmt.where(col.is_(None)) if val is None else stmt.where(col == val)
    return bool(session.scalar(stmt))


def _find_fact(
    session: Session,
    deal_id: str,
    *,
    subject_entity_id: str,
    metric: str,
    key: PeriodKey,
) -> Fact | None:
    """Latest fact for the (subject, metric, period) — any method."""
    stmt = (
        select(Fact)
        .where(Fact.deal_id == deal_id)
        .where(Fact.subject_entity_id == subject_entity_id)
        .where(Fact.metric == metric)
        .where(Fact.period_type == key.period_type)
        .where(Fact.superseded_by_id.is_(None))
        .order_by(Fact.created_at.desc())
        .limit(1)
    )
    for col, val in (
        (Fact.period_start, key.period_start),
        (Fact.period_end, key.period_end),
        (Fact.as_of, key.as_of),
    ):
        stmt = stmt.where(col.is_(None)) if val is None else stmt.where(col == val)
    return session.scalar(stmt)


def _add_derived(
    store: EvidenceStore,
    stats: DeriveStats,
    *,
    subject_entity_id: str,
    metric: MetricId,
    value: Decimal,
    unit: Unit,
    parents: list[tuple[Fact, str]],
    key: PeriodKey,
    currency: str | None,
    confidence: float,
    note: str,
) -> Fact | None:
    if _derived_exists(
        store.session,
        store.deal_id,
        subject_entity_id=subject_entity_id,
        metric=metric.value,
        value=value,
        key=key,
    ):
        stats.skipped_existing += 1
        return None
    fact = store.add_fact(
        subject_entity_id=subject_entity_id,
        metric=metric.value,
        value=value,
        unit=unit.value,
        currency=currency,
        period_type=key.period_type,
        period_start=key.period_start,
        period_end=key.period_end,
        as_of=key.as_of,
        source_kind="derived",
        extraction_method=ExtractionMethod.derived,
        confidence=confidence,
        fact_links=[(p.id, role) for p, role in parents],
        notes=note,
    )
    stats.facts_written += 1
    stats.details.append(metric.value)
    return fact


def _by_subject(facts: list[Fact]) -> dict[str, list[Fact]]:
    out: dict[str, list[Fact]] = {}
    for f in facts:
        out.setdefault(f.subject_entity_id, []).append(f)
    return out


def _min_confidence(facts: list[Fact]) -> float:
    return min((f.confidence for f in facts), default=1.0)


# ---------------------------------------------------------------------------
# individual derivations


def _derive_gross_margin(store: EvidenceStore, stats: DeriveStats, facts: list[Fact]) -> None:
    """gross_profit = revenue − cogs; gross_margin = gross_profit / revenue."""
    for subject, group in _by_subject(facts).items():
        by_metric: dict[str, dict[PeriodKey, Fact]] = {}
        for f in group:
            by_metric.setdefault(f.metric, {})[_period_key(f)] = f
        revenues = by_metric.get(MetricId.revenue.value, {})
        cogs = by_metric.get(MetricId.cogs.value, {})
        gross = by_metric.setdefault(MetricId.gross_profit.value, {})
        for key, rev in revenues.items():
            gp = gross.get(key)
            cg = cogs.get(key)
            if (
                gp is None
                and cg is not None
                and rev.value is not None
                and cg.value is not None
            ):
                gp = _add_derived(
                    store,
                    stats,
                    subject_entity_id=subject,
                    metric=MetricId.gross_profit,
                    value=rev.value - cg.value,
                    unit=Unit.currency,
                    parents=[(rev, "addend"), (cg, "subtrahend")],
                    key=key,
                    currency=rev.currency,
                    confidence=_min_confidence([rev, cg]),
                    note="derived: revenue - cogs",
                )
                if gp is not None:
                    gross[key] = gp
            if gp is None:
                # may exist as a derived fact written on a previous run
                gp = _find_fact(
                    store.session,
                    store.deal_id,
                    subject_entity_id=subject,
                    metric=MetricId.gross_profit.value,
                    key=key,
                )
            if gp is None or gp.value is None or not rev.value:
                continue
            margin = _pct(gp.value, rev.value)
            if margin is None:
                continue
            _add_derived(
                store,
                stats,
                subject_entity_id=subject,
                metric=MetricId.gross_margin,
                value=margin,
                unit=Unit.percent,
                parents=[(gp, "numerator"), (rev, "denominator")],
                key=key,
                currency=None,
                confidence=_min_confidence([gp, rev]),
                note="derived: gross_profit / revenue * 100",
            )


def _derive_runway(store: EvidenceStore, stats: DeriveStats, facts: list[Fact]) -> None:
    """runway_months = cash_balance ÷ net_burn (F-05.AC4 pairing rule).

    A cash fact dated D pairs with the burn fact whose period contains D;
    failing that, the latest burn ending on/before D.
    """
    for subject, group in _by_subject(facts).items():
        cash = [
            f
            for f in group
            if f.metric == MetricId.cash_balance.value and f.value is not None
        ]
        burns = [
            f
            for f in group
            if f.metric == MetricId.net_burn.value and f.value is not None
        ]
        for c in cash:
            as_of = c.as_of or c.period_end
            if as_of is None or c.value is None:
                continue
            containing = [
                b
                for b in burns
                if b.period_start is not None
                and b.period_end is not None
                and b.period_start <= as_of <= b.period_end
            ]
            earlier = [
                b
                for b in burns
                if b.period_end is not None and b.period_end <= as_of
            ]
            burn = (
                containing[0]
                if containing
                else (max(earlier, key=lambda b: b.period_end or as_of) if earlier else None)
            )
            if burn is None or not burn.value or burn.value <= 0:
                continue
            months = (c.value / burn.value).quantize(_TWO_DP)
            _add_derived(
                store,
                stats,
                subject_entity_id=subject,
                metric=MetricId.runway_months,
                value=months,
                unit=Unit.months,
                parents=[(c, "numerator"), (burn, "denominator")],
                key=PeriodKey(PeriodType.point.value, as_of, as_of, as_of),
                currency=None,
                confidence=_min_confidence([c, burn]),
                note="derived: cash_balance / net_burn",
            )


def _derive_concentration(
    store: EvidenceStore, stats: DeriveStats, facts: list[Fact], deal: Deal
) -> None:
    """top_customer_concentration = max / Σ of customer contract_value.

    The cohort is a *snapshot*: one group per `customer_list` document that
    evidences the per-customer facts (per-customer contract periods differ,
    so grouping by period would scatter the cohort).
    """
    session = store.session
    rows = session.execute(
        select(Fact, Evidence.document_id)
        .join(
            Evidence,
            (Evidence.target_id == Fact.id)
            & (Evidence.target_kind == "fact"),
        )
        .join(Document, Evidence.document_id == Document.id)
        .join(Entity, Fact.subject_entity_id == Entity.id)
        .where(Fact.deal_id == store.deal_id)
        .where(Fact.metric == MetricId.contract_value.value)
        .where(Fact.value.isnot(None))
        .where(Fact.superseded_by_id.is_(None))
        .where(Document.doc_type == DocType.customer_list)
        .where(Entity.type == EntityType.customer.value)
        .order_by(Fact.created_at, Fact.id)
    ).all()
    by_doc: dict[str, dict[str, Fact]] = {}
    for fact, doc_id in rows:
        by_doc.setdefault(doc_id, {}).setdefault(fact.subject_entity_id, fact)
    if not by_doc:
        return
    company = ensure_company(store, deal)
    fye = deal.fiscal_year_end_month
    for per_subject in by_doc.values():
        vals = list(per_subject.values())
        if len(vals) < 2:
            continue
        total = sum((f.value for f in vals if f.value is not None), Decimal(0))
        if total <= 0:
            continue
        top = max(vals, key=lambda f: f.value or Decimal(0))
        share = _pct(top.value or Decimal(0), total)
        if share is None:
            continue
        # anchor: fiscal year of the latest contract end, same rule the
        # customer-list extractor uses for its own aggregate
        ends = [f.period_end for f in vals if f.period_end is not None]
        if ends:
            anchor = max(ends)
            fy = anchor.year + 1 if anchor.month > fye else anchor.year
            start, end = fiscal_year_bounds(fy, fye)
            key = PeriodKey(PeriodType.fiscal_year.value, start, end, None)
        else:
            key = PeriodKey(PeriodType.custom.value, None, None, None)
        # the top customer is in the denominator sum too, but the FactLink
        # PK allows one role per parent — numerator wins
        parents = [(top, "numerator")] + [
            (f, "denominator") for f in vals if f.id != top.id
        ]
        _add_derived(
            store,
            stats,
            subject_entity_id=company.id,
            metric=MetricId.top_customer_concentration,
            value=share,
            unit=Unit.percent,
            parents=parents,
            key=key,
            currency=None,
            confidence=_min_confidence(vals),
            note="derived: max(customer contract_value) / sum",
        )


def _derive_nrr(store: EvidenceStore, stats: DeriveStats, facts: list[Fact]) -> None:
    """net_revenue_retention = recurring_revenue[end] ÷ [start] × 100.

    Consecutive same-subject periods only (the cohort case): the earlier
    period's end must abut the later's start within 45 days.
    """
    for subject, group in _by_subject(facts).items():
        rr = sorted(
            (
                f
                for f in group
                if f.metric == MetricId.recurring_revenue.value
                and f.value is not None
                and f.period_start is not None
                and f.period_end is not None
            ),
            key=lambda f: f.period_start or date.min,
        )
        for earlier, later in zip(rr, rr[1:], strict=False):
            if earlier.period_end is None or later.period_start is None:
                continue
            gap = (later.period_start - earlier.period_end).days
            if not (0 < gap <= 45):
                continue
            assert earlier.value is not None and later.value is not None
            nrr = _pct(later.value, earlier.value)
            if nrr is None:
                continue
            _add_derived(
                store,
                stats,
                subject_entity_id=subject,
                metric=MetricId.net_revenue_retention,
                value=nrr,
                unit=Unit.percent,
                parents=[(later, "numerator"), (earlier, "denominator")],
                key=_period_key(later),
                currency=None,
                confidence=_min_confidence([earlier, later]),
                note="derived: recurring_revenue end/start * 100",
            )


def derive_facts(
    session: Session, deal_id: str, *, deal: Deal | None = None
) -> DeriveStats:
    """Compute all derivable facts for `deal_id`; returns counts."""
    deal = deal or session.get(Deal, deal_id)
    if deal is None:
        raise ValueError(f"deal {deal_id} not found")
    store = EvidenceStore(session, deal_id)
    facts = list(
        session.scalars(
            select(Fact)
            .where(Fact.deal_id == deal_id)
            .where(Fact.superseded_by_id.is_(None))
            .where(Fact.value.isnot(None))
            .order_by(Fact.created_at, Fact.id)
        ).all()
    )
    stats = DeriveStats()
    _derive_gross_margin(store, stats, facts)
    _derive_runway(store, stats, facts)
    _derive_concentration(store, stats, facts, deal)
    _derive_nrr(store, stats, facts)
    logger.info(
        "derive deal=%s written=%d skipped=%d",
        deal_id,
        stats.facts_written,
        stats.skipped_existing,
    )
    return stats


__all__ = ["DeriveStats", "derive_facts"]
