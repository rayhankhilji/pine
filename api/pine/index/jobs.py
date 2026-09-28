"""index_deal job handler (ARCHITECTURE §9, F-03).

Chunks every parsed document of the deal (replacing prior chunks), embeds the
chunk texts with the configured provider and stamps each document
`meta["indexed"] = true`. Emits nothing directly — SSE consumers poll status.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.index.chunker import chunk_document
from pine.index.embeddings import get_embedder
from pine.index.vectors import pack_vec
from pine.jobs.queue import enqueue
from pine.jobs.worker import job_handler
from pine.models.document import DocStatus, Document
from pine.models.job import Job, JobKind

logger = logging.getLogger(__name__)


@job_handler(JobKind.index_deal)
def index_deal(session: Session, job: Job) -> None:
    deal_id = job.payload["deal_id"]
    documents = session.scalars(
        select(Document)
        .where(Document.deal_id == deal_id)
        .where(Document.status == DocStatus.parsed)
        .order_by(Document.created_at)
    ).all()

    embedder = get_embedder()
    total = 0
    for document in documents:
        chunks = chunk_document(session, document)
        session.flush()
        if chunks:
            vectors = asyncio.run(embedder.embed([c.text for c in chunks]))
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk.embedding = pack_vec(vector)
                chunk.embedding_dim = embedder.dim
                chunk.embedding_model = embedder.model
            total += len(chunks)
        document.meta = {**document.meta, "indexed": True}
        session.commit()

    # chain: facts extraction runs once the index exists (ARCHITECTURE §6)
    enqueue(
        session,
        JobKind.extract_facts,
        {"deal_id": deal_id},
        deal_id=deal_id,
        idempotency_key=f"facts:{deal_id}:{total}",
    )
    logger.info("index_deal %s: %d chunks over %d documents", deal_id, total, len(documents))
