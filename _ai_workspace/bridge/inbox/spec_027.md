# spec_027: MCP error sanitization (内部情報漏洩防止)

- **Author**: Cowork (中島)
- **Created**: 2026-05-13
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects-ops/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: spec_024 (CC レビュー §6 推奨 #8)

## 1. 目的

CC レビュー (result_024.md §3 #8) で指摘された **MCP tool の except 節が internal 情報を漏らす** 問題を全 6 tool で解消する。

```
[現状の問題]
mcp_server/server.py の全 6 tools の except 節:
  except Exception as e:
      logger.exception("...")
      return f"Error: {type(e).__name__}: {e}"

これにより以下が MCP client に露出する可能性:
- Anthropic API のエラー本文 (rate limit, billing, model deprecation 等)
- 内部 file path (Pydantic ValidationError の loc / input)
- ChromaDB 内部スキーマ情報
- stack trace 断片 (例外の str(e) に含まれる場合)

[修正後]
- 戻り値は固定メッセージ + correlation_id (UUID 短縮)
- 詳細は logger.exception で stderr (運用者だけが見られる)
- 例: "Error [a3b1c]: tool execution failed. See server logs for correlation id a3b1c."
```

## 2. 制約

### 触ってよいファイル

- `mcp_server/server.py` — 全 6 tool の except 節
- `mcp_server/_errors.py` — 新規。`make_error_response(tool_name) -> str` ヘルパー
- `mcp_server/tests/test_server.py` — error sanitization テスト追加
- `docs/mcp-server.md` — error handling セクション追加
- `CHANGELOG.md` — Day 27 追記

### 触ってはいけないもの

- ロジック部分 (各 tool の main body)
- `backend/src/*` 全部
- `frontend/` / `streamlit_app.py`
- `_ai_workspace/`

### コーディングルール

- `uuid.uuid4().hex[:5]` で 5 桁 correlation id を生成、logger に `extra={"corr_id": ...}` で attach
- 戻り値は **絶対に例外オブジェクトの内容を含めない** (str(e) / type(e) も含めない)
- ruff + pytest 緑

## 3. やってほしいこと

### 3-1. `mcp_server/_errors.py` 新規

```python
"""Centralized error handling for MCP tools.

Goal: never leak internal details (file paths, API error bodies, Pydantic
input values) to MCP clients. Errors are logged server-side with a
correlation id, and clients get a generic message referencing the id.
"""

from __future__ import annotations

import logging
import uuid


logger = logging.getLogger(__name__)


def new_correlation_id() -> str:
    """Generate a short correlation id for log<->client tracing."""
    return uuid.uuid4().hex[:5]


def make_error_response(tool_name: str, exc: BaseException, *, corr_id: str | None = None) -> str:
    """Log full exception and return a sanitized message for the client.
    
    Args:
        tool_name: For log context (e.g., 'axis_search').
        exc: The exception caught. Logged with traceback, NOT included in return.
        corr_id: Optional pre-generated correlation id. Auto-generated if None.
    
    Returns:
        A short, client-facing string that does not contain exception details.
    """
    cid = corr_id or new_correlation_id()
    logger.exception(
        "[corr=%s] %s failed", cid, tool_name,
        extra={"corr_id": cid, "tool_name": tool_name},
    )
    return f"Error [{cid}]: {tool_name} failed. Check server logs (correlation id: {cid})."
```

### 3-2. `mcp_server/server.py` の全 6 tool 更新

各 tool の except 節を一行 import + 一行呼び出しに統一:

```python
from mcp_server._errors import make_error_response

# ============================================================================
# Tool 1: axis_search
# ============================================================================
@mcp.tool(...)
async def axis_search(params: SearchInput) -> str:
    """..."""
    try:
        engine = _get_engine()
        results = engine.search(...)
        if params.response_format == ResponseFormat.JSON:
            return format_search_results_json(...)
        return format_search_results_md(...)
    except Exception as e:
        return make_error_response("axis_search", e)
```

同じパターンを 6 tools (search / answer / list_axes / check_integrity / list_documents / ingest_memo) 全部に適用。

### 3-3. ロガー設定

`mcp_server/server.py` の `configure_logging()` 直後に、log フォーマット拡張:

```python
import logging

# Make sure corr_id appears in log lines when present
class _CorrFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, "corr_id"):
            record.corr_id = "-----"
        return super().format(record)

for h in logging.getLogger().handlers:
    h.setFormatter(_CorrFormatter(
        "[%(levelname)s] corr=%(corr_id)s %(name)s: %(message)s"
    ))
    h.stream = __import__("sys").stderr
```

### 3-4. テスト追加 (`mcp_server/tests/test_server.py`)

```python
async def test_axis_search_error_is_sanitized(monkeypatch, caplog):
    """When search fails, the tool returns a sanitized string with a corr_id."""
    from mcp_server import server as srv

    # Force an internal error
    def boom(*a, **kw):
        raise ValueError("Internal value /secret/path leaked")
    monkeypatch.setattr(srv, "_get_engine", boom)

    # Call the tool
    out = await srv.axis_search(SearchInput(query="x"))

    # Assertions:
    # 1. Response does NOT contain the internal message
    assert "secret" not in out
    assert "/path" not in out
    assert "ValueError" not in out

    # 2. Response is the sanitized format
    assert "axis_search failed" in out
    assert "correlation id" in out

    # 3. The log captured the full exception
    assert any("ValueError" in record.message or "Internal value" in record.message
               for record in caplog.records)


# Same pattern for all 6 tools (loop over (tool_func, input_cls) pairs)
@pytest.mark.parametrize(
    "tool_name,tool_callable,input_factory",
    [
        ("axis_search",         srv.axis_search,         lambda: SearchInput(query="x")),
        ("axis_answer",         srv.axis_answer,         lambda: AnswerInput(question="x")),
        ("axis_list_axes",      srv.axis_list_axes,      lambda: ListAxesInput()),
        ("axis_check_integrity",srv.axis_check_integrity,lambda: CheckIntegrityInput()),
        ("axis_list_documents", srv.axis_list_documents, lambda: ListDocumentsInput()),
        ("axis_ingest_memo",    srv.axis_ingest_memo,    lambda: IngestInput(raw_text="x"*30)),
    ],
)
async def test_all_tools_error_sanitized(tool_name, tool_callable, input_factory, monkeypatch):
    """Every tool's error path returns sanitized response."""
    # Force any internal function to raise with detailed message
    monkeypatch.setattr(srv, "_get_engine", lambda: 1/0)  # Will raise ZeroDivisionError
    
    out = await tool_callable(input_factory())
    
    assert "ZeroDivisionError" not in out
    assert "division by zero" not in out
    assert "failed" in out
    assert "correlation id" in out
```

### 3-5. `docs/mcp-server.md` 追記

「Error handling」セクションを追加:

```markdown
## Error handling

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
```

### 3-6. CHANGELOG Day 27

```markdown
### Day 27 (2026-05-13)

- mcp_server/_errors.py: 新規 — `make_error_response()` + correlation id (5 char UUID)
- mcp_server/server.py: 全 6 tool の except 節をサニタイズ済みヘルパーに置き換え
- mcp_server/server.py: log formatter を `[%(levelname)s] corr=%(corr_id)s ...` に拡張
- Internal exception details (file path, API error body, Pydantic input echo) を MCP client に露出させない設計
- tests: 全 6 tool で error 時の戻り値が sanitize されていることを parametrize で検証
- docs/mcp-server.md: Error handling セクション追加
```

### 3-7. 動作確認

```bash
cd ~/projects-ops/axis-knowledge-rag

# 全 tool で error 時の戻り値が sanitize されているか
pytest mcp_server/tests/test_server.py -k "error" -v

# ruff
ruff check .

# 全 pytest
pytest --quiet
```

### 3-8. コミット粒度

1. `feat(mcp): add _errors module with correlation id helper`
2. `refactor(mcp): use make_error_response in all 6 tool except blocks`
3. `chore(mcp): add corr_id to log formatter`
4. `test(mcp): add error sanitization tests for all 6 tools (parametrize)`
5. `docs: add Error handling section to mcp-server.md`
6. `docs: changelog Day 27`

`git push -u origin feat/spec_027-error-sanitization`

### 3-9. result_027.md

特に書くこと:

- before/after の error response 比較
- correlation id がログと戻り値で一致することの確認
- 全 6 tool で同じ sanitize 挙動を testparametrize で確認した結果

## 4. 成功条件

- [ ] 全 6 tool が error 時に sanitize された string を返す
- [ ] correlation id が log と戻り値で一致
- [ ] internal details (path, API error body, Pydantic input) が露出しない
- [ ] 全 pytest PASS
- [ ] ruff 緑
- [ ] CI 緑

## 5. 出力先

`_ai_workspace/bridge/outbox/result_027.md`

## 6. 質問

- **correlation id 長さ**: 5 文字 (uuid4().hex[:5]) で 1M run まで衝突確率 1% 未満。長くしたいなら 8 文字 (uuid4().hex[:8]) も OK。CC 判断
- **既存ロガー設定との互換**: `backend.src.config.configure_logging()` のフォーマット (`[%(levelname)s] %(name)s: %(message)s`) を MCP server が上書きする形で OK
- **log destination**: stderr のみ。ファイルログ未対応 (v0.5 で `logging.handlers.RotatingFileHandler` 検討)

## 7. 補足

### 設計の意図

- MCP tool の error path は client から **絶対に攻撃面にしない**
- correlation id でログとの相関を保ち、運用デバッグは可能に
- spec_026 で部分的に sanitize した `axis_list_documents` も含め、全 6 tool で統一

### 並列 dispatch 注意

spec_026 と spec_027 を別 clone で並列実行。両者 mcp_server/server.py を編集する可能性があるため:

- spec_026: `~/projects/` clone で実行、`mcp_server/server.py` は `axis_list_documents` のみ編集
- spec_027: `~/projects-ops/` clone で実行、`mcp_server/server.py` は **全 6 tool の except 節のみ** 編集

両者の commits を merge する際に conflict 出るかも。conflict 出たら手動 merge で「spec_027 の sanitize ヘルパーが axis_list_documents の except も書き換えている」状態を維持。

### 次の spec 候補

- spec_028 (ChromaDB cosine 距離明示)
- spec_029 (CC 再レビューで A 判定確認)
