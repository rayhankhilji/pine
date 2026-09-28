"""Entity/Relation query helpers — deal-scoped (ARCHITECTURE §4, F-04)."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.models.document import Document
from pine.models.entity import Entity, EntityAlias, Relation
from pine.models.fact import Fact


def get_entity(session: Session, entity_id: str) -> Entity | None:
    return session.get(Entity, entity_id)


def entity_aliases(session: Session, entity_id: str) -> list[EntityAlias]:
    return list(
        session.scalars(
            select(EntityAlias)
            .where(EntityAlias.entity_id == entity_id)
            .order_by(EntityAlias.created_at, EntityAlias.id)
        ).all()
    )


def entity_relations(session: Session, entity_id: str) -> list[Relation]:
    """Live relations touching the entity (either endpoint)."""
    return list(
        session.scalars(
            select(Relation)
            .where(
                (Relation.source_entity_id == entity_id)
                | (Relation.target_entity_id == entity_id)
            )
            .order_by(Relation.created_at, Relation.id)
        ).all()
    )


def entity_facts(session: Session, entity_id: str) -> list[Fact]:
    return list(
        session.scalars(
            select(Fact)
            .where(Fact.subject_entity_id == entity_id)
            .where(Fact.superseded_by_id.is_(None))
            .order_by(Fact.created_at, Fact.id)
        ).all()
    )


def deal_graph(
    session: Session,
    deal_id: str,
    *,
    types: Sequence[str] | None = None,
    limit: int = 500,
) -> tuple[list[Entity], list[Relation]]:
    """Live entities (+ relations between them) for the graph endpoint."""
    stmt = (
        select(Entity)
        .where(Entity.deal_id == deal_id)
        .where(Entity.merged_into_id.is_(None))
        .order_by(Entity.created_at, Entity.id)
        .limit(limit)
    )
    if types:
        stmt = stmt.where(Entity.type.in_(list(types)))
    nodes = list(session.scalars(stmt).all())
    ids = {e.id for e in nodes}
    edges = [
        r
        for r in session.scalars(
            select(Relation)
            .where(Relation.deal_id == deal_id)
            .order_by(Relation.created_at, Relation.id)
        ).all()
        if r.source_entity_id in ids and r.target_entity_id in ids
    ]
    return nodes, edges


def document_names(session: Session, document_ids: Sequence[str]) -> dict[str, str]:
    """document_id → filename for evidence serialisation."""
    if not document_ids:
        return {}
    rows = session.execute(
        select(Document.id, Document.filename).where(
            Document.id.in_(list(document_ids))
        )
    ).all()
    return {doc_id: filename for doc_id, filename in rows}


__all__ = [
    "deal_graph",
    "document_names",
    "entity_aliases",
    "entity_facts",
    "entity_relations",
    "get_entity",
]
