# result_024: 総合コードレビュー (v0.1.0 〜 v0.4.0 / main 全体)

- **Spec**: `inbox/spec_024.md`
- **Executor**: Claude Code (`dev-b`)
- **Started**: 2026-05-13 (HEAD: `6363bdd`)
- **Finished**: 2026-05-13
- **Status**: done (read-only — no source files modified)

## 1. 要約

main HEAD `6363bdd` (v0.4.0 + spec_023 bonus) を対象に security / performance / correctness / maintainability の 4 軸でレビューした。

- Critical (リリースをブロックする) 問題は **0 件**。シークレットの実体漏洩なし、深刻な path traversal / 認証バイパス / SQL/コマンドインジェクション該当箇所なし。
- 一方で「**ポートフォリオとしての完成度**」に直結する **メタデータ不整合・ドキュメント drift** が複数 (バージョン badge / tool 数 / 軸値サンプル / demo GIF 欠落)。採用者の最初の数分の印象を下げるため、合算すると Warning レベル。
- アーキテクチャ判断は ADR 15 件で明文化されており、`DUMMY` モード、`axis_*_norm` 併記、lazy singleton + MCP ToolAnnotations 等、設計の説明力は高い。
- 主な改善余地は (a) ドキュメントの数値整合性、(b) ingester の retry / 重複 I/O、(c) `axis_list_documents` の 200 件上限とゼロ embedding を使った axis-only 検索。

## 2. 全体評価

### **B: 軽微な改善あり** — Critical 0、Warning 6 件、Info 多数

**根拠**:

- セキュリティ的に「公開で危険」な状態ではない。`.env.example` のキーは全て `xxxxx` プレースホルダ、ハードコード API キーなし、ユーザー入力は Pydantic v2 で min/max/pattern 制約済み (max_length 付き)、CORS は閉じた allow-list、PAT 等の認可情報は workflow にも含まれていない。
- 機能面のバグも見つからない。`pytest` 136 件 + coverage 76%+ + ruff 緑、main の commit 履歴も整然 (`merge: spec_NNN` で marker 化、CHANGELOG が日次更新)。
- 一方で **「v0.4.0 タグ + 4 release 公開済み」と spec が述べる状態に対して、READMEバッジは v0.3.0 のまま / api.py の `FastAPI(version=...)` は `0.3.0.dev0` / pyproject は `0.1.0.dev0` / git tag が 1 つも無い** といったメタ不整合が散見される。これは「採用者がリポジトリを開いて最初に見る情報」がズレている状態であり、ポートフォリオ訴求としては修正したほうがよい。
- 上記は全て修正コストが小さい (1〜2 spec で吸収可能) ため A まで上げる余地はあるが、現状そのままだと B 判定。

## 3. 主要発見事項

