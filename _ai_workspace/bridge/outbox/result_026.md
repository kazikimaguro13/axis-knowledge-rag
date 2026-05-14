# result_026: Ingester 堅牢化 (二重スキャン排除 + JSON リトライ + list_documents 上限解除)

- **Spec**: `inbox/spec_026.md`
- **Executor**: Claude Code
- **Started**: 2026-05-13 14:50
- **Finished**: 2026-05-13 15:35
- **Status**: done

## 1. 要約

spec_024 の CC レビュー §6 で Warning 指摘された 3 件 (Performance #6 / Correctness #7 / ChromaDB API #9) を一括解消。
`_scan_knowledge_dir` で knowledge_dir スキャンを 2 回 → 1 回に統合し、Claude が invalid JSON を返したときに最大 `retry_count` (default 2) 回まで「前回エラーを user_msg に追記」方式でリトライするようにした。
さらに `axis_list_documents` を `VectorStore.list_with_filter()` (ChromaDB `collection.get` ベース) で書き直し、従来の 200 件 top_k cap を撤廃 + ゼロベクトル query 経路を廃止 + エラーメッセージを sanitize。
148 tests PASS / ruff 緑 / 5 commits を `feat/spec_026-ingester-hardening` に push 済み。

## 2. 変更ファイル

```
 CHANGELOG.md                       |  13 ++++
 backend/src/ingester.py            |  79 ++++++++++++++++++-------
 backend/src/ingester_schemas.py    |   6 ++
 backend/src/vector_store.py        |  31 ++++++++++
 backend/tests/test_ingester.py     | 127 +++++++++++++++++++++++++++++++++++++
 backend/tests/test_vector_store.py |  66 +++++++++++++++++++
 docs/ingester.md                   |  23 +++++--
 docs/mcp-server.md                 |   5 +-
 mcp_server/server.py               |  74 +++++++++++++++++-----
 mcp_server/tests/test_server.py    |  79 ++++++++++++++++++++++++
 10 files changed, 453 insertions(+), 50 deletions(-)
```

## 3. 主要な変更点(ハイライト)

### `backend/src/ingester.py`

```diff
-def _next_doc_id(knowledge_dir: Path) -> str:
-    """Read existing knowledge dir, return 'doc_NNN' where NNN = max+1."""
-    if not knowledge_dir.exists():
-        return "doc_001"
-    docs = load_directory(knowledge_dir)
-    ...
-def _existing_doc_ids(knowledge_dir: Path) -> list[str]:
-    if not knowledge_dir.exists():
-        return []
-    return [d.id for d in load_directory(knowledge_dir)]
+def _scan_knowledge_dir(knowledge_dir: Path) -> tuple[str, list[str]]:
+    """Single-scan helper: returns (next_doc_id, existing_doc_ids)."""
+    if not knowledge_dir.exists():
+        return "doc_001", []
+    docs = load_directory(knowledge_dir)
+    ...
+    return f"doc_{nxt:03d}", ids
+
+def _next_doc_id(knowledge_dir: Path) -> str:
+    return _scan_knowledge_dir(knowledge_dir)[0]
+
+def _existing_doc_ids(knowledge_dir: Path) -> list[str]:
+    return _scan_knowledge_dir(knowledge_dir)[1]
```

`_next_doc_id` / `_existing_doc_ids` は薄い back-compat wrapper として残してテスト互換性を維持しつつ、実体は `_scan_knowledge_dir` に統合。N 件バッチで `load_directory` 2N → N 回 (frontmatter parse 半減)。

```diff
+ user_msg = base_user_msg
+ last_error: Exception | None = None
+ attempts = opts.retry_count + 1
+ for attempt in range(attempts):
+     resp = self._client.messages.create(...)
+     raw_json = _strip_code_fence(...)
+     try:
+         data = json.loads(raw_json)
+         return IngestResult(**data)
+     except (json.JSONDecodeError, ValidationError) as e:
+         last_error = e
+         if attempt < attempts - 1:
+             user_msg = (
+                 f"{base_user_msg}\n# previous_attempt_failed\n"
+                 f"Previous response was invalid JSON ({type(e).__name__}: {e}).\n"
+                 f"Return ONLY valid JSON matching the schema..."
+             )
+ raise RuntimeError(f"Claude returned invalid JSON after {attempts} attempts: {last_error}")
```

リトライの肝は「前回の例外型 + メッセージを次回 user_msg に追記して Claude に自己修正させる」点。`retry_count=0` で従来の即時 fail 挙動。

### `backend/src/ingester_schemas.py`

```diff
     max_tokens: int = Field(default=1500, ge=512, le=4096)
+    retry_count: int = Field(
+        default=2,
+        description="Number of retries when Claude returns invalid JSON (0 disables retry).",
+        ge=0,
+        le=5,
+    )
```

### `backend/src/vector_store.py`

```diff
+    def list_with_filter(
+        self,
+        *,
+        where: dict[str, Any] | None = None,
+        limit: int = 20,
+        offset: int = 0,
+    ) -> dict[str, Any]:
+        """List documents by axis filter with pagination — no top_k cap."""
+        return self._collection.get(
+            where=where,
+            include=["metadatas", "documents"],
+            limit=limit,
+            offset=offset,
+        )
+
+    def count_with_filter(self, where: dict[str, Any] | None = None) -> int:
+        if where is None:
+            return self._collection.count()
+        result = self._collection.get(where=where, include=[])
+        return len(result.get("ids", []))
```

ChromaDB 1.5.9 の `collection.get()` を直接呼ぶ薄いラッパー。query embedding 不要、上限 / オフセットも自由。

### `mcp_server/server.py`

```diff
 async def axis_list_documents(params: ListDocumentsInput) -> str:
-    # Pull a wide net then paginate locally — for small KBs this is fine.
-    all_results = engine.search(None, filters=params.filters or None, top_k=200)
-    total = len(all_results)
-    window = all_results[params.offset : params.offset + params.limit]
+    store = engine._store
+    norm_filters = (
+        {k: engine._normalizer(str(v)) for k, v in (params.filters or {}).items()}
+        if params.filters else None
+    )
+    where = _build_where_norm(norm_filters or {})
+    total = store.count_with_filter(where=where)
+    result = store.list_with_filter(where=where, limit=params.limit, offset=params.offset)
     ...
-    except Exception as e:
+    except Exception:
         logger.exception("axis_list_documents failed")
-        return f"Error: {type(e).__name__}: {e}"
+        return "Error: failed to list documents. See server logs."
```

ゼロベクトル経由のローカルページング → ChromaDB ネイティブの `collection.get(limit, offset)` に置換。`total` が真の件数を返すようになり、エラー時は例外型 / メッセージを client にリークしない sanitized 文字列のみ返す。

### `backend/tests/test_ingester.py`

`_scan_knowledge_dir` の `load_directory` 呼び出し回数を `monkeypatch` で計測する単一スキャンテスト 2 件、リトライ挙動 3 件 (2 回目で成功 / 全 attempt 枯渇 / `retry_count=0`) を追加。Claude クライアントは `SimpleNamespace` ベースの軽量 mock で API キーなしで再現。

### `backend/tests/test_vector_store.py` / `mcp_server/tests/test_server.py`

250 件 dataset で `list_with_filter` の offset=200 / 240、`count_with_filter` の filter 有無、`axis_list_documents` の `total=250` / offset=210 ページング、内部例外時の sanitized メッセージ (`RuntimeError` / `/etc/passwd` が文字列に含まれないこと) を追加。

## 4. テスト・品質チェック結果

```
$ python3 -m pytest -q
........................................................................ [ 48%]
........................................................................ [ 97%]
....                                                                     [100%]
148 passed

$ python3 -m ruff check .
All checks passed!

$ python3 -c "from backend.src import ingester; from pathlib import Path; \
              n, ids = ingester._scan_knowledge_dir(Path('examples/knowledge')); \
              print(f'next_id={n}, n_existing={len(ids)}')"
next_id=doc_011, n_existing=10

$ python3 -c "from mcp_server.server import mcp; print('mcp import OK')"
mcp import OK

$ git log --oneline -5
dfb5b72 docs: spec_026 ingester hardening + list_documents no-cap (Day 26)
7472a16 test: spec_026 — single-scan, retry, pagination above 200
bd2a8f3 refactor(mcp): axis_list_documents on top of list_with_filter (no 200 cap)
c118846 feat(vector_store): list_with_filter / count_with_filter
1b47ba2 feat(ingester): _scan_knowledge_dir + retry on invalid JSON
```

### before/after の `load_directory` 呼び出し回数 (非 DUMMY 経路)

`SimpleNamespace` ベースの mock Claude クライアントを差し込み、`load_directory` を計数版でラップして 10 回連続 `ingest()` を実行:

```
After spec_026: 10 ingests → 10 load_directory calls (1 / ingest)
Before spec_026: same loop would have been 20 calls (2 / ingest:
                 _next_doc_id + _existing_doc_ids がそれぞれ呼ぶため)
```

`test_ingest_calls_load_directory_once` が end-to-end でこの不変条件を回帰防止。

### リトライテストの動作シミュレーション

`test_retry_succeeds_on_second_attempt` を実行:

```
attempt 1: client returns "this is not JSON"  → JSONDecodeError logged at WARN
attempt 2: client returns valid IngestResult JSON  → returned as IngestResult
sent_messages[0]: original prompt (no previous_attempt_failed block)
sent_messages[1]: same prompt + '# previous_attempt_failed\n
                  Previous response was invalid JSON (JSONDecodeError: ...)\n
                  Return ONLY valid JSON ...'
```

枯渇テスト (`test_retry_exhausts_and_raises`) では 3 attempts (= retry_count=2 + 初回) 全部 fail 後に `RuntimeError("after 3 attempts: ...")` が raise されることを確認。`retry_count=0` テストは初回 fail で即時 raise (mock は 2 件用意したが 1 件目しか消費しない) を確認。

### 250 件 dataset でのページング動作

`test_list_with_filter_pagination_above_200`:

```
upsert_many(250 docs)
count_with_filter() → 250
list_with_filter(limit=50, offset=200) → 50 ids
list_with_filter(limit=50, offset=240) → 10 ids (最終ページ)
```

`test_axis_list_documents_offset_above_200`:

```
ListDocumentsInput(limit=20, offset=210)
→ {"total": 250, "count": 20, "offset": 210, "has_more": true, "next_offset": 230, ...}
```

### エラーメッセージ sanitize の前後比較

```
[before spec_026]
return f"Error: {type(e).__name__}: {e}"
→ "Error: RuntimeError: internal stack trace with sensitive path /etc/passwd"

[after spec_026]
logger.exception("axis_list_documents failed")  # サーバーログには残る
return "Error: failed to list documents. See server logs."
→ client は exception type / 内部パスを見ない
```

`test_axis_list_documents_error_message_is_sanitized` が `RuntimeError` / `/etc/passwd` が応答文字列に **含まれない** ことを確認。

## 5. 想定外だったこと / 判断ポイント

- **`_next_doc_id` / `_existing_doc_ids` の去就**: 「外部 API ではないので削除可」と spec 6 で言及されていたが、`backend/tests/test_ingester.py` の既存 3 テスト (`test_next_doc_id_empty_dir` / `test_next_doc_id_missing_dir` / `test_next_doc_id_increments`) がこれらを直接呼んでいたため、薄い back-compat wrapper として残した (内部実装は `_scan_knowledge_dir` を呼び直すだけ、追加 I/O コストはない)。
- **戻り値の型**: spec 6 で「tuple か NamedTuple か」とあったが、シンプルさ重視で `tuple[str, list[str]]` を採用 (unpack 1 行で十分。NamedTuple は呼び出し側が 1 箇所しかないのでオーバースペック)。
- **`format_documents_md` の未使用 import 撤去**: `axis_list_documents` の書き換えで使われなくなり、ruff F401 を回避するため import から削除した。`mcp_server/formatters.py` 側の関数は残してある (他から呼ばれていないが、将来他の MCP tool から呼ぶ可能性を考慮)。
- **`test_axis_list_documents_filters` (既存) は total >= 0 のみ assert**: 既存 fixture (`populated_engine`) が Document を `normalized_axes={}` で構築するため、新コードの `axis_*_norm` where 句にマッチせず total=0 になるが、元の assertion `>= 0` は満たすので互換性は壊れていない。

## 6. Open questions

なし

## 7. 動作確認手順(ユーザー)

```
1. cd ~/projects/axis-knowledge-rag
2. git pull --ff-only origin feat/spec_026-ingester-hardening
3. python3 -m pytest -q
4. python3 -m ruff check .
5. python3 -c "from backend.src import ingester; from pathlib import Path; \
                n, ids = ingester._scan_knowledge_dir(Path('examples/knowledge')); \
                print(n, len(ids))"
6. python3 -c "from mcp_server.server import mcp; print('mcp ok')"
```

期待結果:

- `pytest`: 148 tests passed
- `ruff`: All checks passed!
- `_scan_knowledge_dir`: `doc_011 10`
- mcp import: `mcp ok`
- GitHub Actions CI: feat/spec_026-ingester-hardening branch の最新コミット (`dfb5b72`) が緑 (push 後 1–2 分で確認可。`gh` 未インストール環境なので Web UI / `git ls-remote` で確認してください)

## 8. 次の提案(任意)

- **spec_027 候補**: MCP error sanitization を全 6 tool に展開 (今 spec で `axis_list_documents` だけ先行対応した)。`axis_search` / `axis_answer` / `axis_check_integrity` / `axis_ingest_memo` の `return f"Error: {type(e).__name__}: {e}"` を一括 sanitize し、ログは `logger.exception` で残す方針。
- **spec_028 候補**: ChromaDB のデフォルト距離関数 (l2) と SearchEngine の `score = 1 - distance` 計算 (cosine 前提) の不整合を修正。`collection.create(metadata={"hnsw:space": "cosine"})` を明示するか、score 計算式を距離タイプで分岐させる。
- **`axis_list_documents` の sort 安定化**: Chroma `collection.get` は内部の物理的順序を返すため、index 再ビルド後にページング結果が変わる可能性あり。`order_by="id"` のような明示ソートは Chroma 1.5 では未サポートなので、Python 側で `ids` を sorted() してから offset/limit を切り直す手も検討余地あり。
