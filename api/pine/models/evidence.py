"""Evidence model (ARCHITECTURE §4, ADR-003).

One `evidence` row is a pointer to a document/page plus a verbatim `quote`
that must be a whitespace-normalised substring of the referenced chunk or
cell text (validated in `pine/facts/store.py`). `target_kind`/`target_id`
are a polymorphic reference to the Fact/Entity/Relation/Claim it supports.

Deviation from §4: `target_kind`/`target_id` are nullable so that evidence
*stubs* can be created before their target exists (§10 agent tools return
pre-created evidence ids; `EvidenceStore.link_evidence` attaches them).
"""

from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pine.db import Base
from pine.models.base import TimestampMixin, new_id


class EvidenceTarget(StrEnum):
    fact = "fact"
    entity = "entity"
    relation = "relation"
    claim = "claim"


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deal.id"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document.id"), nullable=False, index=True
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("chunk.id"), nullable=True
    )
    cell_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cell.id"), nullable=True
    )
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    target_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "chunk_id IS NOT NULL OR cell_id IS NOT NULL",
            name="ck_evidence_chunk_or_cell",
        ),
        Index("ix_evidence_target", "target_kind", "target_id"),
    )