| # | File | Line | Issue | Severity | Category |
|---|---|---|---|---|---|
| 1 | `README.md` | 6, 9, 232 | Version badge `0.3.0` / Status badge `v0.3` / ロードマップ「**5** read-only tools」と表記。実体は v0.4.0 + 6 tools (spec_023 で `axis_ingest_memo` 追加済)。`docs/mcp-server.md` L40, L465 も「5 tools」のまま | 🟡 Warning | Maintainability |
| 2 | `backend/src/api.py` / `pyproject.toml` | api.py:54, pyproject:7 | `FastAPI(version="0.3.0.dev0")` と `pyproject.toml version = "0.1.0.dev0"` が v0.4.0 と完全不一致。`/api/health` の `version` フィールドは `importlib.metadata.version()` 経由で pyproject の値を返すため、本番 health response が `0.1.0.dev0` を返す | 🟡 Warning | Correctness/Maintainability |
| 3 | `README.md` | 14 | `![demo](examples/screenshots/demo.gif)` — `examples/screenshots/` ディレクトリは空 (ファイル無し)。GitHub プレビューで画像 404。L16 にまだ「Day 20 に中島さんが撮影予定」のコメントが残置 | 🟡 Warning | Maintainability |
| 4 | (git) | — | `git tag -l` が空。spec は「v0.1.0/v0.2.0/v0.3.0/v0.4.0 の 4 タグ + 4 GitHub Release 公開済み」と述べているが、ローカルにタグなし。`git describe --tags` も `fatal: No names found` を返す。リモート専用タグの可能性はあるが、`origin` の参照リストにも push 済みタグの形跡が見えない | 🟡 Warning | Correctness |
| 5 | `docs/api-reference.md` | 51, 57 | サンプル axes 値が `["技術記事", "ノウハウ", "メモ"]` / `["入門", "中級", "上級"]`。実体 (`config.yml`) は `["技術記事", "メモ", "議事録", "ToDo"]` / `["初級", "中級", "上級"]`。`ノウハウ` / `入門` という値はリポジトリのどこにも存在しない | 🟡 Warning | Maintainability |
| 6 | `backend/src/ingester.py` | 128, 133 | `ingest()` 1 回ごとに `_next_doc_id()` と `_existing_doc_ids()` が **両方** `load_directory()` を呼ぶ — `knowledge_dir` を 2 度フルスキャン + 全 frontmatter parse。`scripts/yamlize_dir.py` のバッチで N 件処理すると 2N 回のスキャン | 🟡 Warning | Performance |
| 7 | `backend/src/ingester.py` | 159-165 | `json.loads(raw_json)` 失敗時に即 `RuntimeError` で終了。リトライ無し。CHANGELOG / spec_023 では「リトライ」言及ありだが実装無し。バッチ処理では 1 件の bad response で全体停止 | 🟡 Warning | Correctness |
| 8 | `mcp_server/server.py` | 124-126, 171-173, 222-224, 267-268, 323-325 | 全 6 tool の except 節が `return f"Error: {type(e).__name__}: {e}"` — Anthropic API のエラー本文 / 内部 path / Pydantic validation details がそのまま MCP client に返る可能性。ログには `exception` でフル出ているので、戻り値はサニタイズしたい | 🟡 Warning | Security |
| 9 | `backend/src/search.py` / `mcp_server/server.py` | search.py:135-137, server.py:245 | `query=None` の axis-only 検索が `[0.0] * 768` をそのまま Chroma `query()` に渡している。ChromaDB のデフォルト距離は L2 で、ゼロベクトルは「ノルムが小さい埋め込みに近い」という意味不明な順序付けになる。Pagination の安定性も保証されない。`collection.get(where=...)` 系で軸 only パスを分離した方が安全 | 🔵 Info | Correctness |
| 10 | `mcp_server/server.py` | 245 | `axis_list_documents` は `engine.search(None, ..., top_k=200)` を実行 → **200 件で頭打ち**。コメントで「for small KBs this is fine」と認めているが、`docs/mcp-server.md` の "pagination" 説明と齟齬。`total` も常に `min(real_total, 200)` を返す |  🔵 Info | Performance/Correctness |

(上記 10 件以外の所見は §4 の各軸セクションに記載)

## 4. 4 軸別の詳細所見

### A. Security

**全体評価**: シークレットの実体漏洩なし、入力検証は適切、最小権限ワークフロー。Critical 該当なし。

