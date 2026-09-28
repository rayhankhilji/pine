"""Entity and relation vocabularies for the knowledge graph (ARCHITECTURE §4, F-04)."""

import re
import unicodedata
from enum import StrEnum

_SUFFIXES = (
    "inc",
    "incorporated",
    "llc",
    "llp",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "gmbh",
    "sas",
    "plc",
)
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_entity_name(name: str) -> str:
    """Canonical comparison key: lowercase, punctuation stripped, legal suffixes removed."""
    text = unicodedata.normalize("NFKD", name).lower()
    text = _PUNCT_RE.sub(" ", text)
    tokens = [t for t in _WS_RE.split(text) if t and t not in _SUFFIXES]
    return " ".join(tokens)


class EntityType(StrEnum):
    company = "company"
    customer = "customer"
    contract = "contract"
    revenue_stream = "revenue_stream"
    invoice = "invoice"
    person = "person"
    shareholder = "shareholder"
    security_class = "security_class"
    liability = "liability"
    bank_account = "bank_account"
    employee = "employee"
    market = "market"


class RelationType(StrEnum):
    has_customer = "has_customer"
    has_contract = "has_contract"
    generates_revenue = "generates_revenue"
    billed_by = "billed_by"
    owns_shares = "owns_shares"
    employs = "employs"
    owes = "owes"
    banks_with = "banks_with"
    competes_in = "competes_in"
