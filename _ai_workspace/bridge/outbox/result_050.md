# result_050 — v0.9 全体総合コードレビュー (F1–F5 完成後)

- **Reviewer**: Claude Code (`dev-b`)
- **Branch reviewed**: `feat/spec_050-v0.9-final-review` (base = v0.8.1)
- **Diff scope**: `git log v0.8.1..HEAD` = 73 commits, spec_043 → spec_053
  - F1 = spec_045 (Ollama), F2 = spec_046 (Browser Ext), F3 = spec_047
    (Feedback), F4 = spec_048 (Gap Detection), F5 = spec_049 (Bidirectional)
  - 後続 hotfix: spec_051 (HIGH-1 dim mismatch / MID-1 ingest token / MID-3
    detect_no_info 偽陽性), spec_052 (Gemini gen backend), spec_053
    (GraphSidebar 可視化)
- **Method**: read-only code review — `backend/src/{embedder,rag,api,search,
  ingest_web,feedback,gap_detection,graph,config,schemas}.py`,
  `browser-extension/{manifest,popup,background}.{json,js}`,
  `frontend/src/{lib,components}/*.{ts,tsx}`, `mcp_server/{server,schemas,
  formatters}.py`, `evaluation/{feedback,gap}_report.py`, tests under
  `backend/tests/` と `frontend/__tests__/`。**ソース変更 0、commit 0**.

---

## 1. spec 別 所見テーブル (4 軸: Security / Performance / Correctness / Maintainability)

### spec_045 (F1 — Ollama / fully on-prem)

| 軸 | 所見 | 評価 |
| --- | --- | --- |
| Security | Ollama URL は `OllamaConfig.url` (config.yml 経由、信頼境界内)。`google.generativeai` API key は `settings.gemini_api_key` から取得し log に出さない。`ClaudeBackend.__init__` で API key の log 露出無し。**外部入力からの URL injection 経路は無し**。 | ✅ |
| Performance | `OllamaEmbedder.__init__` で `_probe_dim()` (1 RTT) が走り、起動時に 1 回だけ。`embed_batch` は逐次 (Ollama embeddings endpoint が単発)。**timeout / retry 設定無し** — Ollama がハングすると FastAPI request も道連れ。ローカル前提なら許容。Anthropic SDK は built-in retry (default 2 回) があるので Claude 側は OK。 | 🟡 |
| Correctness | Protocol (`Embedder` / `GenerationBackend`) 設計が clean。3 backend (Gemini/Ollama/Dummy × Claude/Gemini/Ollama/Dummy) すべて `make_*()` factory で集約。**HIGH-1 (dim mismatch) は spec_051 で startup fatal にして対処済み** (`api.py` lifespan で `embedder.dim != store.probe_dim()` なら `RuntimeError`)。bge-m3 (1024dim) ⇄ Gemini (768dim) index 再構築 guidance 入りメッセージも親切。`make_generation_backend("auto")` の fallback chain (Claude→Gemini→Dummy) も妥当。 | ✅ |
| Maintainability | テスト 14 unit + 2 integration (test_embedder.py + test_ollama_backend.py)。`OllamaEmbedder` の import を遅延化 (`try: import ollama`) し optional extras `[ollama]` 化済。`auto` mode が spec_052 で追加された差分も非破壊。**`force_dummy` 互換 shim** が `GeminiEmbedder` に残る — v0.10 で剥がす候補だが現状妥当。 | ✅ |

### spec_046 (F2 — Browser Extension MVP)

