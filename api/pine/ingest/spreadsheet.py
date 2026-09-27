import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pine.ingest.types import ParsedCell, ParsedPage, ParsedTable, ParseResult

_CURRENCY_RE = re.compile(r"[$€£]")
_CURRENCY_HEADER_RE = re.compile(
    r"revenue|amount|price|arr|mrr|balance|cost|total|salary|value", re.I
)
_PERCENT_RE = re.compile(r"%\s*$")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d")


def _to_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        cleaned = _CURRENCY_RE.sub("", value).replace(",", "").strip()
        cleaned = _PERCENT_RE.sub("", cleaned)
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def _to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def _col_letter(col: int) -> str:
    letters = ""
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def infer_column_types(rows: list[list[Any]], header_row: int | None) -> list[str]:
    """Classify each column: currency/number/date/percent/text (80 % sample rule)."""
    n_cols = max((len(r) for r in rows), default=0)
    headers = rows[header_row] if header_row is not None and header_row < len(rows) else []
    data_rows = [r for i, r in enumerate(rows) if i != header_row]
    types: list[str] = []
    for c in range(n_cols):
        samples = [r[c] for r in data_rows if c < len(r) and r[c] not in (None, "")]
        if not samples:
            types.append("text")
            continue
        numeric = sum(1 for v in samples if _to_decimal(v) is not None)
        dates = sum(1 for v in samples if _to_date(v) is not None)
        percents = sum(
            1 for v in samples if isinstance(v, str) and _PERCENT_RE.search(v)
        )
        currency_hint = sum(
            1 for v in samples if isinstance(v, str) and _CURRENCY_RE.search(v)
        )
        header = str(headers[c]) if c < len(headers) else ""
        n = len(samples)
        if percents / n >= 0.8:
            types.append("percent")
        elif dates / n >= 0.8:
            types.append("date")
        elif numeric / n >= 0.8:
            if currency_hint / n >= 0.5 or _CURRENCY_HEADER_RE.search(header):
                types.append("currency")
            else:
                types.append("number")
        else:
            types.append("text")
    return types


def _rows_to_table(
    rows: list[list[Any]], order: int, sheet_name: str | None
) -> ParsedTable:
    header_row = 0 if rows else None
    column_types = infer_column_types(rows, header_row)
    cells: list[ParsedCell] = []
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            if val is None:
                continue
            cells.append(
                ParsedCell(
                    row=r,
                    col=c,
                    text="" if val is None else str(val),
                    value_num=_to_decimal(val),
                    value_date=_to_date(val),
                    ref=f"{_col_letter(c)}{r + 1}",
                )
            )
    return ParsedTable(
        order=order,
        n_rows=len(rows),
        n_cols=max((len(r) for r in rows), default=0),
        header_row=header_row,
        sheet_name=sheet_name,
        column_types=column_types,
        cells=cells,
    )


def parse(data: bytes, filename: str) -> ParseResult:
    ext = filename.rsplit(".", 1)[-1].lower()
    pages: list[ParsedPage] = []
    sheet_names: list[str] = []

    if ext == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        for idx, ws in enumerate(wb.worksheets):
            rows = [list(row) for row in ws.iter_rows(values_only=True)]
            table = _rows_to_table(rows, order=0, sheet_name=ws.title)
            sheet_names.append(ws.title)
            text = "\n".join(
                ", ".join("" if v is None else str(v) for v in r) for r in rows
            )
            pages.append(
                ParsedPage(
                    page_no=idx + 1,
                    width=0,
                    height=0,
                    sheet_name=ws.title,
                    text=text,
                    tables=[table],
                )
            )
    elif ext in {"csv", "tsv"}:
        dialect = "excel-tab" if ext == "tsv" else "excel"
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig")), dialect=dialect)
        rows = [list(r) for r in reader]
        table = _rows_to_table(rows, order=0, sheet_name=None)
        text = "\n".join(", ".join(r) for r in rows)
        pages.append(
            ParsedPage(page_no=1, width=0, height=0, text=text, tables=[table])
        )
    else:
        raise ValueError(f"unsupported spreadsheet type: {ext}")

    return ParseResult(pages=pages, meta={"sheets": sheet_names})
