"""Pydantic schemas for search and index endpoints (ARCHITECTURE §5, F-03)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from pine.models.document import DocType


class SearchFilters(BaseModel):
    doc_types: list[DocType] | None = None
    document_ids: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=10, ge=1, le=50)
    filters: SearchFilters | None = None
    rerank: Literal["none", "llm", "cross-encoder"] | None = None


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page_no: int
    text: str
    score: float
    bm25_rank: int | None
    dense_rank: int | None


class SearchResponse(BaseModel):
    results: list[SearchHit]


class IndexStatus(BaseModel):
    status: Literal["indexing", "ready", "stale", "empty"]
    chunk_count: int
    embedded_count: int
    embedding_model: str | None


class IndexResponse(BaseModel):
    job_id: str
