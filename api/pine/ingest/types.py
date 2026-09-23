from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pine.models.document import BlockKind


@dataclass(frozen=True)
class ParsedBlock:
    order: int
    kind: BlockKind
    text: str
    bbox: list[float] | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass(frozen=True)
class ParsedCell:
    row: int
    col: int
    text: str
    value_num: Decimal | None = None
    value_date: date | None = None
    bbox: list[float] | None = None
    ref: str | None = None


@dataclass(frozen=True)
class ParsedTable:
    order: int
    n_rows: int
    n_cols: int
    header_row: int | None = None
    sheet_name: str | None = None
    column_types: list[str] = field(default_factory=list)
    bbox: list[float] | None = None
    title: str | None = None
    cells: list[ParsedCell] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedPage:
    page_no: int
    width: float
    height: float
    is_scanned: bool = False
    sheet_name: str | None = None
    text: str = ""
    blocks: list[ParsedBlock] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)


@dataclass(frozen=True)
class Attachment:
    filename: str
    data: bytes
    path: str = ""


@dataclass(frozen=True)
class ParseResult:
    pages: list[ParsedPage] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    language: str | None = None
    doc_date: date | None = None
    attachments: list[Attachment] = field(default_factory=list)
