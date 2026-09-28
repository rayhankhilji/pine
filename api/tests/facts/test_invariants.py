"""EvidenceStore invariants (ADR-003, F-04.AC3, F-05): nothing persists without evidence."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pine.facts.store import (
    EvidenceInvalid,
    EvidenceRequired,
    EvidenceSpec,
    EvidenceStore,
    whitespace_normalize,
)
from pine.models.chunk import Chunk
from pine.models.deal import Deal
from pine.models.document import (
    Blob,
    Cell,
    Document,
    Page,
    Table,
)
from pine.models.entity import Entity
from pine.models.evidence import Evidence
from pine.models.fact import ExtractionMethod, Fact
from pine.schemas.entities import EntityType, RelationType
from pine.schemas.units import PeriodType, Unit

CHUNK_TEXT = "ARR reached $12.0M in Q4 2025, up 3x   YoY\nacross segments."


@pytest.fixture
def env(session: Session) -> dict[str, str]:
    deal = Deal(name="D", company_name="Acme")
    blob = Blob(sha256="x" * 64, size_bytes=1, mime="text/plain", path="b")
    session.add_all([deal, blob])
    session.flush()
    doc = Document(
        deal_id=deal.id, blob_id=blob.id, filename="f.pdf", path="f.pdf", ext="pdf"
    )
    session.add(doc)
    session.flush()
    page = Page(document_id=doc.id, page_no=1, text=CHUNK_TEXT)
    session.add(page)
    session.flush()
    chunk = Chunk(
        deal_id=deal.id,
        document_id=doc.id,
        page_no=1,
        text=CHUNK_TEXT,
        token_count=10,
        char_start=0,
        char_end=len(CHUNK_TEXT),
        text_hash="h",
    )
    table = Table(page_id=page.id, order=0, n_rows=2, n_cols=2)
    session.add_all([chunk, table])
    session.flush()
    cell = Cell(table_id=table.id, row=1, col=1, text="4,100,000", ref="B2")
    session.add(cell)
    session.flush()
    return {
        "deal": deal.id,
        "doc": doc.id,
        "chunk": chunk.id,
        "cell": cell.id,
    }


@pytest.fixture
def store(session: Session, env: dict[str, str]) -> EvidenceStore:
    return EvidenceStore(session, env["deal"])


def _mk_entity(store: EvidenceStore, env: dict[str, str]) -> Entity:
    return store.add_entity(
        type=EntityType.company,
        canonical_name="Acme",
        evidence=[
            EvidenceSpec(
                document_id=env["doc"],
                page_no=1,
                quote="ARR reached $12.0M",
                chunk_id=env["chunk"],
            )
        ],
    )


# ----------------------------------------------------------------------
# whitespace normalisation


def test_whitespace_normalize() -> None:
    assert whitespace_normalize("a  b\n\tc  ") == "a b c"
    assert whitespace_normalize("") == ""


# ----------------------------------------------------------------------
# add_evidence


def test_evidence_quote_must_be_substring(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    with pytest.raises(EvidenceInvalid):
        store.add_evidence(
            env["doc"], 1, "revenue was $9.7M", chunk_id=env["chunk"]
        )
    with pytest.raises(EvidenceInvalid):
        store.add_evidence(env["doc"], 1, "123", cell_id=env["cell"])
    with pytest.raises(EvidenceInvalid):
        store.add_evidence(env["doc"], 1, "   ", chunk_id=env["chunk"])


def test_evidence_quote_whitespace_normalised(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    # the quote collapses "3x   YoY" while the chunk keeps the wide spacing
    ev = store.add_evidence(
        env["doc"], 1, "up 3x YoY\nacross segments.", chunk_id=env["chunk"]
    )
    assert ev.id
    ev2 = store.add_evidence(
        env["doc"], 1, "$12.0M in Q4 2025", chunk_id=env["chunk"]
    )
    assert ev2.char_start == CHUNK_TEXT.find("$12.0M in Q4 2025")


def test_evidence_cell_source(store: EvidenceStore, env: dict[str, str]) -> None:
    ev = store.add_evidence(env["doc"], 1, "4,100,000", cell_id=env["cell"])
    assert ev.cell_id == env["cell"]


def test_evidence_requires_chunk_or_cell(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    with pytest.raises(EvidenceInvalid):
        store.add_evidence(env["doc"], 1, "ARR")


def test_evidence_db_check_constraint(
    session: Session, env: dict[str, str]
) -> None:
    session.add(
        Evidence(
            deal_id=env["deal"],
            document_id=env["doc"],
            page_no=1,
            quote="x",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_evidence_wrong_deal_chunk(
    session: Session, store: EvidenceStore, env: dict[str, str]
) -> None:
    other_deal = Deal(name="O", company_name="Other")
    session.add(other_deal)
    session.flush()
    foreign = Chunk(
        deal_id=other_deal.id,
        document_id=env["doc"],
        page_no=1,
        text=CHUNK_TEXT,
        token_count=1,
        char_start=0,
        char_end=1,
        text_hash="z",
    )
    session.add(foreign)
    session.flush()
    with pytest.raises(EvidenceInvalid):
        store.add_evidence(env["doc"], 1, "ARR", chunk_id=foreign.id)


def test_link_evidence_stub_and_copy(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    stub = store.add_evidence(
        env["doc"], 1, "ARR reached $12.0M", chunk_id=env["chunk"]
    )
    entity = _mk_entity(store, env)
    linked = store.link_evidence(stub, "entity", entity.id)
    assert linked.target_id == entity.id
    # linking an attached row to a second target copies it
    copy = store.link_evidence(stub, "relation", "some-target")
    assert copy.id != stub.id
    assert copy.target_kind == "relation"
    assert stub.target_id == entity.id  # original untouched


# ----------------------------------------------------------------------
# add_fact invariants


def _fact_kwargs(env: dict[str, str], entity: Entity) -> dict[str, object]:
    return {
        "subject_entity_id": entity.id,
        "metric": "arr",
        "value": 12_000_000,
        "unit": Unit.currency,
        "currency": "USD",
        "period_type": PeriodType.quarter,
        "source_kind": "deck",
        "extraction_method": ExtractionMethod.llm,
    }


def test_add_fact_requires_evidence(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    entity = _mk_entity(store, env)
    for method in ("table", "llm", "manual"):
        with pytest.raises(EvidenceRequired):
            store.add_fact(
                **{  # type: ignore[arg-type]
                    **_fact_kwargs(env, entity),
                    "extraction_method": method,
                }
            )


def test_add_derived_fact_requires_links(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    entity = _mk_entity(store, env)
    with pytest.raises(EvidenceRequired):
        store.add_fact(
            **{  # type: ignore[arg-type]
                **_fact_kwargs(env, entity),
                "extraction_method": "derived",
                "metric": "runway_months",
                "unit": Unit.months,
            }
        )


def test_add_fact_happy_path(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    entity = _mk_entity(store, env)
    fact = store.add_fact(
        **{
            **_fact_kwargs(env, entity),
            "period_start": __import__("datetime").date(2025, 10, 1),
            "period_end": __import__("datetime").date(2025, 12, 31),
            "confidence": 0.9,
            "evidence": [
                EvidenceSpec(
                    document_id=env["doc"],
                    page_no=1,
                    quote="ARR reached $12.0M in Q4 2025",
                    chunk_id=env["chunk"],
                )
            ],
        }
    )
    assert isinstance(fact, Fact)
    ev = store.evidence_for("fact", fact.id)
    assert len(ev) == 1
    assert ev[0].quote == "ARR reached $12.0M in Q4 2025"


def test_add_fact_rejects_bad_quote_in_spec(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    entity = _mk_entity(store, env)
    with pytest.raises(EvidenceInvalid):
        store.add_fact(
            **{  # type: ignore[arg-type]
                **_fact_kwargs(env, entity),
                "evidence": [
                    EvidenceSpec(
                        document_id=env["doc"],
                        page_no=1,
                        quote="not in the chunk",
                        chunk_id=env["chunk"],
                    )
                ],
            }
        )


def test_add_fact_with_existing_evidence_id(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    entity = _mk_entity(store, env)
    stub = store.add_evidence(
        env["doc"], 1, "ARR reached $12.0M", chunk_id=env["chunk"]
    )
    fact = store.add_fact(
        **{  # type: ignore[arg-type]
            **_fact_kwargs(env, entity),
            "evidence": [stub.id],
        }
    )
    assert stub.target_id == fact.id


def test_derived_fact_with_links(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    entity = _mk_entity(store, env)
    spec = EvidenceSpec(
        document_id=env["doc"],
        page_no=1,
        quote="ARR reached $12.0M",
        chunk_id=env["chunk"],
    )
    parent = store.add_fact(
        **{  # type: ignore[arg-type]
            **_fact_kwargs(env, entity),
            "metric": "cash_balance",
            "evidence": [spec],
        }
    )
    derived = store.add_fact(
        **{  # type: ignore[arg-type]
            **_fact_kwargs(env, entity),
            "metric": "runway_months",
            "unit": Unit.months,
            "value": 14,
            "extraction_method": "derived",
            "fact_links": [(parent.id, "numerator")],
        }
    )
    assert derived.extraction_method == "derived"


# ----------------------------------------------------------------------
# entity / relation invariants


def test_add_entity_requires_evidence(store: EvidenceStore) -> None:
    with pytest.raises(EvidenceRequired):
        store.add_entity(type=EntityType.customer, canonical_name="Acme Corp.")


def test_add_relation_requires_evidence(
    store: EvidenceStore, env: dict[str, str]
) -> None:
    a = _mk_entity(store, env)
    b = store.add_entity(
        type=EntityType.customer,
        canonical_name="Beta LLC",
        evidence=[
            EvidenceSpec(
                document_id=env["doc"], page_no=1,
                quote="ARR reached $12.0M", chunk_id=env["chunk"],
            )
        ],
    )
    with pytest.raises(EvidenceRequired):
        store.add_relation(
            type=RelationType.has_customer,
            source_entity_id=a.id,
            target_entity_id=b.id,
        )


def test_add_entity_and_relation_happy(
    session: Session, store: EvidenceStore, env: dict[str, str]
) -> None:
    company = _mk_entity(store, env)
    spec = EvidenceSpec(
        document_id=env["doc"], page_no=1,
        quote="up 3x YoY", chunk_id=env["chunk"],
    )
    customer = store.add_entity(
        type=EntityType.customer, canonical_name="Beta, LLC", evidence=[spec]
    )
    rel = store.add_relation(
        type=RelationType.has_customer,
        source_entity_id=company.id,
        target_entity_id=customer.id,
        evidence=[spec],
    )
    assert rel.type == "has_customer"
    # dedupe: same entity again returns the same row + alias recorded
    again = store.add_entity(
        type=EntityType.customer, canonical_name="Beta LLC", evidence=[spec]
    )
    assert again.id == customer.id
    # relation dedupe
    again_rel = store.add_relation(
        type=RelationType.has_customer,
        source_entity_id=company.id,
        target_entity_id=customer.id,
        evidence=[spec],
    )
    assert again_rel.id == rel.id
    n_ev = len(store.evidence_for("relation", rel.id))
    assert n_ev == 2
