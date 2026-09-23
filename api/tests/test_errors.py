from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from pine.errors import AppError, register_error_handlers


class Payload(BaseModel):
    name: str
    count: int


def make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise AppError("BOOM", "it broke", status=418, details={"x": 1})

    @app.post("/echo")
    def echo(payload: Payload) -> Payload:
        return payload

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("unexpected")

    return app


def test_app_error_envelope() -> None:
    response = TestClient(make_app()).get("/boom")
    assert response.status_code == 418
    assert response.json() == {
        "error": {"code": "BOOM", "message": "it broke", "details": {"x": 1}}
    }


def test_validation_error_envelope() -> None:
    response = TestClient(make_app()).post("/echo", json={"name": 1})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION"
    assert "errors" in body["error"]["details"]


def test_unhandled_error_envelope() -> None:
    response = TestClient(make_app(), raise_server_exceptions=False).get("/crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL"
