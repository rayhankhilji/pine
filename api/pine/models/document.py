from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pine.db import Base
from pine.models.base import TimestampMixin, new_id


class DocType(StrEnum):
    deck = "deck"
    financial_statement = "financial_statement"
    bank_statement = "bank_statement"
    customer_list = "customer_list"
    contract = "contract"
    cap_table = "cap_table"
    board_deck = "board_deck"
    email = "email"
    legal = "legal"
    other = "other"
    unknown = "unknown"


class DocStatus(StrEnum):
    queued = "queued"
    parsing = "parsing"
    parsed = "parsed"
    failed = "failed"
    unsupported = "unsupported"


class BlockKind(StrEnum):
    heading = "heading"
    paragraph = "paragraph"
    list_item = "list_item"
    table = "table"
    figure = "figure"
    caption = "caption"
    header = "header"
    footer = "footer"
    slide_note = "slide_note"


class Blob(TimestampMixin, Base):
    __tablename__ = "blob"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(String(120), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)


class Document(TimestampMixin, Base):
    __tablename__ = "document"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deal.id"), nullable=False, index=True
    )
    blob_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blob.id"), nullable=False
    )
    parent_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document.id"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    ext: Mapped[str] = mapped_column(String(10), nullable=False)
    doc_type: Mapped[DocType] = mapped_column(
        String(30), default=DocType.unknown, nullable=False
    )
    status: Mapped[DocStatus] = mapped_column(
        String(20), default=DocStatus.queued, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("deal_id", "blob_id", "path", name="uq_document_deal_blob_path"),
        Index("ix_document_deal_status", "deal_id", "status"),
        Index("ix_document_deal_doc_type", "deal_id", "doc_type"),
    )


class Page(TimestampMixin, Base):
    __tablename__ = "page"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document.id"), nullable=False, index=True
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float] = mapped_column(nullable=False, default=0.0)
    height: Mapped[float] = mapped_column(nullable=False, default=0.0)
    is_scanned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("document_id", "page_no", name="uq_page_document_no"),
    )


class Block(TimestampMixin, Base):
    __tablename__ = "block"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    page_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("page.id"), nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[BlockKind] = mapped_column(
        String(20), default=BlockKind.paragraph, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("page_id", "order", name="uq_block_page_order"),
    )


class Table(TimestampMixin, Base):
    __tablename__ = "data_table"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    page_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("page.id"), nullable=False, index=True
    )
    block_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("block.id"), nullable=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_cols: Mapped[int] = mapped_column(Integer, nullable=False)
    header_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    column_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)


class Cell(TimestampMixin, Base):
    __tablename__ = "cell"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("data_table.id"), nullable=False, index=True
    )
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    col: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    ref: Mapped[str | None] = mapped_column(String(12), nullable=True)

    __table_args__ = (
        UniqueConstraint("table_id", "row", "col", name="uq_cell_table_row_col"),
    )
