"""Entity extraction beyond tables: contracts and emails (F-04).

Contracts → a `contract` entity per document (named from the filename stem
or the first heading line), a `customer`/`company` party resolved from the
"between X and Y" clause or title, and `has_contract` edges.

Emails → `person` entities from From/To/Cc header lines; `employs` edges
for mailboxes on the company's own domain.

Everything goes through `EvidenceStore`: each entity/edge carries ≥ 1
evidence row quoting a verbatim span of a chunk.
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.facts.extractors.base import ensure_company
from pine.facts.store import EvidenceSpec, EvidenceStore
from pine.models.chunk import Chunk, ChunkKind
from pine.models.deal import Deal
from pine.models.document import DocStatus, DocType, Document
from pine.models.entity import Entity, Relation
from pine.schemas.entities import EntityType, RelationType, normalize_entity_name

logger = logging.getLogger(__name__)

_PROSE_KINDS = {ChunkKind.prose.value, ChunkKind.slide.value, ChunkKind.email.value}

_BETWEEN_RE = re.compile(
    r"between\s+(?P<p1>[^\n]{2,80}?)\s+and\s+"
    r"(?P<p2>[^\n]{2,80}?)\s*(?:\(|,|\.|—|\s+under\s|\s+dated\s|$)",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r"(?:order form|statement of work|sow|master services agreement|msa|agreement)"
    r"\s*[—–-]\s*(?P<party>[^\n]{2,80})",
    re.IGNORECASE,
)
_MAILBOX_RE = re.compile(
    r"^(?P<header>From|To|Cc):\s*(?P<box>[^\n]+)$", re.IGNORECASE | re.M
)
_ADDR_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass
class ExtractEntitiesStats:
    entities: int = 0
    relations: int = 0


def _filename_stem(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    pretty = re.sub(r"[_\-]+", " ", stem).strip()
    return pretty or stem


def _quote_line(text: str, needle: str) -> str | None:
    """The line/sentence containing `needle` — verbatim quote span."""
    idx = text.lower().find(needle.lower())
    if idx < 0:
        # normalised-space search fallback
        norm = " ".join(text.split())
        nidx = norm.lower().find(" ".join(needle.lower().split()))
        if nidx < 0:
            return None
        return norm[nidx : nidx + len(needle)].strip()
    left = max(text.rfind("\n", 0, idx), text.rfind(". ", 0, idx)) + 1
    right_candidates = [
        p for p in (text.find("\n", idx), text.find(". ", idx)) if p >= 0
    ]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left:right].strip()


def _document_text(session: Session, document_id: str) -> list[Chunk]:
    return list(
        session.scalars(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .where(Chunk.kind.in_(_PROSE_KINDS))
            .order_by(Chunk.page_no, Chunk.char_start)
        ).all()
    )


def _counterparty(text: str, company_norm: str) -> str | None:
    norm_text = " ".join(text.split())
    match = _BETWEEN_RE.search(norm_text)
    if match is not None:
        for key in ("p2", "p1"):
            party = match[key].strip()
            if normalize_entity_name(party) != company_norm:
                return party
    title = _TITLE_RE.search(text)
    if title is not None:
        party = title["party"].strip().rstrip(".")
        if normalize_entity_name(party) != company_norm:
            return party
    return None


def extract_contract_entities(
    session: Session, store: EvidenceStore, deal: Deal
) -> ExtractEntitiesStats:
    """One `contract` entity per contract document + has_contract edges."""
    stats = ExtractEntitiesStats()
    seen_entities = {
        r[0]
        for r in session.execute(
            select(Entity.id).where(Entity.deal_id == deal.id)
        )
    }
    seen_relations = {
        r[0]
        for r in session.execute(
            select(Relation.id).where(Relation.deal_id == deal.id)
        )
    }
    documents = session.scalars(
        select(Document)
        .where(Document.deal_id == deal.id)
        .where(Document.status == DocStatus.parsed)
        .where(Document.doc_type == DocType.contract)
        .order_by(Document.created_at)
    ).all()
    if not documents:
        return stats
    company: Entity | None = None
    company_norm = normalize_entity_name(deal.company_name)

    for doc in documents:
        chunks = _document_text(session, doc.id)
        if not chunks:
            continue
        if company is None:
            company = ensure_company(store, deal)
        text = "\n".join(c.text for c in chunks)
        party = _counterparty(text, company_norm)

        name = _filename_stem(doc.filename)
        # evidence for the contract: the line naming the counterparty,
        # else the document's first heading line
        quote = (
            _quote_line(text, party)
            if party
            else None
        ) or _quote_line(text, text.split("\n", 1)[0])
        if quote is None:
            continue
        ev = EvidenceSpec(
            document_id=doc.id,
            page_no=chunks[0].page_no,
            chunk_id=chunks[0].id,
            quote=quote,
        )
        contract = store.add_entity(
            type=EntityType.contract,
            canonical_name=name,
            evidence=[ev],
            source_document_id=doc.id,
        )
        if contract.id not in seen_entities:
            seen_entities.add(contract.id)
            stats.entities += 1
        rel = store.add_relation(
            type=RelationType.has_contract,
            source_entity_id=company.id,
            target_entity_id=contract.id,
            evidence=[ev],
        )
        if rel.id not in seen_relations:
            seen_relations.add(rel.id)
            stats.relations += 1

        if party:
            customer = store.add_entity(
                type=EntityType.customer,
                canonical_name=party,
                evidence=[ev],
                source_document_id=doc.id,
            )
            if customer.id not in seen_entities:
                seen_entities.add(customer.id)
                stats.entities += 1
            for src, tgt in ((company, customer), (customer, contract)):
                rel = store.add_relation(
                    type=(
                        RelationType.has_customer
                        if tgt is customer
                        else RelationType.has_contract
                    ),
                    source_entity_id=src.id,
                    target_entity_id=tgt.id,
                    evidence=[ev],
                )
                if rel.id not in seen_relations:
                    seen_relations.add(rel.id)
                    stats.relations += 1
    return stats


def _person_name(box: str) -> str | None:
    """Display name or local part for a mailbox spec."""
    box = box.strip().rstrip(";,")
    if not box:
        return None
    match = _ADDR_RE.search(box)
    if match is None:
        return None
    display = box[: match.start()].strip(" <\"'")
    if display:
        return display
    local = match[0].split("@", 1)[0]
    pretty = re.sub(r"[._+-]+", " ", local).strip()
    return pretty or match[0]


def extract_email_entities(
    session: Session, store: EvidenceStore, deal: Deal
) -> ExtractEntitiesStats:
    """`person` entities from From/To/Cc headers; employs edges on-domain."""
    stats = ExtractEntitiesStats()
    seen_entities = {
        r[0]
        for r in session.execute(
            select(Entity.id).where(Entity.deal_id == deal.id)
        )
    }
    seen_relations = {
        r[0]
        for r in session.execute(
            select(Relation.id).where(Relation.deal_id == deal.id)
        )
    }
    documents = session.scalars(
        select(Document)
        .where(Document.deal_id == deal.id)
        .where(Document.status == DocStatus.parsed)
        .where(Document.doc_type == DocType.email)
        .order_by(Document.created_at)
    ).all()
    if not documents:
        return stats
    company: Entity | None = None
    first_token = (normalize_entity_name(deal.company_name).split() or [""])[0]

    for doc in documents:
        chunks = _document_text(session, doc.id)
        for chunk in chunks:
            for m in _MAILBOX_RE.finditer(chunk.text):
                quote = m[0].strip()
                for box in m["box"].split(","):
                    name = _person_name(box)
                    if name is None:
                        continue
                    if company is None:
                        company = ensure_company(store, deal)
                    addr_m = _ADDR_RE.search(box)
                    domain = addr_m[0].split("@", 1)[1].lower() if addr_m else ""
                    person = store.add_entity(
                        type=EntityType.person,
                        canonical_name=name,
                        attrs={"email": addr_m[0] if addr_m else None},
                        evidence=[
                            EvidenceSpec(
                                document_id=doc.id,
                                page_no=chunk.page_no,
                                chunk_id=chunk.id,
                                quote=quote,
                            )
                        ],
                        source_document_id=doc.id,
                    )
                    if person.id not in seen_entities:
                        seen_entities.add(person.id)
                        stats.entities += 1
                    if first_token and first_token in domain:
                        rel = store.add_relation(
                            type=RelationType.employs,
                            source_entity_id=company.id,
                            target_entity_id=person.id,
                            evidence=[
                                EvidenceSpec(
                                    document_id=doc.id,
                                    page_no=chunk.page_no,
                                    chunk_id=chunk.id,
                                    quote=quote,
                                )
                            ],
                        )
                        if rel.id not in seen_relations:
                            seen_relations.add(rel.id)
                            stats.relations += 1
    return stats


__all__ = [
    "ExtractEntitiesStats",
    "extract_contract_entities",
    "extract_email_entities",
]
