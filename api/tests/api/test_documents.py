"""Document endpoints: detail, pages, render, file, reparse, tables, jobs, SSE."""

import io
import socket
import threading
import time
import zipfile

import httpx
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from pine.jobs.worker import Worker
from tests.ingest.conftest import make_pdf_with_table, make_xlsx

API = "/api/v1"


def _make_deal(client: TestClient) -> str:
    resp = client.post(
        f"{API}/deals", json={"name": "Docs deal", "company_name": "Acme"}
    )
    assert resp.status_code == 201
    return str(resp.json()["id"])


def _upload(
    client: TestClient, deal_id: str, name: str, data: bytes
) -> dict[str, object]:
    resp = client.post(
        f"{API}/deals/{deal_id}/documents", files=[("files", (name, data))]
    )
    assert resp.status_code == 201
    return resp.json()["documents"][0]  # type: ignore[no-any-return]


async def _drain_worker(session_factory: sessionmaker[Session]) -> None:
    worker = Worker(session_factory, concurrency=1)
    for _ in range(50):
        if await worker.run_once() == 0:
            return


async def test_document_lifecycle(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    deal_id = _make_deal(client)
    doc = _upload(client, deal_id, "report.pdf", make_pdf_with_table())
    assert doc["status"] == "queued"
    assert doc["doc_type"] == "unknown"

    await _drain_worker(session_factory)

    resp = client.get(f"{API}/deals/{deal_id}/documents")
    assert resp.status_code == 200
    doc = resp.json()["items"][0]
    assert doc["status"] == "parsed"
    assert doc["doc_type"] == "financial_statement"  # classified from content
    assert doc["page_count"] == 1

    detail = client.get(f"{API}/documents/{doc['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["pages"][0]["page_no"] == 1
    assert body["pages"][0]["is_scanned"] is False
    assert len(body["tables"]) == 1
    assert body["tables"][0]["n_rows"] == 5

    page = client.get(f"{API}/documents/{doc['id']}/pages/1")
    assert page.status_code == 200
    page_body = page.json()
    assert "Quarterly Revenue Report" in page_body["text"]
    assert page_body["blocks"]
    assert page_body["blocks"][0]["bbox"]
    assert len(page_body["tables"]) == 1

    render = client.get(f"{API}/documents/{doc['id']}/render/1")
    assert render.status_code == 200
    assert render.headers["content-type"] == "image/png"
    assert render.content[:4] == b"\x89PNG"

    file_resp = client.get(f"{API}/documents/{doc['id']}/file")
    assert file_resp.status_code == 200
    assert file_resp.content[:5] == b"%PDF-"
    assert "report.pdf" in file_resp.headers["content-disposition"]


async def test_table_detail(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    deal_id = _make_deal(client)
    doc = _upload(client, deal_id, "financials.xlsx", make_xlsx())
    await _drain_worker(session_factory)

    detail = client.get(f"{API}/documents/{doc['id']}").json()
    assert detail["status"] == "parsed"
    assert detail["doc_type"] == "financial_statement"
    assert {p["sheet_name"] for p in detail["pages"]} == {"P&L", "Balance"}
    assert len(detail["tables"]) == 2

    table_id = detail["tables"][0]["id"]
    resp = client.get(f"{API}/tables/{table_id}")
    assert resp.status_code == 200
    table = resp.json()
    assert table["n_rows"] == 3
    assert table["n_cols"] == 3
    assert table["sheet_name"] == "P&L"
    assert table["cells"][0][0]["text"] == "Metric"
    assert float(table["cells"][1][1]["value_num"]) == 4100000
    assert table["cells"][1][1]["ref"] == "B2"


async def test_reparse_enqueues_job(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    deal_id = _make_deal(client)
    doc = _upload(client, deal_id, "notes.txt", b"hello world")
    await _drain_worker(session_factory)

    resp = client.post(f"{API}/documents/{doc['id']}/reparse")
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    job = client.get(f"{API}/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["kind"] == "parse_document"
    assert job.json()["payload"]["document_id"] == doc["id"]

    await _drain_worker(session_factory)
    detail = client.get(f"{API}/documents/{doc['id']}").json()
    assert detail["status"] == "parsed"


async def test_render_unsupported_type(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    deal_id = _make_deal(client)
    doc = _upload(client, deal_id, "notes.txt", b"plain text")
    await _drain_worker(session_factory)
    resp = client.get(f"{API}/documents/{doc['id']}/render/1")
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_TYPE"


def test_document_not_found(client: TestClient) -> None:
    assert client.get(f"{API}/documents/nope").status_code == 404
    assert client.get(f"{API}/documents/nope/pages/1").status_code == 404
    assert client.get(f"{API}/documents/nope/render/1").status_code == 404
    assert client.get(f"{API}/documents/nope/file").status_code == 404
    assert client.post(f"{API}/documents/nope/reparse").status_code == 404
    assert client.get(f"{API}/tables/nope").status_code == 404
    assert client.get(f"{API}/jobs/nope").status_code == 404


def test_documents_filters_and_cursor(client: TestClient) -> None:
    deal_id = _make_deal(client)
    for i in range(3):
        _upload(client, deal_id, f"f{i}.txt", f"text {i}".encode())
    _upload(client, deal_id, "odd.xyz", b"\x00\x01")

    resp = client.get(f"{API}/deals/{deal_id}/documents?limit=2")
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    page2 = client.get(
        f"{API}/deals/{deal_id}/documents?limit=2&cursor={body['next_cursor']}"
    ).json()
    assert len(page2["items"]) == 2
    ids = {d["id"] for d in body["items"]} | {d["id"] for d in page2["items"]}
    assert len(ids) == 4

    unsupported = client.get(
        f"{API}/deals/{deal_id}/documents?status=unsupported"
    ).json()
    assert len(unsupported["items"]) == 1
    assert unsupported["items"][0]["filename"] == "odd.xyz"


def test_deal_events_sse(client: TestClient) -> None:
    # TestClient runs the ASGI app to completion before returning a response,
    # so infinite SSE streams need a real uvicorn server.
    deal_id = _make_deal(client)
    _upload(client, deal_id, "a.txt", b"hi")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = uvicorn.Server(
        uvicorn.Config(client.app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started

    try:
        with httpx.Client(timeout=10) as http, http.stream(
            "GET", f"http://127.0.0.1:{port}{API}/deals/{deal_id}/events"
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            events: set[str] = set()
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    events.add(line.split(":", 1)[1].strip())
                if {"document.status", "index.status"} <= events:
                    break
        assert {"document.status", "index.status"} <= events
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_deal_events_404(client: TestClient) -> None:
    resp = client.get(f"{API}/deals/nonexistent/events")
    assert resp.status_code == 404


def test_zip_paths_preserved_in_listing(client: TestClient) -> None:
    deal_id = _make_deal(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("contracts/msa.txt", b"msa")
        zf.writestr("fin/pnl.txt", b"pnl")
    client.post(
        f"{API}/deals/{deal_id}/documents",
        files=[("files", ("room.zip", buf.getvalue()))],
    )
    items = client.get(f"{API}/deals/{deal_id}/documents").json()["items"]
    assert {d["path"] for d in items} == {"contracts/msa.txt", "fin/pnl.txt"}
    assert {d["status"] for d in items} == {"queued"}
