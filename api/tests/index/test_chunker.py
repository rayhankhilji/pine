"""Chunker tests — sizing, overlap, spans, table row groups (F-03.AC4)."""

import itertools
import uuid

import tiktoken
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.index.chunker import (
    MAX_TABLE_ROWS,
    MAX_TOKENS,
    TARGET_TOKENS,
    chunk_document,
    chunk_text_spans,
)
from pine.models.chunk import Chunk, ChunkKind
from pine.models.deal import Deal
from pine.models.document import (
    Blob,
    Block,
    BlockKind,
    Cell,
    DocStatus,
    Document,
    Page,
    Table,
)

ENC = tiktoken.get_encoding("o200k_base")


def _tokens(text: str) -> int:
    return len(ENC.encode(text))


def _doc(session: Session, ext: str = "pdf") -> Document:
    deal = Deal(name="D", company_name="C")
    blob = Blob(sha256=uuid.uuid4().hex * 2, size_bytes=1, mime="text/plain", path="p")
    session.add_all([deal, blob])
    session.flush()
    doc = Document(
        deal_id=deal.id,
        blob_id=blob.id,
        filename=f"doc.{ext}",
        path=f"doc.{ext}",
        ext=ext,
        status=DocStatus.parsed,
    )
    session.add(doc)
    session.flush()
    return doc


def _page(session: Session, doc: Document, blocks: list[str], page_no: int = 1) -> Page:
    page = Page(document_id=doc.id, page_no=page_no, text="\n".join(blocks))
    session.add(page)
    session.flush()
    cursor = 0
    for i, text in enumerate(blocks):
        session.add(
            Block(
                page_id=page.id,
                order=i,
                kind=BlockKind.paragraph,
                text=text,
                char_start=cursor,
                char_end=cursor + len(text),
            )
        )
        cursor += len(text) + 1
    session.flush()
    return page


def _sentence_block(n_sentences: int) -> str:
    return " ".join(f"Sentence number {i} has some words." for i in range(n_sentences))


def test_chunk_text_spans_cap_and_target() -> None:
    text = _sentence_block(400)  # ~3200 tokens
    spans = chunk_text_spans(text, ENC)
    assert len(spans) >= 4
    for s, e in spans:
        assert _tokens(text[s:e]) <= MAX_TOKENS
    # most chunks should be near the target, not tiny
    sizes = [_tokens(text[s:e]) for s, e in spans[:-1]]
    assert all(sz >= TARGET_TOKENS for sz in sizes)


def test_chunk_text_spans_overlap() -> None:
    text = _sentence_block(200)
    spans = chunk_text_spans(text, ENC)
    assert len(spans) >= 3
    # consecutive spans overlap: next start is before previous end
    for prev, nxt in itertools.pairwise(spans):
        assert nxt[0] < prev[1]


def test_chunk_text_spans_giant_sentence_split() -> None:
    text = "word " * 3000  # one ~3000-token run with no sentence boundary
    spans = chunk_text_spans(text, ENC)
    assert len(spans) >= 4
    for s, e in spans:
        assert _tokens(text[s:e]) <= MAX_TOKENS


def test_chunk_text_spans_empty() -> None:
    assert chunk_text_spans("", ENC) == []
    assert chunk_text_spans("   ", ENC) == []


def test_chunk_document_prose(session: Session) -> None:
    doc = _doc(session)
    _page(session, doc, [_sentence_block(120)])
    chunks = chunk_document(session, doc, ENC)
    session.flush()
    assert chunks
    assert all(c.kind == ChunkKind.prose for c in chunks)
    assert all(c.token_count <= MAX_TOKENS for c in chunks)
    joined = _sentence_block(120)
    for c in chunks:
        assert joined[c.char_start : c.char_end] == c.text
        assert c.block_ids
        assert len(c.text_hash) == 64


def test_chunk_document_slide_and_email_kinds(session: Session) -> None:
    pptx = _doc(session, ext="pptx")
    _page(session, pptx, ["ARR reached $12.0M in Q4 2025, up 3x YoY"], page_no=7)
    eml = _doc(session, ext="eml")
    _page(session, eml, ["Hi, the data room is ready."])
    slide_chunks = chunk_document(session, pptx, ENC)
    email_chunks = chunk_document(session, eml, ENC)
    assert {c.kind for c in slide_chunks} == {ChunkKind.slide}
    assert slide_chunks[0].page_no == 7
    assert {c.kind for c in email_chunks} == {ChunkKind.email}


def test_chunk_document_table_rows_repeat_header(session: Session) -> None:
    """F-03.AC4: a 200-row table chunks into ≤25-row groups, header first."""
    doc = _doc(session, ext="csv")
    page = Page(document_id=doc.id, page_no=1, text="")
    session.add(page)
    session.flush()
    table = Table(
        page_id=page.id, order=0, n_rows=201, n_cols=3, header_row=0
    )
    session.add(table)
    session.flush()
    header = ["customer_name", "annual_recurring_revenue", "segment"]
    for c, text in enumerate(header):
        session.add(Cell(table_id=table.id, row=0, col=c, text=text))
    for r in range(1, 201):
        for c, text in enumerate([f"Customer {r}", str(r * 1000), "smb"]):
            session.add(Cell(table_id=table.id, row=r, col=c, text=text))
    session.flush()

    chunks = chunk_document(session, doc, ENC)
    row_chunks = [c for c in chunks if c.kind == ChunkKind.table_rows]
    header_line = ", ".join(header)
    # 200 data rows / 25 per chunk = 8 chunks
    assert len(row_chunks) == 8
    for chunk in row_chunks:
        assert chunk.text.startswith(header_line)
        assert chunk.row_start is not None and chunk.row_end is not None
        assert chunk.row_end - chunk.row_start + 1 <= MAX_TABLE_ROWS
        assert chunk.table_id == table.id


def test_chunk_document_rechunk_replaces(session: Session) -> None:
    doc = _doc(session)
    _page(session, doc, [_sentence_block(10)])
    first = chunk_document(session, doc, ENC)
    session.flush()
    n_first = len(first)
    again = chunk_document(session, doc, ENC)
    session.flush()
    assert len(again) == n_first
    total = session.scalar(select(func.count()).select_from(Chunk))
    assert total == n_first
