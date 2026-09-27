"""Job handlers for the ingestion pipeline (ARCHITECTURE §9)."""

import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.config import get_settings
from pine.ingest.classify import classify_document
from pine.ingest.detect import detect_type
from pine.ingest.persist import persist_result
from pine.ingest.registry import get_parser
from pine.jobs.queue import enqueue
from pine.jobs.worker import job_handler
from pine.models.document import Blob, DocStatus, Document
from pine.models.job import Job, JobKind
from pine.storage.blobstore import BlobStore

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = (DocStatus.parsed, DocStatus.failed, DocStatus.unsupported)


def _store() -> BlobStore:
    return BlobStore(Path(get_settings().STORAGE_DIR))


def _maybe_enqueue_index(session: Session, deal_id: str) -> None:
    """When every document is terminal, enqueue index_deal (idempotent)."""
    pending = session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.deal_id == deal_id)
        .where(Document.status.notin_(TERMINAL_STATUSES))
    )
    if pending:
        return
    n_docs = session.scalar(
        select(func.count()).select_from(Document).where(Document.deal_id == deal_id)
    )
    enqueue(
        session,
        JobKind.index_deal,
        {"deal_id": deal_id},
        deal_id=deal_id,
        idempotency_key=f"index:{deal_id}:{n_docs}",
    )


@job_handler(JobKind.parse_document)
def parse_document(session: Session, job: Job) -> None:
    document = session.get(Document, job.payload["document_id"])
    if document is None:
        raise RuntimeError(f"document {job.payload['document_id']} not found")
    document.status = DocStatus.parsing
    session.flush()

    blob = session.get(Blob, document.blob_id)
    if blob is None:
        raise RuntimeError(f"blob {document.blob_id} not found")
    store = _store()
    data = store.get_bytes(blob)

    ext = detect_type(document.filename, data) or document.ext
    parser = get_parser(ext)
    if parser is None:
        document.status = DocStatus.unsupported
        session.flush()
        _maybe_enqueue_index(session, document.deal_id)
        return

    try:
        result = parser(data, document.filename)
        persist_result(session, store, document, result)
    except Exception as exc:
        document.status = DocStatus.failed
        document.error = f"{type(exc).__name__}: {exc}"
        session.flush()
        raise

    document.ext = ext
    document.status = DocStatus.parsed
    session.flush()

    enqueue(
        session,
        JobKind.classify_document,
        {"document_id": document.id},
        deal_id=document.deal_id,
        idempotency_key=f"classify:{document.id}",
    )
    _maybe_enqueue_index(session, document.deal_id)


@job_handler(JobKind.classify_document)
def classify_document_job(session: Session, job: Job) -> None:
    document = session.get(Document, job.payload["document_id"])
    if document is None:
        raise RuntimeError(f"document {job.payload['document_id']} not found")
    doc_type, confidence = classify_document(session, document)
    document.doc_type = doc_type
    document.meta = {**document.meta, "classify_confidence": confidence}


@job_handler(JobKind.index_deal)
def index_deal_stub(session: Session, job: Job) -> None:
    """Stub until P2 chunking/embedding lands."""
    logger.info("index_deal stub for deal %s", job.payload.get("deal_id"))
