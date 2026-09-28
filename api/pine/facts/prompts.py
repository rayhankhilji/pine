"""Prompt construction for LLM fact extraction (ARCHITECTURE §10, F-05).

The user message is deliberately machine-parseable — the deterministic
FakeLLM reads the same `---BEGIN TEXT---`/`---END TEXT---` markers and
`Default period:` line a real model would see.
"""

from pine.llm.base import Message
from pine.models.chunk import Chunk
from pine.models.deal import Deal
from pine.models.document import Document
from pine.schemas.metrics import MetricId
from pine.schemas.units import Unit

# metrics the LLM may emit — internal bank aggregates stay table-only
EXTRACTABLE_METRICS = [
    m.value
    for m in MetricId
    if m.value not in {"revenue_inflow", "bank_inflows"}
]
_UNITS = [u.value for u in Unit]

SYSTEM_PROMPT = """\
You are a financial fact extractor for a due-diligence engine.

Extract quantitative claims from the text. For EVERY fact return:
- metric: one of the allowed metric ids (listed below) — nothing else
- value: the numeric value as a plain number (write 12000000, not "12M");
  null when the claim is non-numeric
- value_text: the claim text when value is null, else null
- unit: one of {units}
- currency: ISO 4217 code when unit is currency (default from context)
- period_label: the period wording VERBATIM from the text
  ("FY2024", "Q4 2025", "Dec-25", "TTM Mar 2026", "as of 31 Dec 2025",
  "2025-01-01 to 2027-12-31"); use the Default period when the sentence
  carries none; null when no period applies at all
- subject_hint: the entity the fact is about when it is not the company
  itself (a customer, shareholder, …), else null
- evidence_quote: a VERBATIM substring of the text backing this fact —
  copied character-for-character, never paraphrased
- confidence: 0.0–1.0

Allowed metrics: {metrics}

Rules:
- Every fact must have a non-empty evidence_quote from the text.
- Never infer values that are not stated; do not compute sums or ratios.
- One fact per distinct claim; skip pure prose with no metric.
""".format(units=", ".join(_UNITS), metrics=", ".join(EXTRACTABLE_METRICS))


def extraction_messages(
    *,
    document: Document,
    chunk: Chunk,
    deal: Deal,
    default_period_label: str | None = None,
) -> list[Message]:
    """System + user message for one chunk's extraction call."""
    doc_date = document.doc_date.isoformat() if document.doc_date else "unknown"
    user = (
        f"Document: {document.filename} (type: {document.doc_type})\n"
        f"Document date: {doc_date}\n"
        f"Company: {deal.company_name}\n"
        f"Deal currency: {deal.currency}\n"
        f"Deal fiscal year end month: {deal.fiscal_year_end_month}\n"
        f"Default period: {default_period_label or 'none'}\n"
        "---BEGIN TEXT---\n"
        f"{chunk.text}\n"
        "---END TEXT---"
    )
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user),
    ]
