"""Deterministic table extractors — shared machinery (ARCHITECTURE §10, F-05).

An `Extractor` looks at one `Table` (via `TableGrid`) and writes `Fact` rows
through `EvidenceStore`, always with cell-level evidence: every fact cites
the value cell (and usually the label cell) it was read from.

`match` returns a confidence in [0, 1]; `run_extractors` runs every extractor
scoring ≥ 0.5 against every parsed table, best first.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.facts.periods import PeriodSpec, parse_period
from pine.facts.store import EvidenceSpec, EvidenceStore, whitespace_normalize
from pine.models.chunk import Chunk
from pine.models.deal import Deal
from pine.models.document import Cell, Document, Page, Table
from pine.models.entity import Entity
from pine.models.evidence import Evidence
from pine.models.fact import Fact
from pine.schemas.entities import EntityType, normalize_entity_name
from pine.schemas.units import PeriodType

MATCH_THRESHOLD = 0.5
HEADER_SCAN_ROWS = 5


@runtime_checkable
class Extractor(Protocol):
    """A deterministic per-table extractor."""

    name: str

    def match(self, grid: "TableGrid", document: Document, deal: Deal) -> float:
        """Confidence 0–1 that this extractor applies to `grid`."""
        ...

    def extract(
        self,
        grid: "TableGrid",
        document: Document,
        store: EvidenceStore,
        deal: Deal,
    ) -> int:
        """Write facts; returns the number of Fact rows created."""
        ...


class TableGrid:
    """Cells of a Table indexed by (row, col) plus page context."""

    def __init__(self, table: Table, cells: list[Cell], page_no: int) -> None:
        self.table = table
        self.cells = {(c.row, c.col): c for c in cells}
        self.page_no = page_no
        self.row_ids = sorted({c.row for c in cells})
        self.col_ids = sorted({c.col for c in cells})

    @classmethod
    def load(cls, session: Session, table: Table) -> "TableGrid":
        cells = session.scalars(
            select(Cell).where(Cell.table_id == table.id)
        ).all()
        page_no = 1
        if table.page_id:
            page = session.get(Page, table.page_id)
            if page is not None:
                page_no = page.page_no
        return cls(table, list(cells), page_no)

    def cell(self, row: int, col: int) -> Cell | None:
        return self.cells.get((row, col))

    def text(self, row: int, col: int) -> str:
        cell = self.cell(row, col)
        return cell.text.strip() if cell is not None else ""

    def row_cells(self, row: int) -> list[Cell]:
        return [
            self.cells[(row, c)]
            for c in self.col_ids
            if (row, c) in self.cells
        ]

    def row_label(self, row: int) -> str:
        """First non-empty text cell of the row (the row label)."""
        for cell in self.row_cells(row):
            if cell.text.strip():
                return cell.text.strip()
        return ""

    def row_numbers(self, row: int, skip_cols: set[int] | None = None) -> list[Cell]:
        """Cells in `row` that carry a parseable number."""
        out = []
        for cell in self.row_cells(row):
            if skip_cols is not None and cell.col in skip_cols:
                continue
            if parse_number(cell) is not None:
                out.append(cell)
        return out


# ---------------------------------------------------------------------------
# cell value / period helpers

_NUMBER_RE = re.compile(r"^-?\s*\(?\$?€?£?[\d,]*\.?\d+[kmbKMB]?%?\s*\)?$")
_MULT = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def parse_number(cell: Cell) -> Decimal | None:
    """Numeric value of a cell: `value_num` first, else parse the text."""
    if cell.value_num is not None:
        return Decimal(cell.value_num)
    text = cell.text.strip()
    if not _NUMBER_RE.match(text):
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.strip("()$€£%").replace(",", "").strip()
    multiplier = 1
    if cleaned and cleaned[-1].lower() in _MULT:
        multiplier = _MULT[cleaned[-1].lower()]
        cleaned = cleaned[:-1]
    try:
        value = Decimal(cleaned) * multiplier
    except InvalidOperation:
        return None
    return -value if negative else value


def cell_period(cell: Cell, fye: int) -> PeriodSpec | None:
    """PeriodSpec for a header cell, preferring `value_date` when present."""
    if cell.value_date is not None:
        day = cell.value_date
        return PeriodSpec(
            period_type=PeriodType.point, period_start=day, period_end=day, as_of=day
        )
    return parse_period(cell.text, fiscal_year_end_month=fye)


def evidence_for_cell(grid: TableGrid, document: Document, cell: Cell) -> EvidenceSpec:
    return EvidenceSpec(
        document_id=document.id,
        page_no=grid.page_no,
        cell_id=cell.id,
        quote=cell.text,
    )


def column_map(
    grid: TableGrid, header_row: int, roles: dict[str, tuple[str, ...]]
) -> dict[str, int]:
    """Map each role to the first column whose header contains a synonym."""
    found: dict[str, int] = {}
    for role, synonyms in roles.items():
        for col in grid.col_ids:
            text = whitespace_normalize(grid.text(header_row, col)).lower()
            if not text:
                continue
            if any(_contains(text, syn) for syn in synonyms):
                found[role] = col
                break
    return found


def find_header_row(
    grid: TableGrid,
    roles: dict[str, tuple[str, ...]],
    required: set[str],
) -> tuple[int, dict[str, int]] | None:
    """First row (within HEADER_SCAN_ROWS) covering all `required` roles."""
    for row in grid.row_ids[:HEADER_SCAN_ROWS]:
        cols = column_map(grid, row, roles)
        if required <= cols.keys():
            return row, cols
    return None


def _contains(text: str, synonym: str) -> bool:
    """Case-insensitive word-ish containment (`s&m` needs boundaries)."""
    return re.search(rf"(?<!\w){re.escape(synonym)}(?!\w)", text) is not None


def fact_exists(
    store: EvidenceStore,
    *,
    subject_entity_id: str,
    metric: str,
    value: Decimal | int,
    spec: PeriodSpec,
    document_id: str,
) -> bool:
    """Dedupe: an identical fact from the same document already exists."""
    stmt = (
        select(func.count())
        .select_from(Fact)
        .join(
            Evidence,
            (Evidence.target_id == Fact.id) & (Evidence.target_kind == "fact"),
        )
        .where(Fact.deal_id == store.deal_id)
        .where(Fact.subject_entity_id == subject_entity_id)
        .where(Fact.metric == metric)
        .where(Fact.value == Decimal(str(value)))
        .where(Fact.period_type == str(spec.period_type))
        .where(Evidence.document_id == document_id)
    )
    for col, val in (
        (Fact.period_start, spec.period_start),
        (Fact.period_end, spec.period_end),
        (Fact.as_of, spec.as_of),
    ):
        stmt = stmt.where(col.is_(None)) if val is None else stmt.where(col == val)
    return bool(store.session.scalar(stmt))


# ---------------------------------------------------------------------------
# company subject


def ensure_company(store: EvidenceStore, deal: Deal) -> Entity:
    """The deal's Company entity — created once with best-effort evidence."""
    session = store.session
    normalized = normalize_entity_name(deal.company_name)
    existing = session.scalar(
        select(Entity)
        .where(Entity.deal_id == store.deal_id)
        .where(Entity.type == EntityType.company.value)
        .where(Entity.normalized_name == normalized)
        .where(Entity.merged_into_id.is_(None))
    )
    if existing is not None:
        _deal_title_alias(store, existing, deal)
        return existing
    spec = _company_evidence(store, deal.company_name)
    entity = store.add_entity(
        type=EntityType.company,
        canonical_name=deal.company_name,
        evidence=[spec],
    )
    _deal_title_alias(store, entity, deal)
    return entity


