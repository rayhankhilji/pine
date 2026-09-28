"""Graph export — JSON {nodes, edges} and GraphML (F-04.AC3 surface)."""

import io
from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.models.entity import Entity, Relation

GraphPayload = dict[str, list[dict[str, Any]]]


def _graph(session: Session, deal_id: str) -> nx.DiGraph:
    g = nx.DiGraph()
    entities = session.scalars(
        select(Entity)
        .where(Entity.deal_id == deal_id)
        .where(Entity.merged_into_id.is_(None))
        .order_by(Entity.created_at, Entity.id)
    ).all()
    for e in entities:
        g.add_node(
            e.id,
            type=e.type,
            name=e.canonical_name,
            confidence=round(e.confidence, 4),
        )
    ids = set(g.nodes)
    relations = session.scalars(
        select(Relation)
        .where(Relation.deal_id == deal_id)
        .order_by(Relation.created_at, Relation.id)
    ).all()
    for r in relations:
        if r.source_entity_id in ids and r.target_entity_id in ids:
            g.add_edge(
                r.source_entity_id,
                r.target_entity_id,
                id=r.id,
                type=r.type,
                confidence=round(r.confidence, 4),
            )
    return g


def export_json(session: Session, deal_id: str) -> GraphPayload:
    """`{nodes: [...], edges: [...]}` — the API/frontend payload shape."""
    g = _graph(session, deal_id)
    return {
        "nodes": [
            {"id": n, **data} for n, data in g.nodes(data=True)
        ],
        "edges": [
            {
                "id": data["id"],
                "type": data["type"],
                "source": src,
                "target": tgt,
                "confidence": data["confidence"],
            }
            for src, tgt, data in g.edges(data=True)
        ],
    }


def export_graphml(session: Session, deal_id: str) -> str:
    """GraphML string via networkx (attributes serialised as strings)."""
    g = _graph(session, deal_id)
    # GraphML wants plain scalar attributes
    for _, data in g.nodes(data=True):
        data["confidence"] = str(data["confidence"])
    for _, _, data in g.edges(data=True):
        data["confidence"] = str(data["confidence"])
    buf = io.BytesIO()
    nx.write_graphml(g, buf)
    return buf.getvalue().decode("utf-8")


__all__ = ["export_json", "export_graphml"]
