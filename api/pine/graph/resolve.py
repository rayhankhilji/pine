"""Entity resolution (F-04.AC2, ARCHITECTURE §10).

Two merge signals:

- **alias hit** — entity B's normalised name is an observed alias of A
  (exact match already handled inside `EvidenceStore.add_entity`)
- **fuzzy** — `rapidfuzz.fuzz.token_set_ratio` over normalised names ≥ 92
  (handles "Northwind" ↔ "Northwind SaaS", word-order swaps, dropped words)

Only entities of the same `type` are ever merged. `merge_entities` repoints
facts, relations (honouring the `(type, source, target)` unique constraint —
colliding duplicates fold into the kept relation and keep their evidence),
entity-scoped evidence, and aliases onto the winner, records the loser's
surface forms as aliases, and stamps `merged_into_id`.
"""

import logging
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.facts.store import EvidenceStore
from pine.models.entity import Entity, EntityAlias, Relation
from pine.models.evidence import Evidence, EvidenceTarget
from pine.models.fact import Fact

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 92


@dataclass
class ResolveStats:
    merged: int = 0
    pairs: list[tuple[str, str]] = field(default_factory=list)


def _alias_norms(session: Session, deal_id: str) -> dict[str, set[str]]:
    rows = session.execute(
        select(EntityAlias.entity_id, EntityAlias.normalized)
        .join(Entity, EntityAlias.entity_id == Entity.id)
        .where(Entity.deal_id == deal_id)
    ).all()
    out: dict[str, set[str]] = {}
    for entity_id, normalized in rows:
        if normalized:
            out.setdefault(entity_id, set()).add(normalized)
    return out


def _find(parent: dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: dict[str, str], a: str, b: str) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[rb] = ra


def _evidence_count(session: Session, entity_id: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Evidence)
            .where(Evidence.target_kind == EvidenceTarget.entity.value)
            .where(Evidence.target_id == entity_id)
        )
        or 0
    )


def merge_entities(store: EvidenceStore, into: Entity, other: Entity) -> Entity:
    """Merge `other` into `into`; returns the surviving entity."""
    session = store.session
    if into.id == other.id:
        return into
    if other.merged_into_id is not None:
        return into

    for fact in session.scalars(
        select(Fact).where(Fact.subject_entity_id == other.id)
    ).all():
        fact.subject_entity_id = into.id

    relations = session.scalars(
        select(Relation).where(
            (Relation.source_entity_id == other.id)
            | (Relation.target_entity_id == other.id)
        )
    ).all()
    for rel in relations:
        new_src = into.id if rel.source_entity_id == other.id else rel.source_entity_id
        new_tgt = into.id if rel.target_entity_id == other.id else rel.target_entity_id
        collision = session.scalar(
            select(Relation)
            .where(Relation.deal_id == store.deal_id)
            .where(Relation.type == rel.type)
            .where(Relation.source_entity_id == new_src)
            .where(Relation.target_entity_id == new_tgt)
            .where(Relation.id != rel.id)
        )
        if collision is not None:
            # fold evidence onto the kept relation, drop the duplicate edge
            for ev in session.scalars(
                select(Evidence)
                .where(Evidence.target_kind == EvidenceTarget.relation.value)
                .where(Evidence.target_id == rel.id)
            ).all():
                ev.target_id = collision.id
            session.delete(rel)
        else:
            rel.source_entity_id = new_src
            rel.target_entity_id = new_tgt

    for ev in session.scalars(
        select(Evidence)
        .where(Evidence.target_kind == EvidenceTarget.entity.value)
        .where(Evidence.target_id == other.id)
    ).all():
        ev.target_id = into.id

    for alias in session.scalars(
        select(EntityAlias).where(EntityAlias.entity_id == other.id)
    ).all():
        alias.entity_id = into.id
    store.add_alias(into, other.canonical_name)

    other.merged_into_id = into.id
    into.confidence = max(into.confidence, other.confidence)
    session.flush()
    logger.info(
        "entity merge deal=%s %r -> %r", store.deal_id, other.canonical_name,
        into.canonical_name,
    )
    return into


def resolve_entities(
    session: Session, deal_id: str, *, threshold: float = FUZZY_THRESHOLD
) -> ResolveStats:
    """Cluster same-type entities on name similarity; merge each cluster."""
    store = EvidenceStore(session, deal_id)
    entities = list(
        session.scalars(
            select(Entity)
            .where(Entity.deal_id == deal_id)
            .where(Entity.merged_into_id.is_(None))
            .order_by(Entity.created_at, Entity.id)
        ).all()
    )
    aliases = _alias_norms(session, deal_id)
    stats = ResolveStats()

    by_type: dict[str, list[Entity]] = {}
    for e in entities:
        by_type.setdefault(e.type, []).append(e)

    for group in by_type.values():
        # union-find over the group
        parent: dict[str, str] = {e.id: e.id for e in group}

        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                alias_hit = (
                    b.normalized_name in aliases.get(a.id, set())
                    or a.normalized_name in aliases.get(b.id, set())
                )
                similar = bool(
                    a.normalized_name
                    and b.normalized_name
                    and fuzz.token_set_ratio(
                        a.normalized_name, b.normalized_name
                    )
                    >= threshold
                )
                if alias_hit or similar:
                    _union(parent, a.id, b.id)

        clusters: dict[str, list[Entity]] = {}
        for e in group:
            clusters.setdefault(_find(parent, e.id), []).append(e)
        for members in clusters.values():
            if len(members) < 2:
                continue
            # winner: most evidence; tie-break = earliest created
            winner = max(
                members,
                key=lambda e: (
                    _evidence_count(session, e.id),
                    -group.index(e),
                ),
            )
            for loser in members:
                if loser.id == winner.id:
                    continue
                merge_entities(store, winner, loser)
                stats.merged += 1
                stats.pairs.append((loser.id, winner.id))
    return stats


__all__ = [
    "FUZZY_THRESHOLD",
    "ResolveStats",
    "merge_entities",
    "resolve_entities",
]
