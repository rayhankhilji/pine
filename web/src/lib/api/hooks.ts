"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type HealthResponse } from "./client";

export type DealStage =
  | "seed"
  | "series_a"
  | "series_b"
  | "growth"
  | "buyout"
  | "other";

export type Deal = {
  id: string;
  name: string;
  company_name: string;
  stage: DealStage;
  currency: string;
  fiscal_year_end_month: number;
  proposed_round_usd: string | null;
  proposed_pre_money_usd: string | null;
  created_at: string;
  updated_at: string;
};

export type DealSummary = Deal & {
  document_count: number;
  last_run_status: string | null;
  open_contradictions: number;
};

export type DealCreate = {
  name: string;
  company_name: string;
  stage?: DealStage;
  currency?: string;
  fiscal_year_end_month?: number;
  proposed_round_usd?: string | null;
  proposed_pre_money_usd?: string | null;
};

export type DealList = { items: DealSummary[]; next_cursor: string | null };

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: api.health,
    retry: false,
  });
}

export function useDeals() {
  return useQuery<DealList>({
    queryKey: ["deals"],
    queryFn: () => api.get<DealList>("/api/v1/deals"),
  });
}

export function useDeal(id: string) {
  return useQuery<Deal>({
    queryKey: ["deal", id],
    queryFn: () => api.get<Deal>(`/api/v1/deals/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateDeal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: DealCreate) =>
      api.post<Deal>("/api/v1/deals", data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["deals"] }),
  });
}
