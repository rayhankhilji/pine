"""detect_contradictions job handler (ARCHITECTURE §9, F-06).

Stub for now — the R1–R7 rules engine lands in P4 (see ROADMAP). The
handler exists so the ingest → index → extract → graph → contradictions
chain completes end-to-end; the worker marks it succeeded on return.
"""

import logging

from sqlalchemy.orm import Session

from pine.jobs.worker import job_handler
from pine.models.job import Job, JobKind

logger = logging.getLogger(__name__)


@job_handler(JobKind.detect_contradictions)
def detect_contradictions(session: Session, job: Job) -> None:
    logger.info(
        "detect_contradictions %s: stub — rules engine lands in P4",
        job.payload.get("deal_id"),
    )
