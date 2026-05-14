# spec_040: GraphRAG + 3D Knowledge Graph (v0.8 マーキー機能)

- **Author**: Cowork (中島)
- **Created**: 2026-05-14
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Type**: v0.8 マーキー機能 (大規模実装、単独 dispatch)
- **Bundles**: Gemini 案 ③ (GraphRAG) + ⑥ (3D Knowledge Graph) を統合

## 1. 目的

axis-knowledge-rag は YAML frontmatter の `refs: [doc_002, doc_003]` フィールドで **ドキュメント間の参照リンク** を既に保持しているが、検索時にこの情報を活用していない。`refs:` を **有向グラフ** として構築し、検索でヒットした親ドキュメントの **1 hop 隣接** を retrieval に追加する **GraphRAG (graph-augmented retrieval)** を導入する。

さらに **3D 知識グラフ可視化** をフロントに追加し、ナレッジ全体の構造を一目で把握できる UI を提供する。Three.js + react-force-graph-3d で力学シミュレーションされる 3D グラフ。

```
[現状 v0.7.0]
- frontmatter.refs: は load されるが「整合性チェック (integrity.py)」だけに使われる
- 検索でヒットした doc の "近所" が無視される (例: ChromaDB 設計 doc を検索 → vector_db ベンチマーク doc も関連だが取れない)
- ナレッジ全体の構造は docs/INDEX.md の手書きリストでしか見えない

[変更後 v0.8 (spec_040)]
- backend/src/graph.py 新設: networkx で refs を有向グラフ化、build_from_docs / neighbors_within_hop / find_path
- search.py に graph_expand=True パラメータ: 上位 parent N 件 → 1 hop 隣接を merge → top_k で再ランク
- /api/graph endpoint: 全ノード + エッジを JSON で返却 (3D 描画用)
- /api/graph/{doc_id}/neighbors endpoint: 単一 doc の N hop 隣接を返す
- MCP axis_neighbors tool: doc_id + hop → 隣接 doc list
- Next.js /graph ページ: react-force-graph-3d で 3D 力学シミュレーション
  - node クリック → サイドパネルに doc 詳細表示
  - axes filter (category / level / topic) で部分グラフ抽出
  - 検索バーで doc を highlight + camera focus
- Streamlit: 2D networkx + matplotlib で簡易グラフタブ (任意、軽量実装)
```

## 2. 制約

### 触ってよいファイル

**Backend (新規 / 修正)**:
- `backend/src/graph.py` — **新規** (KnowledgeGraph クラス、networkx ラッパ + refs 解析)
- `backend/src/search.py` — `graph_expand: bool = False` 引数 + `_expand_with_graph()` 関数追加 (BM25 fusion 後、time_decay 適用前に実行)
- `backend/src/api.py` — `GET /api/graph` / `GET /api/graph/{doc_id}/neighbors` の 2 endpoint
- `backend/src/schemas.py` — `GraphNode` / `GraphEdge` / `GraphResponse` / `NeighborResponse` Pydantic models
- `backend/src/config.py` — `GraphConfig` (`enabled`, `default_hop`, `max_neighbors_per_query`, `expand_on_search`)
- `config.yml` — `graph.*` section 追加 (default `enabled: true`, `expand_on_search: false` = 既存検索は影響なし、明示的に `graph_expand=true` で有効化)
- `backend/tests/test_graph.py` — **新規** (15+ tests)
- `backend/tests/test_search.py` — graph_expand 統合テスト 5 件追加
- `backend/tests/test_api.py` — `/api/graph` e2e 4 件追加

**Frontend (新規 / 修正)**:
- `frontend/src/app/graph/page.tsx` — **新規** (App Router の `/graph`)
- `frontend/src/components/Knowledge3DGraph.tsx` — **新規** (react-force-graph-3d ラッパ)
- `frontend/src/components/GraphSidebar.tsx` — **新規** (node クリック時の doc 詳細パネル)
- `frontend/src/components/GraphFilterBar.tsx` — **新規** (axes filter + search highlight)
- `frontend/src/lib/graphClient.ts` — **新規** (fetch wrapper、graph data cache)
- `frontend/src/app/layout.tsx` — nav に "🕸️ Graph" リンク追加
- `frontend/package.json` — `react-force-graph-3d` + `three` + `d3-force-3d` 依存追加

**MCP**:
- `mcp_server/server.py` — `axis_neighbors` tool 追加 (input: doc_id, hop=1, max=20)
- `mcp_server/schemas.py` — `NeighborsInput` Pydantic
- `mcp_server/formatters.py` — `format_neighbors_md()` / `format_neighbors_json()`

