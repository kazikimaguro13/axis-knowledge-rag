# Changelog

## [Unreleased]

### Day 48 (2026-05-20) — Knowledge-gap detection (spec_048)

v0.9.0 marquee #4: log searches that came up empty or vague, log LLM
answers that admitted "資料に記載がない", aggregate both into a weekly
markdown report. Closes the silent-failure gap that spec_047's 👍 / 👎
loop can't see — the user who searched, found nothing, and quietly
closed the tab now leaves a trace.

- **`backend/src/gap_detection.py`** (new) — `GapRecord` dataclass +
  `GapStore` Protocol + `SqliteGapStore` (stdlib `sqlite3`, WAL mode,
  single shared connection under `threading.Lock`). Default DB path
  `~/.axis_gap.db` (next to `~/.axis_feedback.db` from spec_047).
  `detect_no_info(text)` runs a tight regex over Japanese + English
  "I don't know" phrasings anchored on what the SYSTEM_PROMPT actually
  tells Claude to emit. `make_gap_store(cfg)` returns `None` when
  `gap.enabled=false` so every hook short-circuits at zero cost
- **`backend/src/search.py`** — post-hoc hook after fusion / decay /
  graph expansion: `no_results` when results is empty, `low_score`
  when `results[0].score < gap.low_score_threshold` (0.35 default,
  matches the v0.8 RAGAS "weak hit" band). Axis-only listing calls
  (`query is None`) are skipped. Wrapped in `try / except` →
  `logger.warning` so the gap path can never fail a real search
