"use client";

import { useParams } from "next/navigation";

import { GraphView } from "@/components/graph/graph-view";

export default function Page() {
  const { id } = useParams<{ id: string }>();
  return <GraphView dealId={id} />;
}
