# spec_022: MCP server 化 (`axis_knowledge_rag_mcp`)

- **Author**: Cowork (中島)
- **Created**: 2026-05-13
- **Target**: Claude Code (`dev-b` or `dev-d`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu) or `~/projects-d/...`
- **Status**: pending
- **Bundles**: spec_001〜015 完成前提 (backend モジュール群を再利用)。Anthropic 公式 `mcp-builder` skill のリファレンス (`reference/python_mcp_server.md`, `reference/mcp_best_practices.md`) を参照
- **Skill**: `anthropic-skills:mcp-builder`

## 1. 目的

```
[現状]
- axis-knowledge-rag は Streamlit UI / FastAPI / Next.js (進行中) の 3 form factor
- いずれも「人間 / フロントエンド経由」のアクセス
- Claude や他の MCP 対応クライアントから直接ナレッジを叩く経路がない

[変更後]
- `mcp_server/` 配下に MCP server 実装 (Python, FastMCP ベース, stdio transport)
- 5 つの read-only tools を提供:
  - axis_search    : 軸フィルタ + ベクトル hybrid 検索
  - axis_answer    : RAG (Claude API + 出典)
  - axis_list_axes : 軸定義の取得
  - axis_check_integrity : 参照整合性チェック
  - axis_list_documents  : ドキュメント一覧 (ページング)
- README に「Claude Desktop / Cowork から呼ぶ」セクション追加
- docs/mcp-server.md に詳細解説 (tool 一覧、設定方法、例)
- v0.4 候補だが「ポートフォリオ加点」として spec_022 で前倒し導入
```

採用面接で「自分で作った OSS を MCP server 化して Claude から直接叩く」デモができる = **MCP エコシステムのキャッチアップ姿勢** + **AI 駆動開発の実装力** を一度にアピール可能。

## 2. 制約

### 触ってよいファイル / 新規作成

- `mcp_server/__init__.py` — 新規 (空)
- `mcp_server/__main__.py` — 新規。`python -m mcp_server` で起動するエントリポイント
- `mcp_server/server.py` — 新規。MCP サーバー本体 (FastMCP, tool 定義)
- `mcp_server/schemas.py` — 新規。Pydantic 入力モデル
- `mcp_server/formatters.py` — 新規。Markdown / JSON 整形ヘルパー
- `mcp_server/tests/__init__.py` — 新規
- `mcp_server/tests/test_server.py` — 新規。pytest で各 tool を smoke test
- `pyproject.toml` — `mcp>=1.2.0` を dependencies に追加、`[project.scripts]` で `axis-knowledge-rag-mcp` コマンド登録
- `README.md` — 「MCP サーバー」セクション追加 (Quickstart の下)
- `docs/mcp-server.md` — 新規
- `examples/claude_desktop_config.json` — 新規。Claude Desktop に組み込む設定例
- `CHANGELOG.md` — Day 22 (2026-05-13)

### 触ってはいけないもの

- 既存の `backend/src/*` のロジック (loader / search / rag / normalizer / integrity / vector_store) — そのまま再利用、API 変更しない
- `frontend/` — 完全に無関係
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- Python 3.11+ (既存に合わせる)
- **FastMCP** (`from mcp.server.fastmcp import FastMCP`) を使う
- transport: **stdio** (Claude Desktop / Cowork が subprocess で立ち上げる前提)
- Pydantic v2、`model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')`
- Server 名: `axis_knowledge_rag_mcp` (snake_case, `{service}_mcp` 規約)
- Tool 名は全て `axis_` プレフィックス: `axis_search` / `axis_answer` / `axis_list_axes` / `axis_check_integrity` / `axis_list_documents`
- 全 tool に annotations 設定:
  - `readOnlyHint: True` (どれも書き換えしない)
  - `destructiveHint: False`
  - `idempotentHint: True` (axis_search/answer は random 性ほぼゼロ、idempotent と見なす)
  - `openWorldHint: True` for `axis_answer` (Claude API 叩く), `False` for ローカル完結する 4 つ
- Response format: `markdown` (default) と `json` をサポート、`ResponseFormat` enum
- pagination: `axis_list_documents` で `limit / offset`、`has_more / next_offset / total` を返す
- LangChain / LlamaIndex 禁止 (既存と同じ方針)
- 標準ライブラリ + 既存依存のみ、新規依存は `mcp>=1.2.0` のみ