def _deal_title_alias(store: EvidenceStore, entity: Entity, deal: Deal) -> None:
    """Record the deal title's head ("<Company> — Series B") as an alias.

    Analysts name deals "<company-ish> — <round>"; when the head extends the
    company's first token ("Northwind" → "Northwind SaaS") it is a surface
    form of the company worth resolving on. Aliases carry no evidence
    requirement — they are observed labels, not asserted facts.
    """
    head = re.split(r"\s+[—–-]\s+", deal.name, maxsplit=1)[0].strip()
    norm = normalize_entity_name(head)
    if len(norm.split()) < 2 or norm == entity.normalized_name:
        return
    first = entity.normalized_name.split()[0] if entity.normalized_name else ""
    if first and norm.split()[0] == first:
        store.add_alias(entity, head)


def _company_evidence(store: EvidenceStore, name: str) -> EvidenceSpec:
    """Best evidence for the company name: a verbatim chunk mention, else a
    document anchor (the first chunk/cell of the deal, quoted in full)."""
    session = store.session
    chunks = session.scalars(
        select(Chunk)
        .where(Chunk.deal_id == store.deal_id)
        .order_by(Chunk.created_at, Chunk.id)
        .limit(2000)
    ).all()
    lowered = name.lower()
    for chunk in chunks:
        idx = chunk.text.lower().find(lowered)
        if idx >= 0:
            return EvidenceSpec(
                document_id=chunk.document_id,
                page_no=chunk.page_no,
                chunk_id=chunk.id,
                quote=chunk.text[idx : idx + len(name)],
            )
    # normalised-substring fallback: quote the normalised span itself
    norm = whitespace_normalize(name).lower()
    for chunk in chunks:
        text = whitespace_normalize(chunk.text)
        idx = text.lower().find(norm)
        if idx >= 0:
            return EvidenceSpec(
                document_id=chunk.document_id,
                page_no=chunk.page_no,
                chunk_id=chunk.id,
                quote=text[idx : idx + len(norm)],
            )
    if chunks:
        chunk = chunks[0]
        return EvidenceSpec(
            document_id=chunk.document_id,
            page_no=chunk.page_no,
            chunk_id=chunk.id,
            quote=chunk.text[:200].strip() or chunk.text.strip()[:1],
        )
    # table-only room: anchor on the first non-empty cell of the deal
    row = session.execute(
        select(Cell, Page)
        .join(Table, Cell.table_id == Table.id)
        .join(Page, Table.page_id == Page.id)
        .join(Document, Page.document_id == Document.id)
        .where(Document.deal_id == store.deal_id)
        .where(Cell.text != "")
        .order_by(Cell.created_at, Cell.id)
        .limit(1)
    ).first()
    if row is None:
        raise ValueError(f"deal {store.deal_id} has no content to evidence")
    cell, page = row
    return EvidenceSpec(
        document_id=page.document_id,
        page_no=page.page_no,
        cell_id=cell.id,
        quote=cell.text,
    )