**Streamlit** (任意、軽量):
- `streamlit_app.py` — 第 3 タブ "🕸️ Graph" 追加。`networkx` + `matplotlib` で全体 2D 表示 + axes filter (1 ファイル ~80 行)

**Docs**:
- `docs/adr/ADR-024-graphrag-retrieval-expansion.md` — **新規**
- `docs/adr/ADR-025-3d-graph-visualization.md` — **新規**
- `docs/architecture.md` — §3-3 "Graph layer" を追加 (構造図 ASCII + retrieval flow)
- `docs/api-reference.md` — `/api/graph` 2 endpoint
- `docs/mcp-server.md` — `axis_neighbors` 説明
- `docs/configuration.md` — `graph.*` 設定
- `README.md` — ✨ 特徴に "🕸️ GraphRAG + 3D Visualization" 行
- `CHANGELOG.md` — Day 40 追記

**Dependencies (新規追加)**:
- `pyproject.toml`: `networkx>=3.0` を main deps に追加 (~600KB)
- `frontend/package.json`: `react-force-graph-3d@^1.24` + `three@^0.160` + `d3-force-3d@^3.0` を追加

### 触ってはいけないもの

- `backend/src/{chunker,vector_store,loader,bm25_index,normalizer,integrity,marker,ingester,_decay,_citations,conversation,question_rewriter}.py` — 既存ロジック変更なし
- 既存 `axis_search` / `axis_answer` / `axis_chat` の戻り値型 — 互換維持 (graph_expand は opt-in)
- `evaluation/` — 既存 RAGAS は触らない (graph 評価は spec_041 候補)
- `_ai_workspace/`

### コーディングルール

- **networkx は backend 専用** (frontend に持ち込まない)
- **3D グラフは react-force-graph-3d** に統一 (force-directed layout が built-in、自前 Three.js 実装は避ける)
- 既存パターン: dataclass + type hint + Pydantic v2 + frozen config dataclass
- `KnowledgeGraph` は **不変** (build_from_docs で構築、以後 add_doc / remove_doc しない。再 build は明示的に call)
- グラフサイズが大きい場合 (1000+ nodes) を想定し、`get_all_nodes()` は **pagination 対応** (default limit=500)
- broken refs (存在しない doc_id への参照) は **warning ログ + skip** (整合性チェックは integrity.py 側の責務)
- 自己参照 (`doc_001 → doc_001`) は **silently skip**
- 循環参照 (`doc_001 → doc_002 → doc_001`) は **許容** (networkx は DAG strict ではない)

### デプロイ

- 本 spec は v0.8.0 リリースの **マーキー機能**。tag / Release は spec_036〜039 完了後に一括 v0.8.0 として実施

## 3. やってほしいこと

### 3-1. KnowledgeGraph 実装 (`backend/src/graph.py`)

#### 設計スケッチ

