import asyncio
import inspect
import logging
import socket
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from pine.models.job import (
    JOB_TIMEOUTS_SECONDS,
    STALE_LOCK_MINUTES,
    Job,
    JobKind,
    JobStatus,
)

logger = logging.getLogger(__name__)

JobHandler = Callable[[Session, Job], "None | Awaitable[None]"]

_HANDLERS: dict[JobKind, JobHandler] = {}

POLL_INTERVAL_SECONDS = 0.5
BASE_BACKOFF_SECONDS = 5


def job_handler(kind: JobKind) -> Callable[[JobHandler], JobHandler]:
    """Register a handler for a job kind: `@job_handler(JobKind.parse_document)`."""

    def decorator(fn: JobHandler) -> JobHandler:
        _HANDLERS[kind] = fn
        return fn

    return decorator


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Worker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        concurrency: int = 4,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        worker_id: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self._semaphore = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task[None]] = set()
        self._stopping = asyncio.Event()

    def release_stale_locks(self) -> int:
        """Requeue jobs locked longer than STALE_LOCK_MINUTES (call on startup)."""
        cutoff = _utcnow() - timedelta(minutes=STALE_LOCK_MINUTES)
        with self.session_factory() as session:
            result = session.execute(
                update(Job)
                .where(Job.status == JobStatus.running)
                .where(Job.locked_at < cutoff)
                .values(status=JobStatus.queued, locked_by=None, locked_at=None)
            )
            session.commit()
            count = result.rowcount if isinstance(result, CursorResult) else 0
        if count:
            logger.warning("released %d stale job locks", count)
        return count

    def claim_due_jobs(self, limit: int | None = None) -> list[str]:
        """Atomically claim due queued jobs; returns claimed job ids."""
        limit = limit or self.concurrency
        now = _utcnow()
        claimed: list[str] = []
        with self.session_factory() as session:
            candidates = session.scalars(
                select(Job.id)
                .where(Job.status == JobStatus.queued)
                .where(Job.run_after <= now)
                .order_by(Job.created_at)
                .limit(limit)
            ).all()
            for job_id in candidates:
                result = session.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .where(Job.status == JobStatus.queued)
                    .values(
                        status=JobStatus.running,
                        locked_by=self.worker_id,
                        locked_at=now,
                    )
                )
                if getattr(result, "rowcount", 0) == 1:
                    claimed.append(job_id)
            session.commit()
        return claimed

    async def run_once(self) -> int:
        """One poll cycle: claim due jobs and run them to completion. Returns count run."""
        claimed = self.claim_due_jobs()
        if claimed:
            await asyncio.gather(*(self._execute(job_id) for job_id in claimed))
        return len(claimed)

    async def run_forever(self) -> None:
        self.release_stale_locks()
        while not self._stopping.is_set():
            claimed = self.claim_due_jobs()
            for job_id in claimed:
                task = asyncio.create_task(self._guarded(job_id))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            if not claimed:
                await asyncio.sleep(self.poll_interval)
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _guarded(self, job_id: str) -> None:
        async with self._semaphore:
            await self._execute(job_id)

    def stop(self) -> None:
        self._stopping.set()

    async def _execute(self, job_id: str) -> None:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None or job.status != JobStatus.running:
                return
            handler = _HANDLERS.get(JobKind(job.kind))
            timeout = JOB_TIMEOUTS_SECONDS.get(JobKind(job.kind), 5 * 60)
            try:
                if handler is None:
                    raise RuntimeError(f"no handler registered for {job.kind}")
                if inspect.iscoroutinefunction(handler):
                    await asyncio.wait_for(handler(session, job), timeout=timeout)
                else:
                    await asyncio.wait_for(
                        asyncio.to_thread(handler, session, job), timeout=timeout
                    )
            except TimeoutError:
                self._fail_or_retry(session, job, f"timed out after {timeout}s")
            except Exception as exc:  # noqa: BLE001 — job errors become job failure
                logger.exception("job %s (%s) failed", job.id, job.kind)
                self._fail_or_retry(session, job, f"{type(exc).__name__}: {exc}")
            else:
                job.status = JobStatus.succeeded
                job.locked_by = None
                job.locked_at = None
                job.error = None
            session.commit()

    def _fail_or_retry(self, session: Session, job: Job, error: str) -> None:
        job.attempts += 1
        job.error = error
        job.locked_by = None
        job.locked_at = None
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.failed
            logger.error("job %s dead-lettered after %d attempts", job.id, job.attempts)
        else:
            job.status = JobStatus.queued
            job.run_after = _utcnow() + timedelta(
                seconds=BASE_BACKOFF_SECONDS * 2**job.attempts
            )
