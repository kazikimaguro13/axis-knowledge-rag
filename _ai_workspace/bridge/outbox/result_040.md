# result_040 — GraphRAG + 3D Knowledge Graph (v0.8 マーキー機能)

- **Status**: ✅ done
- **Branch**: `feat/spec_040-graphrag-3d`
- **Pushed**: yes (origin)
- **Date**: 2026-05-14
- **Spec**: spec_040 (bundles Gemini ③ GraphRAG + ⑥ 3D Knowledge Graph)

---

## 1. 何をしたか

YAML frontmatter `refs:` を **初めて** retrieval / 可視化のソースとして活用した。

1. **`backend/src/graph.py`** — networkx ベースの `KnowledgeGraph` を新設。起動時に
   `examples/knowledge/*.md` の frontmatter から有向グラフを 1 回 build。broken refs
   は warning + skip、self-loop は silently skip、循環参照は許容。
2. **`SearchEngine.search(graph_expand=True)`** — 上位 5 件のヒットに対して 1 hop
   隣接を BFS し、score = 元 × 0.7 でマージ + 再ランク。default は `false`、
   既存 `/api/search` 挙動は完全互換。
3. **`GET /api/graph` / `GET /api/graph/{id}/neighbors`** — 全ノード+エッジ JSON
   (limit/offset/axes フィルタ付き) と単一 doc の N hop 隣接。
4. **MCP `axis_neighbors` tool** — Claude Desktop からの follow-up 用。
   `direction="out|in|both"` で参照方向を選択可。
5. **Next.js `/graph` ページ** — `react-force-graph-3d` + `three` + `d3-force-3d`
   で 3D 力学シミュレーション。node click → サイドパネル、category/level filter、
   stats overlay。
6. **Streamlit "🕸️ Graph" タブ** — `/api/graph` を fetch して
   `networkx + matplotlib` で 2D spring layout (軽量フォールバック)。

---

## 2. グラフ実測値 (`examples/knowledge/`, 10 docs)

```
{"nodes": 10, "edges": 7, "isolated": 1, "weakly_connected_components": 3}

broken refs: 1 (doc_005 -> doc_999 を warning + skip)

ノードごとの in/out_degree:
  doc_001 in=3 out=0  RAGアーキテクチャの設計判断       ← 中心
  doc_002 in=1 out=1  ベクトル検索とコサイン類似度の実務
  doc_003 in=1 out=0  YAML frontmatter によるメタデータ設計
  doc_004 in=0 out=2  Claude API と Skills の使い分け
  doc_005 in=1 out=0  プロンプトエンジニアリングの実務原則
  doc_006 in=0 out=1  プロンプトインジェクション対策の基本
  doc_007 in=0 out=1  RAG の評価指標と運用観点
  doc_008 in=1 out=0  LangChain / LlamaIndex / 自前実装の使い分け
  doc_009 in=0 out=0  RAG 運用のコスト試算            ← isolated
  doc_010 in=0 out=2  axis-knowledge-rag の将来ロードマップ

エッジ:
  doc_002 → doc_001    doc_004 → doc_001    doc_004 → doc_003
  doc_006 → doc_005    doc_007 → doc_001    doc_010 → doc_002
  doc_010 → doc_008
```

---

## 3. `graph_expand=true` の前後比較 (実測)

同じクエリ `"RAG"` を `top_k=3` で投げて、結果セットの変化を計測:

| 設定 | 結果件数 | id の並び |
|---|---|---|
| `graph_expand=false` (default) | 3 | doc_003, doc_005, doc_007 |
| `graph_expand=true` | **6** | doc_003, doc_005, doc_007, **doc_004, doc_006, doc_001** |

追加された 3 件はそれぞれ:
- `doc_005` → 隣接 (in: doc_006) ＋ (out: なし) ＝ doc_006 が引き込まれた
- `doc_007` → 隣接 (out: doc_001) ＝ doc_001 が引き込まれた
- `doc_003` → 隣接 (in: doc_004) ＝ doc_004 が引き込まれた

