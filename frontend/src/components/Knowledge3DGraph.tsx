"use client";

import { useMemo } from "react";
import ForceGraph3D from "react-force-graph-3d";
import type { GraphPayload } from "@/lib/graphClient";

type Props = {
  data: GraphPayload;
  onNodeClick: (id: string) => void;
  highlightedId: string | null;
};

const AXIS_COLORS: Record<string, string> = {
  "技術記事": "#3b82f6",
  "メモ": "#a855f7",
  "議事録": "#22c55e",
  "ToDo": "#f97316",
};

export function Knowledge3DGraph({ data, onNodeClick, highlightedId }: Props) {
  const nodes = useMemo(
    () =>
      data.nodes.map((n) => ({
        id: n.id,
        name: n.title || n.id,
        val: 2 + n.in_degree + n.out_degree,
        color: AXIS_COLORS[String(n.axes.category ?? "")] ?? "#9ca3af",
        __raw: n,
      })),
    [data.nodes],
  );

  const links = useMemo(
    () => data.edges.map((e) => ({ source: e.source, target: e.target })),
    [data.edges],
  );

  // react-force-graph-3d's TS signatures are loose — keep `any` confined here.
  /* eslint-disable @typescript-eslint/no-explicit-any */
  return (
    <ForceGraph3D
      graphData={{ nodes, links }}
      nodeRelSize={6}
      nodeLabel={(n: any) =>
        `${n.name}\n(${n.__raw.axes.category ?? "—"} / in=${n.__raw.in_degree} out=${n.__raw.out_degree})`
      }
      nodeColor={(n: any) => (n.id === highlightedId ? "#facc15" : n.color)}
      linkColor={() => "#374151"}
      linkOpacity={0.4}
      linkDirectionalArrowLength={3}
      linkDirectionalArrowRelPos={0.85}
      onNodeClick={(n: any) => onNodeClick(n.id)}
      backgroundColor="#0a0a0a"
      cooldownTicks={150}
    />
  );
  /* eslint-enable @typescript-eslint/no-explicit-any */
}
