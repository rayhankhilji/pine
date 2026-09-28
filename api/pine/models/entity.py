"""Entity / EntityAlias / Relation models (ARCHITECTURE §4, F-04)."""

from typing import Any

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pine.db import Base
from pine.models.base import TimestampMixin, new_id


class Entity(TimestampMixin, Base):
    __tablename__ = "entity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deal.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(300), nullable=False, index=True
    )
    attrs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    merged_into_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("entity.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_entity_deal_type_name",
            "deal_id",
            "type",
            "normalized_name",
            unique=True,
            sqlite_where=text("merged_into_id IS NULL"),
            postgresql_where=text("merged_into_id IS NULL"),
        ),
    )


class EntityAlias(TimestampMixin, Base):
    __tablename__ = "entity_alias"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entity.id"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized: Mapped[str] = mapped_column(String(300), nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document.id"), nullable=True
    )


class Relation(TimestampMixin, Base):
    __tablename__ = "relation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deal.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entity.id"), nullable=False, index=True
    )
    target_entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entity.id"), nullable=False, index=True
    )
    attrs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "type",
            "source_entity_id",
            "target_entity_id",
            name="uq_relation_type_src_tgt",
        ),
    )
