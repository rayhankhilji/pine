"""Structure-aware chunker (ARCHITECTURE §10, F-03).

Prose: blocks are joined with newlines and packed into chunks targeting
TARGET_TOKENS, never exceeding MAX_TOKENS, with ~OVERLAP_TOKENS repeated at
sentence boundaries. `char_start`/`char_end` are offsets into the joined block
text, so `joined[char_start:char_end] == chunk.text` always holds.

Tables: data rows are emitted in groups of at most MAX_TABLE_ROWS with the
header row line repeated first (F-03.AC4); offsets point into the
table-derived text (all row lines joined by newlines).
"""

import hashlib
import re
from functools import lru_cache

import tiktoken
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pine.models.chunk import Chunk, ChunkKind
from pine.models.document import Block, BlockKind, Cell, Document, Page, Table

TARGET_TOKENS = 400
MAX_TOKENS = 800
OVERLAP_TOKENS = 60
MAX_TABLE_ROWS = 25

_SENTENCE_BOUNDARY = re.compile(r"\.\s|\n")


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("o200k_base")


def _count(text: str, enc: tiktoken.Encoding) -> int:
    return len(enc.encode(text))


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Contiguous (start, end) spans covering `text`, split after ". " and newlines."""
    bounds = [0]
    bounds.extend(m.end() for m in _SENTENCE_BOUNDARY.finditer(text) if m.end() < len(text))
    bounds.append(len(text))
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def _cap_piece(text: str, start: int, end: int, enc: tiktoken.Encoding) -> list[tuple[int, int]]:
    """Split a span longer than MAX_TOKENS at token boundaries (mid-block split)."""
    tokens = enc.encode(text[start:end])
    if len(tokens) <= MAX_TOKENS:
        return [(start, end)]
    out: list[tuple[int, int]] = []
    tok_start = 0
    char_start = start
    while tok_start < len(tokens):
        tok_end = min(tok_start + MAX_TOKENS, len(tokens))
        char_end = start + len(enc.decode(tokens[:tok_end]))
        out.append((char_start, char_end))
        tok_start = tok_end
        char_start = char_end
    return out


def chunk_text_spans(
    text: str, enc: tiktoken.Encoding | None = None
) -> list[tuple[int, int]]:
    """Split `text` into chunk spans honouring target/cap/overlap (pure function)."""
    enc = enc or _encoding()
    if not text.strip():
        return []
    pieces: list[tuple[int, int]] = []
    for s, e in _sentence_spans(text):
        pieces.extend(_cap_piece(text, s, e, enc))
    piece_tokens = [_count(text[s:e], enc) for s, e in pieces]
    n = len(pieces)
    spans: list[tuple[int, int]] = []
    start = 0
    while start < n:
        end = start
        tokens = piece_tokens[start]
        j = start + 1
        while j < n:
            # candidate span must stay under the hard cap; stop once target reached
            cand_tokens = _count(text[pieces[start][0] : pieces[j][1]], enc)
            if tokens >= TARGET_TOKENS or cand_tokens > MAX_TOKENS:
                break
            end = j
            tokens = cand_tokens
            j += 1
        spans.append((pieces[start][0], pieces[end][1]))
        if end + 1 >= n:
            break
        # overlap: restart at the earliest piece whose tail totals ~OVERLAP tokens
        acc = 0
        k = end + 1
        while k - 1 > start and acc < OVERLAP_TOKENS:
            acc += piece_tokens[k - 1]
            k -= 1
        start = k if k > start else start + 1
    return spans


def _kind_for(ext: str) -> ChunkKind:
    if ext == "pptx":
        return ChunkKind.slide
    if ext == "eml":
        return ChunkKind.email
    return ChunkKind.prose


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def delete_document_chunks(session: Session, document_id: str) -> None:
    session.execute(delete(Chunk).where(Chunk.document_id == document_id))


def _table_chunks(
    session: Session,
    document: Document,
    page: Page,
    table: Table,
    enc: tiktoken.Encoding,
) -> list[Chunk]:
    cells = session.scalars(
        select(Cell).where(Cell.table_id == table.id).order_by(Cell.row, Cell.col)
    ).all()
    if not cells:
        return []
    rows: dict[int, list[str]] = {}
    for cell in cells:
        rows.setdefault(cell.row, []).append(cell.text)
    row_indices = sorted(rows)
    row_texts = {r: ", ".join(rows[r]).strip() for r in row_indices}

    offsets: dict[int, tuple[int, int]] = {}
    cursor = 0
    for r in row_indices:
        offsets[r] = (cursor, cursor + len(row_texts[r]))
        cursor += len(row_texts[r]) + 1

    header_idx = table.header_row
    header_text = row_texts.get(header_idx) if header_idx is not None else None
    data_rows = [r for r in row_indices if r != header_idx]
    groups = [
        data_rows[i : i + MAX_TABLE_ROWS]
        for i in range(0, len(data_rows), MAX_TABLE_ROWS)
    ]
    if not groups and header_text:
        groups = [[]]  # header-only table still yields one searchable chunk

    chunks: list[Chunk] = []
    for group in groups:
        body = "\n".join(row_texts[r] for r in group if row_texts[r])
        text = f"{header_text}\n{body}" if header_text and body else header_text or body
        if not text.strip():
            continue
        if group:
            char_start, char_end = offsets[group[0]][0], offsets[group[-1]][1]
            row_start, row_end = group[0], group[-1]
        else:
            assert header_idx is not None
            char_start, char_end = offsets[header_idx]
            row_start = row_end = header_idx
        chunks.append(
            Chunk(
                deal_id=document.deal_id,
                document_id=document.id,
                page_no=page.page_no,
                block_ids=[table.block_id] if table.block_id else [],
                text=text,
                token_count=_count(text, enc),
                char_start=char_start,
                char_end=char_end,
                kind=ChunkKind.table_rows,
                table_id=table.id,
                row_start=row_start,
                row_end=row_end,
                text_hash=_hash(text),
            )
        )
    return chunks


def chunk_document(
    session: Session, document: Document, enc: tiktoken.Encoding | None = None
) -> list[Chunk]:
    """(Re)chunk a parsed document: drops prior chunks, returns new Chunk rows."""
    enc = enc or _encoding()
    delete_document_chunks(session, document.id)
    kind = _kind_for(document.ext)
    chunks: list[Chunk] = []

    pages = session.scalars(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_no)
    ).all()
    for page in pages:
        blocks = session.scalars(
            select(Block).where(Block.page_id == page.id).order_by(Block.order)
        ).all()
        prose = [b for b in blocks if b.kind != BlockKind.table and b.text.strip()]
        joined = "\n".join(b.text for b in prose)
        offsets: list[tuple[str, int, int]] = []
        cursor = 0
        for b in prose:
            offsets.append((b.id, cursor, cursor + len(b.text)))
            cursor += len(b.text) + 1
        for s, e in chunk_text_spans(joined, enc):
            text = joined[s:e]
            chunks.append(
                Chunk(
                    deal_id=document.deal_id,
                    document_id=document.id,
                    page_no=page.page_no,
                    block_ids=[bid for bid, bs, be in offsets if bs < e and be > s],
                    text=text,
                    token_count=_count(text, enc),
                    char_start=s,
                    char_end=e,
                    kind=kind,
                    text_hash=_hash(text),
                )
            )
        tables = session.scalars(
            select(Table).where(Table.page_id == page.id).order_by(Table.order)
        ).all()
        for table in tables:
            chunks.extend(_table_chunks(session, document, page, table, enc))

    for chunk in chunks:
        session.add(chunk)
    return chunks