```python
"""Knowledge graph constructed from YAML frontmatter `refs:` field.

The graph is directed (refs: [doc_X] means current_doc → doc_X).
Used for retrieval expansion (graph_expand) and frontend visualization.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterator
import logging
import networkx as nx

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphNode:
    """Graph node representing a single document."""
    doc_id: str
    title: str
    axes: dict[str, str] = field(default_factory=dict)
    in_degree: int = 0   # how many docs reference this
    out_degree: int = 0  # how many docs this references


@dataclass(frozen=True)
class GraphEdge:
    """Directed edge: source_doc references target_doc."""
    source: str
    target: str


class KnowledgeGraph:
    """Wrapper over networkx.DiGraph for knowledge document refs."""

    def __init__(self, graph: nx.DiGraph):
        self._g = graph
        self._node_cache: dict[str, GraphNode] = {}

    @classmethod
    def build_from_docs(cls, docs: list[dict]) -> "KnowledgeGraph":
        """Build graph from list of doc frontmatter dicts.

        Each doc must have 'id' field. 'refs' field is optional (defaults to []).
        Broken refs (target id not in docs) are logged and skipped.
        """
        g = nx.DiGraph()
        doc_ids = {d["id"] for d in docs}
        for d in docs:
            doc_id = d.get("id")
            if not doc_id:
                continue
            g.add_node(doc_id, title=d.get("title", ""), axes=d.get("axes", {}))
        broken: list[tuple[str, str]] = []
        for d in docs:
            src = d.get("id")
            if not src:
                continue
            for tgt in (d.get("refs") or []):
                if tgt == src:
                    continue  # self-loop skipped
                if tgt not in doc_ids:
                    broken.append((src, tgt))
                    continue
                g.add_edge(src, tgt)
        if broken:
            _log.warning("knowledge graph: %d broken refs skipped: %s", len(broken), broken[:5])
        return cls(g)

    def neighbors_within_hop(
        self,
        doc_id: str,
        *,
        hop: int = 1,
        max_neighbors: int = 20,
        direction: str = "both",  # "out" | "in" | "both"
    ) -> list[str]:
        """Return neighbor doc_ids within N hop. BFS-based, deduplicated."""
        if doc_id not in self._g:
            return []
        visited = {doc_id}
        frontier = [doc_id]
        results: list[str] = []
        for _ in range(hop):
            next_frontier = []
            for node in frontier:
                neighbors = self._collect_neighbors(node, direction)
                for n in neighbors:
                    if n not in visited:
                        visited.add(n)
                        results.append(n)
                        next_frontier.append(n)
                        if len(results) >= max_neighbors:
                            return results
            frontier = next_frontier
            if not frontier:
                break
        return results

    def _collect_neighbors(self, node: str, direction: str) -> Iterator[str]:
        if direction in ("out", "both"):
            yield from self._g.successors(node)
        if direction in ("in", "both"):
            yield from self._g.predecessors(node)

    def get_node(self, doc_id: str) -> GraphNode | None:
        if doc_id in self._node_cache:
            return self._node_cache[doc_id]
        if doc_id not in self._g:
            return None
        data = self._g.nodes[doc_id]
        node = GraphNode(
            doc_id=doc_id,
            title=data.get("title", ""),
            axes=data.get("axes", {}),
            in_degree=self._g.in_degree(doc_id),
            out_degree=self._g.out_degree(doc_id),
        )
        self._node_cache[doc_id] = node
        return node

    def get_all_nodes(self, *, limit: int | None = None, offset: int = 0) -> list[GraphNode]:
        """Pagination-aware node listing."""
        all_ids = list(self._g.nodes())
        if limit is not None:
            all_ids = all_ids[offset : offset + limit]
        return [self.get_node(d) for d in all_ids if self.get_node(d)]

    def get_all_edges(self) -> list[GraphEdge]:
        return [GraphEdge(source=u, target=v) for u, v in self._g.edges()]

    def find_path(self, source: str, target: str, *, max_length: int = 5) -> list[str] | None:
        """Find shortest path. None if no path or exceeds max_length."""
        try:
            path = nx.shortest_path(self._g, source=source, target=target)
            if len(path) - 1 > max_length:
                return None
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def stats(self) -> dict[str, int]:
        return {
            "nodes": self._g.number_of_nodes(),
            "edges": self._g.number_of_edges(),
            "isolated": len(list(nx.isolates(self._g))),
            "weakly_connected_components": nx.number_weakly_connected_components(self._g),
        }
```

#### 補助関数 (search 側で使う)

```python
def build_default_graph() -> KnowledgeGraph:
    """Load all docs from knowledge directory and build graph."""
    from backend.src.loader import load_directory
    from backend.src.config import Settings
    docs = load_directory(Settings().knowledge_dir or "./examples/knowledge")
    return KnowledgeGraph.build_from_docs([d.frontmatter for d in docs])
```

### 3-2. Search.py への統合

```python
# backend/src/search.py に追加

from backend.src.graph import KnowledgeGraph

class SearchEngine:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        *,
        # 既存 args ...
        graph: KnowledgeGraph | None = None,
    ):
        # ...
        self._graph = graph

    def search(
        self,
        query: str,
        *,
        # 既存 args ...
        graph_expand: bool = False,
        graph_hop: int = 1,
        graph_max_neighbors: int = 10,
    ) -> list[SearchResult]:
        # 既存の search ロジック (parent_doc / BM25 / time_decay)
        results = self._existing_search(query, ...)

        if graph_expand and self._graph is not None:
            results = self._expand_with_graph(
                results, hop=graph_hop, max_neighbors=graph_max_neighbors
            )
        return results

    def _expand_with_graph(
        self,
        results: list[SearchResult],
        *,
        hop: int,
        max_neighbors: int,
    ) -> list[SearchResult]:
        """Add 1-hop graph neighbors to the result set, deduplicated."""
        seen_ids = {r.doc_id for r in results}
        expanded = list(results)
        for r in results[:5]:  # 上位 5 件だけ展開対象に
            neighbors = self._graph.neighbors_within_hop(
                r.doc_id, hop=hop, max_neighbors=max_neighbors
            )
            for n_id in neighbors:
                if n_id in seen_ids:
                    continue
                seen_ids.add(n_id)
                # neighbor のスコアは元 result の 0.7 倍 (graph expansion bonus)
                neighbor_result = self._fetch_doc_as_result(n_id, score=r.score * 0.7)
                if neighbor_result is not None:
                    expanded.append(neighbor_result)
        expanded.sort(key=lambda x: x.score, reverse=True)
        return expanded
```

