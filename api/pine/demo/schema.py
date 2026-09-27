"""Ground-truth schema for the synthetic demo data room (PRD F-14)."""

from datetime import date

from pydantic import BaseModel, Field


class Period(BaseModel):
    type: str  # point | month | quarter | fiscal_year | ttm | custom
    start: date | None = None
    end: date | None = None


class GroundTruthFact(BaseModel):
    metric: str
    value: int | float
    unit: str  # currency | percent | count | months | ratio | text
    currency: str | None = None
    period: Period
    source_file: str
    tolerance_pct: float = 0.0


class GroundTruthContradiction(BaseModel):
    rule_id: str
    metric: str
    expected_values: list[int | float]
    min_severity: str


class GroundTruthEntity(BaseModel):
    type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)


class GroundTruth(BaseModel):
    facts: list[GroundTruthFact]
    contradictions: list[GroundTruthContradiction]
    entities: list[GroundTruthEntity]
