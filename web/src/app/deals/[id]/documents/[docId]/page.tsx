"use client";

import { ArrowLeft, Download, Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { API_URL } from "@/lib/api/client";
import {
  useDocument,
  usePage,
  useTable,
  type DocumentDetail,
} from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

const IMAGE_EXTS = new Set(["png", "jpg", "jpeg"]);
const RENDER_EXTS = new Set(["pdf", ...IMAGE_EXTS]);
const SHEET_EXTS = new Set(["xlsx", "xls", "csv", "tsv"]);

function docTypeLabel(doc: DocumentDetail): string {
  return doc.doc_type.replace(/_/g, " ");
}

function Header({ doc }: { doc: DocumentDetail }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        variant="ghost"
        size="sm"
        nativeButton={false}
        render={<Link href={`/deals/${doc.deal_id}/documents`} />}
      >
        <ArrowLeft className="size-4" /> Documents
      </Button>
      <h2 className="text-lg font-medium tracking-tight">{doc.filename}</h2>
      <Badge variant="outline" className="font-mono text-xs">
        {docTypeLabel(doc)}
      </Badge>
      <Badge variant="secondary" className="text-xs">
        {doc.status}
      </Badge>
      <span className="font-mono text-xs text-muted-foreground tnum">
        {doc.page_count} page{doc.page_count === 1 ? "" : "s"}
      </span>
      {doc.status === "failed" && doc.error && (
        <span className="text-xs text-destructive">{doc.error}</span>
      )}
      <Button
        variant="secondary"
        size="sm"
        className="ml-auto"
        nativeButton={false}
        render={
          <a href={`${API_URL}/api/v1/documents/${doc.id}/file`} download />
        }
      >
        <Download className="size-4" /> Original
      </Button>
    </div>
  );
}

function PageText({ docId, pageNo }: { docId: string; pageNo: number }) {
  const page = usePage(docId, pageNo);
  if (page.isPending) return <Skeleton className="h-40 w-full" />;
  if (page.isError)
    return (
      <p className="text-sm text-destructive">
        Could not load page text — {page.error.message}
      </p>
    );
  return (
    <div className="flex flex-col gap-2">
      {page.data.is_scanned && (
        <Badge variant="outline" className="w-fit font-mono text-xs">
          OCR
        </Badge>
      )}
      {page.data.blocks.map((block, i) => (
        <p key={i} className="whitespace-pre-wrap text-sm leading-relaxed">
          {block.text}
        </p>
      ))}
      {page.data.blocks.length === 0 && (
        <p className="text-sm text-muted-foreground">No text on this page.</p>
      )}
    </div>
  );
}

