"""Hybrid retrieval: BM25 + dense cosine fused with RRF (ARCHITECTURE §10, F-03).

BM25 (`rank_bm25`) and the dense float32 matrix are built lazily per deal and
cached in module dicts keyed by `(deal_id, chunk_count)` — correct for the
single-process worker/API topology of the MVP. Filters are hard constraints:
they mask the candidate set *before* either ranker produces its top-50.
"""

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import cast

import numpy as np
import numpy.typing as npt
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.index.embeddings import get_embedder, tokenize
from pine.index.vectors import unpack_vec
from pine.models.chunk import Chunk
from pine.models.document import Document

RRF_K = 60
SOURCE_TOP_N = 50


@dataclass(frozen=True)
class SearchFilters:
    doc_types: tuple[str, ...] | None = None
    document_ids: tuple[str, ...] | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    filename: str
    page_no: int
    text: str
    score: float
    bm25_rank: int | None
    dense_rank: int | None


@dataclass
class _Entry:
    chunk: Chunk
    filename: str
    doc_type: str
    doc_date: date | None


class BM25Index:
    """BM25Okapi over a deal's chunks, aligned with chunk ids."""

    def __init__(self, entries: list[_Entry]) -> None:
        self.chunk_ids = [e.chunk.id for e in entries]
        self.bm25 = BM25Okapi([tokenize(e.chunk.text) for e in entries])

    def top(self, query: str, keep: set[str], n: int = SOURCE_TOP_N) -> list[str]:
        """Chunk ids by BM25 score desc, restricted to `keep`, positive scores only."""
        scores = self.bm25.get_scores(tokenize(query))
        order = np.argsort(-scores)
        out: list[str] = []
        for i in order:
            cid = self.chunk_ids[int(i)]
            if cid in keep and scores[i] > 0:
                out.append(cid)
                if len(out) >= n:
                    break
        return out


_BM25_CACHE: dict[tuple[str, int], BM25Index] = {}
_DENSE_CACHE: dict[tuple[str, int], tuple[list[str], npt.NDArray[np.float32]]] = {}


def _load_entries(session: Session, deal_id: str) -> list[_Entry]:
    rows = session.execute(
        select(Chunk, Document.filename, Document.doc_type, Document.doc_date)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.deal_id == deal_id)
        .order_by(Chunk.id)
    ).all()
    return [
        _Entry(chunk=c, filename=fn, doc_type=str(dt), doc_date=dd)
        for c, fn, dt, dd in rows
    ]


def _get_bm25(deal_id: str, entries: list[_Entry]) -> BM25Index:
    key = (deal_id, len(entries))
    index = _BM25_CACHE.get(key)
    if index is None:
        index = BM25Index(entries)
        _BM25_CACHE[key] = index
    return index


def _get_dense(
    deal_id: str, entries: list[_Entry]
) -> tuple[list[str], npt.NDArray[np.float32]] | None:
    key = (deal_id, len(entries))
    cached = _DENSE_CACHE.get(key)
    if cached is not None:
        return cached
    embedded = [e for e in entries if e.chunk.embedding]
    if not embedded:
        return None
    ids = [e.chunk.id for e in embedded]
    mat = np.stack(
        [unpack_vec(e.chunk.embedding) for e in embedded]  # type: ignore[arg-type]
    ).astype(np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat = mat / norms
    _DENSE_CACHE[key] = (ids, mat)
    return ids, mat


def _dense_top(
    deal_id: str,
    entries: list[_Entry],
    query_vec: npt.NDArray[np.float32],
    keep: set[str],
    n: int = SOURCE_TOP_N,
) -> list[str]:
    dense = _get_dense(deal_id, entries)
    if dense is None:
        return []
    ids, mat = dense
    scores = mat @ query_vec
    order = np.argsort(-scores)
    out: list[str] = []
    for i in order:
        cid = ids[int(i)]
        if cid in keep:
            out.append(cid)
            if len(out) >= n:
                break
    return out


def _keep_set(entries: list[_Entry], filters: SearchFilters | None) -> set[str]:
    keep: set[str] = set()
    for e in entries:
        if filters is None:
            keep.add(e.chunk.id)
            continue
        if filters.doc_types and e.doc_type not in filters.doc_types:
            continue
        if filters.document_ids and e.chunk.document_id not in filters.document_ids:
            continue
        if filters.date_from and (e.doc_date is None or e.doc_date < filters.date_from):
            continue
        if filters.date_to and (e.doc_date is None or e.doc_date > filters.date_to):
            continue
        keep.add(e.chunk.id)
    return keep


def _query_vector(texts: list[str]) -> npt.NDArray[np.float32]:
    embedder = get_embedder()
    vec = asyncio.run(embedder.embed(texts))
    arr = np.asarray(vec, dtype=np.float32)[0]
    norm = float(np.linalg.norm(arr))
    return cast(npt.NDArray[np.float32], arr / norm) if norm > 0 else arr


def hybrid_search(
    session: Session,
    deal_id: str,
    query: str,
    k: int = 10,
    filters: SearchFilters | None = None,
) -> list[SearchHit]:
    """BM25 top-50 ∪ dense top-50 fused with RRF(k=60); filters are hard."""
    entries = _load_entries(session, deal_id)
    if not entries:
        return []
    keep = _keep_set(entries, filters)
    if not keep:
        return []

    bm25_top = _get_bm25(deal_id, entries).top(query, keep)
    qv = _query_vector([query])
    dense_top = _dense_top(deal_id, entries, qv, keep) if float(qv @ qv) > 0 else []

    bm25_ranks = {cid: i + 1 for i, cid in enumerate(bm25_top)}
    dense_ranks = {cid: i + 1 for i, cid in enumerate(dense_top)}
    scores: dict[str, float] = {}
    for cid, rank in bm25_ranks.items():
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    for cid, rank in dense_ranks.items():
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)

    by_id = {e.chunk.id: e for e in entries}
    ordered = sorted(scores, key=lambda cid: (-scores[cid], cid))[:k]
    return [
        SearchHit(
            chunk_id=cid,
            document_id=by_id[cid].chunk.document_id,
            filename=by_id[cid].filename,
            page_no=by_id[cid].chunk.page_no,
            text=by_id[cid].chunk.text,
            score=scores[cid],
            bm25_rank=bm25_ranks.get(cid),
            dense_rank=dense_ranks.get(cid),
        )
        for cid in ordered
    ]
