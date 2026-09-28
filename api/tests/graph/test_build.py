"""Graph build + export on the demo room (F-04.AC1/AC2)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import pine.models  # noqa: F401
from pine.facts.extractors import run_extractors
from pine.facts.llm_extract import extract_facts
from pine.graph.build import build_graph
from pine.graph.export import export_graphml, export_json
from pine.models.deal import Deal
from pine.models.entity import Entity, EntityAlias, Relation
from pine.models.evidence import Evidence


def test_build_graph_demo_room(session: Session, demo_deal: Deal) -> None:
    deal = demo_deal
    run_extractors(session, deal.id)
    extract_facts(session, deal.id)
    build_graph(session, deal.id)
    session.commit()

    # contract entities for the five contract docs
    contracts = session.scalar(
        select(func.count())
        .select_from(Entity)
        .where(Entity.deal_id == deal.id)
        .where(Entity.type == "contract")
        .where(Entity.merged_into_id.is_(None))
    )
    assert contracts == 5

    # F-04.AC1 — company Northwind with ≥20 has_customer edges, all evidenced
    company = session.scalar(
        select(Entity)
        .where(Entity.deal_id == deal.id)
        .where(Entity.type == "company")
        .where(Entity.normalized_name == "northwind")
        .where(Entity.merged_into_id.is_(None))
    )
    assert company is not None
    edges = session.scalars(
        select(Relation)
        .where(Relation.deal_id == deal.id)
        .where(Relation.type == "has_customer")
        .where(Relation.source_entity_id == company.id)
    ).all()
    assert len(edges) >= 20
    orphans = [
        r
        for r in edges
        if not session.scalar(
            select(func.count())
            .select_from(Evidence)
            .where(Evidence.target_kind == "relation")
            .where(Evidence.target_id == r.id)
        )
    ]
    assert not orphans

    # F-04.AC2 — "ACME Corporation" in the MSA resolved onto the CSV customer
    acme = session.scalar(
        select(Entity)
        .where(Entity.deal_id == deal.id)
        .where(Entity.type == "customer")
        .where(Entity.normalized_name == "acme")
        .where(Entity.merged_into_id.is_(None))
    )
    assert acme is not None
    alias_forms = {
        r[0]
        for r in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == acme.id)
        )
    }
    assert {"Acme Corporation", "ACME Corporation"} <= alias_forms

    # people from email headers; employs edges only on the company domain
    people = session.scalars(
        select(Entity)
        .where(Entity.deal_id == deal.id)
        .where(Entity.type == "person")
        .where(Entity.merged_into_id.is_(None))
    ).all()
    emails = {p.attrs.get("email") for p in people}
    assert "cfo@northwind.example" in emails
    employs = session.scalar(
        select(func.count())
        .select_from(Relation)
        .where(Relation.deal_id == deal.id)
        .where(Relation.type == "employs")
    )
    assert employs and employs >= 2  # cfo + counsel on northwind.example

    # export shapes
    payload = export_json(session, deal.id)
    assert {n["id"] for n in payload["nodes"]} >= {company.id, acme.id}
    assert all({"id", "type", "name"} <= set(n) for n in payload["nodes"])
    assert all({"id", "type", "source", "target"} <= set(e) for e in payload["edges"])

    graphml = export_graphml(session, deal.id)
    assert "<graphml" in graphml and "has_customer" in graphml

    # re-run is idempotent — no new entities/edges, merges don't regress
    again = build_graph(session, deal.id)
    assert again.merged == 0


def test_build_graph_empty_deal(session: Session) -> None:
    from tests.facts.conftest import mk_deal

    deal = mk_deal(session, "EmptyCo")
    stats = build_graph(session, deal.id)
    assert stats.entities == 0
    assert export_json(session, deal.id) == {"nodes": [], "edges": []}