| 軸 | 所見 | 評価 |
| --- | --- | --- |
| Security | (a) **CORS regex `^(chrome-extension://.*\|http://localhost(:\d+)?\|http://127\.0\.0\.1(:\d+)?)$` は chrome-extension で wildcard** — 任意の Chrome 拡張から POST 可能。 **spec_051 MID-1 で AXIS_INGEST_TOKEN を opt-in 化** して mitigation 済 (README/deployment.md 注記あり)。(b) **path traversal**: `_slugify()` の `[^\w\s-]` 削除で `.` も dropped するため `"../../etc"` → `etcpasswd` → 単なる slug 化。さらに filename は `web_<timestamp>_<slug>.md` で timestamp prefix 強制 → traversal 不可能。(c) **XSS**: title/body は **markdown ファイルに書き込むだけ**、サーバ側で render しない。downstream で render する場合 (Streamlit/Next.js) は既存 markdown sanitizer に委任。(d) **URL scheme 検証無し** — `IngestRequest.url: str` で `javascript:` や `file://` も受理。frontmatter `url:` / body `source:` に書き込まれるだけなので blast radius は低いが、`HttpUrl` 化が望ましい。 | 🟡 |
| Performance | popup.js: `MAX_BODY_CHARS = 5000` で head 切り — 妥当。`save_web_page` は 1 file write、I/O はミリ秒オーダー。`_yaml_dump` は自前 1 階層のみ対応の最小実装で軽量。 | ✅ |
| Correctness | NFKC 正規化 + Python `\w` で Japanese 対応 → `Ｗｅｂ 記事` → `web-記事` (test_slugify_japanese_title で実証)。`selected_text` が body より優先される (test 済)。**同一秒内の 2 回連続 ingest はファイル名衝突 + 上書き**するが UX 上ほぼ起きない。`_yaml_scalar` は YAML reserved indicator / `: ` を quote 対象にしており URL の `:` を区切りと誤解しない設計。8 unit + 2 API integration テストでカバー済。 | ✅ |
| Maintainability | extension は MV3 + vanilla JS + manifest minimal (権限 `activeTab` / `scripting` / `storage` のみ)。`background.js` は default endpoint seed のみで余計な service worker logic 無し。`browser-extension/README.md` で troubleshooting も整備。 | ✅ |

### spec_047 (F3 — Active Learning Feedback)

| 軸 | 所見 | 評価 |
| --- | --- | --- |
| Security | (a) **PII 蓄積リスク**: `FeedbackRecord.query` を平文で SQLite に保存 (`~/.axis_feedback.db`)。ユーザが query に PII / 機密情報を入力すると永続化。`feedback_report.py` も top queries をそのまま markdown に dump → Slack 貼付時に漏出。**Local-first OSS としては許容範囲だが README に注意書きあるべき** (現状 deployment.md に MID-1 周りの注記はあるが PII 注意は無し)。(b) `POST /api/feedback` に rate limit 無し → spammy POST 攻撃の余地 (CORS で localhost / chrome-extension に限定されているので blast radius は低い)。 | 🟡 |
| Performance | `SqliteFeedbackStore` は単一 connection + `threading.Lock` + `PRAGMA journal_mode=WAL`。FastAPI worker 数 × Lock contention は ms 未満。`list_recent` で `WHERE timestamp >= ?` + `idx_feedback_ts` index あり、O(log n) で取れる。 | ✅ |
| Correctness | (a) **2 重送信防止**: ResultCard.tsx / ChatMessage.tsx ともに `disabled={feedback !== null}` で第 2 クリックを block。Optimistic UI で失敗時のみ `prev` (null) に巻き戻し → 再 click 可能。Streamlit 側 (`streamlit_app.py`) は `st.button` の natural rerun + key uniqueness で防いでいる (双方の挙動が異なる点が要注意だが意図的)。(b) Protocol `FeedbackStore` の runtime_checkable 検証あり (test_make_feedback_store_enabled)。(c) feedback 無効時の API 503 路径確認済 (lifespan で `feedback_store=None`、`_require_feedback_store()` が 503 を投げる)。 | ✅ |
| Maintainability | 12 unit + 3 feedback report + 4 API test。`note` / `session_id` / `doc_id` すべて optional、`rating` は Pydantic で `-1 ≤ rating ≤ 1` 制約。idempotent close() 含めて backend 差し替え (Postgres / Redis) の seam がきれい。 | ✅ |

### spec_048 (F4 — Knowledge Gap Detection)

