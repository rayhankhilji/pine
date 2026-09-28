"""Job handlers for the ingestion pipeline (ARCHITECTURE §9)."""

from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pine.config import get_settings
from pine.ingest.classify import classify_document
from pine.ingest.detect import detect_type
from pine.ingest.persist import persist_result
from pine.ingest.registry import get_parser
from pine.ingest.types import ParseResult
from pine.jobs.queue import enqueue
from pine.jobs.worker import job_handler
from pine.models.document import Blob, Block, Cell, DocStatus, Document, Page, Table
from pine.models.job import Job, JobKind
from pine.storage.blobstore import BlobStore

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


def _clear_parse_output(session: Session, document_id: str) -> None:
    """Delete prior Page/Block/Table/Cell rows so a reparse starts clean."""
    page_ids = [
        row[0]
        for row in session.execute(
            select(Page.id).where(Page.document_id == document_id)
        ).all()
    ]
    if not page_ids:
        return
    table_ids = [
        row[0]
        for row in session.execute(
            select(Table.id).where(Table.page_id.in_(page_ids))
        ).all()
    ]
    if table_ids:
        session.execute(delete(Cell).where(Cell.table_id.in_(table_ids)))
        session.execute(delete(Table).where(Table.id.in_(table_ids)))
    session.execute(delete(Block).where(Block.page_id.in_(page_ids)))
    session.execute(delete(Page).where(Page.id.in_(page_ids)))


@job_handler(JobKind.parse_document)
def parse_document(session: Session, job: Job) -> None:
    # txn 1 (short): mark parsing + read blob bytes, then release the write
    # lock so concurrent writers/readers are not stalled during parsing.
    document = session.get(Document, job.payload["document_id"])
    if document is None:
        raise RuntimeError(f"document {job.payload['document_id']} not found")
    document.status = DocStatus.parsing
    document.error = None
    blob = session.get(Blob, document.blob_id)
    if blob is None:
        raise RuntimeError(f"blob {document.blob_id} not found")
    store = _store()
    data = store.get_bytes(blob)
    filename = document.filename
    deal_id = document.deal_id
    session.commit()

    ext = detect_type(filename, data) or document.ext
    parser = get_parser(ext)
    if parser is None:
        document.status = DocStatus.unsupported
        session.commit()
        _maybe_enqueue_index(session, deal_id)
        return

    # parse outside the transaction — parsers are pure CPU/IO
    result: ParseResult | None = None
    parse_error: Exception | None = None
    try:
        result = parser(data, filename)
    except Exception as exc:  # noqa: BLE001 — recorded on the document below
        parse_error = exc

    # txn 2 (short): persist parse output and enqueue follow-ups
    if parse_error is not None:
        document.status = DocStatus.failed
        document.error = f"{type(parse_error).__name__}: {parse_error}"
        session.commit()
        raise parse_error

    assert result is not None
    _clear_parse_output(session, document.id)
    persist_result(session, store, document, result)
    document.ext = ext
    document.status = DocStatus.parsed
    # clear the index stamp — freshly parsed text is not in the index
    document.meta = {k: v for k, v in document.meta.items() if k != "indexed"}
    enqueue(
        session,
        JobKind.classify_document,
        {"document_id": document.id},
        deal_id=deal_id,
        idempotency_key=f"classify:{document.id}",
    )
    _maybe_enqueue_index(session, deal_id)
    session.commit()


@job_handler(JobKind.classify_document)
def classify_document_job(session: Session, job: Job) -> None:
    document = session.get(Document, job.payload["document_id"])
    if document is None:
        raise RuntimeError(f"document {job.payload['document_id']} not found")
    doc_type, confidence = classify_document(session, document)
    document.doc_type = doc_type
    document.meta = {**document.meta, "classify_confidence": confidence}
