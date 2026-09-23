"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export default function Home() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    retry: false,
  });

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-4xl font-semibold tracking-tight">Pine</h1>
      <p className="text-muted-foreground">
        Private Markets Intelligence Engine
      </p>
      <p className="text-sm">
        API status:{" "}
        {health.isPending
          ? "loading…"
          : health.isError
            ? "error"
            : `${health.data.status} (v${health.data.version})`}
      </p>
    </main>
  );
}
