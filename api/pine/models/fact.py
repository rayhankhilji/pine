"""Fact / FactLink models (ARCHITECTURE §4, F-05).

Every Fact is written through `EvidenceStore.add_fact`: non-derived facts
require ≥ 1 Evidence row; derived facts require ≥ 1 FactLink to a parent.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pine.db import Base
from pine.models.base import TimestampMixin, new_id


class ExtractionMethod(StrEnum):
    table = "table"
    llm = "llm"
    derived = "derived"
    manual = "manual"


class Fact(TimestampMixin, Base):
    __tablename__ = "fact"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deal.id"), nullable=False, index=True
    )
    subject_entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entity.id"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_authoritative: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    superseded_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("fact.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_fact_deal_metric_period",
            "deal_id",
            "metric",
            "period_start",
            "period_end",
        ),
    )


class FactLink(TimestampMixin, Base):
    __tablename__ = "fact_link"

    fact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fact.id"), primary_key=True
    )
    parent_fact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fact.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)
