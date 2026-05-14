# spec_026: Ingester 堅牢化 (二重スキャン排除 + JSON リトライ + list_documents 上限解除)

- **Author**: Cowork (中島)
- **Created**: 2026-05-13
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: spec_024 (CC レビュー §6 推奨) — 主に Performance + Correctness 改善

## 1. 目的

CC レビュー (result_024.md) で Warning 指摘された 3 件を一括解消し、Ingester と list_documents の実用品質を上げる。

```
[現状の問題]
1. ingester.py L128-133: ingest() 1 回ごとに _next_doc_id() と _existing_doc_ids() が両方 load_directory() を呼ぶ
   → knowledge_dir を 2 度フルスキャン + 全 frontmatter parse
   → yamlize_dir.py のバッチで N 件処理すると 2N 回スキャン (例: 100 件で 200 回 parse)

2. ingester.py L159-165: json.loads(raw_json) 失敗時に即 RuntimeError、リトライ無し
   → Claude が偶発的に JSON 以外を返した時、1 件で全体停止
   → バッチ処理で N-1 件成功でも N 件目で死ぬとロスが大きい

3. mcp_server/server.py L245 (axis_list_documents): top_k=200 で頭打ち
   → 200 件以上の知識ベースで total が常に min(real_total, 200) を返す
   → pagination 説明と齟齬

[修正後]
1. _next_doc_id と _existing_doc_ids を 1 回スキャンに統合 (load_directory() 1 回呼び)
2. Claude invalid JSON 時に最大 2 回リトライ (system prompt 強化 + fenced code block 除去 ロジック改善)
3. axis_list_documents を ChromaDB の collection.get() ベースに置き換え、上限なし pagination
```

## 2. 制約

### 触ってよいファイル

- `backend/src/ingester.py` — メインの修正対象
- `backend/src/ingester_schemas.py` — 必要なら IngestOptions に `retry_count` フィールド追加
- `backend/tests/test_ingester.py` — リトライテスト追加
- `backend/src/vector_store.py` — `list_documents()` / `list_ids()` メソッドを VectorStore に追加
- `backend/tests/test_vector_store.py` — list 系テスト追加
- `mcp_server/server.py` — `axis_list_documents` の実装変更
- `mcp_server/tests/test_server.py` — pagination の上限解除テスト
- `docs/ingester.md` — リトライ動作説明追記
- `docs/mcp-server.md` — list_documents の挙動説明更新
- `CHANGELOG.md` — Day 26 追記

### 触ってはいけないもの

- `search.py` のロジック (axis-only path はあるが spec_028 で扱う)
- `loader.py` / `embedder.py` / `normalizer.py` / `integrity.py` / `marker.py` の API
- `frontend/` / `streamlit_app.py` / `.github/workflows/`
- `_ai_workspace/`

### コーディングルール

- Pydantic v2、既存パターン踏襲
- リトライは `tenacity` 不要、シンプルな for loop で
- LangChain / LlamaIndex 禁止
- ruff + pytest 緑が前提

## 3. やってほしいこと

### 3-1. ingester.py の二重スキャン排除

現状:

```python
def ingest(self, raw_text: str, options: Optional[IngestOptions] = None) -> IngestResult:
    opts = options or IngestOptions()
    knowledge_dir = Path(opts.knowledge_dir)
    next_id = _next_doc_id(knowledge_dir)        # ← load_directory 1 回目
    ...
    existing_ids = _existing_doc_ids(knowledge_dir)  # ← load_directory 2 回目
```

修正後 (`_scan_knowledge_dir` で 1 回統合):

