# result_041: v0.7 → v0.8 総合コードレビュー

- **spec**: spec_041
- **branch**: review/v0.8-overall
- **date**: 2026-05-14
- **status**: completed
- **type**: code-review (read-only)
- **reviewer**: Claude Code (dev-d)

---

## 1. 要約

v0.8.0 (f3f668e) を spec_036〜040 の 5 spec に渡って 4 軸評価した結果、
**本番コード品質は A 水準を維持** しているが、評価ツールチェーン (spec_038) に
機能不全な EVAL_OVERRIDE_FLAG フック と parent_storage.py の SQLite 999 変数上限
の 2 件の中優先度問題を検出。全体判定は **B** とする。

---

## 2. 全体評価

**判定: B — 軽微な改善あり**

RAG コア (search/citations/graph/session) は型安全・テスト充実・Protocol 化と
いずれも A 水準の設計。問題は 2 件:

1. `run_abtest.py` が `EVAL_OVERRIDE_FLAG` を `os.environ` にセットするが、
   `load_app_config()` はこの変数を一切読まないため A/B テストが常に同一 config
   で走る — 機能として無効化されている。
2. `SqliteParentStorage.get_many()` の IN 句は 1000+ parent_id で SQLite の
   デフォルト bind-variable 上限 (999) を超えて `OperationalError` を引き起こす。

いずれも本番の基本フローには影響しない (①は eval ツール、②は大規模インデックス
時のみ) が、spec_042 として修正を推奨する。

---

## 3. spec 別 4 軸所見

### spec_040 — GraphRAG + 3D Visualization

| 軸 | 所見 |
|---|---|
| **Security** | `nodeLabel` に `n.name` (doc title) を直接埋め込んでいるが、react-force-graph-3d は canvas tooltip レンダリングのため HTML injection は非適用。XSS リスクなし。`/api/graph/{doc_id}/neighbors` の doc_id は networkx のメモリグラフへのキーとして使われるのみで SQL injection/path traversal リスクはない。 |
| **Performance** | `build_default_graph()` は async lifespan 内でフルに同期実行。docs が 1000+ のとき event loop がブロックされる可能性あり (起動時のみ、低頻度のため許容範囲)。`get_all_edges()` は全エッジを Python リストで返すため、エッジ数 E >> 10k の場合に重くなる (現状の知識 DB サイズでは問題なし)。`_fetch_doc_as_result()` は隣接ノードごとに Chroma `collection.get(ids=[…])` を 1 呼び出しずつ行っており、seeds×neighbors 最大 50 呼び出しの N+1 パターン。パフォーマンス上は許容範囲だが、バッチ取得への改善余地あり。`cooldownTicks=150` の設定は 500 nodes 以下の標準的なグラフで WebGL アニメーションが過剰収束を避けつつ応答するための妥当値。 |
| **Correctness** | `neighbors_within_hop()` の BFS early-stop は `max_neighbors` 到達時に即 `return results` するため、中断時の順序は networkx の `successors()`/`predecessors()` の返却順 (= 挿入順) に依存。deterministic だが呼び出し順依存は仕様として文書化すべき。`find_path()` の `max_length=5` カットオフは仕様通りで許容。score 0.7× decay で direct hit が常に graph 展開より高くなる保証は「同じ seed doc からの展開」に対してのみ成立 (異なる seed からの直接結果が 0.7× より低い場合は graph 展開結果が上位に来ることがある) — 設計上許容。`useMemo` の依存配列は `data.nodes` と `data.edges` を独立して参照しており、親 `data` が新 object になると通常は両配列も新参照になるため実害なし。 |
| **Maintainability** | `GraphConfig.knowledge_dir` default が `"./examples/knowledge"` で hard-coded。本番 config.yml の `graph.knowledge_dir` で上書き可能であり ADR-024 に記載あり。`Knowledge3DGraph.tsx` の `any` 型は eslint-disable コメントで明示的に局所化されており、型汚染は最小限。`GraphFilterBar` のカテゴリ/レベル値がハードコード — 将来 config 化が必要になった際の変更点として Open Questions に追記推奨。 |

---

### spec_036 — Session Persistence (Memory / SQLite / Redis)