| 軸 | 所見 | 評価 |
| --- | --- | --- |
| Security | feedback と同様、`query` を平文で `~/.axis_gap.db` に保存。**PII risk は feedback と同等**。gap_report.py の "Top unsatisfied queries" がそのまま markdown 出力されるため Slack 共有時注意。 | 🟡 |
| Performance | (a) **search path overhead**: `_record_gap()` は results.empty / top_score 比較のみで O(1)。disabled 時は `self._gap_store is None` で即 return — **zero hot-path cost を実現**。(b) **rag path overhead**: `_record_llm_gap()` は regex 1 回 (`_NO_INFO_RE.search`) — 数十パターン union だが alternation 数本なので ms 未満。(c) **disk growth 抑制無し** — TTL / rotation / vacuum 設定無し、`SqliteGapStore` は monotonic 増加。**v0.10 で 30/90 日 cleanup ジョブ追加が望ましい** (feedback も同じ問題)。 | 🟡 |
| Correctness | (a) **detect_no_info 偽陽性率**: spec_051 MID-3 で `わかりません` / `不明です` を `(?:。\s*\Z\|\Z)` 終端アンカー化 → 「A は X ですが、B はわかりません、しかし C は Y です。」が False に。test_detect_no_info_partial_answer_is_false で regression guard 済。真陽性 (「結論はわかりません。」) も維持を test で実証。English/Japanese 両対応。**spec で要求された "偽陽性をなるべく抑える" 設計目標は達成**。(b) **search / rag hook が既存 logic を破壊しない**: `_record_gap` / `_record_llm_gap` は **post-hoc + try/except + log warning** — 例外で本来の search/RAG path を止めない。axis-only query (query=None) は skip。(c) gap store と search engine / RAG pipeline で **同一 store instance を共有**するため 1 件の query が `no_results` (search) と `llm_no_info` (rag) で 2 record になることがあるが、reason で識別可能で意図通り。 | ✅ |
| Maintainability | 11 + 3 + endpoint test。Protocol `GapStore` + factory `make_gap_store(cfg)` → None で disabled、503 / no-op の対称性が feedback と完全に揃っている。GapConfig.low_score_threshold (default 0.35) は config.yml で tunable。 | ✅ |

### spec_049 (F5 — Bidirectional Refs)

