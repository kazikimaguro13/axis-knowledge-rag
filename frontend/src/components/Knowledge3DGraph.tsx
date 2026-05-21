"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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

  // ForceGraph3D defaults width/height to window.innerWidth/innerHeight, which
  // overflows the column and breaks page layout (see ADR-032). Measure the
  // wrapper and feed explicit size props so the canvas fits its container.
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setSize({ w: Math.floor(rect.width), h: Math.floor(rect.height) });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // react-force-graph-3d's TS signatures are loose — keep `any` confined here.
  /* eslint-disable @typescript-eslint/no-explicit-any */
  return (
    <div ref={wrapRef} className="absolute inset-0">
      {size.w > 0 && size.h > 0 && (
        <ForceGraph3D
          width={size.w}
          height={size.h}
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
      )}
    </div>
  );
  /* eslint-enable @typescript-eslint/no-explicit-any */
}
