"""build_graph job handler (ARCHITECTURE §9, F-04).

Extracts entities/relations (contracts, emails), runs the resolution pass,
then enqueues `detect_contradictions` keyed on the graph's size so edits
and rebuilds re-trigger detection.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.graph.build import build_graph
from pine.jobs.queue import enqueue
from pine.jobs.worker import job_handler
from pine.models.entity import Entity, Relation
from pine.models.fact import Fact
from pine.models.job import Job, JobKind

logger = logging.getLogger(__name__)


def _graph_fingerprint(session: Session, deal_id: str) -> str:
    """Version stamp for the contradictions idempotency key."""
    facts = session.scalar(
        select(func.count())
        .select_from(Fact)
        .where(Fact.deal_id == deal_id)
        .where(Fact.superseded_by_id.is_(None))
    )
    entities = session.scalar(
        select(func.count())
        .select_from(Entity)
        .where(Entity.deal_id == deal_id)
        .where(Entity.merged_into_id.is_(None))
    )
    relations = session.scalar(
        select(func.count())
        .select_from(Relation)
        .where(Relation.deal_id == deal_id)
    )
    return f"{facts}:{entities}:{relations}"


@job_handler(JobKind.build_graph)
def build_graph_job(session: Session, job: Job) -> None:
    deal_id = job.payload["deal_id"]
    stats = build_graph(session, deal_id)
    fingerprint = _graph_fingerprint(session, deal_id)
    enqueue(
        session,
        JobKind.detect_contradictions,
        {"deal_id": deal_id},
        deal_id=deal_id,
        idempotency_key=f"contradictions:{deal_id}:{fingerprint}",
    )
    logger.info(
        "build_graph %s: +entities=%d +relations=%d merged=%d",
        deal_id,
        stats.entities,
        stats.relations,
        stats.merged,
    )