function SpreadsheetView({ doc }: { doc: DocumentDetail }) {
  const [tableId, setTableId] = useState<string | null>(
    doc.tables[0]?.id ?? null,
  );
  const table = useTable(tableId);

  return (
    <div className="flex flex-col gap-3">
      {doc.tables.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {doc.tables.map((t, i) => (
            <Button
              key={t.id}
              variant={t.id === tableId ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setTableId(t.id)}
            >
              {t.sheet_name ?? t.title ?? `Table ${i + 1}`}
            </Button>
          ))}
        </div>
      )}
      {table.isPending && <Skeleton className="h-64 w-full" />}
      {table.isError && (
        <p className="text-sm text-destructive">
          Could not load table — {table.error.message}
        </p>
      )}
      {table.isSuccess && (
        <div className="overflow-auto rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                {table.data.cells[table.data.header_row ?? 0]?.map((cell, i) => (
                  <TableHead key={i} className="whitespace-nowrap">
                    {cell?.text ?? ""}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {table.data.cells
                .filter((_, i) => i !== (table.data.header_row ?? 0))
                .map((row, i) => (
                  <TableRow key={i}>
                    {row.map((cell, j) => (
                      <TableCell
                        key={j}
                        className="whitespace-nowrap font-mono text-xs tnum"
                      >
                        {cell?.text ?? cell?.value_num ?? cell?.value_date ?? ""}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function PdfLikeView({
  doc,
  pageNo,
  onPage,
}: {
  doc: DocumentDetail;
  pageNo: number;
  onPage: (n: number) => void;
}) {
  const canRender = RENDER_EXTS.has(doc.ext);
  const pages = useMemo(
    () => Array.from({ length: doc.page_count }, (_, i) => i + 1),
    [doc.page_count],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") onPage(Math.max(1, pageNo - 1));
      if (e.key === "ArrowRight") onPage(Math.min(doc.page_count, pageNo + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pageNo, doc.page_count, onPage]);

  return (
    <div className="grid flex-1 grid-cols-[96px_1fr_320px] gap-4">
      {/* thumbnail rail */}
      <div className="flex max-h-[75vh] flex-col gap-2 overflow-y-auto">
        {pages.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onPage(n)}
            className={cn(
              "relative flex w-24 flex-col items-center gap-1 rounded border p-1 text-xs transition-colors",
              n === pageNo
                ? "border-primary bg-primary/5"
                : "border-border hover:border-muted-foreground/40",
            )}
          >
            {canRender ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`${API_URL}/api/v1/documents/${doc.id}/render/${n}?scale=0.4`}
                alt={`Page ${n}`}
                className="w-full rounded-sm"
                loading="lazy"
              />
            ) : (
              <span className="flex h-16 w-full items-center justify-center rounded-sm bg-muted font-mono">
                p{n}
              </span>
            )}
            <span className="font-mono tnum">p{n}</span>
          </button>
        ))}
      </div>

      {/* canvas */}
      <div className="flex items-start justify-center overflow-auto rounded-lg border border-border bg-muted/30 p-4">
        {canRender ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`${API_URL}/api/v1/documents/${doc.id}/render/${pageNo}?scale=1.5`}
            alt={`Page ${pageNo} of ${doc.filename}`}
            className="max-w-full rounded shadow-sm"
          />
        ) : (
          <div className="w-full max-w-2xl rounded bg-card p-6 shadow-sm">
            <PageText docId={doc.id} pageNo={pageNo} />
          </div>
        )}
      </div>

      {/* text panel */}
      <div className="max-h-[75vh] overflow-y-auto rounded-lg border border-border p-4">
        <h3 className="mb-3 font-mono text-xs text-muted-foreground">
          Page {pageNo} text
        </h3>
        <PageText docId={doc.id} pageNo={pageNo} />
      </div>
    </div>
  );
}

function Viewer() {
  const { docId } = useParams<{ docId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const doc = useDocument(docId);

  const [pageNo, setPageNo] = useState(() => {
    const raw = Number(searchParams.get("page") ?? "1");
    return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : 1;
  });

  const onPage = (n: number) => {
    setPageNo(n);
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(n));
    router.replace(`?${params.toString()}`, { scroll: false });
  };

  if (doc.isPending)
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-[60vh] w-full" />
      </div>
    );

  if (doc.isError)
    return (
      <div className="flex flex-col items-center gap-3 py-24">
        <p className="text-sm text-destructive">
          Could not load document — {doc.error.message}
        </p>
        <Button variant="secondary" size="sm" onClick={() => doc.refetch()}>
          Retry
        </Button>
      </div>
    );

  const isSheet =
    SHEET_EXTS.has(doc.data.ext) && doc.data.tables.length > 0;

  if (!isSheet && doc.data.page_count === 0)
    return (
      <div className="flex flex-col gap-4">
        <Header doc={doc.data} />
        <div className="flex flex-col items-center gap-2 py-24">
          <p className="text-sm text-muted-foreground">
            No pages were extracted from this document.
          </p>
        </div>
      </div>
    );

  const clamped = Math.min(Math.max(1, pageNo), doc.data.page_count || 1);

  return (
    <div className="flex flex-1 flex-col gap-4">
      <Header doc={doc.data} />
      {isSheet ? (
        <SpreadsheetView doc={doc.data} />
      ) : (
        <PdfLikeView doc={doc.data} pageNo={clamped} onPage={onPage} />
      )}
    </div>
  );
}

export default function DocumentViewerPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-24 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading viewer…
        </div>
      }
    >
      <Viewer />
    </Suspense>
  );
}
