"""Graph + entity endpoints (ARCHITECTURE §5, F-04) — demo room + synthetic."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.facts.extractors import run_extractors
from pine.facts.llm_extract import extract_facts
from pine.facts.store import EvidenceSpec, EvidenceStore
from pine.graph.build import build_graph
from pine.models.deal import Deal
from pine.models.document import DocType
from pine.models.entity import Entity, EntityAlias
from tests.facts.conftest import mk_chunk, mk_deal, mk_document

API = "/api/v1"


def test_graph_demo_room(
    client: TestClient, session: Session, demo_deal: Deal
) -> None:
    run_extractors(session, demo_deal.id)
    extract_facts(session, demo_deal.id)
    build_graph(session, demo_deal.id)
    session.commit()

    resp = client.get(f"{API}/deals/{demo_deal.id}/graph")
    assert resp.status_code == 200
    body = resp.json()
    nodes, edges = body["nodes"], body["edges"]
    assert len(nodes) >= 20
    for n in nodes:
        assert {"id", "type", "canonical_name", "confidence"} <= n.keys()
    ids = {n["id"] for n in nodes}
    for e in edges:
        assert {"id", "type", "source_entity_id", "target_entity_id"} <= e.keys()
        assert e["source_entity_id"] in ids and e["target_entity_id"] in ids
    # the Company→Customer backbone exists (F-04.AC1 surface check)
    company = next(n for n in nodes if n["type"] == "company")
    has_customer = [
        e
        for e in edges
        if e["type"] == "has_customer" and e["source_entity_id"] == company["id"]
    ]
    assert len(has_customer) >= 20

    # ?types csv filters nodes; edges stay within the filtered node set
    resp = client.get(
        f"{API}/deals/{demo_deal.id}/graph", params={"types": "customer"}
    )
    body = resp.json()
    assert body["nodes"]
    assert all(n["type"] == "customer" for n in body["nodes"])
    assert all(
        e["source_entity_id"] in {n["id"] for n in body["nodes"]}
        and e["target_entity_id"] in {n["id"] for n in body["nodes"]}
        for e in body["edges"]
    )

    # bad type → 422 VALIDATION
    bad = client.get(
        f"{API}/deals/{demo_deal.id}/graph", params={"types": "nope"}
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION"

    # ?format=graphml streams GraphML
    resp = client.get(
        f"{API}/deals/{demo_deal.id}/graph", params={"format": "graphml"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/graphml+xml")
    assert "<graphml" in resp.text


def test_graph_unknown_deal(client: TestClient) -> None:
    resp = client.get(f"{API}/deals/{uuid.uuid4()}/graph")
    assert resp.status_code == 404


def _two_customers(session: Session, deal: Deal) -> tuple[Entity, Entity]:
    doc = mk_document(session, deal, "customers.csv", DocType.customer_list)
    chunk = mk_chunk(session, doc, "Acme Corporation, ARR 100000")
    store = EvidenceStore(session, deal.id)
    ev = [
        EvidenceSpec(
            document_id=doc.id,
            page_no=1,
            chunk_id=chunk.id,
            quote="Acme Corporation",
        )
    ]
    a = store.add_entity(
        type="customer", canonical_name="Acme Corporation", evidence=ev
    )
    b = store.add_entity(
        type="customer", canonical_name="Acme Corp West", evidence=ev
    )
    session.commit()
    return a, b


def test_entity_detail(client: TestClient, session: Session) -> None:
    deal = mk_deal(session, "Northwind")
    a, _b = _two_customers(session, deal)
    resp = client.get(f"{API}/entities/{a.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["canonical_name"] == "Acme Corporation"
    assert body["type"] == "customer"
    assert {al["alias"] for al in body["aliases"]} == {"Acme Corporation"}
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["filename"] == "customers.csv"
    assert body["relations"] == []
    assert body["facts"] == []


def test_entity_detail_404(client: TestClient) -> None:
    assert client.get(f"{API}/entities/{uuid.uuid4()}").status_code == 404


def test_entity_merge_and_split(client: TestClient, session: Session) -> None:
    deal = mk_deal(session, "Northwind")
    a, b = _two_customers(session, deal)

    # 409 on self-merge
    resp = client.post(
        f"{API}/entities/{a.id}/merge", json={"into_entity_id": a.id}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"
    # 404 on missing target
    resp = client.post(
        f"{API}/entities/{a.id}/merge",
        json={"into_entity_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404

    # merge b into a — winner returned, b marked merged
    resp = client.post(
        f"{API}/entities/{b.id}/merge", json={"into_entity_id": a.id}
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == a.id
    session.refresh(b)  # merge committed on the request's own session
    assert b.merged_into_id == a.id
    # merged-away entity 404s on detail
    assert client.get(f"{API}/entities/{b.id}").status_code == 404

    # split: move the distinct-named alias off `a` onto a new entity
    # (the canonical-name alias would collide with `a` itself → 409)
    alias = next(
        al
        for al in session.scalars(
            select(EntityAlias).where(EntityAlias.entity_id == a.id)
        )
        if al.normalized != a.normalized_name
    )
    resp = client.post(
        f"{API}/entities/{a.id}/split", json={"alias_ids": [alias.id]}
    )
    assert resp.status_code == 201
    new_id = resp.json()["id"]
    assert new_id != a.id
    detail = client.get(f"{API}/entities/{new_id}").json()
    assert detail["canonical_name"] == alias.alias
    assert [al["id"] for al in detail["aliases"]] == [alias.id]
    assert detail["evidence"]  # ≥1 evidence invariant preserved

    # alias on another entity → 422
    resp = client.post(
        f"{API}/entities/{a.id}/split", json={"alias_ids": [alias.id]}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION"


def test_entity_split_unknown_alias(
    client: TestClient, session: Session
) -> None:
    deal = mk_deal(session, "Northwind")
    a, _b = _two_customers(session, deal)
    resp = client.post(
        f"{API}/entities/{a.id}/split",
        json={"alias_ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 422


def test_entity_merge_404(client: TestClient) -> None:
    resp = client.post(
        f"{API}/entities/{uuid.uuid4()}/merge",
        json={"into_entity_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
