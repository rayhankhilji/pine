"""Entity resolution — alias hits + fuzzy merge, provenance preserved."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.facts.extractors.base import ensure_company
from pine.facts.store import EvidenceSpec, EvidenceStore
from pine.graph.resolve import merge_entities, resolve_entities
from pine.models.deal import Deal
from pine.models.document import DocType
from pine.models.entity import Entity, EntityAlias, Relation
from pine.models.evidence import Evidence
from pine.models.fact import Fact
from tests.facts.conftest import mk_chunk, mk_deal, mk_document


def _setup(
    session: Session, deal: Deal, text: str = "Northwind deck text"
) -> tuple[EvidenceStore, list[EvidenceSpec]]:
    doc = mk_document(session, deal, "deck.pdf", DocType.deck)
    chunk = mk_chunk(session, doc, text)
    store = EvidenceStore(session, deal.id)
    ev = [
        EvidenceSpec(
            document_id=doc.id, page_no=1, chunk_id=chunk.id, quote=text[:40]
        )
    ]
    return store, ev


def _live(session: Session, deal_id: str, type_: str) -> list[Entity]:
    return list(
        session.scalars(
            select(Entity)
            .where(Entity.deal_id == deal_id)
            .where(Entity.type == type_)
            .where(Entity.merged_into_id.is_(None))
        ).all()
    )


def _aliases(session: Session, entity_id: str) -> set[str]:
    return {
        r[0]
        for r in session.execute(
            select(EntityAlias.alias).where(EntityAlias.entity_id == entity_id)
        )
    }


def test_fuzzy_merge_token_subset(session: Session) -> None:
    """'Northwind' + 'Northwind SaaS' (token_set ≥ 92) → one company."""
    deal = mk_deal(session, "Northwind")
    store, ev = _setup(session, deal, "Northwind SaaS deck")
    a = store.add_entity(
        type="company", canonical_name="Northwind", evidence=ev
    )
    b = store.add_entity(
        type="company", canonical_name="Northwind SaaS", evidence=ev
    )
    assert a.id != b.id
    stats = resolve_entities(session, deal.id)
    assert stats.merged == 1
    companies = _live(session, deal.id, "company")
    assert len(companies) == 1
    loser = companies[0].id == a.id and b or a
    merged_row = session.get(Entity, loser.id)
    assert merged_row is not None and merged_row.merged_into_id == companies[0].id
    assert _aliases(session, companies[0].id) == {"Northwind", "Northwind SaaS"}


def test_alias_hit_merge(session: Session) -> None:
    """Entity whose normalised name is another's alias → merged."""
    deal = mk_deal(session, "Acme Corp")
    store, ev = _setup(session, deal)
    a = store.add_entity(
        type="customer", canonical_name="Acme Corporation", evidence=ev
    )
    # an alias seen on a different document
    store.add_alias(a, "ACME Corporation")
    # add_entity already dedupes exact normalised names → same row
    again = store.add_entity(
        type="customer", canonical_name="Acme Corporation", evidence=ev
    )
    assert again.id == a.id
    # a distinct normalised name that still fuzzy-matches the alias
    store.add_entity(
        type="customer", canonical_name="ACME Corp West", evidence=ev
    )
    stats = resolve_entities(session, deal.id)
    customers = _live(session, deal.id, "customer")
    assert stats.merged >= 1
    assert len(customers) == 1


def test_different_types_not_merged(session: Session) -> None:
    deal = mk_deal(session, "Acme Corp")
    store, ev = _setup(session, deal)
    store.add_entity(type="customer", canonical_name="Northwind", evidence=ev)
    store.add_entity(
        type="shareholder", canonical_name="Northwind Ventures", evidence=ev
    )
    stats = resolve_entities(session, deal.id)
    assert stats.merged == 0
    assert len(_live(session, deal.id, "customer")) == 1
    assert len(_live(session, deal.id, "shareholder")) == 1


def test_dissimilar_names_not_merged(session: Session) -> None:
    deal = mk_deal(session, "Acme Corp")
    store, ev = _setup(session, deal)
    store.add_entity(type="customer", canonical_name="Helios Logistics", evidence=ev)
    store.add_entity(type="customer", canonical_name="Borealis Health", evidence=ev)
    stats = resolve_entities(session, deal.id)
    assert stats.merged == 0
    assert len(_live(session, deal.id, "customer")) == 2


def test_merge_repoints_facts_evidence_relations(session: Session) -> None:
    deal = mk_deal(session, "Northwind")
    store, ev = _setup(session, deal)
    company = ensure_company(store, deal)
    a = store.add_entity(type="customer", canonical_name="Acme Corporation", evidence=ev)
    b = store.add_entity(type="customer", canonical_name="Acme Corp West", evidence=ev)

    # give each an evidence row + b a fact and a relation
    fact_b = store.add_fact(
        subject_entity_id=b.id,
        metric="contract_value",
        value=Decimal("6700000"),
        unit="currency",
        currency="USD",
        period_type="custom",
        period_start=date(2025, 1, 1),
        period_end=date(2027, 12, 31),
        source_kind="contract",
        extraction_method="llm",
        evidence=ev,
    )
    rel_b = store.add_relation(
        type="has_customer",
        source_entity_id=company.id,
        target_entity_id=b.id,
        evidence=ev,
    )
    rel_a = store.add_relation(
        type="has_customer",
        source_entity_id=company.id,
        target_entity_id=a.id,
        evidence=ev,
    )

    merge_entities(store, a, b)

    assert session.get(Entity, b.id).merged_into_id == a.id  # type: ignore[union-attr]
    fact = session.get(Fact, fact_b.id)
    assert fact is not None and fact.subject_entity_id == a.id
    # evidence rows targeting the entity now point at the winner
    evs = session.scalars(
        select(Evidence)
        .where(Evidence.target_kind == "entity")
        .where(Evidence.target_id == a.id)
    ).all()
    assert len(evs) >= 2
    # duplicate has_customer edge folded into the kept relation
    assert session.get(Relation, rel_b.id) is None
    kept = session.get(Relation, rel_a.id)
    assert kept is not None
    rel_evs = session.scalars(
        select(Evidence)
        .where(Evidence.target_kind == "relation")
        .where(Evidence.target_id == rel_a.id)
    ).all()
    assert len(rel_evs) == 2
    # aliases preserved on the winner
    assert "Acme Corp West" in _aliases(session, a.id)
