"""Rule-based document classifier — filename keywords + content heuristics (no LLM)."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.models.document import DocType, Document, Page

_FILENAME_RULES: list[tuple[re.Pattern[str], DocType]] = [
    (re.compile(r"cap[ _-]?table|shareholder|equity", re.I), DocType.cap_table),
    (re.compile(r"bank[ _-]?statement|statement", re.I), DocType.bank_statement),
    (re.compile(r"customer[ _-]?list|customers|arr[ _-]?by", re.I), DocType.customer_list),
    (re.compile(r"board[ _-]?deck|board[ _-]?pack", re.I), DocType.board_deck),
    (re.compile(r"deck|pitch|series", re.I), DocType.deck),
    (
        re.compile(r"agreement|contract|msa|sow|order[ _-]?form|terms", re.I),
        DocType.contract,
    ),
    (re.compile(r"articles|bylaws|indemn|litigation|legal", re.I), DocType.legal),
    (
        re.compile(r"financial|p&l|pnl|income[ _-]?statement|balance", re.I),
        DocType.financial_statement,
    ),
]

_CONTENT_RULES: list[tuple[re.Pattern[str], DocType]] = [
    (re.compile(r"shareholder|shares|fully[ _-]diluted|preferred|common", re.I), DocType.cap_table),
    (re.compile(r"debit|credit|balance|account[ _-]?number|routing", re.I), DocType.bank_statement),
    (re.compile(r"customer|mrr|arr|segment", re.I), DocType.customer_list),
    (
        re.compile(r"revenue|cogs|ebitda|gross[ _-]profit|opex", re.I),
        DocType.financial_statement,
    ),
    (
        re.compile(r"whereas|party|termination|governing[ _-]law|confidential", re.I),
        DocType.contract,
    ),
    (re.compile(r"litigation|plaintiff|defendant|settlement", re.I), DocType.legal),
]


def classify_document(
    session: Session, document: Document
) -> tuple[DocType, float]:
    """Return (doc_type, confidence 0–1)."""
    fname = document.filename
    for pattern, doc_type in _FILENAME_RULES:
        if pattern.search(fname):
            return doc_type, 0.9

    if document.ext == "eml":
        return DocType.email, 1.0
    if document.ext == "pptx":
        return DocType.deck, 0.7

    # content heuristics on first page text
    page = session.scalar(
        select(Page).where(Page.document_id == document.id).order_by(Page.page_no)
    )
    text = (page.text if page else "").lower()
    if not text:
        return DocType.unknown, 0.0
    scores: dict[DocType, int] = {}
    for pattern, doc_type in _CONTENT_RULES:
        hits = len(pattern.findall(text))
        if hits:
            scores[doc_type] = scores.get(doc_type, 0) + hits
    if not scores:
        return DocType.other, 0.3
    best, hits = max(scores.items(), key=lambda kv: kv[1])
    confidence = min(0.95, 0.4 + hits * 0.15)
    return best, round(confidence, 2)