`_fetch_doc_as_result(doc_id, score)` は VectorStore から該当 doc の text と metadata を引いて SearchResult を組む helper。実装は既存パターンを参考に。

### 3-3. FastAPI endpoints

#### `GET /api/graph`

全ノード + エッジを返す (3D 描画用、pagination 対応)。

```python
@app.get("/api/graph", response_model=GraphResponse)
def get_graph(
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    axes_category: str | None = None,
    axes_level: str | None = None,
):
    nodes = state["graph"].get_all_nodes(limit=limit, offset=offset)
    # axes フィルタ
    if axes_category:
        nodes = [n for n in nodes if n.axes.get("category") == axes_category]
    if axes_level:
        nodes = [n for n in nodes if n.axes.get("level") == axes_level]
    node_ids = {n.doc_id for n in nodes}
    edges = [e for e in state["graph"].get_all_edges()
             if e.source in node_ids and e.target in node_ids]
    return GraphResponse(
        nodes=[
            GraphNodeModel(
                id=n.doc_id, title=n.title, axes=n.axes,
                in_degree=n.in_degree, out_degree=n.out_degree,
            ) for n in nodes
        ],
        edges=[GraphEdgeModel(source=e.source, target=e.target) for e in edges],
        stats=state["graph"].stats(),
    )
```

#### `GET /api/graph/{doc_id}/neighbors`

単一 doc の N hop 隣接を返す (graph sidebar 用)。

```python
@app.get("/api/graph/{doc_id}/neighbors", response_model=NeighborResponse)
def get_neighbors(doc_id: str, hop: int = 1, max_neighbors: int = 20):
    g = state["graph"]
    node = g.get_node(doc_id)
    if node is None:
        raise HTTPException(404, detail="doc_id not found in graph")
    neighbor_ids = g.neighbors_within_hop(doc_id, hop=hop, max_neighbors=max_neighbors)
    return NeighborResponse(
        center=GraphNodeModel.from_node(node),
        neighbors=[GraphNodeModel.from_node(g.get_node(nid)) for nid in neighbor_ids if g.get_node(nid)],
        hop=hop,
    )
```

#### lifespan で graph 構築

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 既存の init ...
    if cfg.graph.enabled:
        _log.info("building knowledge graph from %s", knowledge_dir)
        state["graph"] = build_default_graph()
        _log.info("graph stats: %s", state["graph"].stats())
    yield
```

### 3-4. MCP `axis_neighbors` tool

```python
@mcp.tool()
def axis_neighbors(
    doc_id: str,
    hop: int = 1,
    max_neighbors: int = 20,
    response_format: str = "markdown",
) -> str:
    """Return knowledge graph neighbors of a given doc_id within N hop.

    Useful for follow-up exploration: after a search, get related docs via refs.
    """
    try:
        g = _get_graph()
        node = g.get_node(doc_id)
        if node is None:
            return make_error_response(ValueError(f"doc_id {doc_id} not found"), tool="axis_neighbors")
        neighbor_ids = g.neighbors_within_hop(doc_id, hop=hop, max_neighbors=max_neighbors)
        neighbors = [g.get_node(nid) for nid in neighbor_ids if g.get_node(nid)]
        if response_format == "json":
            return format_neighbors_json(node, neighbors, hop)
        return format_neighbors_md(node, neighbors, hop)
    except Exception as e:
        return make_error_response(e, tool="axis_neighbors")
```

`_get_graph()` はモジュール global で 1 回だけ build、以後キャッシュ (起動時 lazy 構築)。

### 3-5. Next.js `/graph` ページ

#### `frontend/src/app/graph/page.tsx`

```tsx
"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { GraphSidebar } from "@/components/GraphSidebar";
import { GraphFilterBar } from "@/components/GraphFilterBar";
import { fetchGraph } from "@/lib/graphClient";

// react-force-graph-3d は WebGL 必須のため SSR disable
const Knowledge3DGraph = dynamic(
  () => import("@/components/Knowledge3DGraph").then(m => m.Knowledge3DGraph),
  { ssr: false, loading: () => <div className="p-8 text-center text-gray-500">Loading 3D graph...</div> }
);

