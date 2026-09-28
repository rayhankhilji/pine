import type { DocType } from "@/lib/api/hooks";

export const DOC_TYPE_LABELS: Record<DocType, string> = {
  deck: "Deck",
  financial_statement: "Financials",
  bank_statement: "Bank stmt",
  customer_list: "Customers",
  contract: "Contract",
  cap_table: "Cap table",
  board_deck: "Board deck",
  email: "Email",
  legal: "Legal",
  other: "Other",
  unknown: "—",
};

export const DOC_TYPES = Object.keys(DOC_TYPE_LABELS) as DocType[];