```python
def _scan_knowledge_dir(knowledge_dir: Path) -> tuple[str, list[str]]:
    """Return (next_doc_id, existing_doc_ids) in a single directory scan."""
    if not knowledge_dir.exists():
        return "doc_001", []
    docs = load_directory(knowledge_dir)
    numbers = []
    ids = []
    for d in docs:
        ids.append(d.id)
        if d.id.startswith("doc_"):
            try:
                numbers.append(int(d.id[4:]))
            except ValueError:
                pass
    nxt = (max(numbers) + 1) if numbers else 1
    return f"doc_{nxt:03d}", ids


def ingest(self, raw_text: str, options=None) -> IngestResult:
    opts = options or IngestOptions()
    knowledge_dir = Path(opts.knowledge_dir)
    next_id, existing_ids = _scan_knowledge_dir(knowledge_dir)
    ...
```

既存の `_next_doc_id` / `_existing_doc_ids` は内部用に残す or `_scan_knowledge_dir` をラップする形で wrapper にしても OK (互換性は気にしなくて良い、外部 API ではない)。

### 3-2. Claude invalid JSON リトライ

`IngestOptions` に `retry_count` (default 2) を追加:

```python
class IngestOptions(_BaseInput):
    ...
    retry_count: int = Field(
        default=2,
        description="Number of retries when Claude returns invalid JSON.",
        ge=0,
        le=5,
    )
```

`ingest()` 内のループ:

```python
last_error: Exception | None = None
for attempt in range(opts.retry_count + 1):
    resp = self._client.messages.create(...)
    raw_json = ...  # extract text
    
    # Tolerate code fences
    if raw_json.strip().startswith("```"):
        raw_json = raw_json.strip().strip("`")
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]
        raw_json = raw_json.strip()
    
    # First/last brace fence
    start = raw_json.find("{")
    end = raw_json.rfind("}")
    if start != -1 and end != -1:
        raw_json = raw_json[start:end+1]
    
    try:
        data = json.loads(raw_json)
        return IngestResult(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        last_error = e
        logger.warning("Ingest attempt %d/%d failed: %s", attempt+1, opts.retry_count+1, e)
        # On retry, append a hint to the user message about the previous error
        if attempt < opts.retry_count:
            user_msg += f"\n\n# previous_attempt_failed\nPrevious response was invalid JSON ({e}). Return ONLY valid JSON, no fences, no commentary."
            continue

raise RuntimeError(f"Claude returned invalid JSON after {opts.retry_count+1} attempts: {last_error}")
```

リトライ時に「前回の失敗理由」を user_msg に追記する点が肝 (Claude が学習する)。

### 3-3. axis_list_documents の 200 件上限解除

#### VectorStore に新メソッド追加 (`backend/src/vector_store.py`):

```python
class VectorStore:
    ...
    def list_with_filter(
        self,
        *,
        where: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List documents with axis filters and pagination, no top_k limit.
        
        Uses ChromaDB collection.get() which doesn't require a query embedding
        and supports arbitrary offset/limit.
        """
        # Chroma collection.get() supports include / where / limit / offset
        return self._collection.get(
            where=where,
            include=["metadatas", "documents"],
            limit=limit,
            offset=offset,
        )
    
    def count_with_filter(self, where: dict[str, Any] | None = None) -> int:
        """Count documents matching the filter (without retrieval)."""
        all_ids = self._collection.get(where=where, include=[])
        return len(all_ids.get("ids", []))
```

#### `mcp_server/server.py` の axis_list_documents 書き換え:

```python
@mcp.tool(...)
async def axis_list_documents(params: ListDocumentsInput) -> str:
    try:
        engine = _get_engine()
        store = engine._store  # OK to reach in: same package
        norm_filters = (
            {k: engine._normalizer(str(v)) for k, v in (params.filters or {}).items()}
            if params.filters else None
        )
        where = _build_where_norm(norm_filters or {})
        
        total = store.count_with_filter(where=where)
        result = store.list_with_filter(
            where=where, limit=params.limit, offset=params.offset
        )
        
        # result["ids"], result["metadatas"], result["documents"] are parallel arrays
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", []) or [{}] * len(ids)
        
        has_more = (params.offset + len(ids)) < total
        next_offset = params.offset + len(ids) if has_more else None
        
        # Build response payloads
        docs = []
        for i, doc_id in enumerate(ids):
            md = metadatas[i] or {}
            axes = {k.removeprefix("axis_"): v for k, v in md.items()
                    if k.startswith("axis_") and not k.endswith("_norm")}
            docs.append({
                "id": doc_id,
                "title": md.get("title", ""),
                "axes": axes,
                "path": md.get("path", ""),
            })
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({
                "total": total,
                "count": len(docs),
                "offset": params.offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "documents": docs,
            }, ensure_ascii=False, indent=2)
        
        # Markdown
        lines = [f"# Documents (total={total}, offset={params.offset}, count={len(docs)})"]
        if has_more:
            lines.append(f"\n_next offset: {next_offset}_\n")
        for d in docs:
            lines.append(f"- `{d['id']}` — {d['title']} — axes: {d['axes']}")
        return "\n".join(lines)
    except Exception:
        logger.exception("axis_list_documents failed")
        return "Error: failed to list documents. See server logs."
```

ポイント:
- `store._collection.get()` を直接使う (search.py 経由ではない)
- ゼロベクトル渡しを廃止 (CC review #9 の根本解決の一部)
- `total` は real total を返す (200 件上限なし)
- error message は sanitize (CC review #8 の partial fix、本格対応は spec_027)

### 3-4. テスト追加

#### `backend/tests/test_ingester.py`:

```python
def test_scan_knowledge_dir_single_call(tmp_path, monkeypatch):
    """_scan_knowledge_dir should call load_directory only once."""
    from backend.src import ingester
    call_count = 0
    original = ingester.load_directory
    def counting(dir_path, **kw):
        nonlocal call_count
        call_count += 1
        return original(dir_path, **kw)
    monkeypatch.setattr(ingester, "load_directory", counting)
    # ... setup tmp_path with 3 sample docs
    next_id, existing = ingester._scan_knowledge_dir(tmp_path)
    assert call_count == 1
    assert next_id.startswith("doc_")
    assert len(existing) >= 0


def test_retry_on_invalid_json(monkeypatch):
    """Should retry up to retry_count when Claude returns invalid JSON."""
    # Mock Anthropic client to return non-JSON on first call, valid JSON on 2nd
    ...
```

#### `backend/tests/test_vector_store.py`:

```python
def test_list_with_filter_pagination(in_memory_store, sample_documents, dummy_embedder):
    # Insert 250 docs
    ...
    # Verify total > 200 visible, pagination works
    result = in_memory_store.list_with_filter(limit=50, offset=200)
    assert len(result["ids"]) == 50
    count = in_memory_store.count_with_filter()
    assert count >= 250
```

#### `mcp_server/tests/test_server.py`:

```python
async def test_axis_list_documents_above_200(populated_store, monkeypatch):
    """axis_list_documents should not cap at 200."""
    # populate >200 docs into the singleton store
    ...
    result = await axis_list_documents(ListDocumentsInput(limit=10, offset=210, response_format=ResponseFormat.JSON))
    data = json.loads(result)
    assert data["total"] >= 250
    assert data["offset"] == 210
```

### 3-5. ドキュメント更新

#### `docs/ingester.md`:

「リトライ動作」セクションを追加 — default 2 回、user_msg に prev_error を追記して学習させる旨。

#### `docs/mcp-server.md`:

`axis_list_documents` 説明から「200 件上限」を削除、`total` が真の総数を返すことを明記。

### 3-6. CHANGELOG Day 26

```markdown
### Day 26 (2026-05-13)

- ingester.py: `_scan_knowledge_dir()` を導入し knowledge_dir スキャンを 1 回に統合 (N 件バッチで 2N→N 回 parse に削減)
- ingester.py: Claude invalid JSON 時に最大 `retry_count` (default 2) 回リトライ、前回エラーを次回 user_msg に追記
- ingester_schemas.py: `IngestOptions.retry_count` フィールド追加
- vector_store.py: `list_with_filter()` / `count_with_filter()` メソッド追加 (ChromaDB `collection.get()` ベース)
- mcp_server/server.py: `axis_list_documents` を `list_with_filter` ベースに書き換え、200 件上限解除、エラー sanitize
- tests: ingester 二重スキャン非対称テスト、vector_store pagination 上限解除テスト、MCP list_documents 250 件テスト
- docs/ingester.md: リトライ動作説明追記
- docs/mcp-server.md: list_documents 上限解除を反映
```

### 3-7. 動作確認

```bash
cd ~/projects/axis-knowledge-rag

# 1 回スキャンの確認
python3 -c "
from backend.src import ingester
from pathlib import Path
next_id, ids = ingester._scan_knowledge_dir(Path('examples/knowledge'))
print(f'next_id={next_id}, n_existing={len(ids)}')
"

# pytest 全 PASS
pytest --quiet

# ruff 緑
ruff check .

# MCP server 起動 (動作不要、import 成功確認)
python3 -c "from mcp_server.server import mcp; print(f'{len([t for t in dir(mcp) if not t.startswith(\"_\")])} attrs')"
```

### 3-8. コミット粒度

1. `feat(ingester): introduce _scan_knowledge_dir for single-scan id+existing`
2. `feat(ingester): add retry_count option + JSON parse retry with error feedback`
3. `feat(vector_store): add list_with_filter / count_with_filter methods`
4. `refactor(mcp): rewrite axis_list_documents on top of list_with_filter (no 200 limit)`
5. `test(ingester): add single-scan + retry tests`
6. `test(vector_store): add pagination above-200 tests`
7. `test(mcp): add axis_list_documents pagination test`
8. `docs: update ingester.md + mcp-server.md for retry and pagination`
9. `docs: changelog Day 26`

`git push -u origin feat/spec_026-ingester-hardening`

### 3-9. result_026.md

特に書くこと:

- before/after で `load_directory()` 呼び出し回数の計測 (timeit or call_count)
- リトライテストの動作シミュレーション (1 回目 fail, 2 回目 pass)
- 250 件 dataset でのページング動作確認
- エラーメッセージ sanitize の前後比較

## 4. 成功条件

- [ ] `_scan_knowledge_dir()` で `load_directory` 呼び出しが 1 回に集約
- [ ] Claude invalid JSON 時に max retry_count 回リトライ
- [ ] `axis_list_documents` が 250 件 dataset で `total=250` を返す
- [ ] 全 pytest PASS
- [ ] ruff 緑
- [ ] CI 緑 (push 後 1〜2 分で確認)
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_026.md`

## 6. 質問

- **`store._collection.get()` の `where` 引数互換**: ChromaDB のバージョン差 (1.0 vs 1.5) で signature が変わる場合あり、最新版 (1.5.9) で動作確認するだけで OK
- **既存 `_next_doc_id` と `_existing_doc_ids` 関数の去就**: 外部から呼ばれていないので削除して `_scan_knowledge_dir` に統合 OK。互換維持必要なら 2 関数を wrapper にして残す
- **`_scan_knowledge_dir` の戻り値**: tuple か NamedTuple か dataclass か。シンプルさ重視で tuple で十分

## 7. 補足

### 設計の意図

- Performance fix (#6) と Correctness fix (#7) が同じファイルなのでセットで
- list_documents の 200 件上限解除は ChromaDB API 知識の証明にもなる (`collection.get()` を使えること)
- リトライ実装は LangChain `langchain.retry` のような重い lib を使わず、シンプル for loop で
- エラー sanitize は spec_027 で本格対応するが、ここで `axis_list_documents` 分だけは前倒し

### 次の spec 候補

- spec_027 (MCP error sanitization 全体)
- spec_028 (ChromaDB cosine 距離明示 + 全エンドポイント整合)
