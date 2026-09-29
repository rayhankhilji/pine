"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ForceGraph2D, {
  type ForceGraphMethods,
  type LinkObject,
  type NodeObject,
} from "react-force-graph-2d";

import { entityTypeLabel } from "@/lib/graph";

import type { Palette } from "./palette";

export interface GraphNode {
  id: string;
  name: string;
  type: string;
}

export interface GraphLink {
  id: string;
  source: string;
  target: string;
  type: string;
}

type FgNode = NodeObject<GraphNode>;
type FgLink = LinkObject<GraphNode, GraphLink>;

const NODE_R = 5;
const HIT_R = 9;
const LABEL_MAX = 26;

function truncate(name: string): string {
  return name.length > LABEL_MAX ? `${name.slice(0, LABEL_MAX - 1)}…` : name;
}

interface GraphCanvasProps {
  nodes: GraphNode[];
  links: GraphLink[];
  /** CSS-var name → resolved colour. */
  palette: Palette;
  /** entity type → CSS var name. */
  colorVarFor: (type: string) => string;
  selectedId: string | null;
  onNodeClick: (id: string) => void;
  onBackgroundClick: () => void;
}

export function GraphCanvas({
  nodes,
  links,
  palette,
  colorVarFor,
  selectedId,
  onNodeClick,
  onBackgroundClick,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraphMethods<FgNode, FgLink> | undefined>(
    undefined,
  );
  const [size, setSize] = useState<{ width: number; height: number } | null>(
    null,
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      setSize({
        width: Math.max(1, Math.floor(rect.width)),
        height: Math.max(1, Math.floor(rect.height)),
      });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const nodeCount = nodes.length;
  const fitted = useRef(false);
  useEffect(() => {
    fitted.current = false;
  }, [nodeCount]);
  useEffect(() => {
    if (!size || !nodeCount || fitted.current) return;
    const timer = setTimeout(() => {
      graphRef.current?.zoomToFit(400, 48);
      fitted.current = true;
    }, 350);
    return () => clearTimeout(timer);
  }, [size, nodeCount]);

  const paintNode = useCallback(
    (node: FgNode, ctx: CanvasRenderingContext2D, scale: number) => {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const selected = node.id === selectedId;
      const color =
        palette[colorVarFor(node.type)] || palette["--muted-foreground"];

      ctx.beginPath();
      ctx.arc(x, y, selected ? NODE_R + 1.5 : NODE_R, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
      if (selected) {
        ctx.beginPath();
        ctx.arc(x, y, NODE_R + 3, 0, 2 * Math.PI);
        ctx.strokeStyle = palette["--foreground"];
        ctx.lineWidth = 1.5 / scale;
        ctx.stroke();
      }

      const fontSize = Math.min(Math.max(11 / scale, 3), 22);
      ctx.font = `${fontSize}px Inter, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = palette["--foreground"];
      ctx.fillText(truncate(node.name), x, y + NODE_R + 2);
    },
    [palette, colorVarFor, selectedId],
  );

  const paintArea = useCallback(
    (node: FgNode, color: string, ctx: CanvasRenderingContext2D) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, HIT_R, 0, 2 * Math.PI);
      ctx.fill();
    },
    [],
  );

  return (
    <div ref={containerRef} className="h-full w-full" data-testid="graph-canvas">
      {size && (
        <ForceGraph2D
          ref={graphRef}
          graphData={{ nodes, links }}
          width={size.width}
          height={size.height}
          nodeId="id"
          linkSource="source"
          linkTarget="target"
          nodeLabel={(node) => `${node.name} — ${entityTypeLabel(node.type)}`}
          nodeCanvasObject={paintNode}
          nodePointerAreaPaint={paintArea}
          linkColor={() => palette["--border"]}
          linkWidth={1}
          linkDirectionalArrowLength={3.5}
          linkDirectionalArrowRelPos={1}
          onNodeClick={(node) => onNodeClick(String(node.id))}
          onBackgroundClick={onBackgroundClick}
          cooldownTicks={160}
          enableNodeDrag={true}
        />
      )}
    </div>
  );
}

export default GraphCanvas;
