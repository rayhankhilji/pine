"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { useDeal } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { key: "", label: "Overview" },
  { key: "documents", label: "Documents" },
  { key: "search", label: "Search" },
  { key: "graph", label: "Graph" },
  { key: "facts", label: "Facts" },
  { key: "contradictions", label: "Contradictions" },
  { key: "memo", label: "Memo" },
  { key: "model", label: "Model" },
  { key: "risks", label: "Risks" },
  { key: "sources", label: "Sources" },
  { key: "runs", label: "Runs" },
] as const;

const STAGE_LABELS: Record<string, string> = {
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  growth: "Growth",
  buyout: "Buyout",
  other: "Other",
};

export default function DealLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const deal = useDeal(id);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-6 pt-4 pb-3">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            Pine
          </Link>
          <span className="text-muted-foreground">/</span>
          <h1 className="text-lg font-medium tracking-tight">
            {deal.data?.name ?? "…"}
          </h1>
          {deal.data && (
            <>
              <span className="text-sm text-muted-foreground">
                {deal.data.company_name}
              </span>
              <Badge variant="outline" className="font-mono text-xs">
                {STAGE_LABELS[deal.data.stage] ?? deal.data.stage}
              </Badge>
            </>
          )}
          <Badge variant="secondary" className="ml-auto font-mono text-xs">
            idle
          </Badge>
        </div>
        <nav className="mx-auto flex w-full max-w-7xl gap-1 overflow-x-auto px-6">
          {SECTIONS.map(({ key, label }) => {
            const href = key ? `/deals/${id}/${key}` : `/deals/${id}`;
            const active =
              key === ""
                ? pathname === href
                : pathname.startsWith(href);
            return (
              <Link
                key={key || "overview"}
                href={href}
                className={cn(
                  "border-b-2 px-3 pb-2 text-sm whitespace-nowrap transition-colors",
                  active
                    ? "border-primary font-medium text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-6 py-6">
        {children}
      </main>
    </div>
  );
}
