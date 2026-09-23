from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from pine.db import Base
from pine.models.base import TimestampMixin, new_id


class DealStage(StrEnum):
    seed = "seed"
    series_a = "series_a"
    series_b = "series_b"
    growth = "growth"
    buyout = "buyout"
    other = "other"


class Deal(TimestampMixin, Base):
    __tablename__ = "deal"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[DealStage] = mapped_column(
        String(20), default=DealStage.series_b, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    fiscal_year_end_month: Mapped[int] = mapped_column(default=12, nullable=False)
    proposed_round_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    proposed_pre_money_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
