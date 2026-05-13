# MCP Server — axis_knowledge_rag_mcp

axis-knowledge-rag を [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) サーバーとして公開するモジュール (`mcp_server/`) の詳細解説。

---

## 1. なぜ MCP 化したか

axis-knowledge-rag は当初 Streamlit UI / FastAPI / Next.js という「人間 → UI → Backend」経路だけを想定していた。これに加えて **Claude Desktop / Cowork / 任意の MCP 対応クライアントから直接ナレッジを叩く経路** を整備した。

**背景と動機:**

| 課題 | 解決策 |
|---|---|
| Claude からナレッジを参照するには URL コピー or 画面経由が必要 | MCP tool として公開し、Claude が自律的に呼び出せる |
| RAG の質問応答を AI エージェントのサブタスクとして組み込めない | `axis_answer` tool を expose し、エージェントループに組み込み可能にする |
| 採用面接デモが「普通の Web アプリ」に見える | Claude Desktop から自分の OSS を直接叩くデモで MCP エコシステム対応を示す |

---

## 2. アーキテクチャ

```
Claude Desktop / Cowork / mcp-cli
        │  (stdio, JSON-RPC 2.0)
        ▼
mcp_server/server.py   ← FastMCP wrapper
        │  (直接 import, 関数呼び出し)
        ├─ backend.src.search.SearchEngine    ← axis filter + vector hybrid
        ├─ backend.src.rag.RAGPipeline        ← Claude API + citations
        ├─ backend.src.integrity.IntegrityChecker
        └─ backend.src.loader.load_directory
                │
                ▼
         ChromaDB (local persistent)
```

**設計の核心: backend モジュールをそのまま import**

`mcp_server/server.py` は薄い wrapper に徹している。`search.py` / `rag.py` / `integrity.py` / `ingester.py` は既に「ライブラリとして使える」設計なので、コード重複ゼロで 6 tools (5 read + 1 ingest) を実装できた。

**lazy singleton パターン:**

初回 tool 呼び出しで `_get_engine()` / `_get_rag()` が実行され、以降はメモ化。VectorStore 初期化 (~100ms) を毎 tool call で繰り返さない。

**stdio transport と stdout 保護:**

MCP stdio transport は `stdout` が JSON-RPC ストリーム。`main()` 内で全 logging handler の stream を `stderr` に向け直し、ログが JSON-RPC を汚染しないようにしている。

---

## 3. 提供 tools 一覧

### 3-1. `axis_search`

軸フィルタ + ベクトル hybrid 検索。Claude API を使わない完全ローカル完結。

**Input schema:**

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `query` | `string \| null` | `null` | 自然文クエリ。省略時は軸フィルタのみで絞り込み |
| `filters` | `dict[str, str\|int]` | `{}` | 軸フィルタ。`{"category": "技術記事"}` 形式 |
| `top_k` | `int` (1–50) | `5` | 返却する最大件数 |
| `response_format` | `"markdown" \| "json"` | `"markdown"` | 出力形式 |

**Markdown 出力サンプル:**

```markdown
# Search results for: `RAG architecture`

**Filters**: {'category': '技術記事'}

**3** result(s)

## [0.921] `doc_001` — RAGアーキテクチャの設計判断
- axes: {'category': '技術記事', 'topic': 'RAG', 'level': '中級'}

RAG (Retrieval-Augmented Generation) は検索と生成を組み合わせたアーキテクチャ...
```

**JSON 出力サンプル:**

```json
{
  "query": "RAG architecture",
  "filters": {"category": "技術記事"},
  "count": 3,
  "results": [
    {
      "id": "doc_001",
      "title": "RAGアーキテクチャの設計判断",
      "score": 0.921,
      "axes": {"category": "技術記事", "topic": "RAG", "level": "中級"},
      "body_snippet": "RAG (Retrieval-Augmented Generation) は...",
      "path": "examples/knowledge/01-rag-patterns.md",
      "refs": ["doc_002"]
    }
  ]
}
```

**Annotations:**

- `readOnlyHint: true` / `destructiveHint: false` / `idempotentHint: true` / `openWorldHint: false`

---

### 3-2. `axis_answer`

RAG 回答生成。Claude API を叩き、出典 `[doc_NNN]` 付きで回答する。ANTHROPIC_API_KEY 未設定時は DUMMY モード（決定論的応答）。

**Input schema:**

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `question` | `string` (1–1000) | 必須 | 質問文 |
| `filters` | `dict[str, str\|int]` | `{}` | 軸フィルタ |
| `top_k` | `int` (1–20) | `5` | コンテキストに含むドキュメント数 |
| `max_tokens` | `int` (128–4096) | `1024` | Claude 回答の最大トークン数 |
| `response_format` | `"markdown" \| "json"` | `"markdown"` | 出力形式 |