- **`backend/src/rag.py`** — `_record_llm_gap(question, text, results)`
  runs `detect_no_info(text)` after `parse_and_validate_citations` and
  records `llm_no_info` (with the top score for the report's "we had
  docs but LLM refused" vs "no docs at all" distinction). Wired into
  both the `answer()` and `chat()` paths; chat logs the *user-facing*
  question rather than the rewritten one so the report is actionable
- **GET /api/gap/report** (`backend/src/api.py`) — new endpoint behind
  `_require_gap_store()` (503 when disabled). Lifespan builds the gap
  store and shares the same instance with `SearchEngine` and
  `RAGPipeline`; close runs on shutdown alongside the chat + feedback
  stores
- **`evaluation/gap_report.py`** (new) — pure-function
  `generate_report(store, days=7)` + `save_report_to_file(...)` writing
  `evaluation/gap_reports/YYYY-WW.md`. Sections: total counts per
  reason (`no_results` / `low_score` / `llm_no_info`), top-10
  unsatisfied queries (count desc, stable tie-break on query string,
  reason annotations + avg top_score), and a 推奨アクション block
  pointing at `examples/knowledge/` + the spec_046 `/api/ingest` path
- **Makefile** — `gap-report` target shells into the renderer with the
  default DB path. `~ $ make gap-report` →
  `evaluation/gap_reports/2026-W21.md`
- **`config.yml` + `backend/src/config.py`** — new `GapConfig`
  (`enabled` + `db_path` + `low_score_threshold`) wired into
  `AppConfig`. `_build_app_config()` reads the new `gap.*` section;
  defaults preserve the on-by-default behaviour
- **schemas**: `GapReportResponse` added to `backend/src/schemas.py`
- **tests**: `backend/tests/test_gap_detection.py` (11 functions
  covering 18 cases — 5 Japanese "no info" patterns, 2 English ones,
  3 negative cases, empty-string detection, low_score record,
  llm_no_info record, recent-window filtering, count, idempotent
  close, factory disabled / enabled); `evaluation/tests/test_gap_report.py`
  (3 — empty placeholder, top-queries section + reason annotations,
  推奨アクション section + file write). All previously-passing tests
  continue to pass; ruff 緑
- **docs**: ADR-029 (rationale, signal-vs-spec_047 alternatives, false-
  positive / PII / schema-overlap consequences); CHANGELOG Day 48
  (this entry)

### Day 47 (2026-05-20) — Active-learning feedback loop (spec_047)

v0.9.0 marquee #3: 👍 / 👎 capture on search results + chat answers,
stored in a local SQLite + summarised by a weekly markdown report. MVP
scope is intentionally just **logging** — automatic weight tuning over
the captured signals is parked for v0.10. The signal layer goes in
first so any future tuning can be evaluated against real ground truth.

- **`backend/src/feedback.py`** (new) — `FeedbackRecord` dataclass +
  `FeedbackStore` Protocol + `SqliteFeedbackStore` (stdlib `sqlite3`,
  WAL mode, single shared connection under `threading.Lock`). Default
  DB path `~/.axis_feedback.db` (next to `~/.axis_chat.db` from
  spec_036). `make_feedback_store(cfg)` returns `None` when
  `feedback.enabled=false` so the API can map that to 503 rather than
  silently swallowing writes
- **POST /api/feedback / GET /api/feedback/report** (`backend/src/api.py`) —
  new endpoints with `FeedbackRequest` / `FeedbackResponse` /
  `FeedbackReportResponse` Pydantic schemas. `rating` is constrained
  to `[-1, 1]` at the schema layer; `doc_id` / `session_id` / `note`
  are all nullable so the search tab (anonymous) and chat tab (with
  session) can use the same endpoint. `_require_feedback_store()` →
  503 when disabled. Lifespan closes the store on shutdown
- **`evaluation/feedback_report.py`** (new) — pure-function
  `generate_report(store, days=7)` + `save_report_to_file(...)` which
  writes `evaluation/feedback_reports/YYYY-WW.md`. Sections: total
  counts (👍 / 👎 / neutral), top-10 queries by frequency, top-5
  unpopular docs (net 👎 over 👍), top-5 popular docs. Docs with
  pos==neg are dropped from both lists — those are the "ignore me"
  signal
- **Makefile** — `feedback-report` target shells into the renderer with
  the default DB path. `~ $ make feedback-report` →
  `evaluation/feedback_reports/2026-W21.md`
- **`config.yml` + `backend/src/config.py`** — new `FeedbackConfig`
  (`enabled` + `db_path`) wired into `AppConfig`. `_build_app_config()`
  reads the new `feedback.*` section; defaults preserve the always-on
  behaviour
- **Frontend (Next.js)**: `frontend/src/lib/feedbackClient.ts` (new,
  single `postFeedback(payload)` helper). `ResultCard.tsx` gets a
  `👍 役立った` / `👎 ふつう` pair under the snippet, plus `query` /
  `sessionId` props from the caller. `ChatMessage.tsx` gets a
  whole-answer 👍 / 👎 pair under the rendered body, plus a per-source
  pair under the sources expander; the user question is stored on the
  message itself as `userQuestion` so each turn's feedback carries the
  right query string. Optimistic UI: the visual state flips on click,
  only reverts if the API rejects the write; the button disables
  itself after one tap to prevent accidental double-submit within the
  same component instance
- **Streamlit (`streamlit_app.py`)**: `_send_feedback(...)` helper +
  buttons in `_render_sources_with_anchors(...)`, with a
  `feedback_key_prefix` so the unique Streamlit button keys don't
  collide across tabs / messages. Live-chat reply gets a whole-answer
  👍 / 👎 pair under the source expander. Toast on success / failure /
  503-disabled
- **schemas**: `FeedbackRequest` / `FeedbackResponse` /
  `FeedbackReportResponse` added to `backend/src/schemas.py`
- **tests**: `backend/tests/test_feedback.py` (12 — uuid generation,
  persistence round-trip, recent-window inclusion / exclusion, count,
  ±1 / 0 ratings, optional doc_id / session_id / note, idempotent
  close, factory disabled / enabled); `evaluation/tests/test_feedback_report.py`
  (3 — empty placeholder, top-queries section, unpopular-docs section
  + file write); `backend/tests/test_api.py` (+4 — happy-path record,
  rating-validation 422, report endpoint round-trip, disabled-store
  503). Existing 379 + spec_047 19 = **398 件 PASS**, 2 skipped (redis +
  ollama optional deps), ruff 緑
- **docs**: ADR-028 (rationale, signal-vs-noise alternatives,
  PII / dedup / scaling consequences); CHANGELOG Day 47 (this entry)

### Day 46 (2026-05-20) — Browser extension MVP (spec_046)

v0.9.0 marquee #2: one-click web page → `examples/knowledge/`. Reading an
article and "kind of meaning to" save it now takes one click instead of
three steps in a memo app.

- **POST /api/ingest** (`backend/src/api.py`) — new endpoint accepting
  `{url, title, body, selected_text?}` and writing
  `examples/knowledge/web_YYYYMMDD_HHMMSS_<slug>.md` via the new
  `backend/src/ingest_web.py` writer. Returns `{saved_path, doc_id}`.
  Validation: `url`/`title` required + length-bounded, large bodies
  capped at 200K chars at the Pydantic layer
- **CORS regex** (`backend/src/api.py`) — the previous literal allow-list
  (`localhost:3000`, `localhost:8501`) is replaced with an
  `allow_origin_regex` matching `chrome-extension://*` plus any
  `localhost` / `127.0.0.1` port. `allow_credentials` flipped to
  `False`; existing frontend / Streamlit clients keep working since
  they never sent cross-origin credentials
- **browser-extension/** — new Chrome MV3 unpacked extension:
  `manifest.json` (MV3 with `activeTab`/`scripting`/`storage`
  permissions), `popup.{html,css,js}`, `background.js` (service worker
  seeding the default endpoint on install), `icon-{16,48,128}.png` (PIL
  placeholder, indigo). Popup prefers `window.getSelection()` over
  `document.body.innerText` (cap 5,000 chars) so a deliberate selection
  beats the full-page dump. Endpoint URL is configurable via
  `chrome.storage.sync`, defaulting to `http://localhost:8000`
- **schemas**: `IngestRequest` / `IngestResponse` added to
  `backend/src/schemas.py`
- **slug**: NFKC + Unicode `\w` so kana / kanji survive in filenames
  (`Ｗｅｂ 記事 サンプル` → `web-記事-サンプル`); empty / all-stripped
  inputs fall back to the `web` sentinel
- **tests**: `backend/tests/test_ingest_web.py` (8 — frontmatter shape,
  slugify JP/ASCII/empty/edge, filename timestamp, selection priority,
  auto-mkdir, axes defaults, refs empty list, url verbatim);
  `backend/tests/test_api.py` (+2 — `/api/ingest` happy path with a
  tmp-dir override, 422 on missing / empty fields). Existing 372 +
  spec_046 10 = **382 件 PASS**, 2 skipped (redis + ollama optional
  deps), ruff 緑
- **docs**: ADR-027 (rationale, alternatives, CORS / extraction
  consequences), `docs/browser-extension.md` (install / usage /
  troubleshooting / permissions table), `browser-extension/README.md`
  (developer-facing install steps), README.md Features bullet

### Day 45 (2026-05-19) — Ollama / Llama.cpp integration (spec_045)

v0.9.0 marquee #1: fully on-prem RAG. Both the embedder and the
generation call can now be served by a local Ollama daemon so internal /
private corpora never leave the network. v0.8.1 behaviour is preserved
exactly when the two new config keys keep their defaults.

- **embedder Protocol + 3 backends**: `backend/src/embedder.py` reworked
  into an `Embedder` Protocol with `GeminiEmbedder` (renamed from the
  v0.8.1 class), `OllamaEmbedder` (new, `bge-m3` default, 1024-dim
  multilingual), and `DummyEmbedder` (replaces the old
  `Embedder(force_dummy=True)` pattern). `make_embedder(EmbedderConfig)`
  factory dispatches; the optional `ollama` Python package is gated by
  the new `[ollama]` extra. On ImportError / unreachable daemon, the
  factory logs a warning and returns `DummyEmbedder` so app startup
  never blocks
- **generation Protocol + 3 backends**: `backend/src/rag.py` adds
  `GenerationBackend` Protocol + `ClaudeBackend` (wraps Anthropic SDK) +
  `OllamaBackend` (wraps `ollama.Client.chat`, translates Claude-style
  `(system, messages)` into the Ollama chat format) +
  `DummyGenerationBackend`. `RAGPipeline.answer` / `chat` now go through
  `self._backend.generate(...)` with a small shim that preserves
  legacy tests that monkey-patched `_client` directly
- **config**: `backend/src/config.py` adds `EmbedderConfig`,
  `GenerationConfig`, and the shared `OllamaConfig` (`model` + `url`),
  wired into `AppConfig`. `_build_app_config()` reads the new
  `config.yml > embedder.*` and `generation.*` sections; both default to
  v0.8.1 backends. `config.yml` ships with the new sections + inline docs
- **question_rewriter**: `rewrite_question()` gained a `backend` arg so
  the chat-rewrite step can also avoid the network when Ollama is used
- **docker-compose**: new `ollama` service under `profiles: ["ollama"]`
  + `ollama-data` named volume. Activate with
  `docker compose --profile ollama up -d ollama` and pull models with
  `docker exec axis-ollama ollama pull <model>`
- **api.py / mcp_server / scripts / streamlit_app**: all factory call
  sites now read `app_cfg.embedder` / `app_cfg.generation`. `/api/health`
  reports `OLLAMA` / `GEMINI` / `DUMMY` / `CLAUDE` accurately for both
  halves of the pipeline
- backend/tests: `test_embedder.py` 4 → 12 (+8 — Protocol runtime check,
  DummyEmbedder dim, 4 factory branches, 2 OllamaEmbedder w/ ollama mock);
  `test_rag.py` 23 → 29 (+6 — GenerationBackend Protocol, 3 factory
  branches, OllamaBackend chat-API contract, RAGPipeline end-to-end with
  injected OllamaBackend); new `test_ollama_backend.py` (2 integration
  tests, gated by `pytest.importorskip("ollama")` + server reachability +
  `AXIS_OLLAMA_INTEGRATION=1` opt-in)
- docs: ADR-026 (Ollama integration, dim-mismatch consequence documented),
  `docs/deployment.md` — new "Fully On-Prem with Ollama" section with
  model selection table and rebuild instructions, `docs/configuration.md`
  — `embedder` / `generation` reference
- 既存 358 tests + 新規 14 件 = **372 件 PASS** (2 skipped: redis + ollama
  optional deps), ruff 緑

### Day 43 (2026-05-14) — demo bugfix (spec_043)

v0.8.1 リリース後の portfolio demo GIF 撮影中に発覚した 2 件の UX バグを修正
(v0.8.2 patch release 候補)。

- **GraphSidebar 視認性**: `bg-slate-50` (body と同色で「そこにある」のが分から
  ない) → `bg-white` + `border-l-2 border-slate-200` + `shadow-sm` に変更。
  初期状態のメッセージにアイコン (🕸️) と操作ガイド (ドラッグで回転、スクロー
  ルでズーム) を追加 (frontend/src/components/GraphSidebar.tsx)
- **検索 body の正規化テキスト混入**: `scripts/build_index.py` で chunker に
  `d.normalized_body or d.body` を渡していたため、`parent.text` / `child.text`
  が NFKC + カタカナ→ひらがな + lowercase 適用済みで ChromaDB に保存されてい
  た (「ベクトル検索は…」が「べくとる検索は…」に化ける)。`d.body` (原文) を
  chunker に渡すよう変更し、embedding 計算時のみ child 毎に `normalizer(c.text)`
  を適用。検索結果の表示テキストが読みやすい原文に
- **DUMMY 抜粋の smart truncate**: `backend/src/rag.py` の DUMMY 答え抜粋
  `[:120]...` (中途切れ + 短すぎ) を `_smart_truncate(text, 200)` 経由に変更。
  文末境界 (`。` / `.` / `!` / `?` / 空行) で切り、見つからなければハードカット。
  suffix は `…` (U+2026) で見栄え向上
- **既存 index 互換**: `VectorStore.load_parents()` に heuristic 判定を追加。
  parents.db のサンプル text に hiragana はあるが katakana も uppercase ASCII
  も無い場合 warning ログを出し、`--rebuild` を推奨 (auto rebuild は data loss
  回避のため行わない)
- backend/tests/test_rag.py: `_smart_truncate` 5 件 (空文字 / 短文 passthrough
  / JP 句点境界 / EN period 境界 / 境界無し hard cut) + DUMMY snippet integration
  1 件 = **6 件追加** (17 → 23)
- docs/design-decisions.md: ADR-007 に Update (spec_043) 節を追加 — 「normalize は
  embedding only、storage は原文」方針を明示
- 既存 352 tests + 新規 6 件 = **358 件 PASS** (1 skipped: redis 未インストール)、
  ruff 緑

### Day 42 (2026-05-14) — v0.8 review fixes (spec_041 HIGH/MID/LOW 5 件解消) (spec_042)

spec_041 のレビューで指摘された 5 件 (HIGH 1 + MID 2 + LOW 2) を一括解消。
A 判定昇格を狙う patch release (v0.8.1)。

- **[HIGH]** backend/src/config.py: `EVAL_OVERRIDE_FLAG` を `load_app_config()`
  に wire (spec_038 で wire 漏れ + spec_041 review で指摘)。`_build_app_config(raw)`
  を切り出し、末尾で `_apply_override_flags(cfg, override)` を適用。dotted-key
  =value 形式、複数 key は `;` 区切り、型強制 (bool > int > float > str)、
  unknown key は WARNING + skip。これで spec_038 の A/B テストが initial 以来初めて
  effective に動作する
- **[MID]** backend/src/parent_storage.py: `SqliteParentStorage.get_many()` を
  `SQLITE_VARIABLE_LIMIT=999` で chunking 実装に変更。1000+ docs での
  `OperationalError: too many SQL variables` を解消。入力順序は保持
- **[MID]** backend/src/conversation.py: `SqliteStore.SCHEMA` に
  `idx_sessions_last_access` index を追加。`CREATE INDEX IF NOT EXISTS` で
  既存 DB は再オープン時に冪等 migrate。TTL / LRU eviction scan が O(N) →
  O(log N)
- **[LOW]** backend/src/conversation.py: `RedisStore.__len__()` docstring に
  「`SCAN_ITER` は O(K) — hot path で使うな」注記
- **[LOW]** backend/src/api.py: lifespan の `build_default_graph()` を
  `asyncio.get_running_loop().run_in_executor(None, ...)` でスレッドオフロード。
  1000+ docs 起動時の event loop ブロックを解消
- backend/tests/test_parent_storage.py: `TestSqliteSpecificScaling` 3 件追加
  (999 / 1000 / 2500 ids)
- backend/tests/test_conversation_sqlite.py: 2 件追加
  (`test_idx_sessions_last_access_exists` + 既存 DB に index が migrate
  されるテスト)
- evaluation/tests/test_run_abtest_integration.py: **新規**。6 件
  (single key / multi key / unknown key warning / no-env / type coercion / chat.enabled)
- docs/adr/ADR-019-ragas-evaluation.md: spec_042 Update 節を追加 — wiring 仕様、
  型強制表、silent fail の方針
- docs/configuration.md: 末尾に `EVAL_OVERRIDE_FLAG` 環境変数セクションを追加
- 既存 tests に回帰なし、新規 11 件 PASS、ruff 緑

### Day 39 (2026-05-14) — Code-fence aware citation parser (spec_039)

v0.7 で「許容、v0.8 候補」としていた **Markdown コードフェンス内 `[1]` の偽陽性** を潰す。
` ```python\nx = arr[1]\n``` ` のようなコード片中の `[1]` が citation marker として描画
されていた問題を解消。backend / frontend の parser に同じスキップロジックを実装し、
対称性を維持。

- backend/src/_citations.py: `_RE_CODE_SPANS` を追加 (fenced ` ```...``` ` + inline
  ` `...` `)。`_build_skip_ranges()` / `_is_in_skip_range()` ヘルパで marker 位置が
  code 範囲内かを判定し、`parse_and_validate_citations()` は skip 範囲内の marker を
  リテラルとして保存、`extract_citations()` は単純にスキップ。新規依存なし
- frontend/src/lib/citations.ts: backend と同じ regex パターン (JS では `re.DOTALL`
  が無いので `[\s\S]` で代用) を `RE_CODE_SPANS` として定義。`buildSkipRanges()` /
  `isInSkipRange()` で同等のスキップ動作を実装
- backend/tests/test_citations.py: `test_code_fence_*` 5 件追加 (fenced inside / inline
  / language identifier / extract_citations skip / multiple fences + inline mix)。
  既存 13 件と合わせて 18 件
- frontend/__tests__/citations.test.ts: 新規 5 件 (code fence skip / inline / lang
  identifier / multiple fences / regression check)。frontend テストランナーは未導入
  なので CI では実行されないが、`tsc --noEmit` は緑 (ambient declare で jest 型を
  shim)
- docs/adr/ADR-020-citation-highlighting.md: Update 節を追加。v0.8 で fence skip
  実装、backend と frontend の対称性、ネスト未対応の Open Questions を記録
- 既存 310 tests に回帰なし、合計 **315 passed + 1 skipped** (redis 未インストール)、
  ruff 緑、`npx tsc --noEmit` 緑

### Day 38 (2026-05-14) — RAGAS regression blocking + A/B 評価 (spec_038)

v0.7 の RAGAS CI を hardening。regression を block する仕組みと、config flag の A/B 評価基盤を追加。

- evaluation/stats.py: **新規**。`TTestResult` frozen dataclass + `paired_t_test(scores_a, scores_b)` — scipy optional (未インストール時は `None` を返し graceful degradation)。同一長・2 件以上のチェックで `ValueError`
- evaluation/run_abtest.py: **新規**。`--dataset` / `--flag` / `--output` 引数。config flag を false / true で 2 回 pipeline を走らせ、per-question スコアを `paired_t_test` に渡す。結果を JSON + Markdown テーブルで出力
- evaluation/report.py: **新規**。`generate_ragas_report(run_path, baseline_path)` — baseline 有無で表形式を切り替え。`generate_abtest_report(abtest_path)` — paired t-test 結果を PR コメント用 Markdown に整形
- evaluation/run_ragas.py: `--block-on-regression` フラグ追加 (default off)。regression あり + flag 有効時に `return 1`。既存引数との互換を維持
- evaluation/requirements.txt + pyproject.toml: `scipy>=1.10,<2` を eval extras に追加 (本体実行に不要)
- .github/workflows/ragas.yml: PR コメントを `generate_ragas_report()` 経由に刷新。Generate + Post の 2 ステップ構成
- .github/workflows/ragas-abtest.yml: **新規**。`workflow_dispatch` のみ。`inputs.flag` を受け取り A/B を実行 → artifact 保存 → `$GITHUB_STEP_SUMMARY` にレポート出力
- Makefile: `eval-abtest` ターゲット追加 (`time_decay.enabled` A/B をワンライナーで実行)
- evaluation/tests/test_stats.py: 新規 5 件 (identical p > 0.99 / 明確差 p < 0.001 / 長さ不一致 / 少数サンプル / scipy 不在 skip)
- evaluation/tests/test_report.py: 新規 3 件 (baseline あり / なし / A/B レポート)
- evaluation/tests/test_run_ragas.py: 新規 2 件 (skip: ragas mock 必要)
- docs/adr/ADR-019-ragas-evaluation.md: Update 節追加 (blocking 方針 + A/B 設計 + コスト追記)
- docs/evaluation.md: A/B Test セクション追加
- 既存 304+ tests に回帰なし、新規 10 件追加 (8 pass + 2 skip)、ruff 緑

### Day 37 (2026-05-14) — Parent Storage: JSON → SQLite migration (spec_037)

v0.8 hardening。spec_031 で導入した `parents.json` を SQLite (`parents.db`) に置換し、
起動時の全ロード遅延とフル書き直し I/O を解消する。既存ユーザーは何もしなくても初回起動で自動移行。

- backend/src/parent_storage.py: **新規**。`ParentStorage` Protocol (runtime_checkable) + `SqliteParentStorage` (WAL mode、lazy SELECT per parent_id、`idx_parents_doc_id` index) + `JsonParentStorage` (v0.7 全ロード、backward compat 用) + `make_parent_storage()` factory (sqlite 優先、JSON 検出時は 1 回だけ自動 migrate + warning ログ)。stdlib `sqlite3` のみ、新規依存なし
- backend/src/vector_store.py: `self._parents` dict (in-memory eager) を `self._parent_storage: ParentStorage` に置換。`__init__` に `storage: str = "sqlite"` パラメータを追加。`add_chunks()` → `_parent_storage.upsert_many()`、`query_with_parents()` → `_parent_storage.get_many(top_pids)` (batch lazy fetch)、`has_parents()` → `count() > 0`、`reset()` → `clear()`。`_persist_parents()` / `PARENTS_SIDECAR_FILENAME` / `PARENTS_SIDECAR_VERSION` を削除
- scripts/build_index.py: `--migrate-parents-json` フラグ追加 (冪等、`parents.db` 既存なら skip)。`--parent-storage {sqlite,json}` フラグ追加 (config.yml を override)。`parents.json` 参照を `parents.db` に更新
- backend/src/config.py: `ParentDocConfig` に `storage: str = "sqlite"` フィールドを追加。`load_app_config()` が `retrieval.parent_doc.storage` をパース
- config.yml: `retrieval.parent_doc.storage: "sqlite"` を追加 (default)
- backend/tests/test_parent_storage.py: **新規** 17 件 — `TestCommon` (sqlite & json パラメトライズ 7 件) + `TestSqliteSpecific` (persist_across_instances / wal_mode / index_on_doc_id 3 件) + `TestMigration` (auto_migrate / no_files / storage_json / existing_sqlite_skips / migrated_data_matches 5 件) 、さらに `TestCommon` は params=2 で 14 実行
- backend/tests/test_vector_store.py: `parents.json` 参照を `parents.db` に更新 (2 箇所)、reset テストを `has_parents()` チェックに変更 (file 非存在チェックを削除)。SQLite パス専用テスト 3 件追加 (has_parents_true_after_add / load_parents_returns_correct_count / has_parents_false_after_reset)
- docs/adr/ADR-023-parent-storage-sqlite.md: 新規 ADR。Context (全ロード遅延) / Decision (SQLite default + JSON fallback) / Alternatives (parquet・LMDB・JSON 維持 を却下) / Consequences (起動改善・VACUUM 未実装の Open question を記録)
- docs/configuration.md: 新規。全 config.yml キーのリファレンス表 (retrieval.parent_doc.storage の移行ノートを含む)
- 既存 291 tests に回帰なし、合計 **304+ tests pass**、ruff 緑
- 性能改善: SQLite lazy init **0.7ms** vs JSON 全ロード **12.8ms** で **約 18 倍高速** (1000 parents)

### Day 36 (2026-05-14) — Pluggable Session Persistence (spec_036)

v0.7 の `ConversationStore` は in-memory dict + `threading.Lock` で、`uvicorn --workers > 1` だと session が worker 間で共有されず、プロセス再起動で 24h TTL の意味も失う致命傷があった。spec_036 で **Protocol + 3 backend** に再設計し、default を **SqliteStore** に切り替え。

- backend/src/conversation.py: `ConversationStore` を `typing.Protocol` (`@runtime_checkable`) に変更。`MemoryStore` (旧 in-memory 実装をリネーム), `SqliteStore` (stdlib `sqlite3` + WAL + FK CASCADE), `RedisStore` (optional dep) の 3 実装を追加。factory `make_conversation_store(chat_cfg)` が `chat.storage.backend` に応じて構築、失敗時は warning + `MemoryStore` fallback。すべて `has(session_id)` メソッドを追加して API 側の `_sessions` 内部アクセスを排除
- backend/src/config.py: `StorageConfig(backend, sqlite_path, redis_url)` を追加、`ChatConfig.storage` field をぶら下げ。`load_app_config()` で `chat.storage.*` を typed パース
- config.yml: `chat.storage.{backend, sqlite_path, redis_url}` を追加 (default `backend: "sqlite"` / `sqlite_path: "~/.axis_chat.db"`)
- backend/src/api.py: lifespan で `make_conversation_store(app_cfg.chat)` を使用、shutdown 時に `store.close()` 呼び出し。`get_chat_history` の `store._sessions` 直接参照を `_store_has()` helper (`has()` メソッド経由) に置換
- mcp_server/_session.py: `ConversationStore(...)` → `MemoryStore(...)` に変更 (MCP プロセスは自己完結なので in-memory で十分、コメントで意図を明記)
- pyproject.toml: `[project.optional-dependencies]` に `redis = ["redis>=5.0,<6"]` を追加 (default install には含めない)
- docker-compose.yml: `redis` service を `profiles: ["redis-backend"]` で optional 追加 (appendonly + allkeys-lru)。`redis-data` named volume も追加
- backend/tests/test_conversation.py: 既存 12 件を `parametrize("memory","sqlite", indirect=True)` で共通 contract test に再編 (14 件 × 2 backend = 28 件)。MemoryStore 固有の TTL/LRU eviction (内部 dict 参照) は別関数として残置
- backend/tests/test_conversation_sqlite.py: 新規 9 件 — persists_across_instances / concurrent_writes (10 thread × 10 append) / eviction_cleans_messages (FK CASCADE) / db_file_creation (nested parent dir) / wal_mode_active / sqlite_lru_eviction / close_idempotent / use_after_close_raises / concurrent_reads_during_write
- backend/tests/test_conversation_redis.py: 新規 6 件 — pytest.importorskip + skipif (Redis 未起動時) で optional。persistence / TTL applied / pipeline atomic / delete / history truncation / short-TTL expiry
- backend/tests/test_rag.py: `ConversationStore()` → `MemoryStore()` に書き換え (3 箇所)
- docs/adr/ADR-022-session-persistence.md: 新規 ADR — Context (worker 多重化 + 再起動で session 喪失) / Decision (Protocol + 3 backend, default SQLite) / Alternatives (a) pickle dump (b) JSON+lock (c) SQLite ✓ (d) Redis ✓ optional (e) PostgreSQL ✗
- docs/deployment.md: §Session Persistence を追加 — 3 backend 比較表 + SQLite restart シナリオ + Redis 起動手順 + privacy mode (`backend: "memory"`)
- 既存 291 tests に回帰なし、合計 **317 passed + 1 skipped** (redis 未インストール)、ruff 緑
- **後方非互換注意**: v0.7 で `from backend.src.conversation import ConversationStore` を class として呼んでいたコードは Protocol 化により壊れる。in-repo callers は全て更新済み、外部利用者は `MemoryStore` か factory に置換が必要

### Day 40 (2026-05-14) — GraphRAG + 3D Knowledge Graph (spec_040)

v0.8 マーキー機能。YAML frontmatter の `refs:` フィールドを *初めて* 検索 / 可視化のソースとして活用する。

- backend/src/graph.py: 新規。`KnowledgeGraph` クラス (networkx.DiGraph ラッパ) + `GraphNode` / `GraphEdge` frozen dataclass。`build_from_docs()` (broken refs を warning + skip、self-loop は silently skip、循環参照は許容) / `neighbors_within_hop(direction="out|in|both")` / `get_node` / `get_all_nodes(limit, offset)` / `find_path(max_length)` / `stats()`。`build_default_graph(knowledge_dir)` ヘルパで `examples/knowledge` から起動時に build
- backend/src/config.py: `GraphConfig(enabled=True, default_hop=1, max_neighbors_per_query=20, expand_on_search=False, knowledge_dir="./examples/knowledge")` を追加。`load_app_config()` で `config.yml > graph.*` をパース
- config.yml: `graph.*` ブロックを追加 (default `enabled: true`, `expand_on_search: false` — 既存検索の挙動は完全互換)
- backend/src/search.py: `SearchEngine.__init__(graph=None)` + `search(graph_expand=False, graph_hop=1, graph_max_neighbors=10)` を追加。`_expand_with_graph()` で上位 5 件の seed に対して 1 hop 隣接を BFS し、score = 元 × 0.7 でマージ + 再ランク。`_fetch_doc_as_result()` は file-level Chroma `.get(ids=[doc_id])` で metadata + body を引き、parent-doc モード時は store.parents から fallback
- backend/src/api.py: lifespan で `build_default_graph(app_cfg.graph.knowledge_dir)` を呼んで `_state["graph"]` に格納し、`SearchEngine(graph=graph)` に渡す。`GET /api/graph` (limit/offset + axes_category/axes_level フィルタ) / `GET /api/graph/{doc_id}/neighbors` (hop, max_neighbors) を追加。`/api/search` も `graph_expand` / `graph_hop` / `graph_max_neighbors` を受け付ける (config の `expand_on_search` と OR)
- backend/src/schemas.py: `SearchRequest` に `graph_expand` / `graph_hop` / `graph_max_neighbors` を追加。`GraphNodeModel` / `GraphEdgeModel` / `GraphStats` / `GraphResponse` / `NeighborResponse` Pydantic v2 を追加
- mcp_server/server.py: `axis_neighbors` tool を追加 (`doc_id` + `hop` + `direction` + `max_neighbors`)。グラフは module global で 1 回 lazy build (`_get_graph()`)
- mcp_server/schemas.py: `NeighborsInput` を追加 (`direction="out|in|both"` を含む)
- mcp_server/formatters.py: `format_neighbors_md()` / `format_neighbors_json()` を追加
- frontend/src/lib/graphClient.ts: 新規。`fetchGraph(filters)` / `fetchNeighbors(docId, hop, max)` + TypeScript インタフェース
- frontend/src/components/Knowledge3DGraph.tsx: 新規。`react-force-graph-3d` ラッパ、category 軸で色分け、node size = 1 + in_degree + out_degree、矢印付き有向エッジ
- frontend/src/components/GraphSidebar.tsx: 新規。クリックされた node の `/api/graph/{id}/neighbors` を表示
- frontend/src/components/GraphFilterBar.tsx: 新規。category / level dropdown + stats overlay
- frontend/src/app/graph/page.tsx: 新規。`/graph` route、`dynamic({ ssr: false })` で react-force-graph-3d を遅延ロード
- frontend/src/app/layout.tsx: nav に "🕸️ Graph" リンクを追加
- frontend/package.json: `react-force-graph-3d@^1.24` / `three@^0.160` / `d3-force-3d@^3.0` を追加
- streamlit_app.py: 第 3 タブ `🕸️ Graph` を追加 — `/api/graph` を fetch → networkx + matplotlib で 2D spring layout 描画 (category 軸で色分け)
- pyproject.toml: `networkx>=3.0,<4` を main deps に追加 (~600 KB)
- backend/tests/test_graph.py: 新規 21 件 — empty / single / directed edge / self-loop skip / broken ref warn / hop=1/2 / max_neighbors cap / direction out/in/both / unknown node / get_node degree / pagination / stats / find_path (exists / no_path / self / max_length 超過) / 循環参照
- backend/tests/test_search.py: 新規 5 件 — graph_expand で隣接追加 / dedup / score=元 × 0.7 / graph=None で no-op + warning / max_neighbors cap
- backend/tests/test_api.py: 新規 4 件 — `/api/graph` 200 + nodes/edges/stats / category フィルタ / `/api/graph/{id}/neighbors` 200 / unknown doc → 404
- docs/adr/ADR-024-graphrag-retrieval-expansion.md: 新規。Context (refs が integrity 専用で retrieval に使われていなかった) / Decision (1 hop expansion + 0.7× decay, opt-in) / Alternatives (Neo4j / ChromaDB metadata / PageRank) / Consequences (networkx 依存 / 結果セット最大 +50 / default off)
- docs/adr/ADR-025-3d-graph-visualization.md: 新規。Context (リスト UI 一辺倒) / Decision (react-force-graph-3d + dynamic({ssr:false})) / Alternatives (sigma.js / Cytoscape / Three raw) / Consequences (deps 増 / WebGL 必須 / ~1000 node 上限)
- docs/architecture.md: §3-3 "Graph layer" を追加 (ASCII フロー図 + 設計ポイント 3 点)、旧 §3-3 を §3-4 にリナンバ
- docs/api-reference.md: `/api/graph` + `/api/graph/{id}/neighbors` + `/api/search` の graph_expand パラメータを追記
- docs/mcp-server.md: §3-7 `axis_neighbors` の入出力スキーマと Markdown サンプル
- README.md: ✨ 特徴 に "🕸️ GraphRAG + 3D Visualization"、⚙️ config.yml テーブルに `graph.*` 行を追加
- 既存 261 tests に回帰なし、合計 **291 tests pass**、ruff 緑、`npm run build` 緑

### Day 34 (2026-05-14) — In-Text Citation Highlighting (spec_034)

- backend/src/_citations.py: 新規。`parse_and_validate_citations()` / `extract_citations()` の 2 関数。`[N]` (1-indexed) インライン引用マーカーをパースし、`[1, 2]` を `[1][2]` に正規化、out-of-range な N (`N > len(sources)`) は silently strip + warning ログ。新規依存 0
- backend/src/rag.py: `SYSTEM_PROMPT` / `CHAT_SYSTEM_PROMPT` の引用ルールを `[doc_NNN]` から `[N]` (1 始まり) に変更。`answer()` / `_generate_chat_answer()` で Claude の生レスポンスを `parse_and_validate_citations()` に通し、`cited_ids` を `sources[N-1].id` のリストとして公開 (API 互換性は維持)。`CITATION_RE` を削除、`re` import も削除
- backend/src/rag.py: `_dummy_answer()` の出力フォーマットを `[doc_NNN]` から `[1]` に変更
- backend/tests/test_citations.py: 新規 13 件 — single / consecutive / `[1, 2]` 正規化 / out-of-range strip / partial-invalid / zero-index / 全 invalid / `n_sources=0` / offset 抽出
- backend/tests/test_rag.py: 新規 3 件 — Claude モック経由で `[N]` → source ID マッピング / out-of-range strip / `[1, 2]` 正規化を確認
- frontend/src/lib/citations.ts: 新規。`parseCitations(text)` が `{kind: "text" | "citation", n}` のセグメント列を返す。バックエンドと対称な regex
- frontend/src/components/AnswerPanel.tsx: `[N]` を `<button>` として描画、クリックで対応 source の `<ResultCard>` を `scrollIntoView` + 黄色フラッシュ。`sources` / `onCitationFocus` prop を追加
- frontend/src/components/ResultCard.tsx: `n` (1-based index) / `highlighted` prop を追加。`highlighted=true` で黄色背景 + `data-highlighted` 属性 (テスト用)。`[N]` チップをタイトル左に表示
- frontend/src/components/ChatMessage.tsx: `[doc_NNN]` regex を削除、`parseCitations()` で `[N]` をボタン化。クリックで自動的に "📚 出典" expander を開き、該当 li を黄色フラッシュ
- frontend/src/app/page.tsx: `highlightedId` state を持ち、`AnswerPanel.onCitationFocus` 経由で対応 `ResultCard` に flash を渡す
- streamlit_app.py: `_render_answer_with_citations()` / `_render_sources_with_anchors()` を追加。`[N]` を `<a href="#axis-src-N">` に変換、CSS `:target` でアンカー遷移時に該当カードを黄色背景化。JS なし・サーバラウンドトリップなしで動作。Search タブ / Chat タブ両方で使用
- docs/adr/ADR-020-citation-highlighting.md: 新規 ADR — Context (どの文がどの出典か不明) / Decision (`[N]` plain-text marker) / Alternatives (a-d) / Consequences (LLM 遵守率, code fence 内偽陽性)
- docs/api-reference.md: `/api/answer` / `/api/chat` のレスポンス例を `[doc_NNN]` から `[N]` に書き換え、`cited_ids` の生成ルール / out-of-range strip の挙動を追記
- README.md: ✨ 特徴 に「🔗 In-Text Citation Highlighting」行を追加
- 既存 API 互換: `text` / `cited_ids` / `sources` のフィールド構造は変更なし。`cited_ids` は引き続き doc-NNN-style ID のリスト
- MCP / 平文クライアント: `[1]` `[2]` がそのまま表示されるが、脚注として自然に読める (ADR-020 alternatives 参照)

### Day 35 (2026-05-14) — Time-Weighted Decay (spec_035)

- backend/src/_decay.py: 新規。`decay_factor()` / `blend_score()` / `_parse_datetime()` の 3 純粋関数。副作用なし・新規依存なし (math.exp のみ)。ISO 8601 文字列・datetime 両対応。パース失敗 / `updated` 不在 / 未来日付はすべて decay=1.0 (ペナルティなし)
- backend/src/config.py: `TimeDecayConfig` (frozen dataclass) を追加。`enabled=False / half_life_days=180 / weight=0.15 / date_field="updated"` を default 値とし、`RetrievalConfig` に `time_decay` フィールドを追加。`load_app_config()` が `retrieval.time_decay.*` を typed に読み込む
- config.yml: `retrieval.time_decay.{enabled,half_life_days,weight,date_field}` を追加 (default: `enabled: false`)。既存挙動変更なし
- backend/src/search.py: `SearchResult` に `metadata: dict[str, Any]` フィールドを追加 (後方互換 default `{}`)。`_to_results()` / `_parent_to_result()` が Chroma / ParentChunk の raw metadata を `SearchResult.metadata` に格納。モジュールレベル `_apply_time_decay()` 関数を追加 (BM25 fusion 後に適用、re-sort + top_k 再スライス)。`SearchEngine.__init__()` に `time_decay_config: TimeDecayConfig | None = None` を追加。`_main()` が config から `time_decay_config` を渡す
- backend/tests/test_decay.py: 新規 14 件 — None/空/今日/half-life/2×half-life/未来日付/ISOzulu/ISO日付のみ/不正文字列/blend weight=0/1/0.5/clamp-high/clamp-neg/recent>old/≤1 invariant
- backend/tests/test_search.py: 新規 5 件 — `_apply_time_decay` でのスコア逆転確認 / 日付なし doc でペナルティなし / time_decay_config=None で既存スコア不変 / enabled=False で no-op / SearchResult.metadata フィールド存在確認
- docs/adr/ADR-021-time-weighted-decay.md: 新規。Context (鮮度考慮) / Decision (exp decay + weight blend) / Alternatives (linear/step/hard-filter を却下) / Consequences (default off・安全側倒れ)
- README.md: ✨ 特徴 に「🕐 Time-Weighted Decay」行を追加、⚙️ config.yml 主要設定テーブルを新設
- 後方互換: `enabled: false` default かつ `SearchResult.metadata` は `field(default_factory=dict)` なので既存 tests / API / RAGAS は全て緑

### Day 32 (2026-05-14) — Conversational RAG (履歴保持チャット) (spec_032)

- backend/src/conversation.py: 新規。in-memory `ConversationStore` (TTL 24h + LRU 100 sessions / `threading.Lock` でスレッドセーフ)、`Message` / `Session` frozen dataclass、モジュール global の default store を `get_default_store()` / `configure_default_store()` / `reset_default_store()` で操作
- backend/src/question_rewriter.py: 新規。Gemini Flash (`gemini-1.5-flash`) で「履歴 + 最後の質問 → standalone クエリ」へ rewrite。API key 不在 / 例外 / 500 字超 / 空応答時は元クエリにフォールバック (UX を絶対に止めない)。`書き換え後の質問:` などの leak prefix を strip
- backend/src/rag.py: `RAGPipeline.chat()` を追加 — rewrite → search → 生成 → store.append の 4 ステップ。`CHAT_SYSTEM_PROMPT` で「履歴と検索結果が矛盾したら検索結果を優先」を指示、直近 3 turn (= 6 messages) を Claude messages に添付。`ChatResponse` dataclass を公開、`_source_to_dict()` で SearchResult を JSON-friendly に
- backend/src/api.py: `POST /api/chat` / `GET /api/chat/{sid}` / `DELETE /api/chat/{sid}` を追加。lifespan で `ConversationStore(max_sessions, ttl_seconds)` を `_state["chat_store"]` に保持 + `configure_default_store()` で global にも反映
- backend/src/schemas.py: `ChatRequest` / `ChatResponseModel` / `ChatMessagePayload` / `ChatHistoryResponse` を追加
- backend/src/config.py: `ChatConfig` / `ChatRewriterConfig` を追加し `load_app_config()` で `config.yml > chat.{enabled, max_history_turns, ttl_seconds, max_sessions, rewriter.{enabled, model}}` を読み込み
- config.yml: `chat.*` ブロックを追加 (default `enabled: true`, `max_history_turns: 6`, `ttl_seconds: 86400`, `max_sessions: 100`, `rewriter.model: gemini-1.5-flash`)
- mcp_server/server.py: `axis_chat` tool を追加 — session_id を保持すれば follow-up が効く対話 RAG。`mcp_server/_session.py` でモジュール global `ConversationStore(max_sessions=20, ttl_seconds=3600)` を持つ (FastAPI 側 store とは独立、MCP プロセス再起動で消える旨を tool docstring に明記)
- mcp_server/schemas.py: `ChatInput` Pydantic 入力を追加
- mcp_server/formatters.py: `format_chat_md()` / `format_chat_json()` を追加 (rewritten_question を caption 表示、session_id を末尾に明示)
- streamlit_app.py: `st.tabs(["🔎 Search", "💬 Chat"])` で 2 タブ構成に。Chat タブは `st.chat_input` / `st.chat_message` + 「会話をリセット」ボタン + 出典 expander、`AXIS_API_BASE` 環境変数で backend URL を切り替え可能
- frontend/src/lib/chatClient.ts: 新規 `postChat()` / `deleteChat()` + localStorage に session_id を保存 (key=`axis-chat-session-id`)
- frontend/src/components/ChatMessage.tsx: 新規。user/assistant でバブル分け、`[doc_NNN]` をハイライト、`📚 出典` を折りたたみ表示、`🔁 rewritten` を caption で表示
- frontend/src/components/ChatInput.tsx: 新規。Enter 送信 + disabled 状態
- frontend/src/app/chat/page.tsx: 新規。App Router の `/chat` ページ。`useEffect` で localStorage から session_id 復元 + auto-scroll
- frontend/src/app/layout.tsx: ナビに `💬 Chat` リンク追加
- backend/tests/test_conversation.py: 新規 12 件 — new/existing session, append+history, history truncation, unknown id → []、TTL eviction (last_access を手動で過去化)、LRU eviction (max=2 で 3 つ作って最古が消える)、delete、thread safety (10 threads × 10 appends = 100 messages 無損失)、default store lifecycle、append on unknown session
- backend/tests/test_question_rewriter.py: 新規 8 件 — 空 history / disabled / no API key / 代名詞解決 (`それの利点は?` + `LangChain` history → `LangChain` を含む書き換え) / API 例外 fallback / 500 字超 fallback / 空応答 fallback / leak prefix strip。`google.generativeai` を monkeypatch で stub
- backend/tests/test_api.py: 新規 6 件 — `/api/chat` で session 発番、同 session_id で再利用、`GET /api/chat/{sid}` で 4 messages 取得、unknown session 404、`DELETE` で 204 → 再 GET 404、empty question で 422
- backend/tests/test_rag.py: 新規 3 件 — `chat()` で session 作成 + 履歴 append、session 再利用で履歴蓄積、empty history では `rewritten_question=None`
- docs/adr/ADR-018-conversational-rag.md: 新規 ADR — Context (single-shot RAG では follow-up が無理) / Decision (in-memory store + Gemini rewrite + hybrid prompt) / Alternatives (LangChain / Redis / full history / streaming) / Consequences (single-worker 制約, 再起動で session 消滅)
- docs/api-reference.md: `/api/chat` の 3 endpoint と single-worker 注記を追加
- docs/architecture.md: §3-2-bis に Conversational RAG フロー (ASCII 図 + 設計ポイント) を追加
- README.md: ✨ 特徴 に「💬 Conversational RAG (履歴保持チャット)」行を追加、ADR-018 へリンク
- 設計バグ修正: `ConversationStore` に `__len__` を定義したことで `store or get_default_store()` がスペース 0 で false 評価される問題を発見、`if store is None` で明示判定するよう修正
- 既存 169 tests + 新規 24 tests = **193 件全パス**、ruff 緑
- 設計の意図: LangChain を避けつつ chat UX を成立させる最少コード。rewrite (検索精度) + 短い履歴添付 (会話感) のハイブリッドで両立。in-memory は v0.7 demo / 個人運用に十分、Redis 化は v0.8 (spec_037) で検討

### Day 33 (2026-05-14) — RAGAS CI/CD (LLM-as-a-Judge 自動評価) (spec_033)

- evaluation/__init__.py: 新規。evaluation パッケージ初期化
- evaluation/datasets/qa_v1.json: 新規。25 件 QA データセット (定義 5 / 比較 5 / Why 5 / How 5 / エッジ 5)、examples/knowledge/01-05.md をカバー
- evaluation/judge.py: 新規。Gemini 1.5 Flash LangChain wrapper。`get_judge_llm()` / `get_judge_embeddings()` を公開
- evaluation/run_ragas.py: 新規。RAGAS 評価ランナー。`--dataset` / `--baseline` / `--output` / `--update-baseline` / `--regression-threshold` オプション。v0.7 は WARN only (exit 0)
- evaluation/baseline.json: 新規。bootstrap 値 (0.0)。nightly CI が実スコアで更新
- evaluation/requirements.txt: 新規。ragas>=0.2.0 / datasets>=2.20 / langchain-google-genai>=2.0 / langchain-core>=0.3
- evaluation/README.md: 新規。使い方 / メトリクス解説 / CI 説明
- .github/workflows/ragas.yml: 新規。nightly (03:00 JST) + PR トリガー (backend/evaluation/config.yml 変更時)。PR コメントでスコア diff 表示、nightly は baseline 自動更新
- Makefile: 新規。`make eval` / `make eval-update-baseline` / `make lint` / `make test`
- pyproject.toml: `[project.optional-dependencies]` に `eval` セクション追加 (ragas/datasets/langchain-google-genai/langchain-core)、packages.find に evaluation* 追加
- docs/adr/ADR-019-ragas-evaluation.md: 新規。judge 選定理由 (Gemini Flash)、コスト見積もり ($1.5/月)、代替案との比較
- docs/evaluation.md: 新規。データセット仕様、メトリクス解説、コスト、将来拡張
- README.md: RAGAS バッジ追加、Evaluation セクション追加、Version バッジを 0.7.0 に更新

### Day 31 (2026-05-14) — Parent Document Retrieval (Small-to-Big) (spec_031)

- backend/src/chunker.py: 新規。Markdown 本文を ParentChunk (H2 単位 / H2 が無ければ doc 全体) と ChildChunk (~256 token; H3+/段落/文末で分割) に純粋関数で分割。LangChain 不使用、`re` + `unicodedata` のみ
  - `ParentChunk` / `ChildChunk` は frozen dataclass。parent_id 形式は `{doc_id}#{ascii-slug}`、CJK タイトルは `md5[:8]` フォールバックで Chroma metadata key に乗せる
  - 文字数 token 換算は 2 文字 ≈ 1 token (JP 平均)、長文 paragraph は文末 (`。`/`.`/`!`/`?`) 境界で greedy 分割
- backend/src/vector_store.py: `add_chunks(parents, children, embeddings)` / `query_children()` / `query_with_parents()` / `load_parents()` / `has_parents()` を追加。child を Chroma collection に upsert (parent_id を metadata に持つ)、parent は ChromaDB ディレクトリ直下の `parents.json` sidecar に永続化。`reset()` は sidecar も削除
- backend/src/search.py: `SearchEngine` に `parent_doc_enabled: bool = False` (後方互換 default OFF) と `top_k_children` を追加。`_search_parent_doc()` で child 検索 → parent_id dedup → max(parent_score) を採用。BM25 fusion は `parent.path` (= file 単位 doc_id) でスコア合算後、同 doc 内に複数 parent がある場合は最高スコアの 1 つに collapse。SearchResult に `body_full: str = ""` フィールドを追加 (parent 全文; 旧経路では空)
- backend/src/rag.py: `build_context(results, max_chars=8000)` 新設。`body_full` が populated なら parent 全文を出典ヘッダ付きで連結 (上限超過時は **直前で打ち切り**、文中切断しない)、未 populated なら snippet にフォールバック。`RAGPipeline` の `answer()` は body_full の有無で `build_context()` / `_format_context()` を自動切替
- backend/src/config.py: `ParentDocConfig` / `RetrievalConfig` / `RAGConfig` / `AppConfig` を追加し、`load_app_config()` で `config.yml > retrieval.parent_doc.{enabled, chunk_strategy, max_child_tokens, top_k_children, top_n_parents}` と `rag.context_max_chars` を typed dataclass に読み込む。`load_axes_config()` は維持 (後方互換)
- config.yml: `retrieval.parent_doc.*` (default `enabled: true`, `max_child_tokens: 256`, `top_k_children: 20`, `top_n_parents: 5`) と `rag.context_max_chars: 8000` を追加
- scripts/build_index.py: `--mode {auto,legacy,parent_doc}` フラグを追加 (`auto` は config.yml に従う)、`--rebuild` を `--reset` のエイリアスとして受理。parent_doc モードでは chunker を呼んで `add_chunks()` で indexing、`parents.json` の出力サイズを stdout に表示
- backend/src/api.py / mcp_server/server.py: lifespan / `_get_engine()` で `load_app_config()` を読み、`parent_doc.enabled=true` でも `parents.json` 不在時は警告ログを出して legacy に **graceful fallback** (UI が真っ白にならない fail-open 方針)。RAGPipeline には `context_max_chars` を伝搬
- backend/src/search.py の CLI も `parents.json` の存在で parent_doc を自動 ON
- docs/adr/ADR-017-parent-document-retrieval.md: 新規 ADR (Context / Decision / 4 alternatives / Consequences / Future work)
- docs/design-decisions.md: ADR-017 セクション追加 (16 → 17 件)
- docs/INDEX.md: ADR 件数 16 → 17、ADR-017 への直接リンク追加
- docs/architecture.md: §3-1 Index time に parent_doc / legacy 両モードを記載、§3-1-bis 「Parent Document Retrieval の構造」を追加 (chunker 構造 ASCII 図と検索フロー)、§4 コンポーネント表に chunker.py 行を追加し vector_store/search/rag の備考を更新
- docs/mcp-server.md: `axis_search` の Annotations 直下に「v0.7 以降は同じ file から複数 H2 が hit し得る」旨の注記を追加 (Pydantic スキーマは不変、既存クライアント互換)
- README.md: ✨ 特徴 に「🧩 Parent Document Retrieval (Small-to-Big)」行を追加、ADR-017 へリンク
- backend/tests/test_chunker.py: 新規 14 件 — H2 なし / H2 分割 / 前文の root parent / token cap / 文末境界 / parent 内に child を内包 / 決定論的 parent_id / orphan child を作らない / 空 body / metadata 継承 / CJK タイトル → md5 slug / heading-only セクション / dataclass frozen / DEFAULT_MAX_CHILD_TOKENS 定数
- backend/tests/test_vector_store.py: 新規 5 件 — `add_chunks()` で children 件数が collection に反映 + `parents.json` 生成、`query_with_parents()` の parent dedup と top_n、`load_parents()` で sidecar から復元、length mismatch 時の ValueError、`reset()` で sidecar も削除
- backend/tests/test_search.py: 新規 4 件 — parent_doc モードで parent_id を返す / parent_id が unique / axis-only path も動作 / `parent_doc_enabled` プロパティ
- 後方互換: `SearchEngine(store, embedder)` (parent_doc_enabled 未指定) は v0.6 と同一挙動。既存 169 tests は全て緑
- 設計の意図: child を embed・parent を返す Small-to-Big パターンで「精度 (小チャンク) と文脈 (H2 セクション) の両立」を実現。parent_doc は JSON sidecar なので埋め込みコストは旧方式と同等、parent text の更新は再 embedding 不要

### Day 30 (2026-05-14) — Public README cleanup + GitHub metadata

- README: 「デモ GIF 取得チェックリスト」セクション削除 (内部 TODO 表記、外部公開不適切)
- README: 冒頭引用ブロックの撮影手順リンクを削除、Demo 文言を簡潔化
- README: 冒頭にコメントアウト img タグを配置 (将来の demo.gif 配置時に外すだけ)
- examples/screenshots/README.md: 新規、撮影ガイドライン
- GitHub About description セット: "軸メタデータ × ベクトル検索 × BM25 の 3-way hybrid RAG OSS..."
- GitHub Topics セット: 14 件 (rag / claude-api / gemini-api / mcp-server / nextjs / fastapi / vector-search / chromadb / bm25 / japanese-nlp / knowledge-management / local-first / llm / python)
- ADR 表記 (Deciders: 中島) は設計史なので残置 (spec_030 §2 制約準拠)

### Day 29 (2026-05-14) — 3-way hybrid search (BM25 fusion) (spec_029)

- backend/src/bm25_index.py: 新規。`BM25Okapi` + 文字 n-gram (n=1, 2) トークナイザ、min-max 正規化済み score を返す。`Normalizer` 統合で query 側も同じ正規化を経由
- backend/src/search.py: `SearchEngine` に `bm25_index` パラメータ追加、`search()` に `bm25_weight: float = 0.5` を追加。`use_bm25` 判定で fusion を skip 可能 (query=None / index 未配線 / weight=0 で v0.5 互換)、fusion 時は vector を `max(top_k*2, 20)` で over-fetch して BM25 が再ランクできる候補を確保
- backend/src/normalizer.py: `Normalizer.identity()` classmethod を追加 (テスト・docs での pass-through 用)
- mcp_server/schemas.py: `SearchInput.bm25_weight: float` (`ge=0.0, le=1.0`, default=0.5) を追加
- mcp_server/server.py: `axis_search` tool が `params.bm25_weight` を `engine.search` に伝搬。docstring 更新
- backend/tests/test_bm25_index.py: 新規 8 件 — `_tokenize`、basic scoring、empty query、no matches、`__len__`、normalizer 経由、single doc edge case
- backend/tests/test_search.py: 新規 5 件 — `bm25_weight=0.0` で v0.5 互換、`bm25_weight=1.0` で BM25-only、ranking change、index 未配線時の no-op、axis-only path での short-circuit
- mcp_server/tests/test_server.py: `test_axis_search_with_bm25_weight` を追加 — `SearchInput.bm25_weight=0.7` が `engine.search` まで forward されることを spy で検証
- docs/design-decisions.md: ADR-016 追加。RRF ではなく weighted sum を選んだ理由、形態素解析ではなく n-gram を選んだ理由を明示
- docs/search-fusion.md: 新規。3-way fusion のアーキ図、`bm25_weight` チューニングガイド、設計判断 (Over-fetch / Weighted Sum / 永続化未実装) を解説
- docs/INDEX.md: ADR 件数 15 → 16、search-fusion.md エントリ追加
- pyproject.toml: `rank-bm25>=0.2.2` を依存追加
- 後方互換: `bm25_weight=0.0` で v0.5 と同一結果を保証 (テストで verify)。MCP サーバ側は index を build せずに起動するため現状 no-op (配線は spec_030 予定)

### Day 27 (2026-05-13) — MCP error sanitization (内部情報漏洩防止) (spec_027)

- mcp_server/_errors.py: 新規 — `make_error_response()` + `new_correlation_id()` (5 char UUID hex)
- mcp_server/server.py: 全 6 tool の except 節を `make_error_response()` 呼び出しに統一。`axis_list_axes` は既存 try/except なしだったので追加
- mcp_server/server.py: `_CorrFormatter` を `configure_logging()` 直後に設定 — `[%(levelname)s] corr=%(corr_id)s %(name)s: %(message)s` フォーマット。`corr_id` 未付与の record は `-----` でフォールバック
- Internal exception details (file path, API error body, Pydantic input echo, ChromaDB fragment) を MCP client に露出させない設計に統一
- mcp_server/tests/test_server.py: `test_axis_search_error_is_sanitized` (caplog で full exception がログに残ることも確認) + `test_all_tools_error_sanitized` (全 6 tool を parametrize、ZeroDivisionError が戻り値に含まれないことを検証)
- docs/mcp-server.md: Error handling セクション (§4) 追加、既存セクション番号を繰り下げ、ファイル構成・テストカバレッジ表を更新 (21 → 28 tests)

### Day 25 (2026-05-13) — Doc 整合性パス (v0.4 メタデータ統一) (spec_025)
- pyproject.toml: `version` を `0.1.0.dev0` → `0.4.0` に更新 (実体に追従)
- backend/src/api.py: `FastAPI(version=...)` を `_pkg_version()` 経由の動的取得に変更。`_pkg_version()` を `FastAPI(...)` 直前に移動。`/api/health` の version レスポンスも自動的に `0.4.0` を返すように
- README.md: Version badge `0.3.0` → `0.4.0`、Status badge `v0.3` → `v0.4`。ロードマップ行の MCP 表記を「5 read-only tools」→「6 tools (5 read + 1 ingest)」に統一
- README.md: 壊れた `![demo](examples/screenshots/demo.gif)` を削除し、Demo セクション (録画予定の注記 + 撮影チェックリストへのリンク) に置換 (方針 A 採用)。撮影チェックリストは末尾セクションに保持
- docs/mcp-server.md: 「5 tools」表記 (L40 / 本文 / L394 / L465) を「6 tools」に統一。`axis_ingest_memo` を tool 一覧表 + 詳細 section (3-6) として追記 (I/O サンプル / annotations / DUMMY モード説明)
- docs/mcp-server.md: `axis_list_axes` セクションの軸サンプル値を config.yml と一致 (category: `['技術記事', 'メモ', '議事録', 'ToDo']` / level: `['初級', '中級', '上級']`、`topic` を required で追記)
- docs/mcp-server.md: テストカバレッジ表に `axis_ingest_memo` 行追加 (18 → 21 tests)
- docs/api-reference.md: `/api/health` サンプルの version を `0.3.0` → `0.4.0` に。`/api/axes` サンプル軸値を config.yml と一致 ("技術記事/メモ/議事録/ToDo" + "初級/中級/上級" + topic を追加)
- docs/INDEX.md: 空の `## Portfolio` セクション (portfolio-notes 残骸) を削除
- docs/deployment.md: 「Local Docker > 起動」手順に `git fetch --tags origin` を追記 (clone 直後のタグ取得手順を明示)
- git tag 状態: ローカル / リモート両方に v0.1.0 〜 v0.4.0 が揃っていることを確認 (`git ls-remote --tags origin` で 4 タグ全件確認)
- 設計の意図: result_024.md (CC 総合レビュー) で指摘された B 判定要因「メタデータ不整合」を一括解消。ロジック変更ゼロ、docs と const のみ。CC レビュー再走で A 判定狙い

### Day 23 (2026-05-13) — AI ingester (memo → YAML 自動変換) (spec_023)
- backend/src/ingester_schemas.py: 新規。Pydantic v2 — `IngestResult` (id pattern `doc_\d{3,}` / refs prefix / body min_length 等を strict validation), `IngestOptions` (knowledge_dir / suggested_category / max_tokens)
- backend/src/ingester.py: 新規。`Ingester` クラス本体 — `rag.py` の Anthropic クライアント生成パターンを継承、`ANTHROPIC_API_KEY` 未設定 or `force_dummy=True` で DUMMY モード (sha256 derived の決定論的 mock)、`_next_doc_id` で `examples/knowledge/` を走査して連番計算、`load_axes_config()` を毎回呼んで config.yml の axes を prompt 制約として注入、`_strip_code_fence` で Claude のコードフェンス耐性、`render_markdown` で `yaml.safe_dump(sort_keys=False)` 経由の整形出力
- scripts/yamlize.py: 新規。単発 CLI — stdout/-o, --suggested-category, --max-tokens, --force-dummy, stdin (`-`) 対応
- scripts/yamlize_dir.py: 新規。バッチ CLI — `*.txt` を走査して `<doc_NNN>-<slug>.md` で出力、in-memory counter で同一バッチ内 id 衝突回避、`_slugify` は非 ASCII title 時に filename stem へフォールバック
- examples/raw_memos/sample_memo_0[1-3].txt: 新規。Slack コピペ風 / 議事録風 / 自己ノート風の 3 サンプル
- backend/tests/test_ingester.py: 新規。13 tests — DUMMY mode, `_next_doc_id` (empty/missing/populated dir), render_markdown round-trip (frontmatter.loads で再パース), schema validation (invalid ref / bad id pattern), `_strip_code_fence` parametrize
- mcp_server/schemas.py: `IngestInput` を追加 (raw_text 20-10000 chars / knowledge_dir / suggested_category / max_tokens / response_format)
- mcp_server/server.py: 6 個目の tool `axis_ingest_memo` を追加 (`openWorldHint=True` で Claude API 呼び出しを明示、json モードは `rendered_md` + `is_dummy` 含む構造体を返す)
- mcp_server/tests/test_server.py: `axis_ingest_memo` の DUMMY mode test 3 件追加 (markdown / json / pydantic input validation)
- docs/ingester.md: 新規。アーキ図、3 形態の使い方、軸推測 prompt 戦略、既知制約、v0.5+ ロードマップ
- docs/INDEX.md: ingester.md エントリ追加、MCP tools 数を 5 → 6 に更新
- README.md: Quickstart 直下に「🤖 メモを自動 YAML 化」セクション追加、MCP tools 表に `axis_ingest_memo` 追加
- 依存追加なし (anthropic + pyyaml + pydantic は既存)

### Day 19 (2026-05-13) — Docker 分割 (backend / frontend) + E2E (spec_019)
- Dockerfile.backend: 新規。`python:3.11-slim`、`pip install -e .`、`EXPOSE 8000`、`HEALTHCHECK` で `/api/health` を 10s 間隔ポーリング、CMD で `scripts.build_index` → `uvicorn backend.src.api:app --host 0.0.0.0 --port 8000`
- Dockerfile.frontend: 新規。multi-stage build (`node:20-alpine` AS builder → AS runner)、`NEXT_TELEMETRY_DISABLED=1`、Next.js standalone output を runner にコピー、非 root user `nextjs:1001` で `node server.js` 起動 (`EXPOSE 3000`)
- frontend/next.config.mjs: `output: "standalone"` + `reactStrictMode: true` を追加 (Docker runtime のスリム化のため)
- docker-compose.yml: 旧 `app` 単一サービスから `backend` + `frontend` の 2 サービス構成に書き直し。`backend` は `healthcheck` で `/api/health` を監視、`frontend` は `depends_on: condition: service_healthy` で backend ready を待ってから起動。ChromaDB は named volume `chroma-data` に永続化
- Dockerfile → Dockerfile.streamlit: 旧 Week 1 単一 Dockerfile を rename して retreat 用に保持 (採用面接で Week 1 → Week 3 進化の説明に使う)
- .dockerignore: monorepo 向けに更新 — `frontend/node_modules`、`frontend/.next`、`.env.local`、`*.md` (除く README/CHANGELOG) を追加
- frontend/.dockerignore: 新規。`node_modules` / `.next` / `out` / `.env*.local` を除外

### Day 18 (2026-05-13) — AnswerPanel + 疑似ストリーミング + 出典リンク (spec_018)
- frontend/src/components/SkeletonLoader.tsx: 新規。`animate-pulse` ベースの汎用スケルトン
- frontend/src/components/AnswerPanel.tsx: 新規。`/api/answer` レスポンス表示用 — typewriter 風 pseudo-streaming (setInterval, 25ms 間隔 / 80 等分 step)、`[doc_NNN]` 正規表現で出典を `<a href="#doc_NNN">` に変換、`aria-live="polite"`、loading/error/empty 各 state、DUMMY mode / model 表示
- frontend/src/components/ResultCard.tsx: `id={result.id}` を `<article>` に付与 → AnswerPanel からの anchor jump 対応、`scroll-mt-4` で固定ヘッダー余白
- frontend/src/app/page.tsx: AnswerPanel 統合、`withRag` チェックボックス (デフォルト ON)、トグルで `/api/answer` ↔ `/api/search` 切替、`answer.cited_ids` を `ResultCard.cited` prop へ連動

### Day 22 (2026-05-13) — MCP server 化 (spec_022)
- mcp_server/__init__.py: 新規 (package marker)
- mcp_server/__main__.py: 新規。`python -m mcp_server` エントリポイント
- mcp_server/schemas.py: Pydantic v2 入力モデル (SearchInput / AnswerInput / ListAxesInput / CheckIntegrityInput / ListDocumentsInput) + ResponseFormat enum
- mcp_server/formatters.py: Markdown / JSON 整形ヘルパー (search / answer / axes / integrity / documents)
- mcp_server/server.py: FastMCP ベース MCP サーバー本体 — 5 read-only tools (axis_search / axis_answer / axis_list_axes / axis_check_integrity / axis_list_documents), lazy singleton (_get_engine / _get_rag), stdio transport 対応 (logging → stderr)
- mcp_server/tests/test_server.py: pytest smoke tests 18 件 — 全 5 tools の markdown/json 両モード、pagination、lazy init、DUMMY モードのみ使用 (CI は API キーなし)
- pyproject.toml: `mcp>=1.2.0` を dependencies に追加、`[project.scripts]` に `axis-knowledge-rag-mcp` 登録、`setuptools.packages.find` に `mcp_server*` 追加、pytest testpaths に `mcp_server/tests` 追加
- README.md: MCP server セクション追加 (Quickstart 直下) — Claude Desktop 設定例、tool 一覧表、docs/mcp-server.md リンク; ロードマップに v0.4.0 ✅ 追加
- docs/mcp-server.md: 新規 — 動機・アーキテクチャ・5 tools 詳細仕様 (I/O サンプル) / Claude Desktop / Cowork / mcp-cli 組み込み手順 / DUMMY モード試験手順 / 既知制約 / 将来計画
- docs/INDEX.md: mcp-server.md エントリ追加
- examples/claude_desktop_config.json: 新規。Claude Desktop 組み込み設定例
- mcp>=1.2.0 (実インストール: 1.27.1)

### Day 20 (2026-05-13)
- README.md: v0.3 全面改稿 — shields.io バッジ (Version 0.3.0 / Next.js 14 追加)、デモ GIF placeholder、Next.js + FastAPI アーキ図 (ASCII)、デモ GIF 取得チェックリスト、ロードマップ v0.1〜v0.3 全 ✅
- docs/architecture.md: v0.3 構成に更新 — Next.js 14 + FastAPI の ASCII コンポーネント図、Mermaid フロー図、コンポーネント責務一覧 (backend/frontend 両方)、v0.3 Docker Compose 構成
- docs/design-decisions.md: ADR-013 (疑似ストリーミング typewriter)、ADR-014 (Streamlit を deprecated せず残す)、ADR-015 (Docker multi-stage frontend slim 化) を追加
- docs/api-reference.md: 全 4 endpoint を最終版に整備 — エラーレスポンス仕様、全フィールド説明、起動方法追記
- docs/deployment.md: 新規 — Local Docker / ChromaDB バックアップ / Fly.io / Cloud Run / TLS プロキシ / CI/CD 構成

### Day 15 (2026-05-13)
- backend/src/schemas.py: Pydantic v2 schemas — HealthResponse, AxisDef, AxesResponse, SearchRequest, SearchResultPayload, SearchResponse, AnswerRequest, AnswerResponse
- backend/src/api.py: FastAPI app with lifespan init (SearchEngine + RAGPipeline 1回のみ), 4 endpoints: GET /api/health, GET /api/axes, POST /api/search, POST /api/answer
- backend/src/api.py: CORS middleware (localhost:3000, localhost:8501), Swagger UI at /api/docs
- backend/tests/test_api.py: 4 TestClient tests (health, search_empty, answer_dummy, axes) — all PASS
- backend/requirements.txt + pyproject.toml: fastapi>=0.115.0, uvicorn[standard]>=0.30.0 追加
- docs/api-reference.md: 4 endpoint の仕様、起動方法、CORS 設定を記載

### Day 12 (2026-05-13)
- pyproject.toml: add `[project.optional-dependencies].dev` with pytest>=8, pytest-cov>=5, ruff>=0.5
- pyproject.toml: add `[tool.pytest.ini_options]`, `[tool.coverage.run/report]`, `[tool.ruff.lint]` sections
- backend/tests/conftest.py: shared fixtures — dummy_embedder, in_memory_store (tmp_path-isolated), search_engine, sample_documents
- backend/tests/test_*.py: convert all 8 test files to pytest style; remove __main__ runners
- backend/tests/test_normalizer.py: 15-case parametrize table + 4-case query_matches_index parametrize
- backend/tests/test_marker.py: parametrize for invalid-name and append-newline variants
- backend/src/*.py + streamlit_app.py: ruff auto-fix (UP035, F401, B905, SIM105)
- .github/workflows/ci.yml: push/PR → ruff check + pytest --cov-fail-under=70, matrix py311/py312
- .github/workflows/docker.yml: push/PR → Docker build-only with GHA layer cache
- Coverage: 72.49% (70% threshold met), 90 tests all PASS

### Day 11 (2026-05-13)
- backend/src/marker.py: AUTO_GENERATED block handling — extract_blocks, update_block, strip_blocks, validate_balance
- backend/src/marker.py: CLI entrypoint (`python -m backend.src.marker`) with --list / --update / --strip / --validate modes
- backend/tests/test_marker.py: 31 tests covering extract, update, strip, validate, nested DOTALL, CRLF, CLI modes
- examples/knowledge/01-rag-patterns.md: demo AUTO_GENERATED summary block (placeholder for Day 13 build script)
- docs/marker.md: design rationale, ASCII diagram, API reference, CLI usage, recommended block names

### Day 10 (2026-05-12)
- backend/src/integrity.py: IntegrityChecker with broken_refs, orphan_docs, cycle detection
- backend/src/integrity.py: CLI entrypoint (`python -m backend.src.integrity`) with --json and --strict flags
- backend/tests/test_integrity.py: 5 tests covering no-error, broken refs, orphans, cycles, self-loops
- scripts/build_index.py: --strict-integrity flag aborts index build on broken refs
- docs/integrity.md: architecture explanation, CLI usage, FAQ, future roadmap

### Day 8 (2026-05-12)
- backend/src/normalizer.py: Japanese text normalizer (NFKC + katakana→hiragana + lowercase), standard library only (unicodedata)
- backend/src/normalizer.py: `normalize_text` pure function + `Normalizer` class (config.yml-driven)
- backend/tests/test_normalizer.py: 16 cases covering NFKC, kana, lowercase, idempotency, options toggle
- docs/normalizer.md: pipeline explanation, edge cases, future extensions
- config.yml: added `lowercase: true` to normalization section

### Day 6 (2026-05-13)
- Dockerfile: python:3.11-slim base, `pip install -e .`, build_index + streamlit run on CMD
- docker-compose.yml: app service (ports 8501:8501, env_file .env, chroma-data volume, examples/knowledge ro mount)
- .dockerignore: exclude .git / _ai_workspace / docs / __pycache__ / .chromadb / .env / node_modules
- examples/knowledge/06-10: 5 new sample knowledge docs (prompt-injection / evaluation-metrics / tooling-comparison / cost-estimation / future-roadmap)
- README.md: v0.1 rewrite — shields.io badges, demo placeholder, features/quickstart/manual setup/roadmap/architecture
- Note: doc_005 → doc_999 broken ref intentionally retained for Week 2 integrity demo

### Day 5 (2026-05-12)
- streamlit_app.py: Streamlit UI with sidebar axis filter, search bar, answer panel, result cards
- streamlit_app.py: @st.cache_resource for SearchEngine and RAGPipeline initialization
- backend/src/config.py: `load_axes_config()` helper to read config.yml
- examples/screenshots/: checklist for README v0.1 demo capture
- Dependencies: streamlit>=1.37.0 added

### Day 4 (2026-05-12)
- backend/src/rag.py: RAGPipeline (Claude API + DUMMY fallback) with citation extraction via `[doc_NNN]` regex
- backend/src/rag.py: CLI entrypoint (`python -m backend.src.rag`) with axis filters
- backend/tests/test_rag.py: 8 DUMMY-mode integration tests (all pass)
- Dependencies: anthropic>=0.34.0 added to requirements.txt and pyproject.toml
- Model: claude-3-5-sonnet-20241022, overridable via CLAUDE_MODEL env var
- DUMMY mode: activated when ANTHROPIC_API_KEY is unset (consistent with Embedder pattern)

### Day 3 (2026-05-12)
- backend/src/search.py: SearchEngine (hybrid axis+vector search) with SearchResult dataclass
- backend/src/search.py: CLI entrypoint (`python -m backend.src.search`)
- backend/tests/test_search.py: 8 integration tests using in-memory VectorStore + force_dummy Embedder
- Verified: Chroma 0.5 `$and` multi-key filter works correctly
- Note: score=0.0 in DUMMY mode is expected (hash-derived embeddings have near-zero cosine similarity)

### Day 2 (2026-05-12)
- backend/src/embedder.py: Gemini text-embedding-004 wrapper with deterministic dummy fallback (CI / offline dev)
- backend/src/vector_store.py: ChromaDB PersistentClient wrapper (axis-aware metadata flattening)
- scripts/build_index.py: index a knowledge directory into `.chromadb/`
- backend/src/config.py: add `COLLECTION_NAME = "axis_knowledge"` constant
- Dependencies: google-generativeai>=0.7.0, chromadb>=0.5.0
- Smoke tests for embedder and vector_store (assert-based, in-memory Chroma)

### Day 1 (2026-05-12)
- Initial project structure
- backend/src/loader.py: Markdown + YAML frontmatter loader
- 5 sample knowledge documents under examples/knowledge/