| 軸 | 所見 | 評価 |
| --- | --- | --- |
| Security | 取得 only / 既存 graph cache を read。新規攻撃面無し。`direction` パラメタは API 側 (`pattern="^(in\|out\|both)$"`) で enum 検証済。 | ✅ |
| Performance | (a) **API 2x call cost**: `fetchNeighborsBidirectional` で `Promise.all([out, in])` 並列実行 — wall-clock は 1 call と同等。グラフは startup 時に in-memory 構築済 (`build_default_graph`)、各 endpoint hit は BFS (`neighbors_within_hop`) で O(hop × deg) — 数 ms 未満。(b) lifespan で graph 構築を `loop.run_in_executor` に逃がしているので大規模 corpus でも liveness probe を block しない (spec_042 LOW #5 改修)。 | ✅ |
| Correctness | (a) **forwardlinks / backlinks 表示順**: BFS visit 順 (`networkx.successors` / `predecessors` の挿入順) — 安定だが「title 順」「in_degree 順」等の意味的ソート無し。hop=1 で max_neighbors=20 のフロントエンド固定値なら問題小さい。(b) **MCP 後方互換**: `NeighborsInput.bidirectional: bool = Field(default=False)` で従来 caller は変更不要。`bidirectional=True` 時は `direction` を ignore して `out`+`in` 両 fetch → `format_neighbors_md_bidirectional` で別 section 出力。(c) HTTP API の `direction` validation (`pattern="^(in\|out\|both)$"`) と MCP の `direction: str` (validation 無し) で **整合性が不完全** — MCP 側で不正値は `_collect_neighbors` の `ValueError` 経由で error response に落ちるので破壊的ではない、minor。(d) frontend `GraphSidebar.tsx` の `useEffect` cleanup (`cancelled = true`) で race-condition 対策あり。(e) 独立ノード (`forwardlinks=[] && backlinks=[]`) で「独立ノードです」表示 → 良い UX。 | ✅ |
| Maintainability | 6 test (3 API direction + 3 GraphSidebar render)。`formatters.py` で markdown / json の 4 variants (single×md/json + bidirectional×md/json) を別関数で分離 — 読みやすい。`_DIRECTION_HEADER` map で header 文字列を一元化。 | ✅ |

---

## 2. 全体としての一貫性所見

### 2-1. 4 つの新規 SQLite (.axis_chat / .axis_feedback / .axis_gap / parents.db) の整理

- 現状: `~/.axis_chat.db` (spec_036), `~/.axis_feedback.db` (spec_047),
  `~/.axis_gap.db` (spec_048), `<chroma_db_path>/parents.db` (spec_037).
  前 3 つは home dir 直下に散在、parents.db は chroma path 配下。
- **共通 Protocol 抽出 (CommonStore base) の余地**: `FeedbackStore` /
  `GapStore` は `record()` / `list_recent()` / `count()` / `close()` と
  shape が完全一致。`ConversationStore` は append / get_history で別、
  `ParentStorage` は get / upsert で別。**feedback と gap だけは 1 つの
  generic `EventStore[T]` Protocol に統合できる** (record(event) / list_recent
  → list[T] / close)。ただし統合の利得は小 (各 ~150 行)、現状の重複は
  読みやすさを上回らないので **v0.10 で必要になったらやればいい**。
- **ファイル配置の整理 (推奨、優先度低)**: `~/.axis/{chat,feedback,gap}.db`
  → 1 つのサブディレクトリに集約すると user の `ls ~ | grep axis` が綺麗
  になる。後方互換のため env var (`AXIS_DATA_DIR`) ベースの opt-in 移行
  にすれば破壊しない。
- **dim mismatch 検出は HIGH-1 で対処済**ながら、SQLite 同士の整合は無
  検証 (例: feedback store と gap store の query 重複検知など)。現状は
  まだ要らない。

### 2-2. v0.9.0 リリース可能か

- **判定: A 判定 = ES (Engineer Survey) / portfolio に貼れる**。
- 根拠:
  1. F1–F5 すべてが Protocol-based でテスト網羅。  
  2. spec_051 で HIGH-1 (dim mismatch) / MID-1 (ingest auth) / MID-3
     (regex 偽陽性) を v0.9.0 タグ前に潰し、ADR-031 / ADR-032 / CHANGELOG
     も追従済。  
  3. 後方互換性 100% — `/api/graph/.../neighbors` の direction 省略
     時は `both` で旧動作、MCP `bidirectional` 既定 False で旧動作、
     `EmbedderConfig.backend` 既定 `"gemini"`、`GenerationConfig.backend`
     既定 `"auto"` で v0.8.1 動作を再現。  
  4. 失敗系の graceful fallback — Ollama 接続失敗 / Gemini key 欠落 /
     Anthropic key 欠落のいずれも startup を止めず DUMMY に落ちる。  
  5. PII / disk growth は **OSS local-first** という positioning の中では
     軽微 (Wiki / TODO に v0.10 候補として明記すればよい)。
- リリース blocker は無し。

### 2-3. 新たに見つけた問題 (priority 付き、0–5 件)

| # | priority | 領域 | 問題 | 推奨アクション |
| --- | --- | --- | --- | --- |
| 1 | **MID** | spec_046 / schemas.py | `IngestRequest.url: str` が scheme 検証無し。`javascript:` や `file://` URL を frontmatter `url:` / body `source:` 行に書き込み可能。 | `pydantic.HttpUrl` に変更、または `re.match(r"^https?://", url)` validator 追加。`AXIS_INGEST_TOKEN` 未設定時は警告 log。 |
| 2 | **LOW** | spec_047 / spec_048 | `.axis_feedback.db` / `.axis_gap.db` に query が平文蓄積、永久成長。 | (a) README / deployment.md に PII 注意書き追加。(b) v0.10 で `FeedbackConfig.retention_days` / `GapConfig.retention_days` + housekeeping ジョブ追加。 |
| 3 | **LOW** | spec_045 / rag.py + embedder.py | `OllamaBackend.generate` / `OllamaEmbedder.embed` に explicit timeout 無し。 | `ollama.Client(host=url, timeout=30)` 等で per-request タイムアウトを設定。FastAPI request hang を防ぐ。 |
| 4 | **LOW** | spec_049 / mcp_server/schemas.py | MCP `NeighborsInput.direction: str` は pydantic Field validation 無し (HTTP API は `pattern` あり)。不正値は `KnowledgeGraph._collect_neighbors` の `ValueError` 経由でエラー応答に落ちるが整合性悪い。 | `direction: Literal["in", "out", "both"]` 化 (HTTP 側と揃える)。 |
| 5 | **LOW** | spec_046 / api.py CORS | `chrome-extension://.*` は任意の extension に open。`AXIS_INGEST_TOKEN` で mitigation はあるが default off。 | (a) README 注記済を維持。(b) 将来 `AXIS_INGEST_TOKEN` を default-on にし、unset 時 startup warning を出す案を v0.10 で検討。 |

**HIGH なし**。MID 1 件、LOW 4 件のみで、いずれもリリース blocker ではない。

### 2-4. ポジティブ評価 (0–5 件)

1. **Protocol-first 設計の徹底** — F1 (Embedder / GenerationBackend), F3
   (FeedbackStore), F4 (GapStore) すべてが `Protocol + runtime_checkable +
   make_*(cfg) factory + Sqlite implementation + Dummy/None fallback` の
   同一テンプレートで実装され、backend を差し替える seam が一貫している。
   将来 Postgres / Redis 実装を追加するときに迷う場所が無い。
2. **失敗時の graceful degradation が網羅的** — Ollama import 失敗 →
   DummyEmbedder、Gemini key 欠落 → DummyGenerationBackend、parents.json
   欠落 → file-level fallback、graph build 失敗 → /api/graph 503、
   feedback/gap disabled → 503。**どこを切っても startup が死なない。**
3. **後方互換へのこだわり** — MCP `bidirectional` 既定 False、HTTP
   `direction` 既定 `both`、generation `backend="auto"` 既定で v0.8.1
   挙動を再現、`force_dummy` 互換 shim 維持。**呼び出し側を一切壊さない。**
4. **spec_051 の hotfix 質が高い** — HIGH-1 (dim mismatch) を **startup
   で fatal にする** 判断は正しい (silent fail の方が遥かに危険)。MID-3
   の regex 偽陽性修正に **真陽性 regression test を明示的に追加** している
   (`test_detect_no_info_sentence_end_wakarimasen_is_true`) — 細かいが
   将来の "改善のつもりで真陽性を壊す" 事故を防ぐ。
5. **テスト網羅性** — F1 14+2、F2 8+2、F3 12+3+4、F4 11+3、F5 6 と
   各 spec で **unit + integration を必ず最低限揃えている**。frontend に
   runner が無い (`graph-sidebar.test.tsx` は placeholder) のは欠点だが
   API 層で同等を埋めている。

---

## 3. v0.10 候補 (発見的に列挙)

1. **データ保持ポリシー**: feedback / gap DB に `retention_days` + cron
   housekeeping、`SELECT … VACUUM` ジョブ。Issue #2 と紐付け。
2. **active learning ループの活用**: 現在 spec_047 / spec_048 は
   "ログだけ"。次のステップは:
   - 👎 が一定数集まった doc の score 自動低減 / BM25 weight 調整。
   - gap report の上位 query から **LLM が ingest 提案** を生成
     (frontmatter 草稿を `/api/ingest` 経由で save、人間 review 後 commit)。
3. **`HttpUrl` validator + ingest token default-on**: Issue #1 と #5。
4. **`~/.axis/` 配下に SQLite 集約**: 2-1 で挙げた配置整理。`AXIS_DATA_DIR`
   env var で opt-in 移行。
5. **MCP / HTTP の direction validation を統一**: Issue #4。
6. **OllamaBackend / OllamaEmbedder の timeout & retry**: Issue #3。
7. **`force_dummy` shim 撤去**: spec_045 で `DummyEmbedder` が登場した
   ため、`GeminiEmbedder(force_dummy=True)` 互換コードは v0.10 で剥がせる。
8. **Common `EventStore[T]` Protocol**: feedback と gap で 50% コード重複
   ありで統合可能 — ただし優先度低。
9. **forwardlinks/backlinks の sort key 選択**: GraphSidebar UI で
   "in_degree 降順" / "title 順" の toggle を導入。
10. **frontend test runner (vitest)**: `graph-sidebar.test.tsx` /
    `citations.test.ts` が runner 待ちで動いていない。

---

## 4. 結論

**Overall Grade: A**  
v0.9.0 (= v0.9.1 / spec_053 後) は **portfolio / ES に貼って恥ずかしくない
品質**。F1–F5 の主要機能は Protocol 設計が一貫しており、spec_051 で
sev:HIGH 級の bug は事前潰し済、後方互換も完璧。残る課題はいずれも
LOW–MID で v0.10 で順次対処すれば十分。

特筆すべきは **失敗時の graceful degradation の網羅性** と **後方互換へ
のこだわり** — local-first OSS が長期 maintain される条件を満たしている。

---

*Generated by Claude Code (`dev-b`), spec_050. Read-only review — no
source modifications, no commits to backend / frontend / mcp_server /
evaluation directories.*
