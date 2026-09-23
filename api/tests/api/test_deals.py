from typing import Any, cast

from fastapi.testclient import TestClient


def _create(client: TestClient, name: str = "Northwind SaaS") -> dict[str, Any]:
    response = client.post(
        "/api/v1/deals",
        json={"name": f"{name} — Series B", "company_name": name},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_deal(client: TestClient) -> None:
    deal = _create(client)
    assert deal["id"]
    assert deal["stage"] == "series_b"
    assert deal["currency"] == "USD"
    assert deal["fiscal_year_end_month"] == 12
    assert deal["created_at"]


def test_create_deal_validation(client: TestClient) -> None:
    response = client.post("/api/v1/deals", json={"name": "x"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION"


def test_get_deal(client: TestClient) -> None:
    deal = _create(client)
    response = client.get(f"/api/v1/deals/{deal['id']}")
    assert response.status_code == 200
    assert response.json()["company_name"] == "Northwind SaaS"


def test_get_deal_404(client: TestClient) -> None:
    response = client.get("/api/v1/deals/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_list_deals_summary_fields(client: TestClient) -> None:
    _create(client)
    response = client.get("/api/v1/deals")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["document_count"] == 0
    assert item["last_run_status"] is None
    assert item["open_contradictions"] == 0


def test_list_deals_pagination(client: TestClient) -> None:
    for i in range(7):
        _create(client, f"Co{i}")

    first = client.get("/api/v1/deals", params={"limit": 3}).json()
    assert len(first["items"]) == 3
    assert first["next_cursor"]

    seen = {d["id"] for d in first["items"]}
    cursor = first["next_cursor"]
    while cursor:
        page = client.get(
            "/api/v1/deals", params={"limit": 3, "cursor": cursor}
        ).json()
        for item in page["items"]:
            assert item["id"] not in seen
            seen.add(item["id"])
        cursor = page["next_cursor"]
    assert len(seen) == 7


def test_update_deal(client: TestClient) -> None:
    deal = _create(client)
    response = client.patch(
        f"/api/v1/deals/{deal['id']}",
        json={"stage": "growth", "fiscal_year_end_month": 6},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "growth"
    assert body["fiscal_year_end_month"] == 6
    assert body["name"] == deal["name"]


def test_delete_deal_soft_then_404(client: TestClient) -> None:
    deal = _create(client)
    response = client.delete(f"/api/v1/deals/{deal['id']}")
    assert response.status_code == 204

    assert client.get(f"/api/v1/deals/{deal['id']}").status_code == 404
    ids = [d["id"] for d in client.get("/api/v1/deals").json()["items"]]
    assert deal["id"] not in ids
