"""Fact endpoints (ARCHITECTURE §5, F-05).

`GET /deals/{id}/facts` lists deal facts with metric/period/source filters
and keyset cursor pagination; each serialized fact embeds its Evidence rows
(with `filename` resolved for viewer deep links) and a `contested` flag
(placeholder `false` until the P4 contradiction engine lands).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from pine.api.schemas.facts import (
    Evidence,
    Fact,
    FactDetail,
    FactPage,
    FactPatch,
)
from pine.db import get_session
from pine.errors import AppError
from pine.models.document import DocType
from pine.models.evidence import EvidenceTarget
from pine.models.fact import Fact as FactModel
from pine.repos import deals as deals_repo
from pine.repos import entities as entities_repo
from pine.repos import facts as facts_repo

router = APIRouter(tags=["facts"])


def _get_deal_or_404(session: Session, deal_id: str) -> None:
    if deals_repo.get_deal(session, deal_id) is None:
        raise AppError("NOT_FOUND", "Deal not found", status=404)


def _get_fact_or_404(session: Session, fact_id: str) -> FactModel:
    fact = facts_repo.get_fact(session, fact_id)
    if fact is None:
        raise AppError("NOT_FOUND", "Fact not found", status=404)
    return fact


def serialize_facts(session: Session, facts: list[FactModel]) -> list[Fact]:
    """ORM rows → Fact schemas with evidence + resolved filenames."""
    ev_map = facts_repo.evidence_map(
        session, EvidenceTarget.fact, [f.id for f in facts]
    )
    doc_ids = sorted(
        {ev.document_id for rows in ev_map.values() for ev in rows}
    )
    names = entities_repo.document_names(session, doc_ids)
    out: list[Fact] = []
    for fact in facts:
        schema = Fact.model_validate(fact)
        schema.evidence = [
            Evidence.model_validate(ev).model_copy(
                update={"filename": names.get(ev.document_id)}
            )
            for ev in ev_map.get(fact.id, [])
        ]
        out.append(schema)
    return out


@router.get("/deals/{deal_id}/facts")
def list_facts(
    deal_id: str,
    session: Annotated[Session, Depends(get_session)],
    metric: str | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    source_kind: DocType | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> FactPage:
    _get_deal_or_404(session, deal_id)
    items, next_cursor = facts_repo.list_facts(
        session,
        deal_id,
        metric=metric,
        period_from=period_from,
        period_to=period_to,
        source_kind=str(source_kind) if source_kind is not None else None,
        cursor=cursor,
        limit=limit,
    )
    return FactPage(
        items=serialize_facts(session, items), next_cursor=next_cursor
    )


@router.get("/facts/{fact_id}")
def get_fact(
    fact_id: str, session: Annotated[Session, Depends(get_session)]
) -> FactDetail:
    fact = _get_fact_or_404(session, fact_id)
    base = serialize_facts(session, [fact])[0]
    parents = facts_repo.derived_from(session, fact.id)
    return FactDetail(
        **base.model_dump(),
        derived_from=serialize_facts(session, parents),
    )


@router.patch("/facts/{fact_id}")
def patch_fact(
    fact_id: str,
    data: FactPatch,
    session: Annotated[Session, Depends(get_session)],
) -> Fact:
    fact = _get_fact_or_404(session, fact_id)
    updated = facts_repo.update_fact(
        session, fact, data.model_dump(exclude_unset=True)
    )
    return serialize_facts(session, [updated])[0]
