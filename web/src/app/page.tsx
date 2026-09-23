"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CircleDashed } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
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
  useCreateDeal,
  useDeals,
  useHealth,
  type DealStage,
} from "@/lib/api/hooks";

const STAGES: { value: DealStage; label: string }[] = [
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "growth", label: "Growth" },
  { value: "buyout", label: "Buyout" },
  { value: "other", label: "Other" },
];

const createSchema = z.object({
  name: z.string().min(1, "Required").max(200),
  company_name: z.string().min(1, "Required").max(200),
  stage: z.enum(["seed", "series_a", "series_b", "growth", "buyout", "other"]),
  currency: z.string().length(3),
  fiscal_year_end_month: z.number().int().min(1).max(12),
});

type CreateValues = z.infer<typeof createSchema>;

function ApiStatusBadge() {
  const health = useHealth();
  if (health.isPending)
    return <Badge variant="secondary">api: connecting…</Badge>;
  if (health.isError) return <Badge variant="destructive">api: offline</Badge>;
  return <Badge variant="outline">api: v{health.data.version}</Badge>;
}

function CreateDealDialog() {
  const [open, setOpen] = useState(false);
  const createDeal = useCreateDeal();
  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      name: "",
      company_name: "",
      stage: "series_b",
      currency: "USD",
      fiscal_year_end_month: 12,
    },
  });

  const onSubmit = (values: CreateValues) => {
    createDeal.mutate(values, {
      onSuccess: () => {
        setOpen(false);
        form.reset();
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm">New deal</Button>} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create deal</DialogTitle>
          <DialogDescription>
            A deal groups a data room and its analysis runs.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-3"
        >
          <Input placeholder="Deal name" {...form.register("name")} />
          <Input
            placeholder="Company name"
            {...form.register("company_name")}
          />
          <Controller
            control={form.control}
            name="stage"
            render={({ field }) => (
              <Select
                value={field.value}
                onValueChange={(v) => field.onChange(v as DealStage)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Stage" />
                </SelectTrigger>
                <SelectContent>
                  {STAGES.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <div className="flex gap-3">
            <Input placeholder="Currency" {...form.register("currency")} />
            <Input
              type="number"
              placeholder="FY end month"
              {...form.register("fiscal_year_end_month", { valueAsNumber: true })}
            />
          </div>
          {createDeal.isError && (
            <p className="text-sm text-destructive">
              {createDeal.error.message}
            </p>
          )}
          <Button type="submit" disabled={createDeal.isPending}>
            {createDeal.isPending ? "Creating…" : "Create deal"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function Home() {
  const deals = useDeals();

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-8">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Pine</h1>
        <ApiStatusBadge />
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" size="sm" disabled>
            Load demo
          </Button>
          <CreateDealDialog />
        </div>
      </div>

      {deals.isPending && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      )}

      {deals.isError && (
        <div className="flex flex-col items-center gap-3 py-24">
          <p className="text-sm text-destructive">
            Could not load deals — {deals.error.message}
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => deals.refetch()}
          >
            Retry
          </Button>
        </div>
      )}

      {deals.isSuccess && deals.data.items.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-24">
          <CircleDashed className="size-5 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            No deals yet — create a deal or load the demo data room.
          </p>
        </div>
      )}

      {deals.isSuccess && deals.data.items.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Stage</TableHead>
              <TableHead className="text-right">Docs</TableHead>
              <TableHead>Last run</TableHead>
              <TableHead className="text-right">Contradictions</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {deals.data.items.map((deal) => (
              <TableRow key={deal.id}>
                <TableCell>
                  <Link
                    href={`/deals/${deal.id}`}
                    className="font-medium hover:underline"
                  >
                    {deal.name}
                  </Link>
                </TableCell>
                <TableCell>{deal.company_name}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="font-mono text-xs">
                    {STAGES.find((s) => s.value === deal.stage)?.label ??
                      deal.stage}
                  </Badge>
                </TableCell>
                <TableCell className="text-right font-mono tnum">
                  {deal.document_count}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {deal.last_run_status ?? "—"}
                </TableCell>
                <TableCell className="text-right font-mono tnum">
                  {deal.open_contradictions}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {new Date(deal.created_at).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </main>
  );
}
