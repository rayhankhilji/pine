"""PeriodSpec parsing, formatting round-trips and comparability (P3.T3)."""

from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pine.facts.periods import (
    PeriodSpec,
    comparable,
    fiscal_quarter_bounds,
    fiscal_year_bounds,
    format_period,
    parse_period,
    quarter_of,
    ttm_bounds,
)
from pine.schemas.units import PeriodType

# ----------------------------------------------------------------------
# explicit formats


@pytest.mark.parametrize(
    ("text", "ptype", "start", "end", "as_of"),
    [
        ("FY2024", "fiscal_year", "2024-01-01", "2024-12-31", None),
        ("FY24", "fiscal_year", "2024-01-01", "2024-12-31", None),
        ("FY 2024", "fiscal_year", "2024-01-01", "2024-12-31", None),
        ("Q4 2025", "quarter", "2025-10-01", "2025-12-31", None),
        ("Q4'25", "quarter", "2025-10-01", "2025-12-31", None),
        ("4Q25", "quarter", "2025-10-01", "2025-12-31", None),
        ("Q1 FY2026", "quarter", "2026-01-01", "2026-03-31", None),
        ("Dec-25", "month", "2025-12-01", "2025-12-31", None),
        ("December 2025", "month", "2025-12-01", "2025-12-31", None),
        ("2025-12", "month", "2025-12-01", "2025-12-31", None),
        ("TTM Mar 2026", "ttm", "2025-04-01", "2026-03-31", None),
        ("TTM December 2025", "ttm", "2025-01-01", "2025-12-31", None),
        ("2025", "fiscal_year", "2025-01-01", "2025-12-31", None),
        ("as of 31 Dec 2025", "point", "2025-12-31", "2025-12-31", "2025-12-31"),
        ("as of December 31, 2025", "point", "2025-12-31", "2025-12-31", "2025-12-31"),
        ("2025-12-31", "point", "2025-12-31", "2025-12-31", "2025-12-31"),
        ("31 December 2025", "point", "2025-12-31", "2025-12-31", "2025-12-31"),
        (
            "2025-01-01 to 2027-12-31",
            "custom",
            "2025-01-01",
            "2027-12-31",
            None,
        ),
    ],
)
def test_parse_formats(
    text: str, ptype: str, start: str, end: str, as_of: str | None
) -> None:
    spec = parse_period(text)
    assert spec is not None, text
    assert spec.period_type == ptype
    assert spec.period_start == date.fromisoformat(start)
    assert spec.period_end == date.fromisoformat(end)
    assert spec.as_of == (date.fromisoformat(as_of) if as_of else None)


def test_parse_bare_ltm() -> None:
    spec = parse_period("LTM")
    assert spec is not None
    assert spec.period_type == PeriodType.ttm
    assert spec.period_start is None


def test_parse_none() -> None:
    assert parse_period("no period here") is None
    assert parse_period("") is None


def test_parse_embedded_in_sentence() -> None:
    spec = parse_period("ARR reached $12.0M in Q4 2025, up 3x YoY")
    assert spec is not None
    assert spec.period_type == PeriodType.quarter
    assert spec.period_start == date(2025, 10, 1)
    assert spec.period_end == date(2025, 12, 31)


# ----------------------------------------------------------------------
# fiscal calendars


def test_fiscal_year_june_fye() -> None:
    spec = parse_period("FY2025", fiscal_year_end_month=6)
    assert spec is not None
    assert spec.period_start == date(2024, 7, 1)
    assert spec.period_end == date(2025, 6, 30)


def test_fiscal_quarters_follow_fye() -> None:
    q1 = parse_period("Q1 2025", fiscal_year_end_month=6)
    q4 = parse_period("Q4 2025", fiscal_year_end_month=6)
    assert q1 is not None and q4 is not None
    assert (q1.period_start, q1.period_end) == (date(2024, 7, 1), date(2024, 9, 30))
    assert (q4.period_start, q4.period_end) == (date(2025, 4, 1), date(2025, 6, 30))


def test_quarter_of_calendar_fye() -> None:
    assert quarter_of(date(2025, 10, 15), 12) == (2025, 4)
    assert quarter_of(date(2025, 4, 15), 6) == (2025, 4)
    assert quarter_of(date(2025, 8, 15), 6) == (2026, 1)


def test_ttm_bounds() -> None:
    assert ttm_bounds(date(2026, 3, 15)) == (date(2025, 4, 1), date(2026, 3, 31))


# ----------------------------------------------------------------------
# hypothesis: format ∘ parse round-trips

_YEARS = st.integers(min_value=1990, max_value=2099)
_FYES = st.integers(min_value=1, max_value=12)


@given(year=_YEARS, fye=_FYES)
@settings(max_examples=200)
def test_fy_round_trip(year: int, fye: int) -> None:
    spec = parse_period(f"FY{year}", fiscal_year_end_month=fye)
    assert spec is not None
    assert spec.period_type == PeriodType.fiscal_year
    assert (spec.period_start, spec.period_end) == fiscal_year_bounds(year, fye)
    reparsed = parse_period(format_period(spec, fye), fye)
    assert reparsed == spec


