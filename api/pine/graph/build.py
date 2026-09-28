"""Graph build orchestrator (P3.T8).

`build_graph` is the pipeline entry point after facts exist:

1. contract documents → `contract`/`customer` entities + `has_contract` /
   `has_customer` edges
2. email documents → `person` entities + `employs` edges
3. resolution pass — alias hits + fuzzy (token_set ≥ 92) merges

All writes flow through `EvidenceStore`; merging repoints every Fact,
Relation and Evidence row so provenance survives consolidation.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from pine.facts.store import EvidenceStore
from pine.graph.extract import (
    extract_contract_entities,
    extract_email_entities,
)
from pine.graph.resolve import resolve_entities
from pine.models.deal import Deal

logger = logging.getLogger(__name__)


@dataclass
class BuildStats:
    entities: int = 0
    relations: int = 0
    merged: int = 0


def build_graph(session: Session, deal_id: str) -> BuildStats:
    deal = session.get(Deal, deal_id)
    if deal is None:
        raise ValueError(f"deal {deal_id} not found")
    store = EvidenceStore(session, deal_id)
    stats = BuildStats()

    for extract in (extract_contract_entities, extract_email_entities):
        s = extract(session, store, deal)
        stats.entities += s.entities
        stats.relations += s.relations

    res = resolve_entities(session, deal_id)
    stats.merged = res.merged
    logger.info(
        "build_graph deal=%s +entities=%d +relations=%d merged=%d",
        deal_id,
        stats.entities,
        stats.relations,
        stats.merged,
    )
    return stats


__all__ = ["BuildStats", "build_graph"]
