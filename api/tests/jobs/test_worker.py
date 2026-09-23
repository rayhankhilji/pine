from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pine.db import Base
from pine.jobs.queue import enqueue
from pine.jobs.worker import Worker, job_handler
from pine.models.job import Job, JobKind, JobStatus


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s


@pytest.fixture(autouse=True)
def clean_handlers() -> Iterator[None]:
    from pine.jobs import worker as worker_mod

    saved = dict(worker_mod._HANDLERS)
    worker_mod._HANDLERS.clear()
    yield
    worker_mod._HANDLERS.clear()
    worker_mod._HANDLERS.update(saved)


async def test_job_succeeds(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    calls: list[str] = []

    @job_handler(JobKind.index_deal)
    def handler(s: Session, job: Job) -> None:
        calls.append(job.id)

    job = enqueue(session, JobKind.index_deal, {"deal_id": "d1"})
    session.commit()

    worker = Worker(session_factory)
    assert await worker.run_once() == 1

    session.refresh(job)
    assert job.status == JobStatus.succeeded
    assert calls == [job.id]
    assert job.locked_by is None


async def test_job_retries_then_dead_letters(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    @job_handler(JobKind.parse_document)
    def handler(s: Session, job: Job) -> None:
        raise ValueError("parse exploded")

    job = enqueue(session, JobKind.parse_document, {}, max_attempts=3)
    session.commit()
    worker = Worker(session_factory)

    # attempt 1: fails, requeued with backoff
    assert await worker.run_once() == 1
    session.refresh(job)
    assert job.status == JobStatus.queued
    assert job.attempts == 1
    assert job.run_after > datetime.now(UTC).replace(tzinfo=None)

    # attempts 2 and 3: force run_after due, then dead-letter
    for expected_attempts in (2, 3):
        job.run_after = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        session.commit()
        assert await worker.run_once() == 1
        session.refresh(job)
        assert job.attempts == expected_attempts

    fresh = session.get(Job, job.id)
    assert fresh is not None
    assert fresh.status == JobStatus.failed
    assert "parse exploded" in (fresh.error or "")


async def test_idempotency_key_dedupes(session: Session) -> None:
    first = enqueue(session, JobKind.index_deal, {}, idempotency_key="index:d1:5")
    second = enqueue(session, JobKind.index_deal, {}, idempotency_key="index:d1:5")
    session.commit()
    assert first.id == second.id
    assert session.query(Job).count() == 1


async def test_stale_lock_released(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    stale = Job(
        kind=JobKind.index_deal,
        status=JobStatus.running,
        locked_by="dead-worker",
        locked_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=20),
    )
    fresh = Job(
        kind=JobKind.index_deal,
        status=JobStatus.running,
        locked_by="live-worker",
        locked_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add_all([stale, fresh])
    session.commit()

    worker = Worker(session_factory)
    assert worker.release_stale_locks() == 1

    session.refresh(stale)
    session.refresh(fresh)
    assert stale.status == JobStatus.queued
    assert stale.locked_by is None
    assert fresh.status == JobStatus.running
    assert fresh.locked_by == "live-worker"


async def test_async_handler(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    done: list[str] = []

    @job_handler(JobKind.build_graph)
    async def handler(s: Session, job: Job) -> None:
        done.append(job.id)

    job = enqueue(session, JobKind.build_graph)
    session.commit()

    assert await Worker(session_factory).run_once() == 1
    session.refresh(job)
    assert job.status == JobStatus.succeeded
    assert done == [job.id]


async def test_no_handler_fails_job(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    job = enqueue(
        session, JobKind.generate_output, {}, max_attempts=1
    )
    session.commit()
    # no handler registered for generate_output in this test's registry
    from pine.jobs import worker as worker_mod

    worker_mod._HANDLERS.pop(JobKind.generate_output, None)
    await Worker(session_factory).run_once()
    session.refresh(job)
    assert job.status == JobStatus.failed
    assert "no handler" in (job.error or "")
