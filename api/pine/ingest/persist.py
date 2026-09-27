"""Persist a ParseResult into Page/Block/Table/Cell rows + attachment Documents."""

import logging

from sqlalchemy.orm import Session

from pine.ingest.detect import detect_type, ext_of, mime_for
from pine.ingest.types import ParseResult
from pine.jobs.queue import enqueue
from pine.models.document import (
    Block,
    Cell,
    DocStatus,
    Document,
    Page,
    Table,
)
from pine.models.job import JobKind
from pine.storage.blobstore import BlobStore

logger = logging.getLogger(__name__)


def persist_result(
    session: Session,
    store: BlobStore,
    document: Document,
    result: ParseResult,
) -> None:
    for p in result.pages:
        page = Page(
            document_id=document.id,
            page_no=p.page_no,
            width=p.width,
            height=p.height,
            is_scanned=p.is_scanned,
            sheet_name=p.sheet_name,
            text=p.text,
        )
        session.add(page)
        session.flush()
        block_ids: list[str] = []
        for b in p.blocks:
            block = Block(
                page_id=page.id,
                order=b.order,
                kind=b.kind,
                text=b.text,
                bbox=b.bbox,
                char_start=b.char_start,
                char_end=b.char_end,
            )
            session.add(block)
            session.flush()
            block_ids.append(block.id)
        for t in p.tables:
            table = Table(
                page_id=page.id,
                block_id=block_ids[t.order] if t.order < len(block_ids) else None,
                order=t.order,
                n_rows=t.n_rows,
                n_cols=t.n_cols,
                header_row=t.header_row,
                sheet_name=t.sheet_name,
                column_types=t.column_types,
                bbox=t.bbox,
                title=t.title,
            )
            session.add(table)
            session.flush()
            for c in t.cells:
                session.add(
                    Cell(
                        table_id=table.id,
                        row=c.row,
                        col=c.col,
                        text=c.text,
                        value_num=c.value_num,
                        value_date=c.value_date,
                        bbox=c.bbox,
                        ref=c.ref,
                    )
                )

    document.page_count = len(result.pages)
    document.meta = {**document.meta, **result.meta}
    if result.language:
        document.language = result.language
    if result.doc_date:
        document.doc_date = result.doc_date

    for att in result.attachments:
        ext = detect_type(att.filename, att.data) or ext_of(att.filename)
        if not ext:
            logger.info("skipping unrecognised attachment %s", att.filename)
            continue
        blob = store.put(session, att.data, att.filename)
        blob.mime = mime_for(ext)
        child = Document(
            deal_id=document.deal_id,
            blob_id=blob.id,
            parent_document_id=document.id,
            filename=att.filename,
            path=att.path or att.filename,
            ext=ext,
            status=DocStatus.queued,
        )
        session.add(child)
        session.flush()
        enqueue(
            session,
            JobKind.parse_document,
            {"document_id": child.id},
            deal_id=document.deal_id,
            idempotency_key=f"parse:{child.id}",
        )
