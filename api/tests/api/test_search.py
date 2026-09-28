"""Search + index endpoints (ARCHITECTURE §5, F-03.AC1–AC4 via API)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from pine.jobs.worker import Worker

API = "/api/v1"


def _make_deal(client: TestClient) -> str:
    resp = client.post(f"{API}/deals", json={"name": "Search deal", "company_name": "C"})
    assert resp.status_code == 201
    return str(resp.json()["id"])


def _upload(client: TestClient, deal_id: str, name: str, data: bytes) -> str:
    resp = client.post(
        f"{API}/deals/{deal_id}/documents", files=[("files", (name, data))]
    )
    assert resp.status_code == 201
    return str(resp.json()["documents"][0]["id"])


async def _drain_worker(session_factory: sessionmaker[Session]) -> None:
    worker = Worker(session_factory, concurrency=1)
    for _ in range(100):
        if await worker.run_once() == 0:
            return


async def _room(
    client: TestClient, session_factory: sessionmaker[Session]
) -> tuple[str, dict[str, str]]:
    """Small synthetic room: deck prose, customer CSV, contract, filler."""
    deal_id = _make_deal(client)
    ids = {
        "deck": _upload(
            client, deal_id, "deck.txt",
            b"Growth metrics. Annual recurring revenue reached $12.0M in Q4 2025, "
            b"up 3x year over year. Net revenue retention 118%.",
        ),
        "customers": _upload(
            client, deal_id, "customers.csv",
            b"customer_name,annual_recurring_revenue,segment\n"
            + b"".join(
                f"Customer {i},{1000 * i},smb\n".encode() for i in range(1, 31)
            ),
        ),
        "contract": _upload(
            client, deal_id, "msa.txt",
            b"Master Services Agreement between Northwind and Acme. "
            b"Section 7.2 - Termination for Change of Control: Customer may "
            b"terminate upon a change of control with thirty days notice.",
        ),
        "filler": _upload(
            client, deal_id, "lorem.txt",
            b"lorem ipsum dolor sit amet consectetur adipiscing elit",
        ),
    }
    await _drain_worker(session_factory)
    return deal_id, ids


async def test_index_status_lifecycle(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    deal_id = _make_deal(client)
    status = client.get(f"{API}/deals/{deal_id}/index")
    assert status.status_code == 200
    assert status.json() == {
        "status": "empty",
        "chunk_count": 0,
        "embedded_count": 0,
        "embedding_model": None,
    }

    resp = client.post(f"{API}/deals/{deal_id}/index")
    assert resp.status_code == 202
    assert resp.json()["job_id"]

    await _drain_worker(session_factory)
    status = client.get(f"{API}/deals/{deal_id}/index")
    assert status.json()["status"] == "empty"  # no parsed docs → nothing chunked


async def test_index_then_search(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    deal_id, ids = await _room(client, session_factory)

    status = client.get(f"{API}/deals/{deal_id}/index").json()
    assert status["status"] == "ready"
    assert status["chunk_count"] > 0
    assert status["embedded_count"] == status["chunk_count"]
    assert status["embedding_model"] == "hash-256"

    # F-03.AC1 — "annual recurring revenue" finds deck prose + customer table
    resp = client.post(
        f"{API}/deals/{deal_id}/search",
        json={"query": "annual recurring revenue", "k": 10},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results
    top3_docs = {r["document_id"] for r in results[:3]}
    assert ids["deck"] in top3_docs
    assert ids["customers"] in top3_docs
    first = results[0]
    assert {
        "chunk_id", "document_id", "filename", "page_no",
        "text", "score", "bm25_rank", "dense_rank",
    } <= set(first)


async def test_search_literal_clause(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """F-03.AC2 — literal 'Section 7.2' ranks its chunk in the top 3."""
    deal_id, ids = await _room(client, session_factory)
    resp = client.post(
        f"{API}/deals/{deal_id}/search", json={"query": "Section 7.2", "k": 5}
    )
    results = resp.json()["results"]
    assert ids["contract"] in {r["document_id"] for r in results[:3]}
    hit = next(r for r in results[:3] if r["document_id"] == ids["contract"])
    assert "Section 7.2" in hit["text"]
    assert hit["bm25_rank"] is not None


async def test_search_filters(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    deal_id, ids = await _room(client, session_factory)
    resp = client.post(
        f"{API}/deals/{deal_id}/search",
        json={
            "query": "annual recurring revenue",
            "k": 10,
            "filters": {"document_ids": [ids["customers"]]},
        },
    )
    results = resp.json()["results"]
    assert results
    assert all(r["document_id"] == ids["customers"] for r in results)


async def test_search_rerank_llm(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: object,
) -> None:
    deal_id, _ids = await _room(client, session_factory)
    resp = client.post(
        f"{API}/deals/{deal_id}/search",
        json={"query": "annual recurring revenue", "k": 5, "rerank": "llm"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["results"]) <= 5


def test_search_404(client: TestClient) -> None:
    resp = client.post(f"{API}/deals/nope/search", json={"query": "x"})
    assert resp.status_code == 404
    assert client.get(f"{API}/deals/nope/index").status_code == 404
    assert client.post(f"{API}/deals/nope/index").status_code == 404


def test_search_validation(client: TestClient) -> None:
    deal_id = _make_deal(client)
    assert (
        client.post(f"{API}/deals/{deal_id}/search", json={"query": ""}).status_code
        == 422
    )
    assert (
        client.post(
            f"{API}/deals/{deal_id}/search", json={"query": "x", "k": 0}
        ).status_code
        == 422
    )


async def test_reindex_after_new_document(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    deal_id, _ids = await _room(client, session_factory)
    assert client.get(f"{API}/deals/{deal_id}/index").json()["status"] == "ready"

    # a re-parsed doc has its `indexed` stamp cleared (see ingest/jobs.py);
    # simulate that state directly — parsed content not covered by the index
    doc_id = _upload(client, deal_id, "late.txt", b"brand new searchable content")
    await _drain_worker(session_factory)
    with session_factory() as s:
        from pine.models.document import Document

        doc = s.get(Document, doc_id)
        assert doc is not None
        doc.meta = {k: v for k, v in doc.meta.items() if k != "indexed"}
        s.commit()
    assert client.get(f"{API}/deals/{deal_id}/index").json()["status"] == "stale"

    resp = client.post(f"{API}/deals/{deal_id}/index")
    assert resp.status_code == 202
    await _drain_worker(session_factory)
    assert client.get(f"{API}/deals/{deal_id}/index").json()["status"] == "ready"

    hits = client.post(
        f"{API}/deals/{deal_id}/search", json={"query": "searchable content"}
    ).json()["results"]
    assert hits