**Markdown 出力サンプル:**

```markdown
# Answer to: RAG とはどのような仕組みですか？

RAG (Retrieval-Augmented Generation) は、検索エンジンと大規模言語モデルを組み合わせたアーキテクチャです [doc_001]。
ベクトルデータベースから関連文書を取得し、それをコンテキストとして LLM に渡すことで、ハルシネーションを低減します [doc_001][doc_002]。

## Sources
- `doc_001` — RAGアーキテクチャの設計判断 (score 0.921) * cited
- `doc_002` — ベクトル検索の仕組み (score 0.874) * cited
```

**JSON 出力サンプル:**

```json
{
  "question": "RAG とはどのような仕組みですか？",
  "answer": "RAG は検索と生成を...",
  "cited_ids": ["doc_001", "doc_002"],
  "is_dummy": false,
  "model": "claude-3-5-sonnet-20241022",
  "sources": [
    {"id": "doc_001", "title": "RAGアーキテクチャの設計判断", "score": 0.921, "axes": {...}}
  ]
}
```

**Annotations:**

- `readOnlyHint: true` / `destructiveHint: false` / `idempotentHint: false` (Claude API は非決定論的) / `openWorldHint: true` (Anthropic API 呼び出し)

---

### 3-3. `axis_list_axes`

`config.yml` に定義された軸の一覧を返す。`axis_search` / `axis_answer` に渡せるフィルタキーを事前確認するために使う。

**Input schema:**

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `response_format` | `"markdown" \| "json"` | `"markdown"` | 出力形式 |

**Markdown 出力サンプル:**

```markdown
# Available axes

- **category** (enum, required) — values: ['技術記事', 'メモ', '議事録', 'ToDo']
- **topic** (string, required)
- **level** (enum) — values: ['初級', '中級', '上級']
- **author** (string)
- **year** (integer)
```

**JSON 出力サンプル:**

```json
{
  "axes": [
    {
      "name": "category",
      "type": "enum",
      "required": true,
      "values": ["技術記事", "メモ", "議事録", "ToDo"]
    },
    {"name": "topic", "type": "string", "required": true},
    {"name": "level", "type": "enum", "values": ["初級", "中級", "上級"]},
    {"name": "author", "type": "string"},
    {"name": "year", "type": "integer"}
  ]
}
```

**Annotations:**

- `readOnlyHint: true` / `destructiveHint: false` / `idempotentHint: true` / `openWorldHint: false`

---

### 3-4. `axis_check_integrity`

ナレッジディレクトリ内のドキュメントの参照整合性を検査する。broken refs / orphan docs / cycles を検出。

**Input schema:**

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `knowledge_dir` | `string` | `"./examples/knowledge"` | 検査対象ディレクトリ |
| `strict` | `bool` | `false` | broken ref があれば summary に明記（UI 表示用） |
| `response_format` | `"markdown" \| "json"` | `"markdown"` | 出力形式 |

**Markdown 出力サンプル (broken ref あり):**

```markdown
# Integrity Report

- Total documents: 10
- Total refs:      8

## Broken refs (1)
- `doc_004` (`examples/knowledge/04-claude-skills.md`) -> **`doc_999` (missing)**

No orphan docs

No cycles
```

**JSON 出力サンプル:**

```json
{
  "total_docs": 10,
  "total_refs": 8,
  "broken_refs": [
    {
      "source_id": "doc_004",
      "source_path": "examples/knowledge/04-claude-skills.md",
      "target_id": "doc_999"
    }
  ],
  "orphan_docs": [],
  "cycles": []
}
```

**Annotations:**

- `readOnlyHint: true` / `destructiveHint: false` / `idempotentHint: true` / `openWorldHint: false`

---

### 3-5. `axis_list_documents`

ナレッジベース内のドキュメント一覧を軸フィルタ + ページング付きで返す。

**Input schema:**

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `filters` | `dict[str, str\|int]` | `{}` | 軸フィルタ |
| `limit` | `int` (1–100) | `20` | 1 ページの最大件数 |
| `offset` | `int` (≥0) | `0` | スキップ件数 |
| `response_format` | `"markdown" \| "json"` | `"markdown"` | 出力形式 |

**Markdown 出力サンプル:**

```markdown
# Documents (total=10, offset=0, count=5)

_next offset: 5_

- `doc_001` — RAGアーキテクチャの設計判断 — axes: {'category': '技術記事', ...}
- `doc_002` — ベクトル検索の仕組み — axes: {'category': '技術記事', ...}
- `doc_003` — YAMLフロントマター設計ガイド — axes: {'category': '技術記事', ...}
- `doc_004` — Claudeスキル活用パターン — axes: {'category': '技術記事', ...}
- `doc_005` — プロンプトエンジニアリング入門 — axes: {'category': '技術記事', ...}
```

