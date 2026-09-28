"""Search + index endpoints (ARCHITECTURE §5, F-03). No business logic here."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.api.schemas.search import (
    IndexResponse,
    IndexStatus,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from pine.config import get_settings
from pine.db import get_session
from pine.errors import AppError
from pine.index.rerank import MAX_CANDIDATES, NoReranker, Reranker, get_reranker
from pine.index.retrieval import SearchFilters, hybrid_search
from pine.index.status import index_status
from pine.jobs.queue import enqueue
from pine.models.document import Document
from pine.models.job import Job, JobKind, JobStatus
from pine.repos import deals as deals_repo

router = APIRouter(prefix="/deals", tags=["search"])


def _deal_or_404(session: Session, deal_id: str) -> None:
    if deals_repo.get_deal(session, deal_id) is None:
        raise AppError("NOT_FOUND", "Deal not found", status=404)


@router.post("/{deal_id}/search")
def search(
    deal_id: str,
    data: SearchRequest,
    session: Annotated[Session, Depends(get_session)],
) -> SearchResponse:
    _deal_or_404(session, deal_id)
    filters = None
    if data.filters is not None:
        filters = SearchFilters(
            doc_types=tuple(str(d) for d in data.filters.doc_types)
            if data.filters.doc_types
            else None,
            document_ids=tuple(data.filters.document_ids)
            if data.filters.document_ids
            else None,
            date_from=data.filters.date_from,
            date_to=data.filters.date_to,
        )
    reranker = get_reranker() if data.rerank is None else _reranker_for(data.rerank)
    pool = max(data.k, MAX_CANDIDATES) if not isinstance(reranker, NoReranker) else data.k
    hits = hybrid_search(session, deal_id, data.query, k=pool, filters=filters)
    hits = reranker.rerank(data.query, hits)[: data.k]
    return SearchResponse(
        results=[
            SearchHit(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                filename=h.filename,
                page_no=h.page_no,
                text=h.text,
                score=h.score,
                bm25_rank=h.bm25_rank,
                dense_rank=h.dense_rank,
            )
            for h in hits
        ]
    )


def _reranker_for(name: str) -> Reranker:
    settings = get_settings().model_copy(update={"RERANKER": name})
    return get_reranker(settings)


@router.post("/{deal_id}/index", status_code=status.HTTP_202_ACCEPTED)
def start_index(
    deal_id: str, session: Annotated[Session, Depends(get_session)]
) -> IndexResponse:
    _deal_or_404(session, deal_id)
    running = session.scalar(
        select(Job)
        .where(Job.deal_id == deal_id)
        .where(Job.kind == JobKind.index_deal)
        .where(Job.status.in_([JobStatus.queued, JobStatus.running]))
        .limit(1)
    )
    if running is not None:
        return IndexResponse(job_id=running.id)
    n_docs = session.scalar(
        select(func.count()).select_from(Document).where(Document.deal_id == deal_id)
    )
    job = enqueue(
        session,
        JobKind.index_deal,
        {"deal_id": deal_id},
        deal_id=deal_id,
        idempotency_key=f"index:{deal_id}:{n_docs}:{uuid.uuid4().hex[:8]}",
    )
    session.commit()
    return IndexResponse(job_id=job.id)


@router.get("/{deal_id}/index")
def get_index_status(
    deal_id: str, session: Annotated[Session, Depends(get_session)]
) -> IndexStatus:
    _deal_or_404(session, deal_id)
    return IndexStatus(**index_status(session, deal_id))
