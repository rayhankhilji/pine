"use client";

import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FileUp,
  Loader2,
  RefreshCw,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useDropzone, type FileWithPath } from "react-dropzone";

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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useDealEvents } from "@/lib/api/events";
import {
  useDocuments,
  useIndexStatus,
  useReparse,
  useUploadDocuments,
  type Document,
  type DocStatus,
  type DocType,
} from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

const DOC_TYPE_LABELS: Record<DocType, string> = {
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

const STATUS_FILTERS: { value: DocStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "queued", label: "Queued" },
  { value: "parsing", label: "Parsing" },
  { value: "parsed", label: "Parsed" },
  { value: "failed", label: "Failed" },
  { value: "unsupported", label: "Unsupported" },
];

function StatusPill({ status, error }: { status: DocStatus; error: string | null }) {
  const pill = (className: string, children: React.ReactNode) => (
    <Badge variant="secondary" className={cn("gap-1", className)}>
      {children}
    </Badge>
  );
  switch (status) {
    case "queued":
      return pill("", "queued");
    case "parsing":
      return pill("", (
        <>
          <Loader2 className="size-3 animate-spin" /> parsing
        </>
      ));
    case "parsed":
      return pill("", "parsed");
    case "unsupported":
      return pill("", (
        <>
          <AlertTriangle className="size-3" /> unsupported
        </>
      ));
    case "failed":
      return (
        <Tooltip>
          <TooltipTrigger
            render={
              <Badge variant="destructive" className="gap-1">
                <AlertTriangle className="size-3" /> failed
              </Badge>
            }
          />
          <TooltipContent>{error ?? "Parsing failed"}</TooltipContent>
        </Tooltip>
      );
  }
}

function formatSize(doc: Document): string {
  const raw = doc.meta["size_bytes"] ?? doc.meta["size"];
  if (typeof raw !== "number") return "—";
  if (raw >= 1024 * 1024) return `${(raw / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(raw / 1024))} KB`;
}

function IndexPill({ dealId }: { dealId: string }) {
  const index = useIndexStatus(dealId);
  const label = index.data?.status ?? "not indexed";
  return (
    <Badge variant="outline" className="font-mono text-xs" aria-live="polite">
      index: {label}
      {index.data ? ` (${index.data.embedded_count})` : ""}
    </Badge>
  );
}

type UploadTask = { name: string; loaded: number; total: number };

function useUpload(dealId: string) {
  const upload = useUploadDocuments(dealId);
  const [tasks, setTasks] = useState<UploadTask[]>([]);
  const [skipped, setSkipped] = useState<{ filename: string; reason: string }[]>([]);

  const start = useCallback(
    (files: File[]) => {
      const form = new FormData();
      for (const file of files) {
        form.append("files", file, file.name);
        const withPath = file as FileWithPath;
        const rel =
          withPath.path ?? withPath.relativePath ?? file.webkitRelativePath;
        form.append("paths", rel || file.name);
      }
      setTasks(
        files.map((f) => ({ name: f.name, loaded: 0, total: f.size || 1 })),
      );
      upload.mutate(
        {
          form,
          onProgress: (p) =>
            setTasks((prev) =>
              prev.map((t, i) =>
                i === 0 ? { ...t, loaded: p.loaded, total: p.total || t.total } : t,
              ),
            ),
        },
        {
          onSuccess: (data) => {
            setTasks([]);
            setSkipped(data.skipped);
          },
          onError: () => setTasks([]),
        },
      );
    },
    [upload],
  );

  return { start, tasks, skipped, error: upload.error, isPending: upload.isPending };
}