**JSON 出力サンプル:**

```json
{
  "total": 10,
  "count": 5,
  "offset": 0,
  "has_more": true,
  "next_offset": 5,
  "documents": [
    {
      "id": "doc_001",
      "title": "RAGアーキテクチャの設計判断",
      "axes": {"category": "技術記事", "topic": "RAG", "level": "中級"},
      "path": "examples/knowledge/01-rag-patterns.md"
    }
  ]
}
```

**Annotations:**

- `readOnlyHint: true` / `destructiveHint: false` / `idempotentHint: true` / `openWorldHint: false`

---

### 3-6. `axis_ingest_memo`

生メモ (Slack 抜粋 / 議事録 / Apple Notes / プレーン Markdown) を axis-knowledge-rag 形式の YAML-frontmatter Markdown に Claude API で変換する。**ファイル書き込みなし** — 変換結果を返すだけなので read-only 扱い (中島さんがプレビューしてから手動 commit する想定)。`ANTHROPIC_API_KEY` 未設定時は DUMMY モード (決定論的 mock)。

**Input schema:**

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `raw_text` | `string` (20–10000) | 必須 | 変換対象の生メモテキスト |
| `knowledge_dir` | `string` | `"./examples/knowledge"` | 既存 KB ディレクトリ。次の `doc_NNN` id 採番 + refs 候補の参照に使う |
| `suggested_category` | `string \| null` | `null` | カテゴリヒント (`"議事録"` 等)。Claude の軸推定をバイアス |
| `max_tokens` | `int` (512–4096) | `1500` | Claude 応答の最大トークン数 |
| `response_format` | `"markdown" \| "json"` | `"markdown"` | 出力形式 |

**Markdown 出力サンプル:**

```markdown
---
id: doc_011
title: ベクトル検索の選定メモ
axes:
  category: 技術記事
  topic: vector-search
  level: 中級
tags: [vector-search, chromadb]
refs: [doc_002]
created: 2026-05-13
updated: 2026-05-13
---

# ベクトル検索の選定メモ

ChromaDB を選定した理由は...
```

**JSON 出力サンプル:**

```json
{
  "id": "doc_011",
  "title": "ベクトル検索の選定メモ",
  "axes": {"category": "技術記事", "topic": "vector-search", "level": "中級"},
  "tags": ["vector-search", "chromadb"],
  "refs": ["doc_002"],
  "rendered_md": "---\nid: doc_011\n...",
  "is_dummy": false
}
```

**Annotations:**

- `readOnlyHint: true` (ファイル書き込みなし) / `destructiveHint: false` / `idempotentHint: false` (Claude API は非決定論的) / `openWorldHint: true` (Anthropic API 呼び出し)

詳細仕様: [docs/ingester.md](ingester.md)

---

## 4. Error handling

MCP tools never leak internal exception details to clients. On error:

1. The full exception (type, message, traceback) is logged to `stderr` with
   a 5-character correlation id.
2. The tool returns a generic message including only the correlation id:

   ```
   Error [a3b1c]: axis_search failed. Check server logs (correlation id: a3b1c).
   ```

This prevents leakage of:
- Anthropic / Gemini API error bodies (rate limits, billing, deprecations)
- Internal file paths (`/home/.../...`)
- Pydantic validation details (which can echo input values back)
- ChromaDB schema fragments

For operators: search server logs for the `corr=<id>` token to find the
full stack trace.

For developers writing new tools: wrap your tool body in `try/except` and
return `make_error_response(<tool_name>, exc)` from `mcp_server._errors`.

---

## 5. Claude Desktop への組み込み手順

### 5-1. 前提

- Python 3.11+
- axis-knowledge-rag を clone 済み
- `pip install -e .` 済み (または `pip install -e ".[dev]"`)
- ChromaDB index ビルド済み (`python -m scripts.build_index ./examples/knowledge --reset`)

### 5-2. macOS

設定ファイルのパス: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "axis-knowledge-rag": {
      "command": "python3",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/axis-knowledge-rag",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "GEMINI_API_KEY": "AIza..."
      }
    }
  }
}
```

### 5-3. Windows

設定ファイルのパス: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "axis-knowledge-rag": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:\\Users\\<your-name>\\axis-knowledge-rag",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "GEMINI_API_KEY": "AIza..."
      }
    }
  }
}
```

### 5-4. Linux / WSL2

Claude Desktop は 2026-05 時点で Linux ネイティブ未対応。WSL2 環境からは Cowork または mcp-cli 経由で使う。設定形式は macOS と同様。

### 5-5. エントリポイントスクリプト経由

`pip install -e .` 後は `axis-knowledge-rag-mcp` コマンドが使える:

