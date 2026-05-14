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

  return (
    <div className="grid h-[calc(100vh-120px)] grid-cols-[1fr_320px] overflow-hidden rounded-lg border bg-white">
      <div className="relative bg-[#0a0a0a]">
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
      <GraphSidebar docId={selectedNode} onClose={() => setSelectedNode(null)} />
    </div>
  );
}