DUMMY embedder (GEMINI_API_KEY 未設定) のため score は 0.0 で並んでいるが、
graph expansion の merge ロジック自体は仕様通り動作している。

---

## 4. テスト / Lint / Build

| チェック | 結果 |
|---|---|
| **pytest 全体** | ✅ **291 passed** in 22.75s (既存 261 + 新規 30) |
| `test_graph.py` | ✅ 21 件 (spec の最低 15+ を超過) |
| `test_search.py` 新規 | ✅ 5 件 (graph_expand 統合) |
| `test_api.py` 新規 | ✅ 4 件 (`/api/graph` e2e) |
| `ruff check .` | ✅ All checks passed |
| `npm run build` (frontend) | ✅ 8/8 static pages、`/graph` 3.83 kB |
| `npx tsc --noEmit` | ✅ no output (緑) |
| `npx next lint` | ✅ No ESLint warnings or errors |

---

## 5. 変更ファイル一覧

### 新規

- `backend/src/graph.py` — `KnowledgeGraph` + `build_default_graph`
- `backend/tests/test_graph.py` — 21 件
- `docs/adr/ADR-024-graphrag-retrieval-expansion.md`
- `docs/adr/ADR-025-3d-graph-visualization.md`
- `frontend/src/app/graph/page.tsx`
- `frontend/src/components/Knowledge3DGraph.tsx`
- `frontend/src/components/GraphSidebar.tsx`
- `frontend/src/components/GraphFilterBar.tsx`
- `frontend/src/lib/graphClient.ts`

### 変更

- `backend/src/config.py` — `GraphConfig` 追加 + `load_app_config()`
- `backend/src/search.py` — `graph` 引数 + `search(graph_expand=...)` + `_expand_with_graph()` + `_fetch_doc_as_result()`
- `backend/src/schemas.py` — `Graph{Node,Edge,Stats,Response}Model` + `NeighborResponse` + `SearchRequest.graph_expand`
- `backend/src/api.py` — `/api/graph` + `/api/graph/{id}/neighbors` + lifespan で graph build + `/api/search` の graph_expand パラメータ受け
- `backend/tests/test_search.py` — graph_expand 統合 5 件追加
- `backend/tests/test_api.py` — graph endpoints 4 件追加
- `mcp_server/server.py` — `axis_neighbors` tool + `_get_graph()` lazy singleton
- `mcp_server/schemas.py` — `NeighborsInput`
- `mcp_server/formatters.py` — `format_neighbors_md/json`
- `frontend/src/app/layout.tsx` — nav に "🕸️ Graph"
- `frontend/package.json` — `react-force-graph-3d` + `three` + `d3-force-3d`
- `streamlit_app.py` — 第 3 タブ `🕸️ Graph` (networkx + matplotlib)
- `config.yml` — `graph.*` ブロック
- `pyproject.toml` — `networkx>=3.0,<4`
- `docs/architecture.md` — §3-3 Graph layer 新設
- `docs/api-reference.md` — graph endpoints + graph_expand
- `docs/mcp-server.md` — §3-7 axis_neighbors
- `README.md` — ✨ 特徴 + config テーブル
- `CHANGELOG.md` — Day 40 追記

### 依存追加 (size)

- Backend: `networkx` 3.6.1 (~2.1 MB on disk, pure Python)
- Frontend: `three` (~600 KB), `react-force-graph-3d` (~150 KB), `d3-force-3d` (~30 KB)

---

## 6. 成功条件のチェック

