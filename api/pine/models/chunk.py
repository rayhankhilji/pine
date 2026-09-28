from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pine.db import Base
from pine.models.base import TimestampMixin, new_id


class ChunkKind(StrEnum):
    prose = "prose"
    table_rows = "table_rows"
    slide = "slide"
    email = "email"
    cells = "cells"


class Chunk(TimestampMixin, Base):
    """Retrieval unit (ARCHITECTURE §4).

    `char_start`/`char_end` are offsets into the concatenated text of the
    covered blocks for prose/slide/email chunks, and into the table-derived
    text (header + row lines joined by newlines) for table_rows chunks.
    `embedding` is a float32 little-endian vector of `embedding_dim` floats
    produced by `embedding_model`.
    """

    __tablename__ = "chunk"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deal.id"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document.id"), nullable=False, index=True
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    block_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[ChunkKind] = mapped_column(
        String(20), default=ChunkKind.prose, nullable=False
    )
    table_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("data_table.id"), nullable=True
    )
    row_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    __table_args__ = (
        Index("ix_chunk_deal_doc_page", "deal_id", "document_id", "page_no"),
    )
