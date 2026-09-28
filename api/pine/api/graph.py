"""Knowledge-graph + entity endpoints (ARCHITECTURE §5, F-04).

`GET /deals/{id}/graph` returns `{nodes, edges}` (optionally filtered by
`?types=` csv and `?limit=`); `?format=graphml` streams the networkx GraphML
export as `application/graphml+xml`. `POST /entities/{id}/merge` re-points
aliases/evidence/relations/facts onto the surviving entity (409 on a
self-merge or a merged-away target); `POST /entities/{id}/split` moves
aliases onto a new entity (201).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from pine.api.facts import serialize_facts
from pine.api.schemas.facts import Evidence
from pine.api.schemas.graph import (
    Entity,
    EntityAlias,
    EntityDetail,
    EntityMerge,
    EntitySplit,
    GraphResponse,
    Relation,
)
from pine.db import get_session
from pine.errors import AppError
from pine.facts.store import EvidenceStore
from pine.graph import export_graphml
from pine.graph.resolve import (
    EntityNameConflict,
    merge_entities,
    split_entity,
)
from pine.models.entity import Entity as EntityModel
from pine.models.evidence import EvidenceTarget
from pine.repos import deals as deals_repo
from pine.repos import entities as entities_repo
from pine.repos import facts as facts_repo
from pine.schemas.entities import EntityType

router = APIRouter(tags=["graph"])

_ENTITY_TYPES = {t.value for t in EntityType}


def _get_deal_or_404(session: Session, deal_id: str) -> None:
    if deals_repo.get_deal(session, deal_id) is None:
        raise AppError("NOT_FOUND", "Deal not found", status=404)


def _get_entity_or_404(session: Session, entity_id: str) -> EntityModel:
    entity = entities_repo.get_entity(session, entity_id)
    if entity is None or entity.merged_into_id is not None:
        raise AppError("NOT_FOUND", "Entity not found", status=404)
    return entity


def _parse_types(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    types = [t.strip() for t in raw.split(",") if t.strip()]
    bad = [t for t in types if t not in _ENTITY_TYPES]
    if bad:
        raise AppError(
            "VALIDATION",
            f"Unknown entity types: {', '.join(bad)}",
            status=422,
            details={"valid": sorted(_ENTITY_TYPES)},
        )
    return types


@router.get("/deals/{deal_id}/graph", response_model=GraphResponse)
def deal_graph(
    deal_id: str,
    session: Annotated[Session, Depends(get_session)],
    types: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    format: str | None = None,
) -> GraphResponse | Response:
    _get_deal_or_404(session, deal_id)
    if format is not None:
        if format != "graphml":
            raise AppError(
                "VALIDATION",
                f"Unknown graph format: {format}",
                status=422,
            )
        return Response(
            content=export_graphml(session, deal_id),
            media_type="application/graphml+xml",
        )
    nodes, edges = entities_repo.deal_graph(
        session, deal_id, types=_parse_types(types), limit=limit
    )
    return GraphResponse(
        nodes=[Entity.model_validate(e) for e in nodes],
        edges=[Relation.model_validate(r) for r in edges],
    )


@router.get("/entities/{entity_id}")
def get_entity(
    entity_id: str, session: Annotated[Session, Depends(get_session)]
) -> EntityDetail:
    entity = _get_entity_or_404(session, entity_id)
    evidence = facts_repo.evidence_map(
        session, EvidenceTarget.entity, [entity.id]
    ).get(entity.id, [])
    names = entities_repo.document_names(
        session, sorted({ev.document_id for ev in evidence})
    )
    facts = entities_repo.entity_facts(session, entity.id)
    return EntityDetail(
        **Entity.model_validate(entity).model_dump(),
        aliases=[
            EntityAlias.model_validate(a)
            for a in entities_repo.entity_aliases(session, entity.id)
        ],
        evidence=[
            Evidence.model_validate(ev).model_copy(
                update={"filename": names.get(ev.document_id)}
            )
            for ev in evidence
        ],
        relations=[
            Relation.model_validate(r)
            for r in entities_repo.entity_relations(session, entity.id)
        ],
        facts=serialize_facts(session, facts),
    )


@router.post("/entities/{entity_id}/merge")
def merge_entity(
    entity_id: str,
    data: EntityMerge,
    session: Annotated[Session, Depends(get_session)],
) -> Entity:
    entity = _get_entity_or_404(session, entity_id)
    if data.into_entity_id == entity.id:
        raise AppError(
            "CONFLICT", "Cannot merge an entity into itself", status=409
        )
    into = entities_repo.get_entity(session, data.into_entity_id)
    if into is None or into.merged_into_id is not None:
        raise AppError("NOT_FOUND", "Target entity not found", status=404)
    if into.deal_id != entity.deal_id:
        raise AppError(
            "VALIDATION",
            "Cannot merge entities across deals",
            status=422,
        )
    winner = merge_entities(EvidenceStore(session, entity.deal_id), into, entity)
    session.commit()
    return Entity.model_validate(winner)


@router.post("/entities/{entity_id}/split", status_code=status.HTTP_201_CREATED)
def split_entity_endpoint(
    entity_id: str,
    data: EntitySplit,
    session: Annotated[Session, Depends(get_session)],
) -> Entity:
    entity = _get_entity_or_404(session, entity_id)
    try:
        fresh = split_entity(
            EvidenceStore(session, entity.deal_id), entity, data.alias_ids
        )
    except EntityNameConflict as exc:
        raise AppError("CONFLICT", str(exc), status=409) from exc
    except ValueError as exc:
        raise AppError("VALIDATION", str(exc), status=422) from exc
    session.commit()
    return Entity.model_validate(fresh)
