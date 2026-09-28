"""EvidenceStore — the only writer of Evidence/Fact/Entity/Relation (ADR-003).

Invariants enforced here (and in `tests/facts/test_invariants.py`):

* Every `Evidence` row references a `chunk_id` or a `cell_id` and its
  `quote` must be a whitespace-normalised substring of that row's text —
  otherwise `EvidenceInvalid`.
* `add_fact` with `extraction_method != derived` requires ≥ 1 evidence item
  (spec or existing id) — otherwise `EvidenceRequired`.
* `add_fact` with `extraction_method = derived` requires ≥ 1 `FactLink`
  parent — otherwise `EvidenceRequired`.
* `add_entity` / `add_relation` likewise require ≥ 1 evidence item.

Evidence stubs: `add_evidence` may be called without a target; the row is
attached later via `link_evidence` (used by agent tools in §10). When an
already-attached row is linked to a second target, a copy is created so that
each Evidence row keeps exactly one target.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.models.chunk import Chunk
from pine.models.document import Cell, DocType
from pine.models.entity import Entity, EntityAlias, Relation
from pine.models.evidence import Evidence, EvidenceTarget
from pine.models.fact import ExtractionMethod, Fact, FactLink
from pine.schemas.entities import normalize_entity_name


class EvidenceInvalid(ValueError):
    """Quote is not a whitespace-normalised substring of the chunk/cell text."""


class EvidenceRequired(ValueError):
    """Fact/Entity/Relation/Claim was written without supporting evidence."""


def whitespace_normalize(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip ends."""
    return " ".join(text.split())


@dataclass(frozen=True)
class EvidenceSpec:
    """Describes a new evidence row to create when adding a fact/entity/relation."""

    document_id: str
    page_no: int
    quote: str
    chunk_id: str | None = None
    cell_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: list[float] | None = None


EvidenceItem = EvidenceSpec | Evidence | str