### 依存追加

`pyproject.toml`:
```toml
dependencies = [
    ...,
    "mcp>=1.2.0",
]

[project.scripts]
axis-knowledge-rag-mcp = "mcp_server.__main__:main"
```

## 3. やってほしいこと

### 3-1. `mcp_server/schemas.py`

```python
"""Pydantic input models for the MCP server tools."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class _BaseInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


class SearchInput(_BaseInput):
    query: Optional[str] = Field(
        default=None,
        description=(
            "Natural-language search query (e.g., 'RAG architecture design'). "
            "If omitted, axis filters alone determine the result set."
        ),
        max_length=500,
    )
    filters: dict[str, str | int] = Field(
        default_factory=dict,
        description=(
            "Axis filters as a flat dict, e.g. {'category': '技術記事', 'level': '中級'}. "
            "Keys must match axes defined in config.yml."
        ),
    )
    top_k: int = Field(
        default=5,
        description="Maximum number of results to return.",
        ge=1,
        le=50,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for humans, 'json' for programmatic use.",
    )

    @field_validator("query")
    @classmethod
    def _empty_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip() == "":
            return None
        return v


class AnswerInput(_BaseInput):
    question: str = Field(
        ...,
        description="The question to ask. Used as both retrieval query and LLM prompt.",
        min_length=1,
        max_length=1000,
    )
    filters: dict[str, str | int] = Field(default_factory=dict, description="Axis filters (same shape as search).")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents to include as context.")
    max_tokens: int = Field(default=1024, ge=128, le=4096, description="Max tokens for the Claude response.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ListAxesInput(_BaseInput):
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class CheckIntegrityInput(_BaseInput):
    knowledge_dir: str = Field(
        default="./examples/knowledge",
        description="Path to the knowledge directory (Markdown files).",
    )
    strict: bool = Field(
        default=False,
        description="If true, return a non-zero exit-style summary when broken refs are found.",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ListDocumentsInput(_BaseInput):
    filters: dict[str, str | int] = Field(default_factory=dict, description="Axis filters.")
    limit: int = Field(default=20, ge=1, le=100, description="Max results.")
    offset: int = Field(default=0, ge=0, description="Skip this many results.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)
```

### 3-2. `mcp_server/formatters.py`

```python
"""Markdown / JSON formatters shared across tools."""

import json
from typing import Any

from backend.src.integrity import IntegrityReport
from backend.src.search import SearchResult


def format_search_results_md(query: str | None, filters: dict, results: list[SearchResult]) -> str:
    lines = []
    title = f"Search results for: `{query}`" if query else "Axis-only filter results"
    lines.append(f"# {title}")
    if filters:
        lines.append(f"\n**Filters**: {filters}\n")
    lines.append(f"\n**{len(results)}** result(s)\n")
    for r in results:
        lines.append(f"## [{r.score:.3f}] `{r.id}` — {r.title}")
        lines.append(f"- axes: {r.axes}")
        if r.refs:
            lines.append(f"- refs: {r.refs}")
        lines.append(f"\n{r.body_snippet}\n")
    return "\n".join(lines)


def format_search_results_json(query: str | None, filters: dict, results: list[SearchResult]) -> str:
    payload = {
        "query": query,
        "filters": filters,
        "count": len(results),
        "results": [
            {
                "id": r.id,
                "title": r.title,
                "score": r.score,
                "axes": r.axes,
                "body_snippet": r.body_snippet,
                "path": r.path,
                "refs": r.refs,
            }
            for r in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def format_integrity_md(report: IntegrityReport) -> str:
    lines = ["# Integrity Report", ""]
    lines.append(f"- Total documents: {report.total_docs}")
    lines.append(f"- Total refs:      {report.total_refs}")
    lines.append("")
    if report.broken_refs:
        lines.append(f"## ❌ Broken refs ({len(report.broken_refs)})")
        for b in report.broken_refs:
            lines.append(f"- `{b.source_id}` (`{b.source_path}`) → **`{b.target_id}` (missing)**")
    else:
        lines.append("✅ No broken refs")
    lines.append("")
    if report.orphan_docs:
        lines.append(f"## ⚠️ Orphan docs ({len(report.orphan_docs)})")
        for o in report.orphan_docs:
            lines.append(f"- `{o}`")
    else:
        lines.append("✅ No orphan docs")
    lines.append("")
    if report.cycles:
        lines.append(f"## ⚠️ Cycles ({len(report.cycles)})")
        for c in report.cycles:
            lines.append("- " + " → ".join(f"`{x}`" for x in c))
    else:
        lines.append("✅ No cycles")
    return "\n".join(lines)
```

