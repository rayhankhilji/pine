import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from pine.errors import register_error_handlers
from pine.logging import JsonFormatter, redact


def test_request_id_generated_and_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    request_id = response.headers["X-Request-Id"]
    assert request_id and len(request_id) == 32


def test_request_id_accepted_from_header(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-Id": "req-123"})
    assert response.headers["X-Request-Id"] == "req-123"


def test_internal_error_includes_request_id() -> None:
    app = FastAPI()

    @app.middleware("http")
    async def rid(request: Request, call_next: Callable[[Request], Any]) -> Response:
        request.state.request_id = "req-err-1"
        response: Response = await call_next(request)
        return response

    register_error_handlers(app)

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("boom")

    response = TestClient(app, raise_server_exceptions=False).get("/crash")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL"
    assert body["error"]["details"]["request_id"] == "req-err-1"


def test_json_formatter_emits_request_id() -> None:
    record = logging.LogRecord("pine.test", logging.INFO, __file__, 1, "hello", (), None)
    record.request_id = "req-xyz"
    entry = json.loads(JsonFormatter().format(record))
    assert entry["request_id"] == "req-xyz"
    assert entry["message"] == "hello"
    assert entry["level"] == "INFO"


def test_redact_masks_account_numbers() -> None:
    assert redact("acct 123456789012 paid") == "acct 12********** paid"
    assert redact("ref 1234") == "ref 1234"