class EvidenceStore:
    def __init__(self, session: Session, deal_id: str) -> None:
        self.session = session
        self.deal_id = deal_id

    # ------------------------------------------------------------------
    # evidence rows

    def _source_text(
        self, chunk_id: str | None, cell_id: str | None
    ) -> tuple[str | None, str | None]:
        """Validate + load the backing chunk/cell; returns (text, bbox_hint)."""
        if chunk_id is None and cell_id is None:
            raise EvidenceInvalid("evidence needs a chunk_id or a cell_id")
        text: str | None = None
        if chunk_id is not None:
            chunk = self.session.get(Chunk, chunk_id)
            if chunk is None or chunk.deal_id != self.deal_id:
                raise EvidenceInvalid(f"chunk {chunk_id} not found in deal")
            text = chunk.text
        if cell_id is not None:
            cell = self.session.get(Cell, cell_id)
            if cell is None:
                raise EvidenceInvalid(f"cell {cell_id} not found")
            if text is None:
                text = cell.text
        return text, None

    def _validate_quote(self, quote: str, source_text: str) -> None:
        if not quote.strip():
            raise EvidenceInvalid("empty evidence quote")
        if whitespace_normalize(quote) not in whitespace_normalize(source_text):
            raise EvidenceInvalid("quote is not a substring of the source text")

    def add_evidence(
        self,
        document_id: str,
        page_no: int,
        quote: str,
        *,
        chunk_id: str | None = None,
        cell_id: str | None = None,
        target_kind: EvidenceTarget | str | None = None,
        target_id: str | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        bbox: list[float] | None = None,
    ) -> Evidence:
        text, _ = self._source_text(chunk_id, cell_id)
        assert text is not None
        self._validate_quote(quote, text)

        if (char_start is None or char_end is None) and chunk_id is not None:
            idx = text.find(quote)
            if idx >= 0:
                char_start, char_end = idx, idx + len(quote)

        evidence = Evidence(
            deal_id=self.deal_id,
            document_id=document_id,
            page_no=page_no,
            chunk_id=chunk_id,
            cell_id=cell_id,
            char_start=char_start,
            char_end=char_end,
            quote=quote,
            bbox=bbox,
            target_kind=str(target_kind) if target_kind is not None else None,
            target_id=target_id,
        )
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def link_evidence(
        self,
        evidence: Evidence | str,
        target_kind: EvidenceTarget | str,
        target_id: str,
    ) -> Evidence:
        """Attach `evidence` to a target; copies the row if it already has one."""
        row = (
            self.session.get(Evidence, evidence)
            if isinstance(evidence, str)
            else evidence
        )
        if row is None:
            raise EvidenceInvalid("evidence row not found")
        kind = str(target_kind)
        if row.target_id is None:
            row.target_kind = kind
            row.target_id = target_id
            self.session.flush()
            return row
        if row.target_kind == kind and row.target_id == target_id:
            return row
        copy = Evidence(
            deal_id=row.deal_id,
            document_id=row.document_id,
            page_no=row.page_no,
            chunk_id=row.chunk_id,
            cell_id=row.cell_id,
            char_start=row.char_start,
            char_end=row.char_end,
            quote=row.quote,
            bbox=list(row.bbox) if row.bbox is not None else None,
            target_kind=kind,
            target_id=target_id,
        )
        self.session.add(copy)
        self.session.flush()
        return copy

    def evidence_for(
        self, target_kind: EvidenceTarget | str, target_id: str
    ) -> list[Evidence]:
        return list(
            self.session.scalars(
                select(Evidence)
                .where(Evidence.target_kind == str(target_kind))
                .where(Evidence.target_id == target_id)
                .order_by(Evidence.created_at, Evidence.id)
            ).all()
        )

    # ------------------------------------------------------------------
    # targets

    def _attach_evidence(
        self,
        items: Sequence[EvidenceItem],
        target_kind: EvidenceTarget,
        target_id: str,
    ) -> list[Evidence]:
        rows: list[Evidence] = []
        for item in items:
            if isinstance(item, EvidenceSpec):
                rows.append(
                    self.add_evidence(
                        item.document_id,
                        item.page_no,
                        item.quote,
                        chunk_id=item.chunk_id,
                        cell_id=item.cell_id,
                        target_kind=target_kind,
                        target_id=target_id,
                        char_start=item.char_start,
                        char_end=item.char_end,
                        bbox=item.bbox,
                    )
                )
            else:
                rows.append(self.link_evidence(item, target_kind, target_id))
        return rows

    def add_fact(
        self,
        *,
        subject_entity_id: str,
        metric: str,
        value: Decimal | int | float | None = None,
        value_text: str | None = None,
        unit: str,
        currency: str | None = None,
        period_type: str,
        period_start: date | None = None,
        period_end: date | None = None,
        as_of: date | None = None,
        source_kind: DocType | str,
        extraction_method: ExtractionMethod | str,
        confidence: float = 1.0,
        evidence: Sequence[EvidenceItem] | None = None,
        fact_links: list[tuple[str, str]] | None = None,
        notes: str | None = None,
    ) -> Fact:
        method = ExtractionMethod(extraction_method)
        evidence = evidence or []
        links = fact_links or []
        if method is ExtractionMethod.derived:
            if not links:
                raise EvidenceRequired("derived fact requires ≥ 1 FactLink parent")
        elif not evidence:
            raise EvidenceRequired(
                f"{method.value} fact requires ≥ 1 evidence item"
            )

        fact = Fact(
            deal_id=self.deal_id,
            subject_entity_id=subject_entity_id,
            metric=metric,
            value=Decimal(str(value)) if value is not None else None,
            value_text=value_text,
            unit=unit,
            currency=currency,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            as_of=as_of,
            source_kind=str(source_kind),
            extraction_method=str(method),
            confidence=confidence,
            notes=notes,
        )
        self.session.add(fact)
        self.session.flush()

        self._attach_evidence(evidence, EvidenceTarget.fact, fact.id)
        for parent_id, role in links:
            self.session.add(
                FactLink(fact_id=fact.id, parent_fact_id=parent_id, role=role)
            )
        self.session.flush()
        return fact

    def add_entity(
        self,
        *,
        type: str,
        canonical_name: str,
        attrs: dict[str, Any] | None = None,
        confidence: float = 1.0,
        evidence: Sequence[EvidenceItem] | None = None,
        source_document_id: str | None = None,
    ) -> Entity:
        """Create an entity, or return the existing exact normalised match.

        An existing match still receives the new evidence rows and an alias
        row recording the observed surface form.
        """
        evidence = evidence or []
        if not evidence:
            raise EvidenceRequired("entity requires ≥ 1 evidence item")
        normalized = normalize_entity_name(canonical_name)
        existing = self.session.scalar(
            select(Entity)
            .where(Entity.deal_id == self.deal_id)
            .where(Entity.type == str(type))
            .where(Entity.normalized_name == normalized)
            .where(Entity.merged_into_id.is_(None))
        )
        entity = existing or Entity(
            deal_id=self.deal_id,
            type=str(type),
            canonical_name=canonical_name,
            normalized_name=normalized,
            attrs=attrs or {},
            confidence=confidence,
        )
        if existing is None:
            self.session.add(entity)
            self.session.flush()
        self._attach_evidence(evidence, EvidenceTarget.entity, entity.id)
        # record every observed surface form as an alias (deduped)
        self._add_alias(entity, canonical_name, source_document_id)
        return entity

    def _add_alias(
        self, entity: Entity, alias: str, source_document_id: str | None
    ) -> None:
        normalized = normalize_entity_name(alias)
        dup = self.session.scalar(
            select(func.count())
            .select_from(EntityAlias)
            .where(EntityAlias.entity_id == entity.id)
            .where(EntityAlias.normalized == normalized)
            .where(EntityAlias.alias == alias)
        )
        if not dup:
            self.session.add(
                EntityAlias(
                    entity_id=entity.id,
                    alias=alias,
                    normalized=normalized,
                    source_document_id=source_document_id,
                )
            )
            self.session.flush()

    def add_alias(
        self, entity: Entity, alias: str, source_document_id: str | None = None
    ) -> EntityAlias:
        normalized = normalize_entity_name(alias)
        row = EntityAlias(
            entity_id=entity.id,
            alias=alias,
            normalized=normalized,
            source_document_id=source_document_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def add_relation(
        self,
        *,
        type: str,
        source_entity_id: str,
        target_entity_id: str,
        attrs: dict[str, Any] | None = None,
        confidence: float = 1.0,
        evidence: Sequence[EvidenceItem] | None = None,
    ) -> Relation:
        evidence = evidence or []
        if not evidence:
            raise EvidenceRequired("relation requires ≥ 1 evidence item")
        existing = self.session.scalar(
            select(Relation)
            .where(Relation.deal_id == self.deal_id)
            .where(Relation.type == str(type))
            .where(Relation.source_entity_id == source_entity_id)
            .where(Relation.target_entity_id == target_entity_id)
        )
        relation = existing or Relation(
            deal_id=self.deal_id,
            type=str(type),
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            attrs=attrs or {},
            confidence=confidence,
        )
        if existing is None:
            self.session.add(relation)
            self.session.flush()
        self._attach_evidence(evidence, EvidenceTarget.relation, relation.id)
        return relation
