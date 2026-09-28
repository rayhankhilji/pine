"""Entity and relation vocabularies for the knowledge graph (ARCHITECTURE §4, F-04)."""

from enum import StrEnum


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