| 軸 | 所見 |
|---|---|
| **Security** | `SqliteStore` の `db_path` は `os.path.expanduser()` 経由で `~/.axis_chat.db` に展開。`config.yml` で任意パスを指定可能だが、config ファイルはオペレーター管理のため path traversal は許容範囲内。`RedisStore` の `url` (認証情報を含む可能性) はログに出力されない — `make_conversation_store()` の warning ログは `e` のみ出力するが Redis の例外メッセージに url が含まれる場合あり (低リスク)。 |
| **Performance** | `SqliteStore._evict_expired_locked()` は `get_or_create()` ごとに呼ばれ、`sessions` テーブルを `last_access < cutoff` でフルスキャン (last_access に index なし)。max_sessions が大きい場合は O(N) スキャンが毎リクエスト発生。チャット用途の session 数は bounded なため現実的な問題は小さいが、index 追加で完全に解消できる。`RedisStore.__len__()` は `scan_iter` で全 meta キーを walk するため Redis キー数に比例して遅い。現在 docstring に注記なし — 追記推奨 (low)。 |
| **Correctness** | `@runtime_checkable ConversationStore` Protocol で `isinstance(store, ConversationStore)` チェックが正常動作。`SqliteStore.close()` 後の `get_or_create()` は `_require_conn()` で `RuntimeError` を raise — 明確な仕様。`make_conversation_store()` の fallback は WARNING ログを出力してから MemoryStore に降格するため、オペレーターが気付ける設計。ログレベルは妥当。 |
| **Maintainability** | Memory/SQLite/Redis の 3 backend を `parametrize` でカバーするテスト構成は新 backend 追加時のベストプラクティス。`__len__` を Protocol に含めることで `len(store)` が全 backend で一貫した意味 (active session 数) を持つ — 設計 OK。 |

---

### spec_037 — Parent JSON → SQLite 自動移行

| 軸 | 所見 |
|---|---|
| **Security** | `SqliteParentStorage` の `db_path` は Chroma directory 直下 (`data/chroma/parents.db`) でユーザー制御外。OK。 |
| **Performance** | **[MID] `get_many()` の IN 句が非チャンク実装** — `",".join("?" * len(parent_ids))` で parent_ids が 999 を超えると SQLite デフォルト bind-variable 上限 (`SQLITE_LIMIT_VARIABLE_NUMBER = 999`) を超えて `OperationalError: too many SQL variables` が発生する。大規模ドキュメントのインデックス時に再現可能。`upsert_many()` は `executemany` 使用 — OK。 |
| **Correctness** | 自動 migrate は `json_path.exists() and not sqlite_path.exists()` の条件で一度だけ実行。原本の `parents.json` は削除されず保持 — 冪等性あり。`make_parent_storage(storage=…)` 引数でテスト時に override 可能。`JsonParentStorage` の backward-compat path は CHANGELOG に「v0.9 で削除予定」と記載あり。ADR-023 への明示的な EOL 条件追記を推奨 (low)。 |
| **Maintainability** | Protocol + factory 設計で backend swap が `config.yml` 1 行変更で完結。`list_all()` が Protocol 外メソッドとして明示されており、Protocol 純化との境界が明確。 |

---

### spec_038 — RAGAS blocking + A/B evaluation

| 軸 | 所見 |
|---|---|
| **Security** | GitHub Actions workflow で `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` を secrets として扱っていることを CHANGELOG / ADR-019 で確認。OK。 |
| **Performance** | 問題なし。RAGAS 実行は API bound なため Python レイヤーのボトルネックは無視できる。 |
| **Correctness** | **[HIGH] `EVAL_OVERRIDE_FLAG` フックが機能していない** — `run_abtest.py` は `os.environ["EVAL_OVERRIDE_FLAG"] = f"{args.flag}=true/false"` をセットしてから `_build_pipeline()` を呼ぶが、`load_app_config()` は `os.environ` を一切参照しない。つまり A run と B run は同一 config で走り、A/B テストとして無意味。`paired_t_test` の direction 判定: `diff == 0` かつ `p < 0.05` のケースは理論的にありえないため実害なし。`--block-on-regression` は `return 1` → `raise SystemExit(main())` で正しく exit code 1 を返す。length mismatch check は scipy import より前に配置 — scipy 不在環境でも ValueError が出ることを確認済み。 |
| **Maintainability** | `scipy` の optional import (try/except ImportError → `return None`) は正しく実装。`evaluation/runs/` の git 蓄積は retention policy 未定義。`.gitignore` に `evaluation/runs/*.json` を追加推奨 (low)。 |

---

### spec_039 — Code-fence aware citation parser

