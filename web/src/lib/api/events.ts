"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";

import { API_URL } from "./client";

export type DocumentStatusEvent = { document_id: string; status: string };
export type IndexStatusEvent = { status: string; embedded_count: number };

/**
 * Subscribe to the deal SSE stream. Document/index changes invalidate the
 * relevant TanStack Query keys; document.status transitions also toast.
 */
export function useDealEvents(dealId: string | null) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!dealId) return;
    const source = new EventSource(`${API_URL}/api/v1/deals/${dealId}/events`);

    source.addEventListener("document.status", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as DocumentStatusEvent;
      queryClient.invalidateQueries({ queryKey: ["documents", dealId] });
      queryClient.invalidateQueries({ queryKey: ["deal", dealId] });
      toast.info(`Document ${data.status}`, {
        description: data.document_id.slice(0, 8),
      });
    });

    source.addEventListener("index.status", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as IndexStatusEvent;
      queryClient.setQueryData(["index", dealId], data);
      queryClient.invalidateQueries({ queryKey: ["documents", dealId] });
      queryClient.invalidateQueries({ queryKey: ["deal", dealId] });
    });

    return () => source.close();
  }, [dealId, queryClient]);
}
