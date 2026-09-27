"""Document endpoints (ARCHITECTURE §5). Routers hold no business logic."""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response as RawResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.api.schemas.document import (
    Block,
    Document,
    DocumentDetail,
    DocumentUpload,
    Page,
    PageSummary,
    ReparseResponse,
    Table,
    TableSummary,
)
from pine.config import get_settings
from pine.db import get_session
from pine.errors import AppError
from pine.models.deal import Deal as DealModel
from pine.models.document import (
    Blob,
    DocStatus,
    DocType,
)
from pine.models.document import (
    Block as BlockModel,
)
from pine.models.document import (
    Document as DocumentModel,
)
from pine.models.document import (
    Page as PageModel,
)
from pine.models.document import (
    Table as TableModel,
)
from pine.repos import deals as deals_repo
from pine.repos import documents as docs_repo
from pine.services.uploads import ingest_upload
from pine.storage.blobstore import BlobStore

router = APIRouter(tags=["documents"])

IMAGE_EXTS = {"png", "jpg", "jpeg"}


def _store() -> BlobStore:
    return BlobStore(Path(get_settings().STORAGE_DIR))


def _deal_or_404(session: Session, deal_id: str) -> DealModel:
    deal = deals_repo.get_deal(session, deal_id)
    if deal is None:
        raise AppError("NOT_FOUND", "Deal not found", status=404)
    return deal


def _get_doc_or_404(session: Session, document_id: str) -> DocumentModel:
    doc = docs_repo.get_document(session, document_id)
    if doc is None:
        raise AppError("NOT_FOUND", "Document not found", status=404)
    return doc


def _blob_bytes(session: Session, doc: DocumentModel) -> tuple[Blob, bytes]:
    blob = session.get(Blob, doc.blob_id)
    if blob is None:
        raise AppError("NOT_FOUND", "Document blob missing", status=404)
    return blob, _store().get_bytes(blob)


@router.post(
    "/deals/{deal_id}/documents", status_code=status.HTTP_201_CREATED
)
async def upload_documents(
    deal_id: str,
    session: Annotated[Session, Depends(get_session)],
    files: Annotated[list[UploadFile], File()],
    paths: Annotated[list[str] | None, Form()] = None,
) -> DocumentUpload:
    deal = _deal_or_404(session, deal_id)
    raw = [(f.filename or "file", await f.read()) for f in files]
    result = ingest_upload(session, _store(), deal, raw, paths or [])
    return DocumentUpload(
        documents=[Document.model_validate(d) for d in result.documents],
        skipped=result.skipped,
    )


@router.get("/deals/{deal_id}/documents")
def list_documents(
    deal_id: str,
    session: Annotated[Session, Depends(get_session)],
    status: Annotated[DocStatus | None, Query()] = None,
    doc_type: Annotated[DocType | None, Query()] = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    _deal_or_404(session, deal_id)
    items, next_cursor = docs_repo.list_documents(
        session, deal_id, status=status, doc_type=doc_type, cursor=cursor, limit=limit
    )
    return {
        "items": [Document.model_validate(d).model_dump(mode="json") for d in items],
        "next_cursor": next_cursor,
    }


@router.get("/documents/{document_id}")
def get_document(
    document_id: str, session: Annotated[Session, Depends(get_session)]
) -> DocumentDetail:
    doc = _get_doc_or_404(session, document_id)
    pages = session.scalars(
        select(PageModel)
        .where(PageModel.document_id == doc.id)
        .order_by(PageModel.page_no)
    ).all()
    table_rows = session.execute(
        select(TableModel, PageModel.page_no)
        .join(PageModel, TableModel.page_id == PageModel.id)
        .where(PageModel.document_id == doc.id)
        .order_by(PageModel.page_no, TableModel.order)
    ).all()
    return DocumentDetail(
        **Document.model_validate(doc).model_dump(),
        pages=[
            PageSummary(
                page_no=p.page_no,
                width=p.width,
                height=p.height,
                is_scanned=p.is_scanned,
                sheet_name=p.sheet_name,
            )
            for p in pages
        ],
        tables=[
            TableSummary(
                id=t.id,
                page_no=page_no,
                order=t.order,
                n_rows=t.n_rows,
                n_cols=t.n_cols,
                header_row=t.header_row,
                sheet_name=t.sheet_name,
                column_types=list(t.column_types),
                title=t.title,
            )
            for t, page_no in table_rows
        ],
    )


@router.get("/documents/{document_id}/pages/{page_no}")
def get_page(
    document_id: str,
    page_no: int,
    session: Annotated[Session, Depends(get_session)],
) -> Page:
    doc = _get_doc_or_404(session, document_id)
    page = docs_repo.get_page(session, doc.id, page_no)
    if page is None:
        raise AppError("NOT_FOUND", "Page not found", status=404)
    blocks = session.scalars(
        select(BlockModel).where(BlockModel.page_id == page.id).order_by(BlockModel.order)
    ).all()
    tables = session.scalars(
        select(TableModel).where(TableModel.page_id == page.id).order_by(TableModel.order)
    ).all()
    return Page(
        page_no=page.page_no,
        width=page.width,
        height=page.height,
        is_scanned=page.is_scanned,
        sheet_name=page.sheet_name,
        text=page.text,
        blocks=[Block.model_validate(b) for b in blocks],
        tables=[Table.model_validate(t) for t in tables],
    )


@router.get("/documents/{document_id}/render/{page_no}")
def render_page(
    document_id: str,
    page_no: int,
    session: Annotated[Session, Depends(get_session)],
    scale: float = Query(default=1.5, gt=0.1, le=6.0),
) -> RawResponse:
    doc = _get_doc_or_404(session, document_id)
    _blob, data = _blob_bytes(session, doc)

    if doc.ext == "pdf":
        import pymupdf

        pdf = pymupdf.open(stream=data, filetype="pdf")
        try:
            if page_no < 1 or page_no > pdf.page_count:
                raise AppError("NOT_FOUND", "Page not found", status=404)
            page = pdf.load_page(page_no - 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
            return RawResponse(content=pix.tobytes("png"), media_type="image/png")
        finally:
            pdf.close()
    if doc.ext in IMAGE_EXTS:
        return RawResponse(content=data, media_type=f"image/{doc.ext}")
    raise AppError(
        "UNSUPPORTED_TYPE", f"Rendering {doc.ext} documents is not supported", status=415
    )


@router.get("/documents/{document_id}/file")
def download_file(
    document_id: str, session: Annotated[Session, Depends(get_session)]
) -> RawResponse:
    doc = _get_doc_or_404(session, document_id)
    blob, data = _blob_bytes(session, doc)
    from urllib.parse import quote

    disposition = f"attachment; filename*=UTF-8''{quote(doc.filename)}"
    return RawResponse(
        content=data,
        media_type=blob.mime or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


@router.post(
    "/documents/{document_id}/reparse", status_code=status.HTTP_202_ACCEPTED
)
def reparse_document(
    document_id: str, session: Annotated[Session, Depends(get_session)]
) -> ReparseResponse:
    from pine.jobs.queue import enqueue
    from pine.models.job import JobKind

    doc = _get_doc_or_404(session, document_id)
    doc.status = DocStatus.queued
    doc.error = None
    job = enqueue(
        session,
        JobKind.parse_document,
        {"document_id": doc.id},
        deal_id=doc.deal_id,
        idempotency_key=f"reparse:{doc.id}:{uuid.uuid4().hex[:8]}",
    )
    session.commit()
    return ReparseResponse(job_id=job.id)