(他のフォーマッタも同様。axis_answer / axis_list_axes / axis_list_documents 用も入れる)

### 3-3. `mcp_server/server.py` (本体)

```python
"""axis_knowledge_rag MCP server (stdio transport, FastMCP-based).

Exposes the project's hybrid search + RAG capabilities as MCP tools so that
Claude Desktop / Cowork / any MCP-compatible client can query the knowledge
base directly.

Run with:
    python -m mcp_server
or via stdio invocation from a client's config file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from backend.src.config import configure_logging, load_axes_config, settings
from backend.src.embedder import Embedder
from backend.src.integrity import IntegrityChecker, format_report
from backend.src.loader import load_directory
from backend.src.normalizer import Normalizer
from backend.src.rag import RAGPipeline
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore

from mcp_server.formatters import (
    format_integrity_md,
    format_search_results_json,
    format_search_results_md,
)
from mcp_server.schemas import (
    AnswerInput,
    CheckIntegrityInput,
    ListAxesInput,
    ListDocumentsInput,
    ResponseFormat,
    SearchInput,
)


configure_logging()
# stdio transport — never log to stdout (JSON-RPC stream lives there)
logger = logging.getLogger("axis_knowledge_rag_mcp")
for h in logging.getLogger().handlers:
    h.stream = __import__("sys").stderr

mcp = FastMCP("axis_knowledge_rag_mcp")


# === lazy singletons (init on first tool call, persist for server lifetime) ===
_engine: SearchEngine | None = None
_rag: RAGPipeline | None = None
_axes_cfg: dict | None = None


def _get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        store = VectorStore(path=settings.chroma_db_path)
        embedder = Embedder()
        normalizer = Normalizer.from_config(load_axes_config())
        _engine = SearchEngine(store, embedder, normalizer)
        logger.info("SearchEngine ready (embedder_mode=%s)", "DUMMY" if embedder.is_dummy else "GEMINI")
    return _engine


def _get_rag() -> RAGPipeline:
    global _rag
    if _rag is None:
        _rag = RAGPipeline(_get_engine())
        logger.info("RAGPipeline ready (rag_mode=%s)", "DUMMY" if _rag.is_dummy else "CLAUDE")
    return _rag


def _get_axes() -> dict:
    global _axes_cfg
    if _axes_cfg is None:
        _axes_cfg = load_axes_config()
    return _axes_cfg


# ============================================================================
# Tool 1: axis_search
# ============================================================================
@mcp.tool(
    name="axis_search",
    annotations={
        "title": "Axis + Vector Hybrid Search",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def axis_search(params: SearchInput) -> str:
    """Search the knowledge base by axis filters + vector similarity (hybrid).

    Best when:
    - You have an exact axis constraint (e.g., category='技術記事') AND a fuzzy
      semantic query (e.g., "RAG architecture design")
    - You want a ranked list of Documents WITHOUT generated text answer

    Args:
        params (SearchInput): {
            query (str|None): natural-language query, optional
            filters (dict): axis filters like {"category": "技術記事"}
            top_k (int): 1-50, default 5
            response_format (markdown|json): output format
        }

    Returns:
        str: formatted list of search hits with id / title / score / axes / snippet.
    """
    try:
        engine = _get_engine()
        results = engine.search(params.query, filters=params.filters or None, top_k=params.top_k)
        if params.response_format == ResponseFormat.JSON:
            return format_search_results_json(params.query, params.filters, results)
        return format_search_results_md(params.query, params.filters, results)
    except Exception as e:  # noqa: BLE001 — top-level safety net
        logger.exception("axis_search failed")
        return f"Error: {type(e).__name__}: {e}"


# ============================================================================
# Tool 2: axis_answer
# ============================================================================
@mcp.tool(
    name="axis_answer",
    annotations={
        "title": "RAG Answer with Citations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,  # Claude API has nondeterministic output
        "openWorldHint": True,    # Calls Anthropic API (external)
    },
)
async def axis_answer(params: AnswerInput) -> str:
    """Generate an answer to a question, grounded in the knowledge base.

    Uses Claude API to compose a citation-bearing response from the top-k
    retrieved Documents. Citation format in the body: [doc_NNN].

    Args:
        params (AnswerInput): {
            question (str): the natural-language question
            filters (dict): optional axis filters
            top_k (int): retrieved Documents count
            max_tokens (int): Claude reply max tokens
            response_format (markdown|json)
        }

    Returns:
        str: answer text + citations (markdown) or JSON wrapper.
    """
    try:
        rag = _get_rag()
        ans = rag.answer(
            params.question,
            filters=params.filters or None,
            top_k=params.top_k,
            max_tokens=params.max_tokens,
        )
        if params.response_format == ResponseFormat.JSON:
            payload = {
                "question": params.question,
                "answer": ans.text,
                "cited_ids": ans.cited_ids,
                "is_dummy": ans.is_dummy,
                "model": ans.model,
                "sources": [
                    {"id": s.id, "title": s.title, "score": s.score, "axes": s.axes}
                    for s in ans.sources
                ],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        lines = []
        lines.append(f"# Answer to: {params.question}")
        lines.append("")
        if ans.is_dummy:
            lines.append("> _DUMMY mode (no ANTHROPIC_API_KEY)_\n")
        lines.append(ans.text)
        lines.append("")
        lines.append("## Sources")
        for s in ans.sources:
            marker = "★ cited" if s.id in ans.cited_ids else ""
            lines.append(f"- `{s.id}` — {s.title} (score {s.score:.3f}) {marker}".strip())
        return "\n".join(lines)
    except Exception as e:
        logger.exception("axis_answer failed")
        return f"Error: {type(e).__name__}: {e}"


# ============================================================================
# Tool 3: axis_list_axes
# ============================================================================
@mcp.tool(
    name="axis_list_axes",
    annotations={
        "title": "List Configured Axes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def axis_list_axes(params: ListAxesInput) -> str:
    """List axes defined in config.yml (name / type / values / required).

    Use this first to discover what filters axis_search / axis_answer accept.
    """
    cfg = _get_axes()
    axes = cfg.get("axes", [])
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"axes": axes}, ensure_ascii=False, indent=2)
    lines = ["# Available axes", ""]
    for a in axes:
        line = f"- **{a['name']}** ({a.get('type', 'string')}"
        if a.get("required"):
            line += ", required"
        line += ")"
        if a.get("values"):
            line += f" — values: {a['values']}"
        lines.append(line)
    return "\n".join(lines)


# ============================================================================
# Tool 4: axis_check_integrity
# ============================================================================
@mcp.tool(
    name="axis_check_integrity",
    annotations={
        "title": "Reference Integrity Check",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def axis_check_integrity(params: CheckIntegrityInput) -> str:
    """Check the knowledge base for broken refs, orphan docs, and cycles."""
    try:
        docs = load_directory(Path(params.knowledge_dir))
        report = IntegrityChecker().check(docs)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(report.as_dict(), ensure_ascii=False, indent=2)
        return format_integrity_md(report)
    except Exception as e:
        logger.exception("axis_check_integrity failed")
        return f"Error: {type(e).__name__}: {e}"


# ============================================================================
# Tool 5: axis_list_documents
# ============================================================================
@mcp.tool(
    name="axis_list_documents",
    annotations={
        "title": "List Documents (with pagination)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def axis_list_documents(params: ListDocumentsInput) -> str:
    """List Documents in the knowledge base, with axis filters + pagination."""
    try:
        engine = _get_engine()
        # Pull a wide net then paginate locally — for small KBs this is fine.
        all_results = engine.search(None, filters=params.filters or None, top_k=200)
        total = len(all_results)
        window = all_results[params.offset : params.offset + params.limit]
        has_more = (params.offset + len(window)) < total
        next_offset = params.offset + len(window) if has_more else None

        if params.response_format == ResponseFormat.JSON:
            payload = {
                "total": total,
                "count": len(window),
                "offset": params.offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "documents": [
                    {"id": r.id, "title": r.title, "axes": r.axes, "path": r.path}
                    for r in window
                ],
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        lines = [f"# Documents (total={total}, offset={params.offset}, count={len(window)})"]
        if has_more:
            lines.append(f"\n_next offset: {next_offset}_\n")
        for r in window:
            lines.append(f"- `{r.id}` — {r.title} — axes: {r.axes}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("axis_list_documents failed")
        return f"Error: {type(e).__name__}: {e}"


def main() -> None:
    """Entrypoint for `python -m mcp_server` / `axis-knowledge-rag-mcp`."""
    mcp.run()


if __name__ == "__main__":
    main()
```

