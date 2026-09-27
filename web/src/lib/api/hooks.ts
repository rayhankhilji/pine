"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "./client";
import type { components } from "./types";

export type DealStage = components["schemas"]["DealStage"];
export type Deal = components["schemas"]["Deal"];
export type DealCreate = components["schemas"]["DealCreate"];
export type DocStatus = components["schemas"]["DocStatus"];
export type DocType = components["schemas"]["DocType"];
export type Document = components["schemas"]["Document"];
export type DocumentDetail = components["schemas"]["DocumentDetail"];
export type Page = components["schemas"]["Page"];
export type TableDetail = components["schemas"]["TableDetail"];
export type TableSummary = components["schemas"]["TableSummary"];
export type DocumentUpload = components["schemas"]["DocumentUpload"];
export type SkippedFile = components["schemas"]["SkippedFile"];
export type DemoResponse = components["schemas"]["DemoResponse"];
export type ReparseResponse = components["schemas"]["ReparseResponse"];

/** List endpoints return un-typed dicts; describe their wire shape here. */
export type ListPage<T> = { items: T[]; next_cursor: string | null };

export type DealSummary = Deal & {
  document_count: number;
  last_run_status: string | null;
  open_contradictions: number;
};

export type DealList = ListPage<DealSummary>;
export type DocumentList = ListPage<Document>;

export type IndexStatus = {
  status: "ready" | "stale" | "indexing" | "not_indexed";
  embedded_count: number;
};

export function useHealth() {
  return useQuery({
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

export function useLoadDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<DemoResponse>("/api/v1/demo"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["deals"] }),
  });
}

export function useDocuments(
  dealId: string,
  filters: { status?: DocStatus; docType?: DocType } = {},
) {
  return useQuery<DocumentList>({
    queryKey: ["documents", dealId, filters.status ?? null, filters.docType ?? null],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (filters.status) params.set("status", filters.status);
      if (filters.docType) params.set("doc_type", filters.docType);
      return api.get<DocumentList>(
        `/api/v1/deals/${dealId}/documents?${params.toString()}`,
      );
    },
    enabled: Boolean(dealId),
  });
}

export function useDocument(documentId: string) {
  return useQuery<DocumentDetail>({
    queryKey: ["document", documentId],
    queryFn: () => api.get<DocumentDetail>(`/api/v1/documents/${documentId}`),
    enabled: Boolean(documentId),
  });
}

export function usePage(documentId: string, pageNo: number) {
  return useQuery<Page>({
    queryKey: ["page", documentId, pageNo],
    queryFn: () =>
      api.get<Page>(`/api/v1/documents/${documentId}/pages/${pageNo}`),
    enabled: Boolean(documentId) && pageNo > 0,
  });
}

export function useTable(tableId: string | null) {
  return useQuery<TableDetail>({
    queryKey: ["table", tableId],
    queryFn: () => api.get<TableDetail>(`/api/v1/tables/${tableId}`),
    enabled: Boolean(tableId),
  });
}

export function useIndexStatus(dealId: string) {
  return useQuery<IndexStatus>({
    queryKey: ["index", dealId],
    queryFn: async () => {
      try {
        return await api.get<IndexStatus>(`/api/v1/deals/${dealId}/index`);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return { status: "not_indexed", embedded_count: 0 };
        }
        throw error;
      }
    },
    enabled: Boolean(dealId),
    retry: false,
  });
}

export function useUploadDocuments(dealId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      form,
      onProgress,
    }: {
      form: FormData;
      onProgress?: (p: { loaded: number; total: number }) => void;
    }) =>
      api.upload<DocumentUpload>(
        `/api/v1/deals/${dealId}/documents`,
        form,
        onProgress,
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["documents", dealId] }),
  });
}

export function useReparse(documentId: string, dealId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<ReparseResponse>(`/api/v1/documents/${documentId}/reparse`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", dealId] });
      queryClient.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
}
