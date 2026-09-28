import type { Fact } from "@/lib/api/hooks";
import { DOC_TYPE_LABELS } from "@/lib/doc-types";

/** Human labels for the fact metric vocabulary (ARCHITECTURE §facts). */
export const METRIC_LABELS: Record<string, string> = {
  arr: "ARR",
  mrr: "MRR",
  revenue: "Revenue",
  recurring_revenue: "Recurring revenue",
  other_revenue: "Other revenue",
  gross_margin: "Gross margin",
  net_revenue_retention: "NRR",
  gross_revenue_retention: "GRR",
  cash_balance: "Cash balance",
  net_burn: "Net burn",
  runway_months: "Runway",
  headcount: "Headcount",
  contract_value: "Contract value",
  top_customer_concentration: "Top-customer concentration",
  shares_outstanding: "Shares outstanding",
  churned_customers: "Churned customers",
  customer_count: "Customers",
};

export function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric.replaceAll("_", " ");
}

/** source_kind is a doc_type for extracted facts, or derived/manual. */
export const SOURCE_KIND_LABELS: Record<string, string> = {
  ...DOC_TYPE_LABELS,
  derived: "Derived",
  manual: "Manual",
};

export function sourceKindLabel(kind: string): string {
  return SOURCE_KIND_LABELS[kind] ?? kind.replaceAll("_", " ");
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function parseDate(value: string | null): Date | null {
  if (!value) return null;
  const d = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** `23 Sep 2026` — DESIGN_SYSTEM §10. */
export function fmtDate(value: string | null): string {
  const d = parseDate(value);
  if (!d) return "—";
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

function monthYear(value: string | null): string {
  const d = parseDate(value);
  if (!d) return "—";
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** `FY2025`, `Q4 2025`, `Mar 2026`, `TTM Mar 2026`, `as of 31 Dec 2025`. */
export function periodLabel(fact: Fact): string {
  const end = fact.period_end ?? fact.period_start ?? fact.as_of;
  const d = parseDate(end);
  switch (fact.period_type) {
    case "fiscal_year":
      return d ? `FY${d.getUTCFullYear()}` : "—";
    case "quarter": {
      if (!d) return "—";
      return `Q${Math.floor(d.getUTCMonth() / 3) + 1} ${d.getUTCFullYear()}`;
    }
    case "month":
      return monthYear(fact.period_start ?? fact.period_end);
    case "ttm":
      return `TTM ${monthYear(fact.period_end ?? fact.period_start)}`;
    case "point":
      return fact.as_of ? `as of ${fmtDate(fact.as_of)}` : fmtDate(end);
    case "custom": {
      const start = parseDate(fact.period_start);
      const stop = parseDate(fact.period_end);
      if (start && stop) return `${fmtDate(fact.period_start)} – ${fmtDate(fact.period_end)}`;
      return fmtDate(end);
    }
    default:
      return fmtDate(end);
  }
}

/**
 * Format a fact value per DESIGN_SYSTEM §10 — currency compact in the deal
 * currency (`$12.0M`), percents with one decimal, counts grouped.
 * `value` is a decimal string; formatting only, never arithmetic.
 */
export function formatFactValue(fact: Fact, dealCurrency = "USD"): string {
  if (fact.unit === "text" || fact.value === null) {
    return fact.value_text ?? "—";
  }
  const num = Number(fact.value);
  if (!Number.isFinite(num)) return fact.value_text ?? "—";
  switch (fact.unit) {
    case "currency":
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: fact.currency ?? dealCurrency,
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(num);
    case "percent":
      return `${num.toFixed(1)}%`;
    case "months":
      return `${Number.isInteger(num) ? num : num.toFixed(1)} mo`;
    case "ratio":
      return `${num.toFixed(2)}×`;
    case "count":
      return num.toLocaleString("en-US");
    default:
      return fact.value_text ?? fact.value;
  }
}