@given(year=_YEARS, quarter=st.integers(min_value=1, max_value=4), fye=_FYES)
@settings(max_examples=200)
def test_quarter_round_trip(year: int, quarter: int, fye: int) -> None:
    spec = parse_period(f"Q{quarter} {year}", fiscal_year_end_month=fye)
    assert spec is not None
    assert spec.period_type == PeriodType.quarter
    assert (spec.period_start, spec.period_end) == fiscal_quarter_bounds(
        year, quarter, fye
    )
    reparsed = parse_period(format_period(spec, fye), fye)
    assert reparsed == spec


@given(day=st.dates(min_value=date(1990, 1, 1), max_value=date(2099, 12, 31)))
@settings(max_examples=200)
def test_point_round_trip(day: date) -> None:
    spec = parse_period(day.isoformat())
    assert spec is not None
    assert spec.period_type == PeriodType.point
    assert spec.as_of == day
    reparsed = parse_period(format_period(spec))
    assert reparsed == spec


@given(
    year=_YEARS,
    month=st.integers(min_value=1, max_value=12),
)
@settings(max_examples=200)
def test_month_round_trip(year: int, month: int) -> None:
    spec = parse_period(f"{year}-{month:02d}")
    assert spec is not None
    assert spec.period_type == PeriodType.month
    assert spec.period_start == date(year, month, 1)
    reparsed = parse_period(format_period(spec))
    assert reparsed is not None
    assert reparsed.period_type == PeriodType.month
    assert reparsed.period_start == spec.period_start
    assert reparsed.period_end == spec.period_end


@given(
    year=_YEARS,
    month=st.integers(min_value=1, max_value=12),
)
@settings(max_examples=100)
def test_ttm_round_trip(year: int, month: int) -> None:
    spec = parse_period(f"TTM {format_month(year, month)}")
    assert spec is not None
    assert spec.period_type == PeriodType.ttm
    reparsed = parse_period(format_period(spec))
    assert reparsed == spec


def format_month(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%b %Y")


# ----------------------------------------------------------------------
# comparability


def _spec(ptype: str, start: str, end: str) -> PeriodSpec:
    return PeriodSpec(
        period_type=PeriodType(ptype),
        period_start=date.fromisoformat(start),
        period_end=date.fromisoformat(end),
    )


def test_comparable_same_fy() -> None:
    assert comparable(_spec("fiscal_year", "2025-01-01", "2025-12-31"),
                      _spec("fiscal_year", "2025-01-01", "2025-12-31"))


def test_comparable_quarter_inside_fy() -> None:
    fy = _spec("fiscal_year", "2025-01-01", "2025-12-31")
    q4 = _spec("quarter", "2025-10-01", "2025-12-31")
    # overlap = 92 days, shorter = 92 → comparable
    assert comparable(fy, q4)
    assert comparable(q4, fy)


def test_comparable_ttm_vs_fy() -> None:
    ttm = _spec("ttm", "2025-04-01", "2026-03-31")
    fy25 = _spec("fiscal_year", "2025-01-01", "2025-12-31")
    fy26 = _spec("fiscal_year", "2026-01-01", "2026-12-31")
    assert comparable(ttm, fy25)  # overlap 275 ≥ 183
    assert not comparable(ttm, fy26)  # overlap 90 < 183


def test_comparable_disjoint() -> None:
    fy24 = _spec("fiscal_year", "2024-01-01", "2024-12-31")
    fy26 = _spec("fiscal_year", "2026-01-01", "2026-12-31")
    assert not comparable(fy24, fy26)


def test_comparable_point_facts() -> None:
    a = PeriodSpec(period_type=PeriodType.point, as_of=date(2025, 12, 31),
                   period_start=date(2025, 12, 31), period_end=date(2025, 12, 31))
    near = PeriodSpec(period_type=PeriodType.point, as_of=date(2026, 1, 20),
                      period_start=date(2026, 1, 20), period_end=date(2026, 1, 20))
    far = PeriodSpec(period_type=PeriodType.point, as_of=date(2026, 3, 1),
                     period_start=date(2026, 3, 1), period_end=date(2026, 3, 1))
    assert comparable(a, near)
    assert not comparable(a, far)


def test_comparable_missing_period() -> None:
    empty = PeriodSpec(period_type=PeriodType.ttm)
    fy = _spec("fiscal_year", "2025-01-01", "2025-12-31")
    assert not comparable(empty, fy)


@given(
    start_a=st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 1, 1)),
    len_a=st.integers(min_value=0, max_value=800),
    start_b=st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 1, 1)),
    len_b=st.integers(min_value=0, max_value=800),
)
@settings(max_examples=300)
def test_comparable_symmetric(
    start_a: date, len_a: int, start_b: date, len_b: int
) -> None:
    a = _spec("custom", start_a.isoformat(), (start_a + timedelta(days=len_a)).isoformat())
    b = _spec("custom", start_b.isoformat(), (start_b + timedelta(days=len_b)).isoformat())
    assert comparable(a, b) == comparable(b, a)


@given(text=st.text())
@settings(max_examples=500)
def test_parse_never_crashes(text: str) -> None:
    spec = parse_period(text)
    if spec is not None and spec.period_start and spec.period_end:
        assert spec.period_start <= spec.period_end
