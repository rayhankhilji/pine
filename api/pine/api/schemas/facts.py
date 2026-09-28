"""Pydantic response/request schemas for facts and evidence (§5, F-05)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from pine.models.fact import ExtractionMethod
from pine.schemas.units import PeriodType, Unit


class Evidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    document_id: str
    page_no: int
    chunk_id: str | None
    cell_id: str | None
    char_start: int | None
    char_end: int | None
    quote: str
    bbox: list[float] | None
    target_kind: str | None
    target_id: str | None
    created_at: datetime
    # populated by the serializer (Evidence rows carry no filename)
    filename: str | None = None


class Fact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deal_id: str
    subject_entity_id: str
    metric: str
    value: Decimal | None
    value_text: str | None
    unit: Unit
    currency: str | None
    period_type: PeriodType
    period_start: date | None
    period_end: date | None
    as_of: date | None
    # DocType at write time, but derived facts carry "derived" — keep it a
    # plain string so serialisation never rejects a stored row
    source_kind: str
    extraction_method: ExtractionMethod
    confidence: float
    is_authoritative: bool
    superseded_by_id: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    evidence: list[Evidence] = []
    contested: bool = False  # placeholder until P4 contradictions land


class ContradictionSummary(BaseModel):
    """Placeholder shape for the P4 Contradiction engine (§5)."""

    id: str
    rule_id: str
    metric: str | None
    severity: str
    status: str


class FactDetail(Fact):
    derived_from: list[Fact] = []
    contradictions: list[ContradictionSummary] = []


class FactPatch(BaseModel):
    # `value` (and any other extra key) is rejected with 422 VALIDATION —
    # value corrections arrive as manual facts via a later phase.
    model_config = ConfigDict(extra="forbid")

    notes: str | None = None
    is_authoritative: bool | None = None


class FactPage(BaseModel):
    items: list[Fact]
    next_cursor: str | None
