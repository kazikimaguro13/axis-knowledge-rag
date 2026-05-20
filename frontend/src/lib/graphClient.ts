// API client for the spec_040 knowledge-graph endpoints.
// Mirrors backend/src/schemas.py {Graph,Neighbor}Response.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface GraphNode {
  id: string;
  title: string;
  axes: Record<string, string | number>;
  in_degree: number;
  out_degree: number;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphStats {
  nodes: number;
  edges: number;
  isolated: number;
  weakly_connected_components: number;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
}

export interface NeighborPayload {
  center: GraphNode;
  neighbors: GraphNode[];
  hop: number;
}

export interface GraphFilters {
  category?: string;
  level?: string;
  limit?: number;
}

export async function fetchGraph(filters: GraphFilters = {}): Promise<GraphPayload> {
  const params = new URLSearchParams();
  params.set("limit", String(filters.limit ?? 500));
  if (filters.category) params.set("axes_category", filters.category);
  if (filters.level) params.set("axes_level", filters.level);
  const res = await fetch(`${API_BASE}/api/graph?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`/api/graph failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as GraphPayload;
}

export async function fetchNeighbors(
  docId: string,
  hop = 1,
  maxNeighbors = 20,
  direction: "in" | "out" | "both" = "both",
): Promise<NeighborPayload> {
  const params = new URLSearchParams({
    hop: String(hop),
    max_neighbors: String(maxNeighbors),
    direction,
  });
  const res = await fetch(
    `${API_BASE}/api/graph/${encodeURIComponent(docId)}/neighbors?${params.toString()}`,
  );
  if (!res.ok) {
    throw new Error(`/api/graph/${docId}/neighbors failed: ${res.status}`);
  }
  return (await res.json()) as NeighborPayload;
}

// spec_049: Obsidian-style bidirectional refs.
//   forwardlinks = docs this doc refs (direction=out)
//   backlinks    = docs that ref this doc (direction=in)
// Fetched in parallel so wall-clock latency matches the single-call version.
export interface NeighborSet {
  center: GraphNode;
  forwardlinks: GraphNode[];
  backlinks: GraphNode[];
  hop: number;
}

export async function fetchNeighborsBidirectional(
  docId: string,
  hop = 1,
  maxNeighbors = 20,
): Promise<NeighborSet> {
  const [outRes, inRes] = await Promise.all([
    fetchNeighbors(docId, hop, maxNeighbors, "out"),
    fetchNeighbors(docId, hop, maxNeighbors, "in"),
  ]);
  return {
    center: outRes.center,
    forwardlinks: outRes.neighbors,
    backlinks: inRes.neighbors,
    hop,
  };
}
