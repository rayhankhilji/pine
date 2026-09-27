"""Pydantic response schemas for documents, pages, tables and jobs (§5)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from pine.models.document import BlockKind, DocStatus, DocType
from pine.models.job import JobKind, JobStatus


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    blob_id: str
    parent_document_id: str | None
    filename: str
    path: str
    ext: str
    doc_type: DocType
    status: DocStatus
    error: str | None
    page_count: int
    language: str | None
    doc_date: date | None
    meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SkippedFile(BaseModel):
    filename: str
    reason: str


class DocumentUpload(BaseModel):
    documents: list[Document]
    skipped: list[SkippedFile]


class PageSummary(BaseModel):
    page_no: int
    width: float
    height: float
    is_scanned: bool
    sheet_name: str | None


class TableSummary(BaseModel):
    id: str
    page_no: int
    order: int
    n_rows: int
    n_cols: int
    header_row: int | None
    sheet_name: str | None
    column_types: list[str]
    title: str | None


class DocumentDetail(Document):
    pages: list[PageSummary]
    tables: list[TableSummary]


class Block(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order: int
    kind: BlockKind
    text: str
    bbox: list[float] | None
    char_start: int | None
    char_end: int | None


class Table(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    page_id: str
    block_id: str | None
    order: int
    n_rows: int
    n_cols: int
    header_row: int | None
    sheet_name: str | None
    column_types: list[str]
    bbox: list[float] | None
    title: str | None


class Page(BaseModel):
    page_no: int
    width: float
    height: float
    is_scanned: bool
    sheet_name: str | None
    text: str
    blocks: list[Block]
    tables: list[Table]


class Cell(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    row: int
    col: int
    text: str
    value_num: Decimal | None
    value_date: date | None
    bbox: list[float] | None
    ref: str | None


class TableDetail(Table):
    # Dense matrix; positions with no stored cell are null.
    cells: list[list[Cell | None]]


class ReparseResponse(BaseModel):
    job_id: str


class Job(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str | None
    kind: JobKind
    payload: dict[str, Any]
    status: JobStatus
    attempts: int
    max_attempts: int
    run_after: datetime
    error: str | None
    idempotency_key: str | None
    created_at: datetime
    updated_at: datetime
