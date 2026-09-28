"""Fact query helpers — deal-scoped, keyset cursor like repos/deals.py."""

import base64
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from pine.models.evidence import Evidence, EvidenceTarget
from pine.models.fact import Fact, FactLink


def get_fact(session: Session, fact_id: str) -> Fact | None:
    return session.get(Fact, fact_id)


def _encode_cursor(fact: Fact) -> str:
    raw = f"{fact.created_at.isoformat()}|{fact.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at, fact_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(created_at), fact_id
    except (ValueError, IndexError):
        return None


def list_facts(
    session: Session,
    deal_id: str,
    *,
    metric: str | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    source_kind: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Fact], str | None]:
    stmt: Select[tuple[Fact]] = (
        select(Fact)
        .where(Fact.deal_id == deal_id)
        .order_by(Fact.created_at, Fact.id)
    )
    if metric is not None:
        stmt = stmt.where(Fact.metric == metric)
    if source_kind is not None:
        stmt = stmt.where(Fact.source_kind == source_kind)
    # overlap: the fact's effective [start, end] (period_* falling back to
    # as_of) must intersect [period_from, period_to]
    if period_from is not None:
        stmt = stmt.where(
            func.coalesce(Fact.period_end, Fact.as_of) >= period_from
        )
    if period_to is not None:
        stmt = stmt.where(
            func.coalesce(Fact.period_start, Fact.as_of) <= period_to
        )
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded is not None:
            created_at, fact_id = decoded
            stmt = stmt.where(
                or_(
                    Fact.created_at > created_at,
                    (Fact.created_at == created_at) & (Fact.id > fact_id),
                )
            )
    items = list(session.scalars(stmt.limit(limit + 1)).all())
    next_cursor = _encode_cursor(items[limit - 1]) if len(items) > limit else None
    return items[:limit], next_cursor


def evidence_map(
    session: Session,
    target_kind: EvidenceTarget | str,
    target_ids: list[str],
) -> dict[str, list[Evidence]]:
    """Batch-load evidence rows for a set of targets, keyed by target_id."""
    if not target_ids:
        return {}
    rows = session.scalars(
        select(Evidence)
        .where(Evidence.target_kind == str(target_kind))
        .where(Evidence.target_id.in_(target_ids))
        .order_by(Evidence.created_at, Evidence.id)
    ).all()
    out: dict[str, list[Evidence]] = {}
    for row in rows:
        if row.target_id is not None:
            out.setdefault(row.target_id, []).append(row)
    return out


def derived_from(session: Session, fact_id: str) -> list[Fact]:
    """Parent facts of `fact_id` via FactLink, in link order."""
    return list(
        session.scalars(
            select(Fact)
            .join(FactLink, FactLink.parent_fact_id == Fact.id)
            .where(FactLink.fact_id == fact_id)
            .order_by(Fact.created_at, Fact.id)
        ).all()
    )


def update_fact(session: Session, fact: Fact, fields: dict[str, Any]) -> Fact:
    """Apply a PATCH body (`exclude_unset` keys only) to a fact."""
    if "notes" in fields:
        fact.notes = fields["notes"]
    if fields.get("is_authoritative") is not None:
        fact.is_authoritative = bool(fields["is_authoritative"])
        if fact.is_authoritative:
            # one authoritative fact per (subject, metric, period): clear
            # the flag on same-period siblings
            stmt = (
                select(Fact)
                .where(Fact.deal_id == fact.deal_id)
                .where(Fact.subject_entity_id == fact.subject_entity_id)
                .where(Fact.metric == fact.metric)
                .where(Fact.period_type == fact.period_type)
                .where(Fact.id != fact.id)
                .where(Fact.is_authoritative.is_(True))
            )
            for col, val in (
                (Fact.period_start, fact.period_start),
                (Fact.period_end, fact.period_end),
                (Fact.as_of, fact.as_of),
            ):
                stmt = stmt.where(col.is_(None)) if val is None else stmt.where(col == val)
            for sib in session.scalars(stmt).all():
                sib.is_authoritative = False
    session.commit()
    session.refresh(fact)
    return fact


def distinct_metrics(session: Session, deal_id: str) -> list[str]:
    rows = session.scalars(
        select(Fact.metric)
        .where(Fact.deal_id == deal_id)
        .distinct()
        .order_by(Fact.metric)
    ).all()
    return list(rows)


__all__ = [
    "derived_from",
    "distinct_metrics",
    "evidence_map",
    "get_fact",
    "list_facts",
    "update_fact",
]
