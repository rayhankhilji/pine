from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.models.job import Job, JobKind


def enqueue(
    session: Session,
    kind: JobKind | str,
    payload: dict[str, Any] | None = None,
    deal_id: str | None = None,
    idempotency_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> Job:
    """Enqueue a job. If `idempotency_key` already exists, return the existing row."""
    if idempotency_key is not None:
        existing = session.scalar(
            select(Job).where(Job.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing
    job = Job(
        deal_id=deal_id,
        kind=JobKind(kind),
        payload=payload or {},
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
    )
    if run_after is not None:
        job.run_after = run_after
    session.add(job)
    session.flush()
    return job
