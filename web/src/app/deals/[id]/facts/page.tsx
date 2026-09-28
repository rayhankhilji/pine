"use client";

import {
  AlertTriangle,
  Database,
  Loader2,
  Quote,
  Star,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useDeal,
  useFacts,
  usePatchFact,
  type Evidence,
  type Fact,
} from "@/lib/api/hooks";
import {
  formatFactValue,
  metricLabel,
  periodLabel,
  sourceKindLabel,
} from "@/lib/facts";
import { cn } from "@/lib/utils";

function ContestedChip() {
  return (
    <Badge
      variant="outline"
      className="gap-1 border-warning/30 text-warning-foreground"
    >
      <AlertTriangle className="size-3" /> contested
    </Badge>
  );
}

function EvidenceCell({ fact, dealId }: { fact: Fact; dealId: string }) {
  if (fact.evidence.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className="h-6 gap-1 px-1.5 font-mono text-xs"
            aria-label={`Show ${fact.evidence.length} evidence quotes for ${metricLabel(fact.metric)}`}
          />
        }
      >
        <Quote className="size-3" />
        {fact.evidence.length}
      </PopoverTrigger>
      <PopoverContent className="flex flex-col gap-2">
        <PopoverTitle>Evidence</PopoverTitle>
        <ul className="flex max-h-64 flex-col gap-2 overflow-y-auto">
          {fact.evidence.map((ev: Evidence) => (
            <li
              key={ev.id}
              className="flex flex-col gap-1 border-l-2 border-accent pl-2"
            >
              <p className="text-xs leading-snug">“{ev.quote}”</p>
              <Link
                href={`/deals/${dealId}/documents/${ev.document_id}?page=${ev.page_no}`}
                className="font-mono text-xs text-primary hover:underline"
              >
                {ev.filename ?? "document"} · p{ev.page_no}
              </Link>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

function ConfidenceCell({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="h-1 w-10 rounded bg-muted">
        <div
          className="h-1 rounded bg-primary"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-xs tnum">{pct}%</span>
    </div>
  );
}

function AuthoritativeToggle({ fact, dealId }: { fact: Fact; dealId: string }) {
  const patch = usePatchFact(dealId);
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-6 w-7 p-0"
      aria-pressed={fact.is_authoritative}
      aria-label={
        fact.is_authoritative
          ? `Unmark ${metricLabel(fact.metric)} as authoritative`
          : `Mark ${metricLabel(fact.metric)} as authoritative`
      }
      disabled={patch.isPending}
      onClick={() =>
        patch.mutate({
          factId: fact.id,
          patch: { is_authoritative: !fact.is_authoritative },
        })
      }
    >
      <Star
        className={cn(
          "size-3.5",
          fact.is_authoritative
            ? "fill-primary text-primary"
            : "text-muted-foreground",
        )}
      />
    </Button>
  );
}

export default function FactsPage() {
  const { id: dealId } = useParams<{ id: string }>();
  const deal = useDeal(dealId);

  const [metric, setMetric] = useState<string>("");
  const [sourceKind, setSourceKind] = useState<string>("");
  const [contestedOnly, setContestedOnly] = useState(false);

  // Unfiltered query backs the filter vocabulary; shares the cache key with
  // the filtered query when no filters are set, so it costs no extra request.
  const vocabQuery = useFacts(dealId);
  const facts = useFacts(dealId, {
    metric: metric || undefined,
    sourceKind: sourceKind || undefined,
  });

  const vocab = useMemo(() => {
    const metrics = new Set<string>();
    const kinds = new Set<string>();
    for (const page of vocabQuery.data?.pages ?? []) {
      for (const f of page.items) {
        metrics.add(f.metric);
        kinds.add(f.source_kind);
      }
    }
    return { metrics, kinds };
  }, [vocabQuery.data]);

  const items = useMemo(() => {
    const all = facts.data?.pages.flatMap((p) => p.items) ?? [];
    const filtered = contestedOnly ? all.filter((f) => f.contested) : all;
    return [...filtered].sort((a, b) =>
      a.metric === b.metric
        ? (b.period_end ?? "").localeCompare(a.period_end ?? "")
        : a.metric.localeCompare(b.metric),
    );
  }, [facts.data, contestedOnly]);

  const currency = deal.data?.currency ?? "USD";
  const filtersActive = Boolean(metric || sourceKind || contestedOnly);
  const hasNextPage = facts.hasNextPage;
  const isFetchingNextPage = facts.isFetchingNextPage;
  const nextPageError = facts.isFetchNextPageError;
  const loadMore = () => void facts.fetchNextPage();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-medium tracking-tight">Facts</h2>
        {facts.isSuccess && (
          <Badge variant="outline" className="font-mono text-xs">
            {items.length}
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-2">
          <Select
            value={metric}
            onValueChange={(v) => setMetric(v === "all" ? "" : (v as string))}
          >
            <SelectTrigger className="w-44" aria-label="Filter by metric">
              <SelectValue placeholder="All metrics" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All metrics</SelectItem>
              {[...vocab.metrics].sort().map((m) => (
                <SelectItem key={m} value={m}>
                  {metricLabel(m)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant={contestedOnly ? "secondary" : "ghost"}
            size="sm"
            className="gap-1"
            aria-pressed={contestedOnly}
            onClick={() => setContestedOnly((v) => !v)}
          >
            <AlertTriangle className="size-3.5 text-warning-foreground" />
            Contested
          </Button>
        </div>
      </div>

      {vocab.kinds.size > 0 && (
        <div className="flex flex-wrap gap-1">
          <button
            type="button"
            onClick={() => setSourceKind("")}
            aria-pressed={sourceKind === ""}
            className={cn(
              "rounded-md border px-2 py-0.5 text-xs transition-colors",
              sourceKind === ""
                ? "border-primary bg-primary/10 text-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            All sources
          </button>
          {[...vocab.kinds].sort().map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setSourceKind(sourceKind === k ? "" : k)}
              aria-pressed={sourceKind === k}
              className={cn(
                "rounded-md border px-2 py-0.5 text-xs transition-colors",
                sourceKind === k
                  ? "border-primary bg-primary/10 text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {sourceKindLabel(k)}
            </button>
          ))}
        </div>
      )}

      {facts.isPending && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      )}

      {facts.isError && (
        <div className="flex flex-col items-center gap-3 py-24">
          <p className="text-sm text-destructive">
            Could not load facts — {facts.error.message}
          </p>
          <Button variant="secondary" size="sm" onClick={() => facts.refetch()}>
            Retry
          </Button>
        </div>
      )}

      {facts.isSuccess && items.length === 0 && (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 py-24">
          <Database className="size-5 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {filtersActive
              ? "No facts match the selected filters."
              : "No facts extracted yet — documents are still processing."}
          </p>
        </div>
      )}

      {facts.isSuccess && items.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead>Period</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Method</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
                <TableHead>Evidence</TableHead>
                <TableHead className="text-right">
                  <span className="sr-only">Authoritative</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((fact) => (
                <FactRowWithCurrency
                  key={fact.id}
                  fact={fact}
                  dealId={dealId}
                  currency={currency}
                />
              ))}
            </TableBody>
          </Table>

          {hasNextPage && (
            <div className="flex justify-center">
              <Button
                variant="secondary"
                size="sm"
                disabled={isFetchingNextPage}
                onClick={loadMore}
              >
                {isFetchingNextPage && (
                  <Loader2 className="size-3.5 animate-spin" />
                )}
                Load more
              </Button>
            </div>
          )}

          {nextPageError && (
            <div className="rounded-lg border border-border bg-muted/40 p-3 text-sm">
              Could not load more facts —{" "}
              <button
                type="button"
                className="text-primary hover:underline"
                onClick={loadMore}
              >
                retry
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function FactRowWithCurrency({
  fact,
  dealId,
  currency,
}: {
  fact: Fact;
  dealId: string;
  currency: string;
}) {
  const method = fact.extraction_method;
  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-2">
          <span className="font-medium">{metricLabel(fact.metric)}</span>
          {fact.contested && <ContestedChip />}
        </div>
        <span className="font-mono text-xs text-muted-foreground">
          {fact.metric}
        </span>
      </TableCell>
      <TableCell className="text-right">
        <span className="font-mono tnum">{formatFactValue(fact, currency)}</span>
        {fact.value !== null && fact.value_text && (
          <div className="font-mono text-xs text-muted-foreground">
            {fact.value_text}
          </div>
        )}
      </TableCell>
      <TableCell className="font-mono text-xs tnum">
        {periodLabel(fact)}
      </TableCell>
      <TableCell>
        <Badge variant="outline" className="font-mono text-xs">
          {sourceKindLabel(fact.source_kind)}
        </Badge>
      </TableCell>
      <TableCell>
        {(method === "derived" || method === "manual") && (
          <Badge variant="secondary" className="font-mono text-xs">
            {method}
          </Badge>
        )}
      </TableCell>
      <TableCell>
        <ConfidenceCell value={fact.confidence} />
      </TableCell>
      <TableCell>
        <EvidenceCell fact={fact} dealId={dealId} />
      </TableCell>
      <TableCell className="text-right">
        <AuthoritativeToggle fact={fact} dealId={dealId} />
      </TableCell>
    </TableRow>
  );
}
