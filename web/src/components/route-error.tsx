"use client";

import { Button } from "@/components/ui/button";

export function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 py-24">
      <p className="text-sm text-destructive">
        {error.message || "Something went wrong."}
      </p>
      <p className="text-xs text-muted-foreground">
        Check that the API is running, then retry.
      </p>
      <Button variant="secondary" size="sm" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
