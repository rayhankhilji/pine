from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from pine.models.deal import DealStage


class DealCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=200)
    stage: DealStage = DealStage.series_b
    currency: str = Field(default="USD", min_length=3, max_length=3)
    fiscal_year_end_month: int = Field(default=12, ge=1, le=12)
    proposed_round_usd: Decimal | None = None
    proposed_pre_money_usd: Decimal | None = None


class DealUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    stage: DealStage | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fiscal_year_end_month: int | None = Field(default=None, ge=1, le=12)
    proposed_round_usd: Decimal | None = None
    proposed_pre_money_usd: Decimal | None = None


class Deal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    company_name: str
    stage: DealStage
    currency: str
    fiscal_year_end_month: int
    proposed_round_usd: Decimal | None
    proposed_pre_money_usd: Decimal | None
    created_at: datetime
    updated_at: datetime


class DealSummary(Deal):
    document_count: int = 0
    last_run_status: str | None = None
    open_contradictions: int = 0