function DocumentRow({ doc, dealId }: { doc: Document; dealId: string }) {
  const reparse = useReparse(doc.id, dealId);
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/deals/${dealId}/documents/${doc.id}`}
          className="font-medium hover:underline"
        >
          {doc.filename}
        </Link>
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {doc.path}
      </TableCell>
      <TableCell>
        <Badge variant="outline" className="font-mono text-xs">
          {DOC_TYPE_LABELS[doc.doc_type]}
        </Badge>
      </TableCell>
      <TableCell>
        <StatusPill status={doc.status} error={doc.error} />
      </TableCell>
      <TableCell className="text-right font-mono tnum">
        {doc.page_count || "—"}
      </TableCell>
      <TableCell className="text-right font-mono text-xs text-muted-foreground tnum">
        {formatSize(doc)}
      </TableCell>
      <TableCell className="text-right">
        {doc.status === "failed" && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => reparse.mutate()}
            disabled={reparse.isPending}
          >
            <RefreshCw
              className={cn("size-3.5", reparse.isPending && "animate-spin")}
            />
            Retry
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

export default function DocumentsPage() {
  const { id: dealId } = useParams<{ id: string }>();
  useDealEvents(dealId);

  const [statusFilter, setStatusFilter] = useState<DocStatus | "all">("all");
  const [showUnreadable, setShowUnreadable] = useState(false);

  const documents = useDocuments(dealId, {
    status: statusFilter === "all" ? undefined : statusFilter,
  });
  const upload = useUpload(dealId);

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length) upload.start(accepted);
    },
    [upload],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    noClick: true,
    noKeyboard: true,
  });

  const { readable, unreadable } = useMemo(() => {
    const items = documents.data?.items ?? [];
    return {
      readable: items.filter(
        (d) => d.status !== "failed" && d.status !== "unsupported",
      ),
      unreadable: items.filter(
        (d) => d.status === "failed" || d.status === "unsupported",
      ),
    };
  }, [documents.data]);

  const dropzoneClass = cn(
    "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors",
    isDragActive ? "border-primary bg-primary/5" : "border-border",
  );

  const dropzoneBody = (
    <div {...getRootProps({ className: dropzoneClass })}>
      <input {...getInputProps()} />
      <Upload className="size-5 text-muted-foreground" />
      {isDragActive ? (
        <p className="text-sm">Drop files to upload</p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Drag a data room here — folders, zips, or individual files
        </p>
      )}
      <Button variant="secondary" size="sm" onClick={open}>
        Browse files
      </Button>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-medium tracking-tight">Documents</h2>
        <IndexPill dealId={dealId} />
        <div className="ml-auto flex gap-1">
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f.value}
              variant={statusFilter === f.value ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setStatusFilter(f.value)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {upload.tasks.length > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
          {upload.tasks.map((t) => (
            <div key={t.name} className="flex flex-col gap-1">
              <div className="flex justify-between text-xs">
                <span className="font-mono">{t.name}</span>
                <span className="text-muted-foreground" aria-valuenow={t.loaded}>
                  {Math.round((t.loaded / t.total) * 100)}%
                </span>
              </div>
              <div className="h-1.5 rounded bg-muted">
                <div
                  className="h-1.5 rounded bg-primary transition-all"
                  style={{ width: `${Math.round((t.loaded / t.total) * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {upload.error && (
        <p className="text-sm text-destructive">
          Upload failed — {upload.error.message}
        </p>
      )}

      {upload.skipped.length > 0 && (
        <div className="rounded-lg border border-border bg-muted/40 p-3 text-sm">
          {upload.skipped.length} file{upload.skipped.length === 1 ? "" : "s"}{" "}
          skipped:{" "}
          <span className="text-muted-foreground">
            {upload.skipped.map((s) => `${s.filename} (${s.reason})`).join(", ")}
          </span>
        </div>
      )}

      {documents.isPending && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      )}

      {documents.isError && (
        <div className="flex flex-col items-center gap-3 py-24">
          <p className="text-sm text-destructive">
            Could not load documents — {documents.error.message}
          </p>
          <Button variant="secondary" size="sm" onClick={() => documents.refetch()}>
            Retry
          </Button>
        </div>
      )}

      {documents.isSuccess && documents.data.items.length === 0 && (
        <div className="flex-1">{dropzoneBody}</div>
      )}

      {documents.isSuccess && documents.data.items.length > 0 && (
        <>
          {dropzoneBody}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Path</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Pages</TableHead>
                <TableHead className="text-right">Size</TableHead>
                <TableHead className="text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {readable.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} dealId={dealId} />
              ))}
            </TableBody>
          </Table>

          {unreadable.length > 0 && (
            <div className="rounded-lg border border-border">
              <button
                type="button"
                className="flex w-full items-center gap-2 px-4 py-2 text-sm"
                onClick={() => setShowUnreadable((v) => !v)}
                aria-expanded={showUnreadable}
              >
                {showUnreadable ? (
                  <ChevronDown className="size-4" />
                ) : (
                  <ChevronRight className="size-4" />
                )}
                <FileUp className="size-4 text-muted-foreground" />
                Unreadable files
                <Badge variant="secondary" className="font-mono text-xs">
                  {unreadable.length}
                </Badge>
              </button>
              {showUnreadable && (
                <Table>
                  <TableBody>
                    {unreadable.map((doc) => (
                      <DocumentRow key={doc.id} doc={doc} dealId={dealId} />
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
