"""Facts endpoints (ARCHITECTURE §5, F-05) — filters, detail, patch, 404s."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pine.facts.extractors.base import ensure_company
from pine.facts.store import EvidenceSpec, EvidenceStore
from pine.models.deal import Deal
from pine.models.document import DocType
from tests.facts.conftest import mk_chunk, mk_deal, mk_document

API = "/api/v1"


@pytest.fixture
def deal(session: Session) -> Deal:
    return mk_deal(session, "Northwind")


@pytest.fixture
def facts(session: Session, deal: Deal) -> dict[str, str]:
    """One fact per metric/source/period shape, via EvidenceStore."""
    deck = mk_document(session, deal, "deck.pptx", DocType.deck)
    fin = mk_document(session, deal, "pl.xlsx", DocType.financial_statement)
    deck_chunk = mk_chunk(session, deck, "ARR reached $12.0M in Q4 2025")
    fin_chunk = mk_chunk(
        session, fin, "Revenue FY2025 $9.7M; FY2024 $8.1M; COGS FY2025 $3.0M"
    )
    session.commit()
    store = EvidenceStore(session, deal.id)
    company = ensure_company(store, deal)
    ev_deck = [
        EvidenceSpec(
            document_id=deck.id,
            page_no=1,
            chunk_id=deck_chunk.id,
            quote="ARR reached $12.0M in Q4 2025",
        )
    ]
    ev_fin = [
        EvidenceSpec(
            document_id=fin.id,
            page_no=1,
            chunk_id=fin_chunk.id,
            quote="Revenue FY2025 $9.7M; FY2024 $8.1M; COGS FY2025 $3.0M",
        )
    ]
    arr = store.add_fact(
        subject_entity_id=company.id,
        metric="arr",
        value=Decimal("12000000"),
        unit="currency",
        currency="USD",
        period_type="quarter",
        period_start=date(2025, 10, 1),
        period_end=date(2025, 12, 31),
        source_kind="deck",
        extraction_method="llm",
        confidence=0.9,
        evidence=ev_deck,
    )
    rev25 = store.add_fact(
        subject_entity_id=company.id,
        metric="revenue",
        value=Decimal("9700000"),
        unit="currency",
        currency="USD",
        period_type="fiscal_year",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source_kind="financial_statement",
        extraction_method="table",
        confidence=1.0,
        evidence=ev_fin,
    )
    rev24 = store.add_fact(
        subject_entity_id=company.id,
        metric="revenue",
        value=Decimal("8100000"),
        unit="currency",
        currency="USD",
        period_type="fiscal_year",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        source_kind="financial_statement",
        extraction_method="table",
        confidence=1.0,
        evidence=ev_fin,
    )
    cogs = store.add_fact(
        subject_entity_id=company.id,
        metric="cogs",
        value=Decimal("3000000"),
        unit="currency",
        currency="USD",
        period_type="fiscal_year",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source_kind="financial_statement",
        extraction_method="table",
        confidence=1.0,
        evidence=ev_fin,
    )
    margin = store.add_fact(
        subject_entity_id=company.id,
        metric="gross_margin",
        value=Decimal("69.07"),
        unit="percent",
        period_type="fiscal_year",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source_kind="derived",
        extraction_method="derived",
        confidence=1.0,
        fact_links=[(rev25.id, "denominator"), (cogs.id, "numerator")],
    )
    session.commit()
    return {
        "arr": arr.id,
        "rev25": rev25.id,
        "rev24": rev24.id,
        "cogs": cogs.id,
        "margin": margin.id,
    }


def test_list_facts_all(
    client: TestClient, session: Session, deal: Deal, facts: dict[str, str]
) -> None:
    resp = client.get(f"{API}/deals/{deal.id}/facts")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 5
    fact = next(i for i in items if i["id"] == facts["arr"])
    assert fact["metric"] == "arr"
    assert Decimal(fact["value"]) == Decimal(12000000)
    assert fact["unit"] == "currency"
    assert fact["contested"] is False
    # embedded evidence with resolved filename + page for viewer deep links
    assert len(fact["evidence"]) == 1
    ev = fact["evidence"][0]
    assert ev["filename"] == "deck.pptx"
    assert ev["page_no"] == 1
    assert ev["quote"] == "ARR reached $12.0M in Q4 2025"


def test_list_facts_metric_filter(
    client: TestClient, deal: Deal, facts: dict[str, str]
) -> None:
    resp = client.get(f"{API}/deals/{deal.id}/facts", params={"metric": "revenue"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {i["id"] for i in items} == {facts["rev25"], facts["rev24"]}


def test_list_facts_source_kind_filter(
    client: TestClient, deal: Deal, facts: dict[str, str]
) -> None:
    resp = client.get(
        f"{API}/deals/{deal.id}/facts", params={"source_kind": "deck"}
    )
    assert [i["id"] for i in resp.json()["items"]] == [facts["arr"]]
    bad = client.get(
        f"{API}/deals/{deal.id}/facts", params={"source_kind": "nope"}
    )
    assert bad.status_code == 422


def test_list_facts_period_filter(
    client: TestClient, deal: Deal, facts: dict[str, str]
) -> None:
    # Q4 2025 window: arr (Oct–Dec 2025) overlaps; FY2025 spans it too
    resp = client.get(
        f"{API}/deals/{deal.id}/facts",
        params={"period_from": "2025-10-01", "period_to": "2025-12-31"},
    )
    ids = {i["id"] for i in resp.json()["items"]}
    assert facts["arr"] in ids
    assert facts["rev25"] in ids
    assert facts["rev24"] not in ids
    # a 2023 window matches nothing
    resp = client.get(
        f"{API}/deals/{deal.id}/facts",
        params={"period_from": "2023-01-01", "period_to": "2023-12-31"},
    )
    assert resp.json()["items"] == []


def test_list_facts_cursor(
    client: TestClient, deal: Deal, facts: dict[str, str]
) -> None:
    page1 = client.get(f"{API}/deals/{deal.id}/facts", params={"limit": 2})
    assert page1.status_code == 200
    body = page1.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    page2 = client.get(
        f"{API}/deals/{deal.id}/facts",
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert page2.status_code == 200
    ids1 = {i["id"] for i in body["items"]}
    ids2 = {i["id"] for i in page2.json()["items"]}
    assert ids1.isdisjoint(ids2)


def test_list_facts_unknown_deal(client: TestClient) -> None:
    resp = client.get(f"{API}/deals/{uuid.uuid4()}/facts")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_fact_detail_derived_from(
    client: TestClient, deal: Deal, facts: dict[str, str]
) -> None:
    resp = client.get(f"{API}/facts/{facts['margin']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "gross_margin"
    assert body["extraction_method"] == "derived"
    assert body["contradictions"] == []
    parents = {f["id"] for f in body["derived_from"]}
    assert parents == {facts["rev25"], facts["cogs"]}
    # parents serialize as full facts with evidence
    assert all(f["evidence"] for f in body["derived_from"])


def test_fact_detail_404(client: TestClient) -> None:
    resp = client.get(f"{API}/facts/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_patch_fact_notes_and_authoritative(
    client: TestClient, deal: Deal, facts: dict[str, str]
) -> None:
    resp = client.patch(
        f"{API}/facts/{facts['arr']}",
        json={"notes": "per deck", "is_authoritative": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["notes"] == "per deck"
    assert body["is_authoritative"] is True


def test_patch_fact_value_rejected(
    client: TestClient, deal: Deal, facts: dict[str, str]
) -> None:
    resp = client.patch(f"{API}/facts/{facts['arr']}", json={"value": 1})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION"


def test_patch_fact_404(client: TestClient) -> None:
    resp = client.patch(f"{API}/facts/{uuid.uuid4()}", json={"notes": "x"})
    assert resp.status_code == 404
