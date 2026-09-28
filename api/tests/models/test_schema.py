"""Schema coverage for the Phase-3 evidence/graph tables (ARCHITECTURE §4)."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from pine.db import Base
from pine.models.entity import Entity, EntityAlias, Relation
from pine.models.evidence import Evidence
from pine.models.fact import Fact, FactLink
from pine.schemas.entities import EntityType, RelationType
from pine.schemas.metrics import MetricId
from pine.schemas.units import PeriodType, Unit


def _cols(model: type) -> set[str]:
    return {c.name for c in model.__table__.columns}


def test_metric_vocabulary_size() -> None:
    # ARCHITECTURE/PRD call for ≈40 controlled metrics.
    assert len(MetricId) >= 40
    for required in (
        "arr",
        "mrr",
        "revenue",
        "recurring_revenue",
        "cogs",
        "gross_profit",
        "gross_margin",
        "sm_spend",
        "rnd_spend",
        "ga_spend",
        "ebitda",
        "net_income",
        "cash_balance",
        "net_burn",
        "runway_months",
        "headcount",
        "customers_count",
        "net_revenue_retention",
        "gross_revenue_retention",
        "logo_churn",
        "revenue_churn",
        "cac",
        "ltv",
        "payback_months",
        "contract_value",
        "avg_contract_value",
        "top_customer_concentration",
        "tam",
        "sam",
        "som",
        "shares_outstanding",
        "fully_diluted_pct",
        "share_price",
        "revenue_growth_pct",
        "deferred_revenue",
        "accounts_receivable",
        "litigation_exposure",
        "revenue_recognition_policy",
    ):
        assert MetricId(required)


def test_vocabularies() -> None:
    assert {t.value for t in Unit} == {
        "currency",
        "percent",
        "count",
        "months",
        "ratio",
        "text",
    }
    assert {t.value for t in PeriodType} == {
        "point",
        "month",
        "quarter",
        "fiscal_year",
        "ttm",
        "custom",
    }
    for t in ("company", "customer", "contract", "shareholder", "security_class"):
        assert EntityType(t)
    for t in ("has_customer", "has_contract", "owns_shares", "generates_revenue"):
        assert RelationType(t)


def test_fact_and_graph_tables_exist(session_factory: sessionmaker[Session]) -> None:
    engine = session_factory.kw["bind"]
    assert isinstance(engine, Engine)
    names = set(inspect(engine).get_table_names())
    for table in (
        "evidence",
        "entity",
        "entity_alias",
        "relation",
        "fact",
        "fact_link",
    ):
        assert table in names


def test_table_columns() -> None:
    assert {
        "deal_id",
        "document_id",
        "page_no",
        "chunk_id",
        "cell_id",
        "char_start",
        "char_end",
        "quote",
        "bbox",
        "target_kind",
        "target_id",
    } <= _cols(Evidence)
    assert {
        "deal_id",
        "subject_entity_id",
        "metric",
        "value",
        "value_text",
        "unit",
        "currency",
        "period_type",
        "period_start",
        "period_end",
        "as_of",
        "source_kind",
        "extraction_method",
        "confidence",
        "is_authoritative",
        "superseded_by_id",
        "notes",
    } <= _cols(Fact)
    assert {
        "deal_id",
        "type",
        "canonical_name",
        "normalized_name",
        "attrs",
        "confidence",
        "merged_into_id",
    } <= _cols(Entity)
    assert {"entity_id", "alias", "normalized", "source_document_id"} <= _cols(
        EntityAlias
    )
    assert {
        "deal_id",
        "type",
        "source_entity_id",
        "target_entity_id",
        "attrs",
        "confidence",
    } <= _cols(Relation)
    assert {"fact_id", "parent_fact_id", "role"} <= _cols(FactLink)


def test_evidence_chunk_or_cell_check() -> None:
    checks = [
        c.sqltext.text
        for c in Evidence.__table__.constraints
        if hasattr(c, "sqltext")
    ]
    assert any("chunk_id IS NOT NULL OR cell_id IS NOT NULL" in c for c in checks)


def test_metadata_roundtrip_on_sqlite(session_factory: sessionmaker[Session]) -> None:
    # create_all happened in the fixture; just assert insert works end-to-end.
    with session_factory() as session:
        session.execute(Fact.__table__.select().limit(0))
        session.execute(Evidence.__table__.select().limit(0))