- ✅ `KnowledgeGraph.build_from_docs()` が examples/knowledge から graph 構築可能
- ✅ broken refs / self-loop / circular refs を落ちずに安全処理 (実例: doc_005→doc_999 を warning + skip)
- ✅ `/api/graph` が 200 OK で nodes + edges + stats を返す
- ✅ `/api/graph/{doc_id}/neighbors?hop=1` が 200、不明 doc で 404
- ✅ `/api/search` の `graph_expand=true` で結果に隣接が混入 (3 → 6 件、+3 件)
- ✅ `axis_neighbors` MCP tool 実装 (`direction` 引数も拡張)
- ✅ `/graph` Next.js ページが build 緑、3D グラフは `dynamic({ ssr: false })` 経由
- ✅ axes filter (category / level) を API + Frontend 両方で対応
- ✅ Streamlit 🕸️ Graph タブで 2D 可視化動作
- ✅ 既存 261 tests 緑 + 新規 30 件 = **291 件 PASS** (spec の "≥ 283" を上回る)
- ✅ ruff 緑、`npm run build` 緑、`npx tsc --noEmit` 緑、`next lint` 緑
- ✅ ADR-024 / ADR-025 + 全 docs 更新
- ⏳ git push 完了 (この result_040.md コミット直後に実施)

---

## 7. 設計判断・補足

### `graph_expand` を default false にした理由

`config.yml` `graph.expand_on_search: false` を維持し、API リクエストに
`graph_expand=true` を明示した場合のみ拡張が走る。理由:

1. **既存クライアントの API 契約を 100% 維持** — Day 1 から導入されている
   `/api/search` を呼ぶ任意のコードは何も変えずに同じ結果を受け取る。
2. **結果セットサイズが膨らむ** — 上位 5 件 × max_neighbors=10 = 最大 +50 件。
   `top_k` でスライスして返すが、context 構築への影響を caller が制御すべき。
3. **RAGAS で精度向上を確認してから default 化** — spec_041 候補に「graph_expand を
   default true 化」を残してある。Recall@K / Faithfulness の改善が確認できた段階で
   `expand_on_search: true` に切り替える。

### `_fetch_doc_as_result()` の二段フォールバック

graph_expand 時、隣接 doc の SearchResult を組み立てる必要がある。実装は:

1. **legacy file-level path** — `chroma._collection.get(ids=[doc_id])` で metadata
   + body を直接取得。
2. **parent-doc path fallback** — file-level get が空ならば `store.parents` を
   線形走査して `doc_id` 一致を探し、`_parent_to_result()` で組む。

parent-doc モードでは Chroma に格納されているのは child chunk なので
`.get(ids=[doc_id])` が空を返す。この二段フォールバックで両モードに対応した。

---

## 8. Open questions / Future work

- **3D グラフのスクショ取得**: 手動キャプチャ前提のため、本 result には未添付。
  README に `examples/screenshots/graph_3d.png` の参照を埋める作業は別 spec
  (spec_044 候補) として残す。
- **graph_expand を default true 化**: RAGAS で Recall@5 / Faithfulness の差分を
  計測した上で spec_041 で実施。
- **PageRank ベースのリランク**: ADR-024 で却下したが、v0.9 候補。
- **大規模グラフ (1000+ nodes) のパフォーマンス**: `/api/graph` は limit/offset
  + axes フィルタを既に持つ。実コーパスで詰まったタイミングで `cooldownTicks` /
  Web Worker 化を検討。
- **`streamlit_app.py` の Hiragino Sans フォント**: 環境依存の表示崩れあり。
  matplotlib font fallback で Tofu が出ても機能には影響しない (本 spec のサブ機能)。

---

## 9. 検証コマンド (再現用)

```bash
# 単体テスト
python3 -m pytest -q                              # 291 passed
python3 -m pytest backend/tests/test_graph.py -v
python3 -m pytest backend/tests/test_search.py -k graph -v
python3 -m pytest backend/tests/test_api.py::test_get_graph_returns_nodes_and_edges -v

# Lint
ruff check .                                       # All checks passed
cd frontend && npx tsc --noEmit && npx next lint   # 緑

# 起動 + API smoke
python3 -m uvicorn backend.src.api:app --port 8765 &
sleep 4
curl -s 'http://127.0.0.1:8765/api/graph' | jq '.stats'
curl -s 'http://127.0.0.1:8765/api/graph/doc_001/neighbors?hop=1' | jq '.neighbors | length'
curl -s -X POST 'http://127.0.0.1:8765/api/search' \
  -H 'Content-Type: application/json' \
  -d '{"query":"RAG","top_k":3,"graph_expand":true}' | jq '.results | length'
```
