import type { EntityType } from "@/lib/api/hooks";

/** Human labels for the entity-type vocabulary (ARCHITECTURE §4). */
export const ENTITY_TYPE_LABELS: Record<string, string> = {
  company: "Company",
  customer: "Customer",
  contract: "Contract",
  revenue_stream: "Revenue stream",
  invoice: "Invoice",
  person: "Person",
  shareholder: "Shareholder",
  security_class: "Security class",
  liability: "Liability",
  bank_account: "Bank account",
  employee: "Employee",
  market: "Market",
};

export const ENTITY_TYPES = Object.keys(ENTITY_TYPE_LABELS) as EntityType[];

export function entityTypeLabel(type: string): string {
  return ENTITY_TYPE_LABELS[type] ?? type.replaceAll("_", " ");
}

/**
 * Entity type → chart token (CSS custom property name). Semantic mapping:
 * company = pine green, customer = slate blue, contract = amber,
 * shareholder = violet, security_class = teal, liability = oxblood,
 * person = grey; anything else falls back to --muted-foreground.
 */
export const ENTITY_TYPE_COLOR_VARS: Record<string, string> = {
  company: "--chart-1",
  customer: "--chart-4",
  contract: "--chart-3",
  shareholder: "--chart-6",
  security_class: "--chart-7",
  liability: "--chart-5",
  person: "--chart-8",
};

export const DEFAULT_TYPE_COLOR_VAR = "--muted-foreground";

export function entityTypeColorVar(type: string): string {
  return ENTITY_TYPE_COLOR_VARS[type] ?? DEFAULT_TYPE_COLOR_VAR;
}

export const RELATION_TYPE_LABELS: Record<string, string> = {
  has_customer: "has customer",
  has_contract: "has contract",
  generates_revenue: "generates revenue",
  billed_by: "billed by",
  owns_shares: "owns shares",
  employs: "employs",
  owes: "owes",
  banks_with: "banks with",
  competes_in: "competes in",
};

export function relationTypeLabel(type: string): string {
  return RELATION_TYPE_LABELS[type] ?? type.replaceAll("_", " ");
}