export default function GraphPage() {
  const [graphData, setGraphData] = useState<any>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [filters, setFilters] = useState<{ category?: string; level?: string }>({});

  useEffect(() => {
    fetchGraph(filters).then(setGraphData);
  }, [filters]);

  return (
    <main className="grid grid-cols-[1fr_320px] h-[calc(100vh-60px)]">
      <div className="relative">
        <GraphFilterBar onChange={setFilters} stats={graphData?.stats} />
        {graphData && (
          <Knowledge3DGraph
            data={graphData}
            onNodeClick={(id) => setSelectedNode(id)}
            highlightedId={selectedNode}
          />
        )}
      </div>
      <GraphSidebar docId={selectedNode} onClose={() => setSelectedNode(null)} />
    </main>
  );
}
```

#### `frontend/src/components/Knowledge3DGraph.tsx`

```tsx
"use client";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import { useMemo } from "react";

type Node = { id: string; title: string; axes: Record<string, string>; in_degree: number; out_degree: number };
type Edge = { source: string; target: string };

type Props = {
  data: { nodes: Node[]; edges: Edge[] };
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
  const nodes = useMemo(() => data.nodes.map(n => ({
    id: n.id,
    name: n.title || n.id,
    val: 2 + n.in_degree + n.out_degree,
    color: AXIS_COLORS[n.axes.category ?? ""] ?? "#9ca3af",
    __raw: n,
  })), [data.nodes]);

  const links = useMemo(() => data.edges.map(e => ({ source: e.source, target: e.target })), [data.edges]);

  return (
    <ForceGraph3D
      graphData={{ nodes, links }}
      nodeRelSize={6}
      nodeLabel={(n: any) => `${n.name}\n(${n.__raw.axes.category ?? "—"} / in=${n.__raw.in_degree} out=${n.__raw.out_degree})`}
      nodeColor={(n: any) => n.id === highlightedId ? "#facc15" : n.color}
      linkColor={() => "#374151"}
      linkOpacity={0.4}
      linkDirectionalArrowLength={3}
      linkDirectionalArrowRelPos={0.85}
      onNodeClick={(n: any) => onNodeClick(n.id)}
      backgroundColor="#0a0a0a"
      cooldownTicks={150}
    />
  );
}
```

#### `frontend/src/components/GraphSidebar.tsx`

```tsx
import { useEffect, useState } from "react";

type Props = { docId: string | null; onClose: () => void };