- `.env.example` のキーは全て placeholder (`sk-ant-xxxxx`, `AIzaSyxxxxx`)。`grep -r 'sk-ant-\|AIzaSy[A-Za-z0-9_-]\{15,\}\|github_pat_'` でも実キー検出なし。
- `.gitignore` で `.env*` を正しく除外、`.env.example` のみ negate で残す。
- FastAPI 側の入力は全て Pydantic v2、`SearchRequest.top_k` `ge=1, le=50` 等の境界が明示、`AnswerRequest.max_tokens` `ge=128, le=4096`、MCP 側も `extra="forbid"` で未知フィールド拒否。
- `loader.load_document(path)` は `path.exists()` / `is_file()` を確認するが、**呼び出し側からの path 受け取りに対する traversal validation はない**。MCP `axis_check_integrity` の `knowledge_dir` パラメータ (`./examples/knowledge` がデフォルト) は任意の絶対パスを受け取って `load_directory()` する。stdio MCP server を信頼できるクライアントから呼ぶ前提なら問題なしだが、書き込みを後で導入する際は要注意。
- `marker.py` の CLI は file write を伴うが、これは local user 操作なので問題なし。
- CORS は閉じた allow-list (`localhost:3000`, `localhost:8501`)。`docs/api-reference.md` L211 が `CORS_ORIGINS` 環境変数 (v0.4 で実装予定) と書いているが **実装が無いまま v0.4 がタグ済み** という matter of fact。
- `.github/workflows/*.yml` は `actions/checkout`, `setup-python`, `docker/build-push-action` のみで `secrets:` 参照なし、push to registry も off。最小権限。

**Prompt injection 耐性**:
- `rag.py` の system prompt は「Document 内容のみから回答」「[doc_NNN] でマーク」と制約を明示している。ただし `user_msg` に `question` が直挿入されており、ユーザー側で `[doc_999]` 偽出典や「無視して」系の指示を入れた場合の防御は system prompt のみに依存。
- `ingester.py` も同様で、`raw_text` がそのまま prompt に入る。出力は Pydantic `IngestResult` で構造化検証 (id pattern, refs prefix, body min_length) されるため、構造逸脱は弾けるが、axes/title の内容を悪意で操作される可能性は残る。ローカル個人ユースなら許容範囲。
- **アクション**: ADR に「prompt injection は信頼境界外の入力ソースを想定していない (個人ナレッジツールのため)」と明記しておくと、レビュアーが評価しやすい。

### B. Performance