```json
{
  "mcpServers": {
    "axis-knowledge-rag": {
      "command": "axis-knowledge-rag-mcp",
      "cwd": "/path/to/axis-knowledge-rag",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

---

## 6. DUMMY モードで試す手順

API キーなしで動作確認できる。

```bash
# 1. index ビルド (DUMMY embedder で OK)
python3 -m scripts.build_index ./examples/knowledge --reset

# 2. MCP Inspector で起動 (Node.js 18+ 必要)
npx @modelcontextprotocol/inspector python3 -m mcp_server

# 3. Inspector の UI (http://localhost:5173) で:
#    - "List tools" → 6 つの axis_* tools が表示される
#    - axis_list_axes を実行 → Available axes が返る
#    - axis_search: query="RAG" → 検索結果が返る
#    - axis_answer: question="RAG とは" → DUMMY 回答が返る
#    - axis_check_integrity → broken refs 1 件 (doc_999) が検出される
#    - axis_list_documents: limit=3 → has_more=true + pagination が確認できる
#    - axis_ingest_memo: raw_text="..." → YAML frontmatter Markdown が返る

# 4. pytest で自動テスト (DUMMY mode)
python3 -m pytest mcp_server/tests/ -v
```

**mcp-cli を使う場合:**

```bash
pip install mcp-cli
mcp-cli run python3 -m mcp_server &
mcp-cli tools list
mcp-cli tool call axis_list_axes '{}'
mcp-cli tool call axis_search '{"query": "RAG", "top_k": 3}'
```

---

## 7. 既知の制約

| 制約 | 詳細 |
|---|---|
| stdio transport のみ | HTTP transport は spec_023 候補。stdio で Claude Desktop / Cowork には対応 |
| write 系 tool なし | `axis_add_document` / `axis_reindex` は spec_024 / v0.5 候補 |
| pagination は local | `axis_list_documents` は `top_k=200` で全件取得しメモリ上でページング。大規模 KB では要改善 |
| `axis_check_integrity` は毎回ファイル読み直し | キャッシュなし。大量ファイル時は遅い可能性あり |
| `openWorldHint` は `axis_answer` のみ `true` | 他 4 tools はローカル完結のため `false` |

---

## 8. 将来計画

### spec_023: Streamable HTTP transport

FastAPI と統合し、`/mcp` エンドポイントで HTTP + SSE による transport を追加。認証ヘッダーで複数ユーザー対応。

```python
# 将来のイメージ
app = FastAPI()
app.mount("/mcp", mcp.streamable_http_app())
```

### spec_024: Write tools

| Tool | 説明 |
|---|---|
| `axis_add_document` | Markdown + YAML frontmatter をナレッジに追加し index を更新 |
| `axis_reindex` | ディレクトリ全体を再インデックス |
| `axis_remove_document` | ID 指定でドキュメントを削除 |

### spec_025: OAuth 2.1 認証

公開 MCP サーバーとして運用する場合、OAuth 2.1 (PKCE) によるユーザー認証を追加。

### Kubernetes デプロイ

`axis-knowledge-rag-mcp` コンテナをサイドカーとして K8s Pod に同梱し、Claude Desktop から `stdio` 経由でアクセスする構成も実験中。

---

## 9. ファイル構成

```
mcp_server/
├── __init__.py          # 空 (package marker)
├── __main__.py          # python -m mcp_server エントリポイント
├── server.py            # FastMCP サーバー本体 (6 tools)
├── _errors.py           # error sanitization helper (make_error_response + correlation id)
├── schemas.py           # Pydantic 入力モデル
├── formatters.py        # Markdown / JSON 整形ヘルパー
└── tests/
    ├── __init__.py
    └── test_server.py   # pytest smoke tests (DUMMY mode, 28 tests)
```

## 10. テストカバレッジ

```
$ python3 -m pytest mcp_server/tests/ -v
======= 28 passed =======
```

テストの観点:

| カテゴリ | テスト数 | 内容 |
|---|---|---|
| lazy init | 2 | `_get_engine` / `_get_rag` が例外なく初期化できる |
| axis_search | 4 | markdown/json 両モード、フィルタのみ、空クエリ正規化 |
| axis_answer | 2 | markdown/json 両モード (DUMMY モード) |
| axis_list_axes | 3 | markdown/json/実 config.yml からの軸読み取り |
| axis_check_integrity | 3 | broken ref 検出 / JSON 形式 / エラーなし |
| axis_list_documents | 4 | pagination (markdown/json), 最終ページ, フィルタ |
| axis_ingest_memo | 3 | markdown/json 両モード (DUMMY) + pydantic 入力バリデーション |
| error sanitization | 7 | axis_search 詳細テスト + 全 6 tool parametrize (内部情報非露出・corr_id 確認) |