### 3-4. `mcp_server/__main__.py`

```python
"""Allow `python -m mcp_server` invocation."""

from mcp_server.server import main

if __name__ == "__main__":
    main()
```

### 3-5. `mcp_server/tests/test_server.py`

pytest-based smoke tests:

- `_get_engine()` / `_get_rag()` の lazy init で例外でない
- `axis_search` to MCP tool function 直接呼び (Pydantic model 経由) で結果 string が返る
- `axis_list_axes` で config.yml 由来の軸が markdown / json 両モードで出る
- `axis_check_integrity` で broken_refs を検出
- `axis_list_documents` pagination が `offset / limit / has_more / next_offset` 正しく返す
- DUMMY モードでのみテスト (CI は API キーなし)

各 test は `tmp_path` fixture で chromadb と knowledge dir を tmp に切り出して隔離。

### 3-6. `pyproject.toml` 修正

```diff
 dependencies = [
   ...,
+  "mcp>=1.2.0",
 ]

+[project.scripts]
+axis-knowledge-rag-mcp = "mcp_server.server:main"
```

### 3-7. `README.md` セクション追加

(Quickstart の直下に):

```markdown
## 🔌 MCP server として使う

Claude Desktop / Cowork / 任意の MCP 対応クライアントから、本リポジトリのナレッジを直接検索 / 質問できます。

### Claude Desktop 設定例

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) または `%APPDATA%\Claude\claude_desktop_config.json` (Windows) に追記:

```json
{
  "mcpServers": {
    "axis-knowledge-rag": {
      "command": "python",
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

### 提供される tools

| Tool | 役割 |
|---|---|
| `axis_search` | 軸フィルタ + ベクトル hybrid 検索 |
| `axis_answer` | RAG (Claude API + 出典) |
| `axis_list_axes` | 軸定義の取得 |
| `axis_check_integrity` | 参照整合性チェック |
| `axis_list_documents` | ドキュメント一覧 (pagination) |

詳細: [docs/mcp-server.md](docs/mcp-server.md)
```

### 3-8. `docs/mcp-server.md`

300〜500 行:

- なぜ MCP 化したか (動機)
- アーキテクチャ (server.py が backend モジュールをそのまま再利用)
- 5 tools の詳細仕様 (input schema, output schema, 使い分け)
- Claude Desktop / Cowork / generic MCP client への組み込み手順
- DUMMY モードで試す手順
- 既知の制約 (stdio のみ、HTTP transport は v0.5 候補)
- 将来計画 (streamable HTTP / OAuth / kubernetes デプロイ)

### 3-9. `examples/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "axis-knowledge-rag": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/PATH/TO/axis-knowledge-rag",
      "env": {
        "ANTHROPIC_API_KEY": "your-key-here",
        "GEMINI_API_KEY": "your-key-here"
      }
    }
  }
}
```

### 3-10. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
pip install -e . --break-system-packages

# Build index first (既存)
python -m scripts.build_index ./examples/knowledge --reset

# MCP server を stdio で起動 (テスト用には MCP Inspector が便利)
# Anthropic 公式 inspector を使う場合:
npx @modelcontextprotocol/inspector python -m mcp_server

# それで:
# - "List tools" → 5 つの axis_* tools が見える
# - axis_list_axes を実行 → markdown response 返る
# - axis_search で query="RAG", filters={"category":"技術記事"} を実行 → 結果が返る
# - axis_answer で question="RAG とは" を実行 → DUMMY モード回答が返る
# - axis_check_integrity → broken refs 1 件 (doc_999) 出力
# - axis_list_documents で limit=5 offset=0 → 5 件 + has_more=true

pytest mcp_server/tests/ -v
```

