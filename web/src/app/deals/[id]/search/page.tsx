"use client";

import { Loader2, Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useIndexStatus,
  useSearch,
  type DocType,
  type SearchHit,
} from "@/lib/api/hooks";
import { DOC_TYPES, DOC_TYPE_LABELS } from "@/lib/doc-types";
import { cn } from "@/lib/utils";

const K_OPTIONS = [5, 10, 25];

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function queryTerms(query: string): string[] {
  return query.split(/\s+/).filter((t) => t.length > 1);
}

function Highlighted({ text, query }: { text: string; query: string }) {
  const terms = queryTerms(query);
  if (!terms.length) return <>{text}</>;
  const re = new RegExp(`(${terms.map(escapeRe).join("|")})`, "i");
  const splitRe = new RegExp(`(${terms.map(escapeRe).join("|")})`, "gi");
  const parts = text.split(splitRe);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 && re.test(part) ? (
          <mark key={i} className="rounded-sm bg-highlight px-0.5 text-foreground">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

function snippet(text: string, query: string): string {
  const terms = queryTerms(query);
  const max = 360;
  if (text.length <= max) return text;
  const lower = text.toLowerCase();
  let pos = -1;
  for (const t of terms) {
    const at = lower.indexOf(t.toLowerCase());
    if (at >= 0 && (pos < 0 || at < pos)) pos = at;
  }
  const start = Math.max(0, (pos < 0 ? 0 : pos) - 120);
  const end = Math.min(text.length, start + max);
  return `${start > 0 ? "…" : ""}${text.slice(start, end)}${end < text.length ? "…" : ""}`;
}

function HitRow({ hit, dealId, query }: { hit: SearchHit; dealId: string; query: string }) {
  return (
    <Link
      href={`/deals/${dealId}/documents/${hit.document_id}?page=${hit.page_no}`}
      className="block rounded-lg border border-border bg-card p-3 transition-colors hover:bg-muted/50"
    >
      <div className="flex items-center gap-2 text-xs">
        <span className="font-medium">{hit.filename}</span>
        <Badge variant="outline" className="font-mono">p{hit.page_no}</Badge>
        <span className="ml-auto font-mono text-muted-foreground tnum">
          {hit.score.toFixed(4)}
        </span>
        <span className="font-mono text-muted-foreground">
          bm25:{hit.bm25_rank ?? "—"} dense:{hit.dense_rank ?? "—"}
        </span>
      </div>
      <p className="mt-1.5 text-sm text-muted-foreground">
        <Highlighted text={snippet(hit.text, query)} query={query} />
      </p>
    </Link>
  );
}

export default function SearchPage() {
  const { id: dealId } = useParams<{ id: string }>();
  const index = useIndexStatus(dealId);
  const search = useSearch(dealId);

  const [query, setQuery] = useState("");
  const [k, setK] = useState(10);
  const [docTypes, setDocTypes] = useState<Set<DocType>>(new Set());
  const [submitted, setSubmitted] = useState<string | null>(null);

  const hits = useMemo(() => search.data?.results ?? [], [search.data]);

  function run() {
    const q = query.trim();
    if (!q) return;
    setSubmitted(q);
    search.mutate({
      query: q,
      k,
      filters: docTypes.size ? { doc_types: [...docTypes] } : null,
    });
  }

  function toggleType(t: DocType) {
    setDocTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  const notReady = index.data && index.data.status !== "ready";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-medium tracking-tight">Search</h2>
        {index.data && (
          <Badge variant="outline" className="font-mono text-xs">
            index: {index.data.status} ({index.data.embedded_count})
          </Badge>
        )}
      </div>

      {notReady && (
        <div className="rounded-lg border border-border bg-muted/40 p-3 text-sm">
          The index is {index.data?.status} — results may be incomplete.{" "}
          {index.data?.status === "stale" && "Reindex from the documents page."}
        </div>
      )}

      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="annual recurring revenue"
          aria-label="Search query"
          className="max-w-md"
        />
        <Button type="submit" disabled={search.isPending || !query.trim()}>
          {search.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <SearchIcon className="size-4" />
          )}
          Search
        </Button>
        <div className="ml-2 flex items-center gap-1 text-xs text-muted-foreground">
          k:
          {K_OPTIONS.map((opt) => (
            <Button
              key={opt}
              type="button"
              variant={k === opt ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setK(opt)}
            >
              {opt}
            </Button>
          ))}
        </div>
      </form>

      <div className="flex flex-wrap gap-1">
        {DOC_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => toggleType(t)}
            aria-pressed={docTypes.has(t)}
            className={cn(
              "rounded-md border px-2 py-0.5 text-xs transition-colors",
              docTypes.has(t)
                ? "border-primary bg-primary/10 text-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {DOC_TYPE_LABELS[t]}
          </button>
        ))}
      </div>

      {search.isPending && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      )}

      {search.isError && (
        <div className="flex flex-col items-center gap-3 py-16">
          <p className="text-sm text-destructive">
            Search failed — {search.error.message}
          </p>
          <Button variant="secondary" size="sm" onClick={run}>
            Retry
          </Button>
        </div>
      )}

      {!search.isPending && !search.isError && submitted === null && (
        <div className="flex flex-col items-center gap-2 py-24">
          <SearchIcon className="size-5 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Hybrid search over every parsed document in this deal.
          </p>
        </div>
      )}

      {search.isSuccess && hits.length === 0 && (
        <p className="py-16 text-center text-sm text-muted-foreground">
          No results for “{submitted}”.
        </p>
      )}

      {search.isSuccess && hits.length > 0 && (
        <div className="flex flex-col gap-2">
          {hits.map((hit) => (
            <HitRow key={hit.chunk_id} hit={hit} dealId={dealId} query={submitted ?? ""} />
          ))}
        </div>
      )}
    </div>
  );
}
