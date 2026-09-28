"""Unit and period vocabularies (ARCHITECTURE §4)."""

from enum import StrEnum

# Functional syntax: a class-body member named `count` would shadow
# `str.count` and fail mypy strict.
Unit = StrEnum(
    "Unit", ["currency", "percent", "count", "months", "ratio", "text"]
)


class PeriodType(StrEnum):
    point = "point"
    month = "month"
    quarter = "quarter"
    fiscal_year = "fiscal_year"
    ttm = "ttm"
    custom = "custom"
