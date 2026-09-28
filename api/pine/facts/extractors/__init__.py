"""Table-extractor registry (ARCHITECTURE §10, F-05).

`run_extractors` walks every table of every parsed document in the deal,
scores each registered extractor with `match` and runs those at or above
`MATCH_THRESHOLD`, best confidence first.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.facts.extractors.bank_statement import BankStatementExtractor
from pine.facts.extractors.base import MATCH_THRESHOLD, Extractor, TableGrid
from pine.facts.extractors.cap_table import CapTableExtractor
from pine.facts.extractors.customer_list import CustomerListExtractor
from pine.facts.extractors.pnl import PnlExtractor
from pine.facts.store import EvidenceStore
from pine.models.deal import Deal
from pine.models.document import DocStatus, Document, Page, Table

logger = logging.getLogger(__name__)

EXTRACTORS: list[Extractor] = [
    BankStatementExtractor(),
    CustomerListExtractor(),
    CapTableExtractor(),
    PnlExtractor(),  # last: generic row-label matching, lowest selectivity
]


def run_extractors(session: Session, deal_id: str) -> int:
    """Run all matching table extractors over the deal; returns facts written."""
    deal = session.get(Deal, deal_id)
    if deal is None:
        raise ValueError(f"deal {deal_id} not found")
    store = EvidenceStore(session, deal_id)

    rows = session.execute(
        select(Table, Document)
        .join(Page, Table.page_id == Page.id)
        .join(Document, Page.document_id == Document.id)
        .where(Document.deal_id == deal_id)
        .where(Document.status == DocStatus.parsed)
        .order_by(Document.created_at, Table.created_at)
    ).all()

    written = 0
    for table, document in rows:
        grid = TableGrid.load(session, table)
        scored = sorted(
            (
                (extractor.match(grid, document, deal), extractor)
                for extractor in EXTRACTORS
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        for confidence, extractor in scored:
            if confidence < MATCH_THRESHOLD:
                continue
            n = extractor.extract(grid, document, store, deal)
            if n:
                logger.info(
                    "extractor %s wrote %d facts from %s (%s)",
                    extractor.name,
                    n,
                    document.filename,
                    document.id,
                )
                written += n
    return written


__all__ = [
    "EXTRACTORS",
    "MATCH_THRESHOLD",
    "Extractor",
    "TableGrid",
    "run_extractors",
]
