"use client";

import { useEffect, useState } from "react";

/** CSS vars the canvas needs resolved to concrete colours. */
export const PALETTE_VARS = [
  "--chart-1",
  "--chart-2",
  "--chart-3",
  "--chart-4",
  "--chart-5",
  "--chart-6",
  "--chart-7",
  "--chart-8",
  "--foreground",
  "--muted-foreground",
  "--border",
] as const;

export type Palette = Record<string, string>;

function resolvePalette(): Palette {
  const styles = getComputedStyle(document.documentElement);
  const out: Palette = {};
  for (const name of PALETTE_VARS) {
    out[name] = styles.getPropertyValue(name).trim();
  }
  return out;
}

/**
 * Resolved design-token colours for canvas painting. Re-resolves when the
 * `class` attribute on <html> changes (light/dark toggle).
 */
export function useChartPalette(): Palette | null {
  const [palette, setPalette] = useState<Palette | null>(null);

  useEffect(() => {
    const update = () => setPalette(resolvePalette());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return palette;
}
