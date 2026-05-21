"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { GraphFilterBar } from "@/components/GraphFilterBar";
import { GraphSidebar } from "@/components/GraphSidebar";
import { fetchGraph, type GraphPayload } from "@/lib/graphClient";

// react-force-graph-3d needs WebGL — disable SSR to avoid `window is undefined`.
const Knowledge3DGraph = dynamic(
  () =>
    import("@/components/Knowledge3DGraph").then((m) => m.Knowledge3DGraph),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Loading 3D graph...
      </div>
    ),
  },
);

export default function GraphPage() {
  const [graphData, setGraphData] = useState<GraphPayload | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [filters, setFilters] = useState<{ category?: string; level?: string }>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    fetchGraph({ ...filters, limit: 500 })
      .then(setGraphData)
      .catch((e) => setError(String(e)));
  }, [filters]);

  // Flexbox (not grid) + min-w-0 on the canvas column: react-force-graph-3d
  // defaults its canvas to window.innerWidth, which forces a grid 1fr column's
  // min-content to the viewport width and pushes a sized sidebar off-screen.
  // See ADR-032.
  return (
    <div className="flex h-[calc(100vh-120px)] overflow-hidden rounded-lg border bg-white">
      <div className="relative min-w-0 flex-1 bg-[#0a0a0a]">
        <GraphFilterBar onChange={setFilters} stats={graphData?.stats} />
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-red-400">
            グラフ取得失敗: {error}
          </div>
        )}
        {!error && graphData && (
          <Knowledge3DGraph
            data={graphData}
            onNodeClick={setSelectedNode}
            highlightedId={selectedNode}
          />
        )}
        {!error && !graphData && (
          <div className="flex h-full items-center justify-center text-sm text-slate-300">
            Loading graph data...
          </div>
        )}
      </div>
      <div className="w-80 shrink-0">
        <GraphSidebar docId={selectedNode} onClose={() => setSelectedNode(null)} />
      </div>
    </div>
  );
}
