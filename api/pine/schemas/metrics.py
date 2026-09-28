"""Controlled metric vocabulary (ARCHITECTURE §4, PRD F-05).

Every `Fact.metric` is one of these ids. `revenue_inflow` / `bank_inflows`
are internal aggregates produced by the bank-statement extractor and used by
contradiction rule R7; they are not LLM-facing.
"""

from enum import StrEnum


class MetricId(StrEnum):
    # top line
    arr = "arr"
    mrr = "mrr"
    revenue = "revenue"
    recurring_revenue = "recurring_revenue"
    revenue_growth_pct = "revenue_growth_pct"
    deferred_revenue = "deferred_revenue"
    accounts_receivable = "accounts_receivable"
    revenue_recognition_policy = "revenue_recognition_policy"

    # cost / profitability
    cogs = "cogs"
    gross_profit = "gross_profit"
    gross_margin = "gross_margin"
    sm_spend = "sm_spend"
    rnd_spend = "rnd_spend"
    ga_spend = "ga_spend"
    ebitda = "ebitda"
    net_income = "net_income"

    # cash
    cash_balance = "cash_balance"
    net_burn = "net_burn"
    runway_months = "runway_months"

    # customers / retention
    headcount = "headcount"
    customers_count = "customers_count"
    net_revenue_retention = "net_revenue_retention"
    gross_revenue_retention = "gross_revenue_retention"
    logo_churn = "logo_churn"
    revenue_churn = "revenue_churn"
    cac = "cac"
    ltv = "ltv"
    payback_months = "payback_months"
    contract_value = "contract_value"
    avg_contract_value = "avg_contract_value"
    top_customer_concentration = "top_customer_concentration"

    # market
    tam = "tam"
    sam = "sam"
    som = "som"

    # cap table
    shares_outstanding = "shares_outstanding"
    fully_diluted_pct = "fully_diluted_pct"
    share_price = "share_price"

    # legal / risk
    litigation_exposure = "litigation_exposure"

    # internal aggregates (bank statements; used by R7, not LLM-facing)
    revenue_inflow = "revenue_inflow"
    bank_inflows = "bank_inflows"
