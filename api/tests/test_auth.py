from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pine.config import get_settings
from pine.db import get_session
from pine.main import create_app


@pytest.fixture
def secured_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("PINE_API_KEY", "test-secret")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: iter([])
    client = TestClient(app)
    yield client
    client.close()
    monkeypatch.delenv("PINE_API_KEY", raising=False)
    get_settings.cache_clear()


def test_missing_key_is_unauthorized(secured_client: TestClient) -> None:
    response = secured_client.get("/api/v1/anything")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_wrong_key_is_unauthorized(secured_client: TestClient) -> None:
    response = secured_client.get("/api/v1/anything", headers={"X-API-Key": "nope"})
    assert response.status_code == 401


def test_valid_key_passes(secured_client: TestClient) -> None:
    response = secured_client.get("/api/v1/health", headers={"X-API-Key": "test-secret"})
    assert response.status_code == 200


def test_health_is_open_without_key(secured_client: TestClient) -> None:
    response = secured_client.get("/api/v1/health")
    assert response.status_code == 200


def test_open_when_no_key_configured(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