### 3-11. コミット (8〜10 件)

1. `chore: add mcp>=1.2.0 to dependencies + axis-knowledge-rag-mcp script entry`
2. `feat(mcp): add Pydantic input schemas in mcp_server/schemas.py`
3. `feat(mcp): add format helpers in mcp_server/formatters.py`
4. `feat(mcp): implement 5 read-only tools in mcp_server/server.py`
5. `feat(mcp): add __main__.py for python -m mcp_server`
6. `test(mcp): add pytest smoke tests for 5 tools (DUMMY mode)`
7. `docs(mcp): add docs/mcp-server.md (tools, integration, future plans)`
8. `docs: add MCP server section to README + examples/claude_desktop_config.json`
9. `docs: changelog Day 22`

`git push -u origin feat/spec_022-mcp-server`

### 3-12. result_022.md

特に書くこと:

- 全 5 tools の I/O サンプル (markdown / json 両モード)
- MCP Inspector で動作確認した tool 一覧スクショ (取れなければ手順)
- DUMMY モードでテスト全 pass の coverage
- ANTHROPIC_API_KEY / GEMINI_API_KEY 設定時の本物動作確認 (キーがあれば)
- Future plans: streamable HTTP transport, write tools (index_add_doc / index_remove_doc), Claude Desktop に組み込んだ実演 GIF

