"""index_deal job + status service tests."""

import uuid

import pytest
from sqlalchemy.orm import Session

import pine.index.jobs  # noqa: F401 — registers the index_deal handler
from pine.index.status import index_status
from pine.jobs.queue import enqueue
from pine.models.chunk import Chunk
from pine.models.deal import Deal
from pine.models.document import (
    Blob,
    Block,
    BlockKind,
    DocStatus,
    Document,
    Page,
)
from pine.models.job import JobKind, JobStatus


@pytest.fixture(autouse=True)
def _hash_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "hash")
    from pine.config import get_settings

    get_settings.cache_clear()


def _parsed_doc(session: Session, deal: Deal, text: str, name: str) -> Document:
    blob = Blob(sha256=uuid.uuid4().hex * 2, size_bytes=1, mime="text/plain", path=name)
    session.add(blob)
    session.flush()
    doc = Document(
        deal_id=deal.id,
        blob_id=blob.id,
        filename=name,
        path=name,
        ext="txt",
        status=DocStatus.parsed,
        page_count=1,
    )
    session.add(doc)
    session.flush()
    page = Page(document_id=doc.id, page_no=1, text=text)
    session.add(page)
    session.flush()
    session.add(
        Block(
            page_id=page.id,
            order=0,
            kind=BlockKind.paragraph,
            text=text,
            char_start=0,
            char_end=len(text),
        )
    )
    session.flush()
    return doc


def _deal(session: Session) -> Deal:
    deal = Deal(name="D", company_name="C")
    session.add(deal)
    session.flush()
    return deal


def test_index_deal_creates_embedded_chunks(session: Session) -> None:
    deal = _deal(session)
    doc = _parsed_doc(session, deal, "ARR reached $12.0M in Q4 2025.", "notes.txt")
    job = enqueue(
        session, JobKind.index_deal, {"deal_id": deal.id}, deal_id=deal.id
    )

    from pine.jobs.worker import _HANDLERS

    _HANDLERS[JobKind.index_deal](session, job)

    chunks = session.query(Chunk).filter(Chunk.document_id == doc.id).all()
    assert chunks
    assert all(c.embedding for c in chunks)
    assert all(c.embedding_dim == 256 for c in chunks)
    assert all(c.embedding_model == "hash-256" for c in chunks)
    assert doc.meta.get("indexed") is True


def test_index_status_lifecycle(session: Session) -> None:
    deal = _deal(session)
    assert index_status(session, deal.id)["status"] == "empty"

    _parsed_doc(session, deal, "some text", "a.txt")
    job = enqueue(
        session, JobKind.index_deal, {"deal_id": deal.id}, deal_id=deal.id
    )
    # queued index job → indexing
    assert index_status(session, deal.id)["status"] == "indexing"

    from pine.jobs.worker import _HANDLERS

    _HANDLERS[JobKind.index_deal](session, job)
    job.status = JobStatus.succeeded
    session.commit()

    status = index_status(session, deal.id)
    assert status["status"] == "ready"
    assert status["chunk_count"] > 0
    assert status["embedded_count"] == status["chunk_count"]
    assert status["embedding_model"] == "hash-256"

    # a new parsed doc that was never indexed → stale
    _parsed_doc(session, deal, "late arrival", "b.txt")
    session.commit()
    assert index_status(session, deal.id)["status"] == "stale"


def test_index_deal_reindexes_stale_doc(session: Session) -> None:
    deal = _deal(session)
    doc = _parsed_doc(session, deal, "first text", "a.txt")
    job = enqueue(session, JobKind.index_deal, {"deal_id": deal.id})
    from pine.jobs.worker import _HANDLERS

    _HANDLERS[JobKind.index_deal](session, job)
    session.commit()
    assert index_status(session, deal.id)["status"] == "ready"

    # simulate a re-parse: new content, stamp cleared
    page = session.query(Page).filter(Page.document_id == doc.id).one()
    block = session.query(Block).filter(Block.page_id == page.id).one()
    block.text = "changed content entirely"
    page.text = "changed content entirely"
    doc.meta = {k: v for k, v in doc.meta.items() if k != "indexed"}
    session.commit()
    assert index_status(session, deal.id)["status"] == "stale"

    job2 = enqueue(session, JobKind.index_deal, {"deal_id": deal.id})
    _HANDLERS[JobKind.index_deal](session, job2)
    session.commit()
    assert index_status(session, deal.id)["status"] == "ready"
    texts = {c.text for c in session.query(Chunk).all()}
    assert texts == {"changed content entirely"}
