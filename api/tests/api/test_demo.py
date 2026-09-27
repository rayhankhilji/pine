"""POST /demo — builds fixtures, creates the Northwind deal, ingests (F-14)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from pine.jobs.worker import Worker
from tests.demo.test_build import EXPECTED_FILES

API = "/api/v1"
N_INGESTED = len(EXPECTED_FILES) - 1  # ground_truth.json is not ingested


async def _drain(session_factory: sessionmaker[Session], max_rounds: int = 100) -> None:
    # concurrency=1: in-memory StaticPool shares one connection across
    # sessions; parallel workers interleave and see stale snapshots.
    worker = Worker(session_factory, concurrency=1)
    for _ in range(max_rounds):
        if await worker.run_once() == 0:
            return


def test_demo_creates_deal_and_ingests(client: TestClient) -> None:
    resp = client.post(f"{API}/demo", json={})
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] is None
    deal_id = body["deal_id"]

    deal = client.get(f"{API}/deals/{deal_id}").json()
    assert deal["name"] == "Northwind SaaS — Series B"
    assert deal["company_name"] == "Northwind"
    assert deal["stage"] == "series_b"
    assert float(deal["proposed_round_usd"]) == 25_000_000
    assert float(deal["proposed_pre_money_usd"]) == 150_000_000

    items = client.get(f"{API}/deals/{deal_id}/documents?limit=200").json()["items"]
    assert len(items) == N_INGESTED
    paths = {d["path"] for d in items}
    assert "05_Contracts/MSA_Acme_Corporation.pdf" in paths
    assert "08_Emails/email_04.eml" in paths
    assert "ground_truth.json" not in paths
    assert all(d["status"] == "queued" for d in items)


def test_demo_conflict_while_ingesting(client: TestClient) -> None:
    resp = client.post(f"{API}/demo", json={})
    assert resp.status_code == 202
    resp2 = client.post(f"{API}/demo", json={})
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "CONFLICT"


async def test_demo_parses_all_files(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    resp = client.post(f"{API}/demo", json={})
    deal_id = resp.json()["deal_id"]

    await _drain(session_factory)

    items = client.get(f"{API}/deals/{deal_id}/documents?limit=200").json()["items"]
    statuses = {d["status"] for d in items}
    # everything parses; the image-only PDF is parsed-but-scanned or
    # marked unsupported only if a parser is missing — never left queued
    assert "queued" not in statuses and "parsing" not in statuses
    assert statuses <= {"parsed", "failed", "unsupported"}
    parsed = [d for d in items if d["status"] == "parsed"]
    assert len(parsed) >= 15

    # the eml attachment becomes a child document
    children = [d for d in items if d["parent_document_id"]]
    assert len(children) >= 1

    # a completed demo deal no longer blocks a new one
    resp2 = client.post(f"{API}/demo", json={"name": "Northwind again"})
    assert resp2.status_code == 202
    assert resp2.json()["deal_id"] != deal_id