## 4. 成功条件

- [ ] `python -m mcp_server` でエラーなく起動 (stdio 待機状態)
- [ ] MCP Inspector / mcp-cli で 5 tools が discover される
- [ ] 5 tools 全て markdown / json 両モードで結果を返す
- [ ] DUMMY モードで全テスト PASS
- [ ] LangChain / LlamaIndex 不使用維持
- [ ] dev-b で push 成功
- [ ] README に MCP セクション追加
- [ ] docs/mcp-server.md (300 行以上)

## 5. 出力先

`_ai_workspace/bridge/outbox/result_022.md`

## 6. 質問

- **mcp パッケージのバージョン**: `mcp>=1.2.0` 想定だが、最新が異なる場合は最新 stable に追随、result に明記
- **stdio のみで良いか**: 当面 stdio。streamable HTTP は将来 ADR-016 として spec_023 候補。質問は不要、stdio で進める
- **MCP Inspector が WSL で動くか**: Node 系なので動くはずだが、もし問題があれば手動 stdio テスト (echo JSON-RPC) で確認、result に書く
- **tests の coverage 目標**: 既存と同じ 70%+ を目標。MCP server は I/O wrapper 主体なので高くなりやすい
- **claude_desktop_config.json のパス**: README には macOS / Windows 両方記載。Linux はユーザー判断 (Claude Desktop が Linux 未対応の頃の話なので置き換え)

## 7. 補足

### 設計の意図

- **backend モジュールをそのまま import**: search.py / rag.py / etc は既に「ライブラリとして使える」設計になっているので、MCP server は薄い wrapper に徹する。コード重複ゼロ
- **stdio transport**: Claude Desktop / Cowork の慣習に揃える。HTTP は spec_023 で
- **lazy singleton**: 初回 tool 呼び出しで `_get_engine()` / `_get_rag()`、以降は memo。VectorStore 初期化が ~100ms かかるのを毎回繰り返さない
- **stdout/stderr 分離**: stdio transport は stdout が JSON-RPC ストリーム。logger は stderr に向ける (これを忘れると client 側 parse failure になる)
- **annotations**: `readOnlyHint: True` は全 tool、`openWorldHint` は `axis_answer` のみ True (外部 Claude API 呼ぶため)
- **`mcp_server/` を top-level package に**: `backend/` `frontend/` `scripts/` と並列に配置。「もう 1 つの form factor」と認識される構造
- **5 tools のスコープ**: read-only に絞り込み。write 系 (index 追加 / 削除) は spec_024 / v0.5 で

### Day 22+ 連携

- spec_023: MCP server に streamable HTTP transport 追加 (FastAPI と統合)
- spec_024: write tools (`axis_add_document`, `axis_reindex`)
- spec_025: OAuth 2.1 認証 (公開 MCP として運用するなら)
- README の roadmap 表に v0.4 → "MCP server (stdio)" を ✅ released で追記

### このプロジェクトを終えて (中島さんへ)

MCP server 化することで:
- 採用面接でデモ: Claude Desktop で「自分のナレッジ検索 tool を作りました、見てください」が刺さる
- フューチャー ES の「工夫した点」に「**MCP 化で AI エコシステム接続性を担保**」が 1 行追加できる
- 自分自身も毎日 Cowork / Claude Desktop から `axis_search` で自分のメモを引けるようになる (実用性 ↑)
