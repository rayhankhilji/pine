"""Upload endpoint tests — PRD F-01.AC1..AC4 + zip guards."""

import io
import zipfile

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.config import get_settings
from pine.models.document import Blob, Document

API = "/api/v1"


def _make_deal(client: TestClient) -> str:
    resp = client.post(
        f"{API}/deals", json={"name": "Test deal", "company_name": "Acme"}
    )
    assert resp.status_code == 201
    return str(resp.json()["id"])


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _upload(
    client: TestClient,
    deal_id: str,
    files: list[tuple[str, bytes]],
    paths: list[str] | None = None,
) -> httpx2.Response:
    parts = [("files", (name, data)) for name, data in files]
    data = {"paths": paths} if paths else None
    return client.post(f"{API}/deals/{deal_id}/documents", files=parts, data=data)


def test_zip_upload_expands_nested(client: TestClient, session: Session) -> None:
    """T-F01-AC1: zip with 10 files in nested folders -> 10 queued Documents."""
    deal_id = _make_deal(client)
    entries = {f"folder{i // 3}/file_{i}.txt": f"content {i}".encode() for i in range(10)}
    resp = _upload(client, deal_id, [("room.zip", _zip(entries))])
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["documents"]) == 10
    assert body["skipped"] == []
    paths = {d["path"] for d in body["documents"]}
    assert "folder0/file_0.txt" in paths
    assert "folder3/file_9.txt" in paths
    assert all(d["status"] == "queued" for d in body["documents"])
    count = session.scalar(
        select(func.count()).select_from(Document).where(Document.deal_id == deal_id)
    )
    assert count == 10


def test_file_too_large(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-F01-AC2: file over the limit -> 413 FILE_TOO_LARGE, no Document row."""
    monkeypatch.setenv("MAX_FILE_MB", "0")
    get_settings.cache_clear()
    deal_id = _make_deal(client)
    resp = _upload(client, deal_id, [("big.txt", b"x" * 100)])
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"
    count = session.scalar(
        select(func.count()).select_from(Document).where(Document.deal_id == deal_id)
    )
    assert count == 0
    get_settings.cache_clear()


def test_identical_files_share_blob(client: TestClient, session: Session) -> None:
    """T-F01-AC3: byte-identical files -> one Blob, two Document rows."""
    deal_id = _make_deal(client)
    payload = b"identical content"
    resp = _upload(client, deal_id, [("a.txt", payload), ("b.txt", payload)])
    assert resp.status_code == 201
    assert len(resp.json()["documents"]) == 2
    doc_count = session.scalar(
        select(func.count()).select_from(Document).where(Document.deal_id == deal_id)
    )
    blob_count = session.scalar(select(func.count()).select_from(Blob))
    assert doc_count == 2
    assert blob_count == 1


def test_unsupported_extension_marked_unsupported(client: TestClient) -> None:
    """T-F01-AC4: .xyz file -> Document stored with status=unsupported."""
    deal_id = _make_deal(client)
    resp = _upload(client, deal_id, [("weird.xyz", b"\x00\x01\x02binary")])
    assert resp.status_code == 201
    doc = resp.json()["documents"][0]
    assert doc["status"] == "unsupported"
    assert doc["ext"] == "xyz"


def test_zip_skips_macosx_and_dotfiles(client: TestClient) -> None:
    deal_id = _make_deal(client)
    entries = {
        "docs/a.txt": b"a",
        "__MACOSX/._a.txt": b"junk",
        ".DS_Store": b"junk",
        "docs/.hidden": b"junk",
    }
    resp = _upload(client, deal_id, [("room.zip", _zip(entries))])
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["documents"]) == 1
    skipped = {s["filename"] for s in body["skipped"]}
    assert skipped == {"__MACOSX/._a.txt", ".DS_Store", "docs/.hidden"}


def test_zip_rejects_path_traversal(client: TestClient) -> None:
    deal_id = _make_deal(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", b"evil")
        zf.writestr("ok/good.txt", b"good")
    resp = _upload(client, deal_id, [("room.zip", buf.getvalue())])
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["path"] == "ok/good.txt"
    assert body["skipped"][0]["filename"] == "../evil.txt"


def test_duplicate_upload_same_path_skipped(client: TestClient) -> None:
    deal_id = _make_deal(client)
    payload = b"same file"
    _upload(client, deal_id, [("a.txt", payload)])
    resp = _upload(client, deal_id, [("a.txt", payload)])
    assert resp.status_code == 201
    body = resp.json()
    assert body["documents"] == []
    assert body["skipped"][0]["reason"] == "duplicate"


def test_upload_404_for_missing_deal(client: TestClient) -> None:
    resp = _upload(client, "nonexistent", [("a.txt", b"a")])
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_corrupt_zip_rejected(client: TestClient) -> None:
    deal_id = _make_deal(client)
    # PK signature but not a real zip
    resp = _upload(client, deal_id, [("bad.zip", b"PK\x03\x04 garbage")])
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION"


def test_enqueues_parse_jobs(client: TestClient, session: Session) -> None:
    from pine.models.job import Job, JobKind

    deal_id = _make_deal(client)
    resp = _upload(client, deal_id, [("notes.txt", b"hello")])
    doc_id = resp.json()["documents"][0]["id"]
    job = session.scalar(
        select(Job).where(
            Job.payload["document_id"].as_string() == doc_id,
            Job.kind == JobKind.parse_document,
        )
    )
    assert job is not None
    assert job.deal_id == deal_id
    assert job.idempotency_key == f"parse:{doc_id}"