| 軸 | 所見 |
|---|---|
| **Security** | 問題なし。 |
| **Performance** | `_is_in_skip_range()` は O(code_block_count) のリニアサーチ。通常応答で code block が数個程度なら無視できるコスト。 |
| **Correctness** | backend の `re.DOTALL` と frontend の `[\s\S]` は意味的に等価。ネストフェンス (4連バックティック) は未対応だが Known limitation として ADR-020 に記載あり。インライン code の `[^`\n]+` パターンで改行を含むコードは inline span として認識されない — 仕様通り (inline code は単行のみ)。backend / frontend regex の対称性: `\s*` (空白許容) の扱いが両者で同一 (`\s*,\s*`) — 対称を確認。 |
| **Maintainability** | backend と frontend でソースを共有していないため将来の修正で非対称が生じるリスクは ADR-020 で Known trade-off として明示されている。現時点では対称が保たれている。 |

---

## 4. 新たに見つけた問題

### [HIGH] #1 — EVAL_OVERRIDE_FLAG が load_app_config() に到達しない

- **file**: `evaluation/run_abtest.py:45,51` / `backend/src/config.py:171-250`
- **内容**: `run_abtest.py` は `os.environ["EVAL_OVERRIDE_FLAG"]` をセットするが、
  `_build_pipeline()` → `load_app_config()` はファイルパス (`config.yml`) のみを読み、
  環境変数を参照しない。A と B が同一 config で実行されるため A/B テストが機能しない。
- **修正案**: `load_app_config()` が `EVAL_OVERRIDE_FLAG` を読み込んで指定 dotted-key を
  上書きするか、`_build_pipeline(override_flag=…)` を明示引数で受け取る設計に変更。

### [MID] #2 — SqliteParentStorage.get_many() の SQLite 999 bind-variable 上限

- **file**: `backend/src/parent_storage.py:70-80`
- **内容**: `",".join("?" * len(parent_ids))` で生成した IN 句は `parent_ids` が 999 を超えると
  `sqlite3.OperationalError: too many SQL variables` を引き起こす。
  大規模コーパス (999+ docs) の `build_index` 時に再現可能。
- **修正案**: `parent_ids` を 999 件ずつチャンクして複数クエリ発行 + 結果をマージ。

### [MID] #3 — SqliteStore: sessions テーブルに last_access index なし

- **file**: `backend/src/conversation.py:192-207` (SCHEMA 定義)
- **内容**: `_evict_expired_locked()` は `get_or_create()` ごとに
  `DELETE WHERE last_access < ?` を実行するが `last_access` に index がない。
  max_sessions が大きい (デフォルト 1000) 高頻度チャットでは O(N) スキャンが毎リクエスト発生。
- **修正案**: SCHEMA に `CREATE INDEX IF NOT EXISTS idx_sessions_last_access ON sessions(last_access)` を追加。

### [LOW] #4 — RedisStore.__len__() に O(K) コストの注記なし

- **file**: `backend/src/conversation.py:506-510`
- **内容**: `scan_iter("axis:session:*:meta")` でキー全数を walk するため Redis のキー数 K に比例する。
  大規模 multi-host 環境でサービスメトリクス取得時に重い。docstring への注記が必要。
- **修正案**: `__len__` の docstring に "O(K) scan over all Redis keys; avoid on hot paths" を追記。

### [LOW] #5 — build_default_graph() が async lifespan をブロック

- **file**: `backend/src/api.py:75` / `backend/src/graph.py:232-255`
- **内容**: `build_default_graph()` は同期関数で、lifespan の async context 内で直接呼ばれる。
  知識ファイルが 1000+ の場合、起動時に event loop が数秒ブロックされる可能性。
- **修正案**: `asyncio.get_event_loop().run_in_executor(None, build_default_graph, ...)` または
  `anyio.to_thread.run_sync()` でスレッドオフロード。

---

## 5. ポジティブ評価

### ✅ #1 — ConversationStore Protocol 化 (spec_036)

`@runtime_checkable Protocol` + factory + fallback の三層構造が完璧に機能している。
`isinstance` チェック、`close()` の graceful shutdown、fallback warning の一貫性は
v0.7 の単一クラスから大きな設計的前進。新 backend を追加する際のボイラープレートが最小。

### ✅ #2 — Parents JSON → SQLite 自動 migrate (spec_037)

`not sqlite_path.exists() and json_path.exists()` の一度限り条件で冪等な自動移行を実現。
原本 JSON を保持することでロールバックが可能。`executemany` によるバルク insert でパフォーマンス改善。
18× 速度向上という具体的な数値が CHANGELOG に記録されている点も優秀。

### ✅ #3 — RAGAS blocking の設計 (spec_038)

`--block-on-regression` のデフォル off + `--regression-threshold` の parameterize は
CI の段階的導入として理想的。`return 1` + `raise SystemExit(main())` による正確な exit code、
`scipy` optional 化のパターン (lazy import + `return None`) は手堅い実装。

### ✅ #4 — Code-fence skip の backend/frontend 対称性 (spec_039)

Python と TypeScript で regex を独立実装しているにも関わらず、`_build_skip_ranges()` ↔
`buildSkipRanges()` のロジックが完全に対称。`re.DOTALL` ↔ `[\s\S]` の等価変換、
`lastIndex = 0` リセットによる RegExp stateful trap の回避と、細部まで整合が取れている。

### ✅ #5 — 3D グラフの SSR 無効化と cooldown 設定 (spec_040)

`dynamic(import(…), { ssr: false })` で WebGL の `window is undefined` 問題を正確に回避。
`cooldownTicks={150}` の選択も 500 nodes 以下の標準グラフで適切な収束速度を提供する。
broken refs / self-loop のスキップを warning log 付きで行い、1 件の bad reference が
サーバー起動を壊さない堅牢性も特筆すべき点。

---

## 6. 推奨される次の spec

### spec_042 候補 (修正 spec)

以下の 3 点をまとめて修正することを推奨:

1. **EVAL_OVERRIDE_FLAG を load_app_config() に wire する** (HIGH — A/B テスト機能不全の根本修正)
2. **`get_many()` の 999 チャンキング** (MID — 大規模インデックス時の OperationalError 対策)
3. **`sessions` テーブルへの `last_access` index 追加** (MID — 高頻度チャット時の O(N) 回避)

副作用として `run_abtest.py` の integration test (config フラグが実際に反映されるかの end-to-end test) も追加すべき。

---

## 7. Open Questions

| # | 質問 | 優先度 |
|---|---|---|
| OQ-1 | `GraphFilterBar` のカテゴリ/レベル値 (`["技術記事","メモ","議事録","ToDo"]`) は hard-coded。axes config から動的取得するべきか? | low |
| OQ-2 | `JsonParentStorage` の EOL 条件を ADR-023 に明示すべき (現在 CHANGELOG のみ) | low |
| OQ-3 | `evaluation/runs/` JSON の git retention policy — `.gitignore` 追加 or `evaluation/runs/` をサブディレクトリで管理するか | low |
| OQ-4 | `react-force-graph-3d` の TS 型定義が不完全なため `any` を局所使用中。@types/react-force-graph-3d の出現を監視して型化を検討 | low |
| OQ-5 | Redis Cluster サポートは v0.9 / spec_044 で追跡中 (conversation.py docstring 参照) — spec list に登録済みか確認 | low |

---

## 8. v0.6 (spec_028 A 判定時) からの進化総評

spec_028 の A 判定時 (v0.5 系) は「引き渡し可能」だったが、機能は検索 + 基本 RAG に留まっていた。
v0.8.0 では **10 機能** (Parent Doc / Conversational / RAGAS / Citation / Time Decay + GraphRAG / Session Persist / Parent SQLite / RAGAS blocking / Code-fence) を追加した。

特に以下の品質面での前進が顕著:

- **Protocol 化**: ConversationStore / ParentStorage の 2 系統が typing.Protocol + factory に統一され、テストと本番で backend を差し替え可能な設計に進化。
- **統計的評価**: RAGAS + scipy paired t-test による A/B 評価基盤の確立。機能不全 (OQ なし、HIGH 問題あり) だが設計の方向性は正しい。
- **XSS/injection 防御**: spec_027 (error sanitization) + spec_039 (code-fence aware citation) + spec_036 (path expanduser) で複数の injection 経路を潰している。
- **GraphRAG**: networkx を薄くラップして BFS/最短経路/degree を提供。broken ref を非致命的に処理する堅牢設計は高く評価。

v0.6→v0.8 の進化量に対して問題件数 (high 1 / mid 2 / low 2) は少なく、
**スプリント速度と品質のバランスは良好**。spec_042 で残課題を解消すれば A 判定への昇格が見込める。

---

*レビュー実施日: 2026-05-14 / reviewer: Claude Code dev-d / HEAD: f3f668e*
