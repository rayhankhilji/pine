"""Period parsing and comparability (ARCHITECTURE §10, F-05).

`parse_period` turns the period labels found in financial documents —
"FY2025", "Q4'25", "4Q25", "Dec-25", "December 2025", "2025-12",
"TTM Mar 2026", "LTM", bare "2025", "as of 31 Dec 2025" — into a
`PeriodSpec` of concrete dates.

Fiscal calendars follow the deal's `fiscal_year_end_month` (FYE): the fiscal
year is named by the calendar year it *ends* in, so FYE=6 → FY2025 covers
2024-07-01..2025-06-30 and fiscal quarters are numbered from the FY start
(FYE=6 → Q1 = Jul–Sep). FYE=12 makes fiscal == calendar.

`comparable` decides whether two facts' periods describe the same interval
closely enough to be compared (contradiction engine, P4).
"""

import calendar
import re
from datetime import date, timedelta
from typing import Protocol

from pydantic import BaseModel

from pine.schemas.units import PeriodType


class PeriodSpec(BaseModel):
    """A parsed period label resolved to concrete (inclusive) dates."""

    period_type: PeriodType
    period_start: date | None = None
    period_end: date | None = None
    as_of: date | None = None


class PeriodLike(Protocol):
    """Structural type shared by PeriodSpec and the Fact ORM row.

    Read-only properties so a `StrEnum`-typed `period_type` (PeriodSpec) and
    a plain `str` column (Fact) both satisfy the protocol.
    """

    @property
    def period_type(self) -> str: ...
    @property
    def period_start(self) -> date | None: ...
    @property
    def period_end(self) -> date | None: ...
    @property
    def as_of(self) -> date | None: ...


# ---------------------------------------------------------------------------
# date arithmetic


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, _last_day(year, month))


def _add_months(day: date, months: int) -> date:
    """Shift a first-of-month date by `months`; result stays first-of-month."""
    total = (day.year * 12 + day.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def fiscal_year_bounds(fy_year: int, fye: int = 12) -> tuple[date, date]:
    """Inclusive start/end of the fiscal year ending in calendar `fy_year`."""
    if fye == 12:
        return date(fy_year, 1, 1), date(fy_year, 12, 31)
    return date(fy_year - 1, fye + 1, 1), date(fy_year, fye, _last_day(fy_year, fye))


def fiscal_quarter_bounds(
    fy_year: int, quarter: int, fye: int = 12
) -> tuple[date, date]:
    """Inclusive start/end of fiscal quarter `quarter` (1–4) of FY `fy_year`."""
    if not 1 <= quarter <= 4:
        raise ValueError(f"quarter must be 1–4, got {quarter}")
    fy_start, _ = fiscal_year_bounds(fy_year, fye)
    start = _add_months(fy_start, 3 * (quarter - 1))
    return start, _add_months(start, 3) - timedelta(days=1)


def quarter_of(day: date, fye: int = 12) -> tuple[int, int]:
    """Fiscal (year label, quarter) containing `day`."""
    fy_year = day.year if fye == 12 else (day.year + 1 if day.month > fye else day.year)
    fy_start, _ = fiscal_year_bounds(fy_year, fye)
    months = (day.year - fy_start.year) * 12 + (day.month - fy_start.month)
    return fy_year, months // 3 + 1


def ttm_bounds(end: date) -> tuple[date, date]:
    """TTM window ending on `end`: the 12 whole months ending with end's month."""
    month_end = date(end.year, end.month, _last_day(end.year, end.month))
    return _add_months(date(end.year, end.month, 1), -11), month_end


# ---------------------------------------------------------------------------
# patterns

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RANGE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|through|\u2013|\u2014)\s*(\d{4}-\d{2}-\d{2})\b"
)
_DMY_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\.?,?\s+'?(\d{{2,4}})\b",
    re.IGNORECASE,
)
_MDY_RE = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,\s*(\d{{4}})\b",
    re.IGNORECASE,
)
_AS_OF_RE = re.compile(r"\bas\s+(?:of|at)\s+(.+)", re.IGNORECASE)
_TTM_RE = re.compile(r"\b(?:TTM|LTM)\b", re.IGNORECASE)
_FY_RE = re.compile(r"\bFY\s*'?\s*(\d{2,4})[ae]?\b", re.IGNORECASE)
_Q_RE = re.compile(r"\bQ([1-4])\s*'?\s*(?:FY)?\s*'?(\d{2,4})\b", re.IGNORECASE)
_Q_ALT_RE = re.compile(r"\b([1-4])Q\s*(?:FY)?\s*'?(\d{2,4})\b", re.IGNORECASE)
_ISO_MONTH_RE = re.compile(r"\b(\d{4})-(\d{2})\b")
_MY_RE = re.compile(
    rf"\b({_MONTH_ALT})\.?\s*[-/ ]\s*'?(\d{{2,4}})\b|\b({_MONTH_ALT})\.?\s+'?(\d{{4}})\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)(\d{2})\b")


def _year(raw: str) -> int:
    """Normalise a 2- or 4-digit year; 2-digit years are 20xx."""
    year = int(raw)
    return 2000 + year if year < 100 else year


def _parse_full_date(text: str) -> date | None:
    match = _ISO_DATE_RE.search(text)
    if match:
        return date(int(match[1]), int(match[2]), int(match[3]))
    match = _DMY_RE.search(text)
    if match:
        return date(_year(match[3]), _MONTHS[match[2].lower()], int(match[1]))
    match = _MDY_RE.search(text)
    if match:
        return date(int(match[3]), _MONTHS[match[1].lower()], int(match[2]))
    return None


