"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { GitBranch } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeal, useGraph } from "@/lib/api/hooks";
import {
  entityTypeColorVar,
  entityTypeLabel,
  ENTITY_TYPES,
} from "@/lib/graph";
import { cn } from "@/lib/utils";

import { EntityPanelBody } from "./entity-panel";
import { useChartPalette } from "./palette";

const GraphCanvas = dynamic(() => import("./graph-canvas"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-md" />,
});

function TypeChip({
  type,
  count,
  color,
  active,
  onToggle,
}: {
  type: string;
  count: number;
  color: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onToggle}
      className={cn(
        "flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs transition-colors",
        active
          ? "border-primary bg-primary/10 text-foreground"
          : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      <span
        aria-hidden
        className="size-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {entityTypeLabel(type)}
      <span className="font-mono tnum text-muted-foreground">{count}</span>
    </button>
  );
}

export function GraphView({ dealId }: { dealId: string }) {
  const reduceMotion = useReducedMotion();
  const deal = useDeal(dealId);
  const graph = useGraph(dealId);
  const palette = useChartPalette();
  const [excluded, setExcluded] = useState<ReadonlySet<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of graph.data?.nodes ?? []) {
      counts.set(node.type, (counts.get(node.type) ?? 0) + 1);
    }
    return counts;
  }, [graph.data]);

  const nameFor = useMemo(() => {
    const names = new Map<string, string>();
    for (const node of graph.data?.nodes ?? []) {
      names.set(node.id, node.canonical_name);
    }
    return (id: string) => names.get(id) ?? "unknown entity";
  }, [graph.data]);

  const filtered = useMemo(() => {
    const nodes: { id: string; name: string; type: string }[] = [];
    for (const node of graph.data?.nodes ?? []) {
      if (!excluded.has(node.type)) {
        nodes.push({ id: node.id, name: node.canonical_name, type: node.type });
      }
    }
    const visible = new Set(nodes.map((n) => n.id));
    const links = (graph.data?.edges ?? [])
      .filter(
        (e) => visible.has(e.source_entity_id) && visible.has(e.target_entity_id),
      )
      .map((e) => ({
        id: e.id,
        source: e.source_entity_id,
        target: e.target_entity_id,
        type: e.type,
      }));
    return { nodes, links };
  }, [graph.data, excluded]);

  const presentTypes = useMemo(() => {
    const order = new Map(ENTITY_TYPES.map((t, i) => [t as string, i]));
    return [...typeCounts.keys()].sort(
      (a, b) =>
        (order.get(a) ?? 99) - (order.get(b) ?? 99) || a.localeCompare(b),
    );
  }, [typeCounts]);

  const toggleType = (type: string) =>
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });

  const enter = reduceMotion
    ? { initial: { opacity: 0 }, animate: { opacity: 1 } }
    : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };

  const selectedNode = (graph.data?.nodes ?? []).find(
    (n) => n.id === selectedId,
  );
  const selectedName = selectedNode?.canonical_name ?? null;
  const selectedType = selectedNode?.type ?? null;

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-medium tracking-tight">Knowledge graph</h2>
        {graph.isSuccess && graph.data.nodes.length > 0 && (
          <span className="font-mono text-xs text-muted-foreground tnum">
            {filtered.nodes.length} entities · {filtered.links.length} relations
          </span>
        )}
      </div>

      {graph.isPending && (
        <div className="flex flex-1 flex-col gap-4">
          <div className="flex gap-1">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-20" />
            ))}
          </div>
          <Skeleton className="min-h-[480px] w-full flex-1" />
        </div>
      )}

      {graph.isError && (
        <div className="flex flex-col items-center gap-3 py-24">
          <p className="text-sm text-destructive">
            Could not load the graph — {graph.error.message}
          </p>
          <Button variant="secondary" size="sm" onClick={() => graph.refetch()}>
            Retry
          </Button>
        </div>
      )}

      {graph.isSuccess && graph.data.nodes.length === 0 && (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-24">
          <GitBranch className="size-5 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            No entities yet — documents are still processing.
          </p>
        </div>
      )}

      {graph.isSuccess && graph.data.nodes.length > 0 && (
        <>
          <div
            className="flex flex-wrap gap-1"
            aria-label="Filter by entity type"
          >
            {presentTypes.map((type) => (
              <TypeChip
                key={type}
                type={type}
                count={typeCounts.get(type) ?? 0}
                color={
                  palette?.[entityTypeColorVar(type)] ??
                  "var(--muted-foreground)"
                }
                active={!excluded.has(type)}
                onToggle={() => toggleType(type)}
              />
            ))}
          </div>

          <motion.div
            {...enter}
            transition={{ duration: 0.22, ease: [0, 0, 0, 1] }}
            className="relative min-h-[480px] flex-1 overflow-hidden rounded-md border border-border bg-surface"
          >
            {palette && (
              <GraphCanvas
                nodes={filtered.nodes}
                links={filtered.links}
                palette={palette}
                colorVarFor={entityTypeColorVar}
                selectedId={selectedId}
                onNodeClick={setSelectedId}
                onBackgroundClick={() => setSelectedId(null)}
              />
            )}
          </motion.div>
        </>
      )}

      <Sheet
        open={selectedId !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null);
        }}
      >
        <SheetContent side="right" className="sm:max-w-md">
          <SheetHeader>
            <div className="flex items-center gap-2">
              {selectedType && (
                <Badge variant="outline" className="font-mono text-xs">
                  {entityTypeLabel(selectedType)}
                </Badge>
              )}
              <SheetTitle>
                {selectedName ?? "Entity"}
              </SheetTitle>
            </div>
            <SheetDescription className="sr-only">
              Entity detail
            </SheetDescription>
          </SheetHeader>
          {selectedId && (
            <EntityPanelBody
              entityId={selectedId}
              dealId={dealId}
              currency={deal.data?.currency ?? "USD"}
              nameFor={nameFor}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