- **ingester.py の二重スキャン (#6)** — main の hot path ではないが、`yamlize_dir.py` の N 件バッチで 2N 回 frontmatter parse が走る。`load_directory()` の戻り値を1回だけ取って `_next_doc_id` / `_existing_doc_ids` に渡せば 1 回に圧縮可能。
- **`embed_batch` が逐次呼び出し** (`embedder.py:55-57`) — Gemini `embed_content` の本物 batch API を使わず for loop。`scripts/build_index.py` で初回 100 件のナレッジを embed する場合、100 API calls + rate-limit 衝突リスク。
- **`axis_list_documents` の 200 件上限 (#10)** — ChromaDB の `get()` を使えば pagination もコレクションサイズの上限もない。
- **`_to_results` の score 解釈** (`search.py:75`) — `score = max(0.0, min(1.0, 1.0 - dist))`。Chroma の default は L2 距離で範囲が [0, ∞) なので、距離 > 1 で score=0 にクリップされる。ChromaDB collection 作成時に `metadata={"hnsw:space": "cosine"}` を渡していないため、`vector_store.py:61` のままだと L2。実用上「ほとんどの結果が score=0 に張り付く」可能性がある。`docs/api-reference.md` L120 では「ベクトル類似度スコア (0.0〜1.0)」と書いているのでドキュメント整合性も要修正。
- **Dockerfile.backend の起動時 build_index** (`Dockerfile.backend:25`) — 毎回 `python -m scripts.build_index && uvicorn ...`。volume `chroma-data` で永続化されているのに毎回 upsert を実行 → idempotent ではあるが、GEMINI key 設定時は無駄な embed API call が発生。起動時間も伸びる。`store.count() == 0` の時のみ build する条件分岐が望ましい。
- **streamlit_app.py の Embedder() 二重生成** (L57) — `Embedder().is_dummy` を確認するためだけに別インスタンス生成。`engine._embedder.is_dummy` で十分。
- **`integrity._find_cycles`** — DFS で O(V+E)。再帰深度は Python のデフォルト (1000) なので、`>1000` ノードの直線参照チェーンで RecursionError 可能性あり。現実のナレッジ規模では問題ない。
- **Streamlit の `engine._store.count()` private access** (L91) — 性能ではなく maintainability。

### C. Correctness

- **api.py / pyproject の version drift (#2)** — 上記の通り。`/api/health` レスポンスが間違った version を返す。
- **axis-only path のゼロ embedding (#9)** — 上記の通り。リスティング結果順序が不定。
- **`marker.update_block` は最初の 1 個しか書き換えない** (`marker.py:90` の `count=1`) — ADR-008 でも「同名ブロック複数は未対応」と明記済み。意図的制約 ✓
- **`validate_balance` の crossed-name 検出不能** — 同名ブロックが交差する病的ケースは漏れる。ネスト未対応も同じ。これらは ADR-008 で documentation 化されており意図通り ✓
- **`_dummy_result` body** — DUMMY が `IngestResult.body min_length=20` を必ず満たすか: `f"<!-- DUMMY mode... -->\n\n{raw_text.strip()}"` で、ヘッダーだけで 35 文字を超えるので OK ✓
- **`IngestResult` validation の bypass 経路なし** ✓ — Pydantic v2 `field_validator` を後付け、`refs prefix doc_` を強制。
- **`yamlize_dir.py` の id 上書き** — Claude が出した id を `current_id` で上書きする (`scripts/yamlize_dir.py:87`)。バッチ内で id 衝突を避ける意図はコメントで説明済み ✓ ただし副作用として、Claude が refs に含めた `current_id` 以外の id (人間が編集後に意味的につながりを持たせる予定の id) があれば、書き戻された ID と整合が取れなくなる可能性。レアケース。
- **CORS の env-var 化** — README/docs が「v0.4 で実装予定」と謳うが未実装 (api.py:62-70 は hardcoded)。v0.4 リリース済みなので「未達成のロードマップ項目」になっている。
- **CLAUDE_MODEL default `claude-3-5-sonnet-20241022`** (`rag.py:20`, `ingester.py:26`, `README.md:218`) — 2024-10 のモデル。プロジェクトの 2026-05 時点での "最新を使っている感" を出すには `claude-sonnet-4-5` 等への更新が望ましい。env-var override で対応可能なので必須ではない。

### D. Maintainability

- **ADR が 15 件、Context/Decision/Consequences/Alternatives 完備** — `docs/design-decisions.md` 599 行は portfolio として強力。
- **CHANGELOG が日次・spec_NNN 単位で詳細** — 何をやったかの粒度が均一。
- **dead code はほぼ無し** — `_build_where` (raw axis) と `_build_where_norm` (正規化軸) は両方残っているが、`_build_where` は v0.9 normalize 統合前のテストとの後方互換のために残されたことが docstring に書かれている。意図的。
- **frontend/src/lib/api.ts と backend/src/schemas.py の手動同期** — `// Types mirror backend/src/schemas.py` コメントで認識済み。OpenAPI codegen 化はトレードオフ判断ありえる。
- **MCP server の例外ハンドラの broad catch** (#8) — top-level safety net としては妥当だが、戻り値サニタイズが弱い。
- **test 命名** — `test_*` 関数は意図が読める短い名前 (`test_search_empty`, `test_axes`, `_reset_singletons` fixture など)。コメント・docstring も最小限で適切。
- **Streamlit の private access** — `streamlit_app.py:91` で `engine._store.count()`。`SearchEngine.count()` proxy を生やすか、UI 側で `store` を直接受け取る方が良い。
- **共通フォーマッタが 3 か所**: `mcp_server/formatters.py` (markdown/json)、`streamlit_app.py` (st.markdown 直接)、`frontend/src/components/ResultCard.tsx` — 表現コンテキストが違うので DRY 違反というほどではないが、`body_snippet` のフォーマット (200 char) のような数値が複数ファイルに散らばっているのは把握しておきたい。
- **Dockerfile.streamlit が残置されている** (ADR-014 で意図通り) — README/architecture.md に「レガシー / 後退路」と明記済み ✓

### E. v0.1〜v0.4 累積で気になるアーキ判断

- **4 form factor 並存 (Streamlit + FastAPI + Next.js + MCP)** — ADR-014 で正当化済み。FastAPI と Next.js は独立 service なので Docker 上は分かれている。Streamlit は別 image (`Dockerfile.streamlit`) で `docker-compose.yml` にも含まれない (ロード時に streamlit_app 単独実行を想定)。妥当な分離。
- **`mcp_server/` と `backend/` の責務分離** — `mcp_server/server.py` は薄い wrapper で、`backend.src.{search, rag, integrity, loader, ingester}` を import するのみ。逆方向 import なし ✓。`docs/mcp-server.md` でも「コード重複ゼロ」と謳っており実態と一致。
- **`Dockerfile.backend` が `mcp_server/` を COPY していない** — backend container は MCP を起動しないので OK。MCP は別実行系として `pip install -e .` でユーザー環境にインストールする想定 (`pyproject.toml [project.scripts] axis-knowledge-rag-mcp`)。
- **`examples/raw_memos/` と `examples/knowledge/` の役割分担** — `docs/ingester.md` で明文化済 ✓
- **既知の broken ref `doc_005 → doc_999`** — CHANGELOG Day 6 で「Week 2 integrity demo 用に意図的に残置」と明記。`integrity` check のデモソースとして機能し、設計判断としては OK だが、`axis_check_integrity` を本番でデフォルト走らせると "broken ref が常に 1 件出る" 状態が定常化していることに注意 (`integrity.fail_on_broken: false` で運用継続可能、現 config で false なので OK)。

## 5. ポジティブ評価 (What looks good)

採用面接でアピールできる強み:

1. **「フレームワーク非依存」を ADR-001 で明示** — LangChain/LlamaIndex を意識的に避け、`embedder` / `vector_store` / `search` / `rag` を 6000 行未満で書き切っている。設計理解の深さが伝わる。
2. **DUMMY モードを一級市民として導入** — `Embedder` / `RAGPipeline` / `Ingester` の 3 か所で同じパターン (`_use_dummy` + factory ガード) を採用、CI が API キーゼロで全 pipeline を流せる。ADR-005 で justification あり。
3. **`axis_*` と `axis_*_norm` 二重保存設計** — Japanese 表記ゆれ (NFKC/カナ/lowercase) を index/query 両側で揃えつつ、UI 表示用の生値を保つ判断 (ADR-006/007)。実装も `_flatten_axes_with_norm` 等で読みやすい。
4. **MCP `ToolAnnotations` を正しく設定** — `readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint` を全 6 tool で適切に分けている。`axis_answer` と `axis_ingest_memo` のみ `openWorldHint=True` で外部 API 呼び出しを明示 = MCP 仕様準拠の模範例。
5. **lazy singleton + 明示 reset fixture** — `mcp_server/server.py` の `_engine` / `_rag` / `_axes_cfg` は最初の tool 呼出しまで遅延、`tests/test_server.py` の `_reset_singletons` autouse fixture で state leakage を遮断。stdio long-lived server 向けの典型パターンを正しく実装。
6. **Pydantic v2 schema が strict** — `extra="forbid"`, `str_strip_whitespace=True`, `validate_assignment=True`、id `pattern=r"^doc_\d{3,}$"`、`refs` の `field_validator` で prefix チェック。LLM 出力の構造検証が堅牢。
7. **CHANGELOG が「spec_NNN とソースの commit ハッシュ」レベルで詳細** — 採用者が「いつ何が入ったか」を辿れる。Day 11 marker / Day 18 typewriter 等、技術的な judgement が記述されている。
8. **CI が現実的なしきい値** — `--cov-fail-under=70`, ruff `select=[E F I W UP B SIM]`, py3.11/3.12 matrix。過剰な厳格設定で誰も触れない状態にしておらず、保守性が高い。

## 6. 推奨される次の spec

中島さんが優先度で判断するための候補。**全て optional** で、現状でも B 判定で OK だが、A に持ち上げたい場合の候補。

- **spec_025 候補 (低工数・高インパクト)**: ドキュメント整合性パス
  - README badge 0.3.0 → 0.4.0
  - api.py `version="..."` → 動的に `_pkg_version()` 由来に
  - pyproject.toml `version = "0.4.0"` (もしくは tag → release で自動更新)
  - docs/mcp-server.md と README の「5 tools」→「6 tools」
  - docs/api-reference.md の axes サンプル値を config.yml と一致
  - `examples/screenshots/demo.gif` の生成 or README の `<!-- DEMO_GIF_HERE -->` プレースホルダ削除
  - git tag 不存在の調査・修復
- **spec_026 候補 (中工数)**: Ingester 堅牢化
  - `_next_doc_id` と `_existing_doc_ids` を 1 回スキャンに統合
  - Claude の invalid JSON 時に N 回リトライ + 最後の試行で structured 出力モードへフォールバック
  - `axis_list_documents` を ChromaDB の `get()` ベースに置き換え (200 件上限解消)
- **spec_027 候補 (中工数)**: MCP error sanitization
  - `mcp_server/server.py` の 6 か所の except を generic 文言 + correlation_id へ変更、詳細は logger.exception のみ
- **spec_028 候補 (オプション)**: ベクトル距離関数の明示
  - ChromaDB collection 作成時に `metadata={"hnsw:space": "cosine"}` を渡し、`_to_results` の score 計算と一致させる
  - rebuild index が必要なため migration note 必須

## 7. Open questions

中島さんに判断を仰ぎたいもの:

- **Q1**: spec 本文では「v0.1.0 / v0.2.0 / v0.3.0 / v0.4.0 の 4 タグ + 4 GitHub Release 公開済み」とあるが、`git tag -l` が空。タグはローカル削除済みでリモートのみ存在する状態か (`git ls-remote --tags origin` で確認可能だが、レビューは read-only 制約のため未実行)。あるいは GitHub 側で release を直接作成し、タグはまだ push していない状態か。リリースが本当に公開済みなら、タグ・バッジ・version 文字列の食い違いはより目立つので確認したい。
- **Q2**: CLAUDE_MODEL のデフォルト `claude-3-5-sonnet-20241022` は意図的か (env-var override 前提)、それともポートフォリオ用に最新モデル (例: `claude-sonnet-4-5`) に更新する余地があるか。
- **Q3**: prompt injection (`raw_text` / `question` の直挿入) に対して、ADR-016 を追加して "信頼境界外の入力を受け取らない想定" を明記する方針で良いか。それとも次の spec で sanitization layer (例えば fence エスケープ) を入れる方針にするか。
- **Q4**: `axis_list_documents` の 200 件上限はそのまま残し、Open Issue として README/docs に書く方針で良いか。それとも次の spec で `collection.get()` ベースに書き直す予定か。
- **Q5**: `examples/screenshots/demo.gif` を最終的に撮影するか、それとも README から img 行を削除して「demo は YouTube/Loom リンクで提供」等の別形式に切り替えるか。

## 8. 動作確認手順 (ユーザー)

このタスクは read-only review なので、result_024.md の内容を中島さん側で確認するのみ:

```
1. /home/nakashima/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_024.md を開く
2. § 3 の「主要発見事項」テーブルを読み、Critical/Warning が無いか確認
3. § 6 の「推奨される次の spec」を、優先度で取捨選択
4. § 7 の Open questions に回答 → Cowork (中島) で次の dispatch を組む
```

期待結果:

- ファイル変更 0 (`git status` で `_ai_workspace/bridge/outbox/result_024.md` のみ untracked or modified)
- 全体評価 B が記録されている
- Severity 別に 10 件の主要発見事項が表で読める

## 9. 次の提案

- **spec_025 (推奨)**: §6 の Doc 整合性パス — 低リスク・高インパクトなので、A 判定昇格を目指すなら最初にこれ
- **spec_026** (中島さんの可用性次第): Ingester 堅牢化
- **spec_027** (security baseline 強化): MCP error sanitization
