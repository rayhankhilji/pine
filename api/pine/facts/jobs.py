"""extract_facts job handler (ARCHITECTURE §9, F-05).

Runs the deterministic table extractors, then the LLM prose pass, then the
derived-fact pass, and finally enqueues `build_graph` keyed on the deal's
fact count so re-extraction triggers a graph rebuild.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.facts.derive import derive_facts
from pine.facts.extractors import run_extractors
from pine.facts.llm_extract import extract_facts
from pine.jobs.queue import enqueue
from pine.jobs.worker import job_handler
from pine.models.fact import Fact
from pine.models.job import Job, JobKind, JobStatus

logger = logging.getLogger(__name__)


@job_handler(JobKind.extract_facts)
def extract_facts_job(session: Session, job: Job) -> None:
    deal_id = job.payload["deal_id"]
    # index_deal is enqueued as soon as every *document* is terminal, but a
    # classify job for the last-parsed doc may still be queued/running under
    # a concurrent worker — defer rather than extract on stale doc_types.
    pending_classify = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.deal_id == deal_id)
        .where(Job.kind == JobKind.classify_document.value)
        .where(Job.status.in_((JobStatus.queued.value, JobStatus.running.value)))
    )
    if pending_classify:
        enqueue(
            session,
            JobKind.extract_facts,
            {"deal_id": deal_id},
            deal_id=deal_id,
            run_after=datetime.now(UTC) + timedelta(seconds=2),
        )
        return

    table_facts = run_extractors(session, deal_id)
    llm_stats = extract_facts(session, deal_id)
    derived = derive_facts(session, deal_id)
    fact_count = session.scalar(
        select(func.count())
        .select_from(Fact)
        .where(Fact.deal_id == deal_id)
        .where(Fact.superseded_by_id.is_(None))
    )
    enqueue(
        session,
        JobKind.build_graph,
        {"deal_id": deal_id},
        deal_id=deal_id,
        idempotency_key=f"graph:{deal_id}:{fact_count}",
    )
    logger.info(
        "extract_facts %s: table=%d llm=%d derived=%d (facts=%d)",
        deal_id,
        table_facts,
        llm_stats.facts_written,
        derived.facts_written,
        fact_count,
    )
