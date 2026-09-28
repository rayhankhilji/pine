"""Per-deal index status (ARCHITECTURE §5, F-03 states).

Derived from `chunk` rows, `index_deal` jobs and the `meta["indexed"]` stamp
written on each document when it is indexed:

- `indexing` — an index_deal job is queued or running
- `empty`    — no chunks exist and nothing is indexing
- `stale`    — a parsed document is not covered by the index (its `indexed`
               stamp was cleared or never set — e.g. uploaded/reparsed later)
- `ready`    — chunks exist and every parsed document is indexed
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.models.chunk import Chunk
from pine.models.document import DocStatus, Document
from pine.models.job import Job, JobKind, JobStatus


def index_status(session: Session, deal_id: str) -> dict[str, Any]:
    chunk_count = session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.deal_id == deal_id)
    ) or 0
    embedded_count = session.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.deal_id == deal_id)
        .where(Chunk.embedding.is_not(None))
    ) or 0
    embedding_model = session.scalar(
        select(Chunk.embedding_model)
        .where(Chunk.deal_id == deal_id)
        .where(Chunk.embedding_model.is_not(None))
        .limit(1)
    )

    active = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.deal_id == deal_id)
        .where(Job.kind == JobKind.index_deal)
        .where(Job.status.in_([JobStatus.queued, JobStatus.running]))
    )
    if active:
        status = "indexing"
    elif chunk_count == 0:
        status = "empty"
    else:
        metas = session.scalars(
            select(Document.meta)
            .where(Document.deal_id == deal_id)
            .where(Document.status == DocStatus.parsed)
        ).all()
        stale = any(not (meta or {}).get("indexed") for meta in metas)
        status = "stale" if stale else "ready"

    return {
        "status": status,
        "chunk_count": chunk_count,
        "embedded_count": embedded_count,
        "embedding_model": embedding_model,
    }