def _point(day: date) -> PeriodSpec:
    return PeriodSpec(
        period_type=PeriodType.point,
        period_start=day,
        period_end=day,
        as_of=day,
    )


def _month(year: int, month: int) -> PeriodSpec:
    start, end = month_bounds(year, month)
    return PeriodSpec(
        period_type=PeriodType.month, period_start=start, period_end=end
    )


def parse_period(text: str, fiscal_year_end_month: int = 12) -> PeriodSpec | None:
    """Parse the first period label found in `text`; None when absent.

    Patterns are tried most-specific first so e.g. "2025-12" is a month and
    never a bare year, and "as of 31 Dec 2025" is a point, not a month.
    """
    fye = fiscal_year_end_month

    match = _AS_OF_RE.search(text)
    if match:
        day = _parse_full_date(match[1])
        if day is not None:
            return _point(day)

    match = _RANGE_RE.search(text)
    if match:
        start, end = date.fromisoformat(match[1]), date.fromisoformat(match[2])
        return PeriodSpec(
            period_type=PeriodType.custom, period_start=start, period_end=end
        )

    match = _TTM_RE.search(text)
    if match:
        # the reference date (if any) follows the token: "TTM Mar 2026",
        # "TTM ended 31 December 2025" — parse it from the remainder.
        rest = text[match.end() : match.end() + 40]
        ttm_start: date | None = None
        ttm_end: date | None = None
        day = _parse_full_date(rest)
        if day is not None:
            ttm_start, ttm_end = ttm_bounds(day)
        else:
            mm = _MY_RE.search(rest)
            if mm is not None:
                name = mm[1] or mm[3]
                year = _year(mm[2] or mm[4])
                ttm_start, ttm_end = ttm_bounds(
                    date(year, _MONTHS[name.lower()], 1)
                )
        return PeriodSpec(
            period_type=PeriodType.ttm, period_start=ttm_start, period_end=ttm_end
        )

    day = _parse_full_date(text)
    if day is not None:
        return _point(day)

    # quarters before FY so "Q1 FY2026" resolves to the quarter, not the year
    match = _Q_RE.search(text) or _Q_ALT_RE.search(text)
    if match:
        quarter, year = int(match[1]), _year(match[2])
        start, end = fiscal_quarter_bounds(year, quarter, fye)
        return PeriodSpec(
            period_type=PeriodType.quarter, period_start=start, period_end=end
        )

    match = _FY_RE.search(text)
    if match:
        start, end = fiscal_year_bounds(_year(match[1]), fye)
        return PeriodSpec(
            period_type=PeriodType.fiscal_year, period_start=start, period_end=end
        )

    match = _ISO_MONTH_RE.search(text)
    if match and 1 <= int(match[2]) <= 12:
        return _month(int(match[1]), int(match[2]))

    match = _MY_RE.search(text)
    if match:
        name = match[1] or match[3]
        year = _year(match[2] or match[4])
        return _month(year, _MONTHS[name.lower()])

    match = _YEAR_RE.search(text)
    if match:
        start, end = fiscal_year_bounds(_year(match[0]), fye)
        return PeriodSpec(
            period_type=PeriodType.fiscal_year, period_start=start, period_end=end
        )
    return None


# ---------------------------------------------------------------------------
# formatting (round-trip partner of parse_period)

_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_period(spec: PeriodSpec, fiscal_year_end_month: int = 12) -> str:
    """Render a PeriodSpec as a label `parse_period` reads back losslessly."""
    if spec.period_type == PeriodType.point and spec.as_of is not None:
        return f"as of {spec.as_of.isoformat()}"
    if spec.period_type == PeriodType.fiscal_year and spec.period_end is not None:
        return f"FY{spec.period_end.year}"
    if spec.period_type == PeriodType.quarter and spec.period_start is not None:
        fy, quarter = quarter_of(spec.period_start, fiscal_year_end_month)
        return f"Q{quarter} {fy}"
    if spec.period_type == PeriodType.month and spec.period_start is not None:
        return f"{_MONTH_ABBR[spec.period_start.month]} {spec.period_start.year}"
    if spec.period_type == PeriodType.ttm and spec.period_end is not None:
        return f"TTM {_MONTH_ABBR[spec.period_end.month]} {spec.period_end.year}"
    if spec.period_start is not None and spec.period_end is not None:
        return f"{spec.period_start.isoformat()} to {spec.period_end.isoformat()}"
    return spec.period_type.value


# ---------------------------------------------------------------------------
# comparability (contradiction engine, P4)

POINT_TOLERANCE_DAYS = 45


def _interval(spec: PeriodLike) -> tuple[date, date] | None:
    if spec.period_start is not None and spec.period_end is not None:
        return spec.period_start, spec.period_end
    if spec.as_of is not None:
        return spec.as_of, spec.as_of
    return None


def comparable(a: PeriodLike, b: PeriodLike) -> bool:
    """True when two facts' periods describe overlapping time.

    - two point facts: within ±45 days
    - otherwise: intervals must overlap by ≥ 50 % of the shorter interval
      (covers TTM-vs-FY/quarter as a special case of interval overlap)
    """
    if (
        a.period_type == PeriodType.point.value
        and b.period_type == PeriodType.point.value
        and a.as_of is not None
        and b.as_of is not None
    ):
        return abs((a.as_of - b.as_of).days) <= POINT_TOLERANCE_DAYS

    int_a, int_b = _interval(a), _interval(b)
    if int_a is None or int_b is None:
        return False
    overlap = (min(int_a[1], int_b[1]) - max(int_a[0], int_b[0])).days + 1
    if overlap <= 0:
        return False
    shorter = min(
        (int_a[1] - int_a[0]).days + 1, (int_b[1] - int_b[0]).days + 1
    )
    return overlap * 2 >= shorter
