"""Document query helpers — deal-scoped, keyset cursor like repos/deals.py."""

import base64
from datetime import datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from pine.models.document import DocStatus, DocType, Document, Page, Table


def get_document(session: Session, document_id: str) -> Document | None:
    return session.get(Document, document_id)


def _encode_cursor(doc: Document) -> str:
    raw = f"{doc.created_at.isoformat()}|{doc.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at, doc_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(created_at), doc_id
    except (ValueError, IndexError):
        return None


def list_documents(
    session: Session,
    deal_id: str,
    *,
    status: DocStatus | None = None,
    doc_type: DocType | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Document], str | None]:
    stmt: Select[tuple[Document]] = (
        select(Document)
        .where(Document.deal_id == deal_id)
        .order_by(Document.created_at, Document.id)
    )
    if status is not None:
        stmt = stmt.where(Document.status == status)
    if doc_type is not None:
        stmt = stmt.where(Document.doc_type == doc_type)
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded is not None:
            created_at, doc_id = decoded
            stmt = stmt.where(
                or_(
                    Document.created_at > created_at,
                    (Document.created_at == created_at) & (Document.id > doc_id),
                )
            )
    items = list(session.scalars(stmt.limit(limit + 1)).all())
    next_cursor = _encode_cursor(items[limit - 1]) if len(items) > limit else None
    return items[:limit], next_cursor


def get_page(session: Session, document_id: str, page_no: int) -> Page | None:
    return session.scalar(
        select(Page)
        .where(Page.document_id == document_id)
        .where(Page.page_no == page_no)
    )


def document_statuses(session: Session, deal_id: str) -> dict[str, str]:
    """document_id -> status for every document of a deal (for SSE diffing)."""
    rows = session.execute(
        select(Document.id, Document.status).where(Document.deal_id == deal_id)
    ).all()
    return {doc_id: str(status) for doc_id, status in rows}


def table_with_page(session: Session, table_id: str) -> tuple[Table, Page] | None:
    row = session.execute(
        select(Table, Page).join(Page, Table.page_id == Page.id).where(Table.id == table_id)
    ).first()
    return (row[0], row[1]) if row else None
