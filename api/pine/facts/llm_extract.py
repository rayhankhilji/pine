"""LLM prose fact extraction (ARCHITECTURE §10, F-05.AC2/AC3).

For every prose/slide/email chunk of relevant classified documents the
configured LLM returns an `ExtractedBatch`. Each `ExtractedFact` is
validated before persistence:

- `metric`/`unit` are checked against the controlled vocabularies
- `evidence_quote` must be a whitespace-normalised substring of the chunk
  text — rejected facts log `EVIDENCE_MISMATCH` and are NOT persisted
- `period_label` is parsed through `parse_period` under the deal's fiscal
  calendar; unparseable labels degrade to `custom`
- `subject_hint` / entity mentions resolve to deal entities (exact
  normalised match), else the fact attaches to the deal Company

Persistence goes exclusively through `EvidenceStore` with chunk-level
evidence; reruns are deduped by (subject, metric, value, period, document).
All calls go through `pine.llm.record.call_llm` for accounting + caching.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.config import Settings, get_settings
from pine.facts.extractors.base import ensure_company, fact_exists
from pine.facts.periods import PeriodSpec, parse_period
from pine.facts.prompts import extraction_messages
from pine.facts.store import EvidenceSpec, EvidenceStore, whitespace_normalize
from pine.llm.base import LLM
from pine.llm.record import call_llm
from pine.models.chunk import Chunk, ChunkKind
from pine.models.deal import Deal
from pine.models.document import DocStatus, Document
from pine.models.entity import Entity, EntityAlias
from pine.models.fact import Fact
from pine.schemas.entities import normalize_entity_name
from pine.schemas.metrics import MetricId
from pine.schemas.units import PeriodType, Unit

logger = logging.getLogger(__name__)

PURPOSE = "extract_facts"

# LLM extraction only reads prose-ish chunks — tables are handled
# deterministically by the extractor registry.
PROSE_KINDS = {
    ChunkKind.prose.value,
    ChunkKind.slide.value,
    ChunkKind.email.value,
}
_METRIC_IDS = {m.value for m in MetricId}
_UNIT_IDS = {u.value for u in Unit}
_MENTION_RE_CACHE: dict[str, re.Pattern[str]] = {}


class ExtractedFact(BaseModel):
    """One fact as returned by the LLM (strict validation upstream of store)."""

    metric: str
    value: Decimal | None = None
    value_text: str | None = None
    unit: str
    currency: str | None = None
    period_label: str | None = None
    subject_hint: str | None = None
    evidence_quote: str
    confidence: float = 0.8

    @field_validator("metric")
    @classmethod
    def _metric_in_vocab(cls, v: str) -> str:
        if v not in _METRIC_IDS:
            raise ValueError(f"unknown metric: {v}")
        return v

    @field_validator("unit")
    @classmethod
    def _unit_in_vocab(cls, v: str) -> str:
        if v not in _UNIT_IDS:
            raise ValueError(f"unknown unit: {v}")
        return v


class ExtractedBatch(BaseModel):
    facts: list[ExtractedFact] = []


@dataclass
class ExtractStats:
    chunks: int = 0
    calls: int = 0
    facts_written: int = 0
    evidence_mismatches: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)


class _EntityMentions:
    """Normalised-name → entity lookup over entities + aliases for a deal."""

    def __init__(self, session: Session, deal_id: str) -> None:
        self._by_norm: dict[str, str] = {}
        rows = session.execute(
            select(Entity.id, Entity.canonical_name, Entity.normalized_name)
            .where(Entity.deal_id == deal_id)
            .where(Entity.merged_into_id.is_(None))
        ).all()
        for entity_id, canonical, normalized in rows:
            self._by_norm.setdefault(normalized, entity_id)
            canon_norm = normalize_entity_name(canonical)
            self._by_norm.setdefault(canon_norm, entity_id)
        alias_rows = session.execute(
            select(EntityAlias.entity_id, EntityAlias.normalized)
            .join(Entity, EntityAlias.entity_id == Entity.id)
            .where(Entity.deal_id == deal_id)
            .where(Entity.merged_into_id.is_(None))
        ).all()
        for entity_id, normalized in alias_rows:
            if normalized:
                self._by_norm.setdefault(normalized, entity_id)

    def resolve(self, text: str, hint: str | None = None) -> str | None:
        """Entity id whose normalised name/alias appears in `text`."""
        norm_text = whitespace_normalize(text).lower()
        if hint:
            norm = normalize_entity_name(hint)
            if norm in self._by_norm:
                return self._by_norm[norm]
        best: tuple[int, str] | None = None
        for norm, entity_id in self._by_norm.items():
            if not norm:
                continue
            pattern = _MENTION_RE_CACHE.get(norm)
            if pattern is None:
                pattern = re.compile(rf"(?<!\w){re.escape(norm)}(?!\w)")
                _MENTION_RE_CACHE[norm] = pattern
            if pattern.search(norm_text) and (
                best is None or len(norm) > best[0]
            ):
                best = (len(norm), entity_id)
        return best[1] if best else None


def _spec_for(ef: ExtractedFact, deal: Deal) -> PeriodSpec:
    label = (ef.period_label or "").strip()
    if label:
        spec = parse_period(label, fiscal_year_end_month=deal.fiscal_year_end_month)
        if spec is not None:
            return spec
    return PeriodSpec(period_type=PeriodType.custom)


def _quote_ok(quote: str, chunk_text: str) -> bool:
    return bool(quote.strip()) and whitespace_normalize(
        quote
    ) in whitespace_normalize(chunk_text)


def _persist_fact(
    store: EvidenceStore,
    *,
    deal: Deal,
    document: Document,
    chunk: Chunk,
    ef: ExtractedFact,
    subject_id: str,
) -> bool:
    spec = _spec_for(ef, deal)
    if ef.value is None and not (ef.value_text or "").strip():
        return False
    if ef.value is not None and fact_exists(
        store,
        subject_entity_id=subject_id,
        metric=ef.metric,
        value=ef.value,
        spec=spec,
        document_id=document.id,
    ):
        return False
    store.add_fact(
        subject_entity_id=subject_id,
        metric=ef.metric,
        value=ef.value,
        value_text=ef.value_text,
        unit=ef.unit,
        currency=ef.currency or deal.currency,
        period_type=spec.period_type,
        period_start=spec.period_start,
        period_end=spec.period_end,
        as_of=spec.as_of,
        source_kind=document.doc_type,
        extraction_method="llm",
        confidence=ef.confidence,
        evidence=[
            EvidenceSpec(
                document_id=document.id,
                page_no=chunk.page_no,
                chunk_id=chunk.id,
                quote=ef.evidence_quote,
            )
        ],
    )
    return True


async def _extract_chunk(
    session: Session,
    deal: Deal,
    document: Document,
    chunk: Chunk,
    store: EvidenceStore,
    mentions: _EntityMentions,
    stats: ExtractStats,
    *,
    llm: LLM | None,
    settings: Settings,
    default_period_label: str | None,
) -> None:
    messages = extraction_messages(
        document=document,
        chunk=chunk,
        deal=deal,
        default_period_label=default_period_label,
    )
    stats.calls += 1
    try:
        result = await call_llm(
            session,
            purpose=PURPOSE,
            messages=messages,
            schema=ExtractedBatch,
            deal_id=deal.id,
            llm=llm,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001 — one bad call must not kill the run
        stats.errors.append(f"{chunk.id}: {type(exc).__name__}: {exc}")
        logger.warning("extract_facts call failed for chunk %s: %s", chunk.id, exc)
        return
    batch = result.parsed
    assert isinstance(batch, ExtractedBatch)
    company = ensure_company(store, deal)
    for ef in batch.facts:
        if not _quote_ok(ef.evidence_quote, chunk.text):
            stats.evidence_mismatches += 1
            logger.warning(
                "EVIDENCE_MISMATCH deal=%s chunk=%s metric=%s quote=%r",
                deal.id,
                chunk.id,
                ef.metric,
                ef.evidence_quote[:120],
            )
            continue
        subject_id = (
            mentions.resolve(chunk.text, ef.subject_hint) or company.id
        )
        if _persist_fact(
            store,
            deal=deal,
            document=document,
            chunk=chunk,
            ef=ef,
            subject_id=subject_id,
        ):
            stats.facts_written += 1
        else:
            stats.rejected += 1


def _reference_period_label(session: Session, deal: Deal) -> str | None:
    """Label of the most recent fiscal year already evidenced in the deal."""
    latest_end = session.scalar(
        select(func.max(Fact.period_end))
        .where(Fact.deal_id == deal.id)
        .where(Fact.period_type == PeriodType.fiscal_year.value)
        .where(Fact.period_end.isnot(None))
    )
    return f"FY{latest_end.year}" if latest_end is not None else None


def extract_facts(
    session: Session,
    deal_id: str,
    *,
    llm: LLM | None = None,
    settings: Settings | None = None,
    doc_types: set[str] | None = None,
) -> ExtractStats:
    """Run LLM extraction over the deal's prose chunks; returns stats."""
    settings = settings or get_settings()
    deal = session.get(Deal, deal_id)
    if deal is None:
        raise ValueError(f"deal {deal_id} not found")
    store = EvidenceStore(session, deal_id)
    mentions = _EntityMentions(session, deal_id)
    default_period = _reference_period_label(session, deal)

    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.deal_id == deal_id)
        .where(Document.status == DocStatus.parsed)
        .where(Chunk.kind.in_(PROSE_KINDS))
        .order_by(Chunk.created_at, Chunk.id)
    )
    if doc_types is not None:
        stmt = stmt.where(Document.doc_type.in_(doc_types))
    rows = session.execute(stmt).all()

    stats = ExtractStats(chunks=len(rows))
    for chunk, document in rows:
        asyncio.run(
            _extract_chunk(
                session,
                deal,
                document,
                chunk,
                store,
                mentions,
                stats,
                llm=llm,
                settings=settings,
                default_period_label=default_period,
            )
        )
    logger.info(
        "llm extraction deal=%s chunks=%d facts=%d mismatches=%d rejected=%d",
        deal_id,
        stats.chunks,
        stats.facts_written,
        stats.evidence_mismatches,
        stats.rejected,
    )
    return stats


__all__ = [
    "ExtractStats",
    "ExtractedBatch",
    "ExtractedFact",
    "extract_facts",
]
