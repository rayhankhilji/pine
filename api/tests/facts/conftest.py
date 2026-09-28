"""Shared fixtures/helpers for facts tests — demo room + synthetic content."""

import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import pine.contradictions.jobs  # noqa: F401 — registers detect_contradictions
import pine.facts.jobs  # noqa: F401 — registers extract_facts
import pine.graph.jobs  # noqa: F401 — registers build_graph
import pine.index.jobs  # noqa: F401 — registers index_deal
import pine.ingest.jobs  # noqa: F401 — registers parse/classify handlers
from pine.api.schemas.deal import DealCreate
from pine.config import get_settings
from pine.demo.build import build_demo
from pine.jobs.worker import _HANDLERS
from pine.models.chunk import Chunk, ChunkKind
from pine.models.deal import Deal
from pine.models.document import (
    Blob,
    DocStatus,
    DocType,
    Document,
    Page,
)
from pine.models.job import Job, JobKind, JobStatus
from pine.repos import deals as deals_repo
from pine.services.uploads import ingest_upload
from pine.storage.blobstore import BlobStore


def drain_jobs(session: Session, limit: int = 300) -> None:
    """Run every queued job synchronously until the queue is empty."""
    for _ in range(limit):
        job = session.scalar(
            select(Job)
            .where(Job.status == JobStatus.queued)
            .order_by(Job.created_at)
            .limit(1)
        )
        if job is None:
            return
        _HANDLERS[JobKind(job.kind)](session, job)
        job.status = JobStatus.succeeded
        session.commit()
    raise AssertionError("job queue did not drain")


def mk_deal(session: Session, name: str = "Acme Corp") -> Deal:
    return deals_repo.create_deal(
        session, DealCreate(name="D", company_name=name)
    )


def mk_document(
    session: Session, deal: Deal, filename: str, doc_type: DocType
) -> Document:
    blob = Blob(
        sha256=uuid.uuid4().hex, size_bytes=1, mime="text/plain", path=filename
    )
    session.add(blob)
    session.flush()
    doc = Document(
        deal_id=deal.id,
        blob_id=blob.id,
        filename=filename,
        path=filename,
        ext=filename.rsplit(".", 1)[-1],
        status=DocStatus.parsed,
        doc_type=doc_type,
    )
    session.add(doc)
    session.flush()
    return doc


def mk_chunk(
    session: Session,
    document: Document,
    text: str,
    *,
    page_no: int = 1,
    kind: ChunkKind = ChunkKind.prose,
) -> Chunk:
    page = Page(document_id=document.id, page_no=page_no, text=text)
    session.add(page)
    session.flush()
    chunk = Chunk(
        deal_id=document.deal_id,
        document_id=document.id,
        page_no=page_no,
        text=text,
        token_count=len(text) // 4,
        char_start=0,
        char_end=len(text),
        kind=kind,
        text_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    session.add(chunk)
    session.flush()
    return chunk


@pytest.fixture
def demo_deal(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Deal:
    """The built Northwind room ingested + fully parsed/classified/indexed."""
    storage = tmp_path / "storage"
    monkeypatch.setenv("STORAGE_DIR", str(storage))
    get_settings.cache_clear()
    room = build_demo(tmp_path / "room")
    deal = mk_deal(session, "Northwind")
    store = BlobStore(storage)
    files: list[tuple[str, bytes]] = []
    paths: list[str] = []
    for path in sorted(room.rglob("*")):
        if not path.is_file() or path.name == "ground_truth.json":
            continue
        files.append((path.name, path.read_bytes()))
        paths.append(path.relative_to(room).as_posix())
    ingest_upload(session, store, deal, files, paths)
    drain_jobs(session)
    return deal