export function GraphSidebar({ docId, onClose }: Props) {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    if (!docId) { setData(null); return; }
    fetch(`/api/graph/${docId}/neighbors?hop=1&max_neighbors=20`)
      .then(r => r.json()).then(setData);
  }, [docId]);

  if (!docId) return (
    <aside className="border-l bg-gray-50 p-4 text-sm text-gray-500">
      ノードをクリックして詳細を表示
    </aside>
  );

  return (
    <aside className="border-l bg-white p-4 overflow-y-auto text-sm">
      <button onClick={onClose} className="text-xs text-gray-500 hover:underline mb-2">✕ 閉じる</button>
      {data ? (
        <>
          <h3 className="text-base font-semibold mb-1">{data.center.title}</h3>
          <p className="text-xs text-gray-500 mb-3">{data.center.id}</p>
          <div className="mb-4">
            {Object.entries(data.center.axes).map(([k, v]) => (
              <span key={k} className="inline-block mr-1 mb-1 rounded bg-blue-100 px-2 py-0.5 text-xs">
                {k}: {String(v)}
              </span>
            ))}
          </div>
          <h4 className="text-sm font-semibold mb-2">🔗 隣接 ({data.neighbors.length})</h4>
          <ul className="space-y-1">
            {data.neighbors.map((n: any) => (
              <li key={n.id} className="text-xs">
                <span className="font-medium">{n.title}</span>
                <span className="text-gray-400 ml-1">({n.id})</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="text-gray-400">Loading...</div>
      )}
    </aside>
  );
}
```

#### `frontend/src/components/GraphFilterBar.tsx`

```tsx
type Props = { onChange: (f: { category?: string; level?: string }) => void; stats?: any };

export function GraphFilterBar({ onChange, stats }: Props) {
  return (
    <div className="absolute top-3 left-3 z-10 bg-white/90 backdrop-blur rounded-lg shadow p-3 text-xs">
      <h3 className="font-semibold mb-2">🕸️ Knowledge Graph</h3>
      {stats && (
        <p className="text-gray-500 mb-2">
          {stats.nodes} nodes, {stats.edges} edges<br/>
          {stats.isolated} isolated, {stats.weakly_connected_components} components
        </p>
      )}
      <select onChange={e => onChange({ category: e.target.value || undefined })} className="border rounded px-1 mb-1 w-full">
        <option value="">all categories</option>
        <option value="技術記事">技術記事</option>
        <option value="メモ">メモ</option>
        <option value="議事録">議事録</option>
        <option value="ToDo">ToDo</option>
      </select>
    </div>
  );
}
```

#### `frontend/src/lib/graphClient.ts`

```ts
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchGraph(filters: { category?: string; level?: string } = {}) {
  const params = new URLSearchParams({ limit: "500" });
  if (filters.category) params.set("axes_category", filters.category);
  if (filters.level) params.set("axes_level", filters.level);
  const res = await fetch(`${API}/api/graph?${params}`);
  if (!res.ok) throw new Error(`graph fetch failed: ${res.status}`);
  return res.json();
}
```

#### `frontend/src/app/layout.tsx` nav 追加

既存 nav に `🕸️ Graph` リンクを追加 (`/graph`)。

### 3-6. Streamlit "Graph" タブ (任意、軽量)

```python
# streamlit_app.py に追加
import networkx as nx
import matplotlib.pyplot as plt
import requests

def _graph_tab():
    st.subheader("🕸️ Knowledge Graph")
    try:
        data = requests.get(f"{AXIS_API_BASE}/api/graph?limit=200").json()
    except Exception as e:
        st.error(f"graph 取得失敗: {e}")
        return

    st.write(f"**{data['stats']['nodes']} nodes / {data['stats']['edges']} edges**")

    G = nx.DiGraph()
    for n in data["nodes"]:
        G.add_node(n["id"], title=n["title"], category=n.get("axes", {}).get("category", ""))
    for e in data["edges"]:
        G.add_edge(e["source"], e["target"])

    fig, ax = plt.subplots(figsize=(10, 8))
    pos = nx.spring_layout(G, k=0.5, iterations=30)
    cats = [G.nodes[n].get("category", "") for n in G.nodes()]
    color_map = {"技術記事": "#3b82f6", "メモ": "#a855f7", "議事録": "#22c55e", "ToDo": "#f97316"}
    colors = [color_map.get(c, "#9ca3af") for c in cats]
    nx.draw(G, pos, ax=ax, node_color=colors, node_size=200,
            with_labels=True, font_size=6, font_family="Hiragino Sans",
            arrows=True, edge_color="#9ca3af", alpha=0.7)
    st.pyplot(fig)
```

Streamlit `st.tabs` を 3 タブに拡張: `["🔎 Search", "💬 Chat", "🕸️ Graph"]`。

### 3-7. config.yml

```yaml
graph:
  enabled: true               # API + viz 有効化
  default_hop: 1              # /api/graph/{id}/neighbors の default
  max_neighbors_per_query: 20 # 1 query 上限
  expand_on_search: false     # /api/search が自動 graph_expand するか (default false、明示的に opt-in)
```

`backend/src/config.py` に `GraphConfig` dataclass 追加、`load_app_config()` でパース。

### 3-8. テスト

#### `backend/tests/test_graph.py` (15 件)

1. `test_build_from_empty_docs` — 空 list → 空グラフ
2. `test_build_with_single_doc_no_refs` — 1 node 0 edge
3. `test_build_directed_edges` — refs: [B] が doc_A から張られる
4. `test_self_loop_skipped` — doc_A.refs=[doc_A] は無視
5. `test_broken_ref_logged_and_skipped` — refs に存在しない doc_id があっても落ちず warning
6. `test_neighbors_within_hop_1` — 1 hop で直接隣接のみ
7. `test_neighbors_within_hop_2` — 2 hop で間接も含む
8. `test_neighbors_max_limit` — max_neighbors=2 で 2 件で stop
9. `test_neighbors_direction_out_only` — direction="out" で in は含まない
10. `test_neighbors_direction_in_only` — direction="in" で out は含まない
11. `test_get_node_unknown_returns_none` — 存在しない id → None
12. `test_get_node_in_out_degree` — degree が正しく計算される
13. `test_find_path_exists` — A→B→C のパス取得
14. `test_find_path_no_path` — 切断グラフで None
15. `test_find_path_self_returns_single_node` — find_path(A, A) → [A]
16. `test_stats` — nodes / edges / isolated / weakly_connected_components が正しい
17. `test_pagination_get_all_nodes` — limit/offset で部分取得
18. `test_circular_refs_allowed` — A→B→A の循環で例外なし、neighbors_within_hop も正常

#### `backend/tests/test_search.py` (graph_expand 統合、5 件追加)

1. `test_search_with_graph_expand_adds_neighbors` — top 5 + 隣接 → 結果数が増える
2. `test_search_graph_expand_dedupe` — 隣接が既に top 内にあれば dedup
3. `test_search_graph_expand_score_decay` — 隣接スコアは元の 0.7 倍
4. `test_search_no_graph_no_expand` — graph=None でも graph_expand=True が落ちない (no-op + warning)
5. `test_search_graph_expand_max_neighbors` — max=2 で各 source から 2 件まで

#### `backend/tests/test_api.py` (graph endpoints、4 件)

1. `test_get_graph_returns_nodes_and_edges` — 200, nodes/edges 配列
2. `test_get_graph_filter_by_category` — `?axes_category=技術記事` で部分グラフ
3. `test_get_neighbors_known_doc` — 200 + neighbors list
4. `test_get_neighbors_unknown_doc_404` — 不明 doc_id で 404

### 3-9. 依存追加

#### `pyproject.toml`

```toml
[project]
dependencies = [
    # ... 既存 ...
    "networkx>=3.0,<4",
]
```

#### `frontend/package.json`

```json
{
  "dependencies": {
    // ... 既存 ...
    "react-force-graph-3d": "^1.24.0",
    "three": "^0.160.0",
    "d3-force-3d": "^3.0.5"
  }
}
```

`npm install` で導入、`npm run build` が緑になることを確認。

### 3-10. ADR

#### `docs/adr/ADR-024-graphrag-retrieval-expansion.md`

- **Context**: v0.7 までは検索結果に `refs:` の情報が反映されていなかった
- **Decision**: networkx で有向グラフ構築、search.py で 1 hop 拡張、スコアは 0.7 倍 decay
- **Alternatives**:
  - (a) Neo4j 専用グラフ DB → 却下 (依存重い、個人運用に不要)
  - (b) ChromaDB の metadata クエリで refs を join → 却下 (ChromaDB は graph 演算苦手)
  - (c) networkx + in-memory (採用)
  - (d) NetworkX → スコア重み計算は PageRank → 検討するが v0.8 では simple 0.7 decay で十分
- **Consequences**:
  - networkx 依存 (~600KB) を main deps に追加
  - graph 再構築は起動時のみ (再起動不要なら lazy load OK)
  - graph_expand=true 時、結果数は最大 +50 件膨らむ可能性

#### `docs/adr/ADR-025-3d-graph-visualization.md`

- **Context**: ナレッジ間の関係を視覚的に表現したい
- **Decision**: react-force-graph-3d (Three.js + d3-force-3d 既知 wrapper) で力学シミュレーション 3D グラフ
- **Alternatives**:
  - (a) sigma.js (2D) → 却下 (差別化弱い、3D の方が映える)
  - (b) Cytoscape.js → 却下 (バイオ系向け、UI 古い)
  - (c) D3.js raw → 却下 (3D の自前実装はコスト高い)
  - (d) react-force-graph-3d (採用) — MIT, 5KB API, 充実したドキュメント
- **Consequences**:
  - frontend deps が `three` (~600KB) + `react-force-graph-3d` (~150KB) で増える
  - WebGL 必須 → モバイル / IE は表示不可 (gracefully degrade で "non-supported" メッセージ表示)
  - 大規模グラフ (1000+ nodes) は描画重い → API で pagination & axes filter 必須

### 3-11. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
git checkout -b feat/spec_040-graphrag-3d

# Backend deps
pip install -e .
pip show networkx | head -3

# Backend lint + test
ruff check .
python3 -m pytest -q
python3 -m pytest -q backend/tests/test_graph.py backend/tests/test_search.py::test_search_with_graph_expand -v

# API smoke
uvicorn backend.src.api:app --port 8000 &
sleep 3
curl -s 'http://localhost:8000/api/graph?limit=50' | jq '.stats'
curl -s 'http://localhost:8000/api/graph/doc_001/neighbors?hop=1' | jq '.neighbors | length'
curl -s -X POST 'http://localhost:8000/api/search' \
  -H 'Content-Type: application/json' \
  -d '{"query":"RAG","top_k":3,"graph_expand":true}' | jq '.hits | length'
kill %1

# Frontend
cd frontend
npm install
npm run build 2>&1 | tail -10
# /graph ページが build 緑であることを確認

# Streamlit (任意)
streamlit run streamlit_app.py
# → 🕸️ Graph タブで 2D グラフ表示確認
```

### 3-12. コミット粒度

1. `feat(graph): KnowledgeGraph wrapper over networkx with build_from_docs + neighbors_within_hop`
2. `test(graph): cover broken refs, self-loops, hop expansion, find_path, stats`
3. `feat(search): graph_expand parameter + _expand_with_graph with 0.7x score decay`
4. `feat(api): GET /api/graph + /api/graph/{id}/neighbors endpoints with axes filter`
5. `feat(config): graph.{enabled, default_hop, max_neighbors_per_query, expand_on_search}`
6. `feat(mcp): axis_neighbors tool with markdown/json formatters`
7. `feat(frontend): /graph page + Knowledge3DGraph + GraphSidebar + GraphFilterBar`
8. `feat(frontend): react-force-graph-3d + three + d3-force-3d dependencies`
9. `feat(streamlit): Graph tab with 2D networkx + matplotlib visualization`
10. `docs: ADR-024 + ADR-025 + architecture / api-reference / configuration / README / CHANGELOG`

`git push -u origin feat/spec_040-graphrag-3d`

### 3-13. result_040.md に書くこと

- グラフ stats (nodes / edges / isolated / components) を実 examples/knowledge/ で計測
- `/api/search graph_expand=true` の前後比較 (同じクエリで結果数 / 上位の変化)
- 3D グラフのスクショ取得手順 (手動、ESC キーで画面キャプチャ → `examples/screenshots/graph_3d.png`)
- 全テスト数 (261 + 27 = 288 程度)、ruff 緑、npm run build 緑
- 既存 261 tests に回帰なし
- networkx 依存追加によるインストールサイズ増加 (`pip show networkx` で表示)

## 4. 成功条件

- [ ] `KnowledgeGraph.build_from_docs()` が examples/knowledge から graph 構築可能
- [ ] broken refs / self-loop / circular refs を **落ちずに安全処理** (warning ログ + skip 1 件)
- [ ] `/api/graph` が 200 OK で nodes + edges + stats を返す
- [ ] `/api/graph/{doc_id}/neighbors?hop=1` が 200 OK、不明 doc_id で 404
- [ ] `/api/search` の `graph_expand=true` で結果に隣接が混入 + score=元 × 0.7
- [ ] `axis_neighbors` MCP tool が Claude Desktop から呼べる
- [ ] `/graph` Next.js ページが描画され、ノードクリック → サイドバー表示が動く
- [ ] axes filter で部分グラフ表示が動く
- [ ] Streamlit 🕸️ Graph タブで 2D 可視化動作
- [ ] 既存 261 tests 緑 + 新規 graph 関連 >=22 件 = **>=283 件 PASS**
- [ ] ruff 緑、`npm run build` 緑、`npx tsc --noEmit` 緑
- [ ] ADR-024 / ADR-025 + 全 docs 更新
- [ ] git push 完了 (main には push しない)

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_040.md`

## 6. 質問があるとき

- **graph build を起動時か lazy か**: 本 spec は起動時 (lifespan で build_default_graph)。docs が 1000+ になる場合は lazy load + キャッシュ無効化戦略が必要だが、v0.8 では起動時で OK
- **3D グラフのパフォーマンス**: 500 nodes 程度なら問題なし、1000+ で重い場合は cooldownTicks を下げる / axes filter を強制
- **graph_expand=true を search default にするか**: 本 spec では default false (明示的に opt-in)。run 後 RAGAS で精度が向上するなら spec_041 で default true 化を検討
- **streamlit_app.py の Graph タブ**: matplotlib + Hiragino Sans 日本語フォントが入っていない可能性あり (font fallback)。warning だけで OK、本機能はサブ
- **networkx version**: `>=3.0,<4` で固定。3.x は API 安定、4.0 出たら追従

迷ったら `result_040.md` の Open questions に書いて `status: blocked` で終了。

## 7. 補足

### 設計の意図

- GraphRAG は **2025-2026 RAG コミュニティで急速に注目** されている。Microsoft の GraphRAG 論文 (2024) が話題。本リポジトリで自前実装することで、ポートフォリオに「GraphRAG を理解+実装した」と書ける
- 3D 可視化は **ES / 採用面接でデモ映えが大きい**。スクショ 1 枚で「ナレッジの規模感」が伝わる
- `refs:` を既に YAML で持っているのに使えていなかった、という「**もったいない**」を解消する筋の良い改善

### 将来の拡張余地

- **spec_041 候補**: PageRank で重要 node を highlight、search ranking に node centrality を mix
- **spec_042 候補**: 編集モード — 3D グラフ上で node ドラッグでクラスタを作る、refs を GUI で追加
- **spec_043 候補**: 時系列アニメーション — 「過去 1 週間で追加された node を highlight」など
- **v0.9 候補**: グラフ嵌入 (graph embedding、Node2Vec) を embedding と blend した hybrid retrieval

### 既知のリスク

- **react-force-graph-3d の SSR 非対応**: `dynamic({ ssr: false })` で回避済み、`'use client'` 必須
- **WebGL 非対応環境**: モバイル Safari の古い版 / IE は表示不可。`<noscript>` / WebGL check で gracefully degrade
- **大規模グラフのレンダリング負荷**: 500 node 以下が現実的、1000+ は要 pagination + filter
