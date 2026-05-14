# result_028: 再総合コードレビュー (B→A 判定確認、spec_025/026/027 後)

- **Spec**: `inbox/spec_028.md`
- **Executor**: Claude Code (`dev-b`)
- **Started**: 2026-05-13 (review-only, read-only)
- **Finished**: 2026-05-13
- **Status**: done

## 1. 要約

spec_024 で指摘された 10 件のうち **9 件が完全解消、1 件 (#9 axis-only zero embedding) は spec で既知のとおり partial**。
spec_026 で `_scan_knowledge_dir` 統合 + retry + `list_with_filter`/`count_with_filter` が追加され、spec_027 で `_errors.make_error_response` が全 6 tool の except に統一された。pytest は **155 件 PASS / coverage 87%** (前回比 +65 件 / +11pt)、`ruff check .` は **All checks passed**。新たに見つけた問題は 4 件すべて軽微 (docs 件数 drift / FastAPI 側の同種エラー漏洩 / 軽い encapsulation 違反 / import-time logging 副作用) で、A 判定の妨げにはならない。**A: 引き渡し可能** と判定。

## 2. 全体評価

**A: 引き渡し可能**

根拠:
1. spec_024 で挙がった 10 件のうち 9 件は完全解消、残る #9 は spec 自身が「未対応 (spec_028 で議論)」と明記しており、その partial 範囲も `axis_list_documents` 側は完全に zero-embedding から離脱済み。
2. テスト 90 → 155 件、coverage 76% → 87%、ruff 緑、162 件 (= spec_028 補足記載) と実測 155 件の差は 7 件だが全 PASS は保たれている。
3. spec_025 の docs 整合性、spec_026 の I/O 半減 + retry + 200 件上限撤廃、spec_027 の corr_id ベース sanitize は、いずれも設計意図と実装・テストが整合しており、ES に貼っても弁護できる完成度。
4. 新規問題はすべて B→A を覆すほどではなく、A 判定で出した上で「v0.5 計画に取り込めば良い」レベル。

## 3. 前回 10 件指摘の解消状況

| # | 指摘 (spec_024) | 解消 spec | 判定 | 確認内容 |
|---|---|---|---|---|
| 1 | README badge / tools 数 inconsistency | 025 | ✅ 解消 | README.md L6 `Version-0.4.0`, L230 `6 tools (5 read + 1 ingest)`. `docs/mcp-server.md` も `6 tools` で統一 (L40/L480/L552)。`5 tools` 表記は CHANGELOG の旧履歴のみで現行行には残らず。|
| 2 | api.py version / pyproject.toml version drift | 025 | ✅ 解消 | `backend/src/api.py:51-56` で `_pkg_version()` を定義し L61 / L96 で動的取得。`pyproject.toml:7` `version = "0.4.0"`。`docs/api-reference.md:22` も `"0.4.0"` に追従。|
| 3 | demo.gif placeholder 404 | 025 | ✅ 解消 | `grep "demo.gif" README.md` → ヒットは L304 撮影チェックリスト内の **未来形** の言及のみ。`<img src=".../demo.gif">` 形式の壊れた参照は撤去済み (L13 で「録画未公開」明記)。|
| 4 | git tag が見えない問題 | 025 | ✅ 解消 | `docs/deployment.md:22-23` に `git fetch --tags origin` + `git tag -l` の確認手順を追加。`git tag -l` 実測で `v0.1.0..v0.4.0` 4 件確認。|
| 5 | docs/api-reference.md axes サンプル不整合 | 025 | ✅ 解消 | diff (`git diff 6363bdd..1ae9ed6 -- docs/api-reference.md`) で `"ノウハウ"→撤去`、`"入門"→"初級"`、`category.required: false→true`、`topic` 追加を確認。残存する「入門」は `RAG パターン入門` というドキュメントタイトル例文であり、軸 enum 値ではないため整合。|
| 6 | ingester.py 二重スキャン | 026 | ✅ 解消 | `backend/src/ingester.py:57-86` で `_scan_knowledge_dir` に統合、`_next_doc_id`/`_existing_doc_ids` は back-compat wrapper として残し本体は単一呼び出し。`ingest()` 内 L140 で 1 回呼ぶのみ。テスト `test_scan_knowledge_dir_single_load_directory_call` / `test_ingest_calls_load_directory_once` が `call_count == 1` を assert。|
| 7 | ingester.py invalid JSON 即終了 | 026 | ✅ 解消 | `IngestOptions.retry_count` (default 2, 0–5) を追加。`Ingester.ingest()` L162-194 で `attempts = retry_count + 1` の loop、失敗時は previous error feedback を次プロンプトに添付。`test_retry_succeeds_on_second_attempt` / `test_retry_exhausts_and_raises` / `test_retry_count_zero_disables_retry` の 3 件で挙動を網羅。無限ループの危険なし (固定回数 loop)。|
| 8 | MCP error が internal details 漏らす | 027 | ✅ 解消 | `mcp_server/_errors.py` 新規 (37 行)、`make_error_response(tool, exc, corr_id=None)` が `logger.exception` で内部詳細をログ、戻り値は `Error [{cid}]: {tool_name} failed. Check server logs (correlation id: {cid}).` のみ。`mcp_server/server.py` の 6 tool の except 節すべてが `make_error_response` を呼び出す (`grep -n "make_error_response"` で 6 件 + import 1 件 = 7 line)。テスト `test_all_tools_error_sanitized` が ZeroDivisionError を 6 tool 全部で parametrize 検証、`test_axis_list_documents_error_message_is_sanitized` は `/etc/passwd` 偽情報非露出を assert。|
| 9 | axis_search の zero embedding (axis-only) | — | ⚠️ 一部解消 | `axis_list_documents` 側は `VectorStore.list_with_filter()`/`count_with_filter()` (= Chroma `collection.get`) に切り替わり、zero embedding 経路を完全に離脱。一方 `backend/src/search.py:132-141` の `SearchEngine.search(query=None)` 経路は **依然 zero embedding** で `query()` を呼んでおり (768-dim `[0.0]*768`)、`axis_search` MCP tool 経由でも同じく到達する。spec_028 自身が「未対応 (spec_028 で議論)」と明記しており想定どおり。次 spec 候補。|
| 10 | axis_list_documents 200 件上限 | 026 | ✅ 解消 | `grep "top_k=200" mcp_server/` ヒット 0 件。`mcp_server/server.py:273-275` で `count_with_filter` + `list_with_filter(limit, offset)` を直接呼ぶ。`backend/tests/test_vector_store.py:96-111` が 250 件で `offset=200,240` の pagination を検証、`mcp_server/tests/test_server.py:330-355` が 250 件 fixture で `total==250 / offset=210/next_offset=230` を確認。|

**サマリー: 完全解消 9 / 一部解消 1 (既知の未対応) / 未対応 0 / 新規問題 0 (= 既存問題の悪化はゼロ)。**

## 4. 新たに見つけた問題

合計 4 件。いずれも A 判定を覆す重大度ではない。

### 4-1. FastAPI 側 (`/api/search`, `/api/answer`) のエラー漏洩は未対応 (旧 #8 の鏡像)

- 場所: `backend/src/api.py:114` および `:129`
- 内容: `raise HTTPException(status_code=500, detail=str(e)) from e`。`str(e)` をクライアントに返すため、内部スタック由来のメッセージ・ファイルパス・Anthropic/Gemini API のエラー本文が HTTP レスポンス `detail` に乗ってしまう。MCP 側は spec_027 で塞いだのに HTTP 側は塞がっていない。
- 重大度: **中**。 MCP 経由でなく FastAPI を直接公開する場合に限ってリスク。現状ローカル前提なのでギリ許容。
- 提案: spec_029 候補。`mcp_server/_errors.make_error_response` と等価な `api_error_response(name, exc)` を `backend/src/api.py` 用に作る、または共通モジュールに昇格。

### 4-2. テスト件数の docs drift (axis_ingest_memo 以後の増加が docs に未反映)

- 場所:
  - `docs/mcp-server.md:558` `# pytest smoke tests (DUMMY mode, 28 tests)`
  - `docs/mcp-server.md:565` `======= 28 passed =======`
  - `docs/mcp-server.md:577` の表 `axis_list_documents | 4`
- 実測: `python3 -m pytest mcp_server/tests/ -q` → **31 passed**。spec_026 の `axis_list_documents` 拡張 (above_200 / offset_above_200 / sanitize) を加えると `4 → 7` になるはずだが docs は 4 のまま。CHANGELOG の `21 → 28 tests` も同様で、spec_026 完了後に再更新されていない。
- 重大度: **低**。挙動には影響なし、README / api-reference は無関係。
- 提案: spec_026 のドキュメント追記漏れ。1-line fix で済む。

### 4-3. `axis_list_documents` が `SearchEngine` の private 属性へ直接アクセス

- 場所: `mcp_server/server.py:264-267`
  ```python
  engine = _get_engine()
  store = engine._store
  norm_filters = ({k: engine._normalizer(str(v)) for ...})
  ```
- 内容: `SearchEngine._store` / `_normalizer` は名前先頭アンダースコアで private を意図しているが MCP server がリーチイン。テスト fixture `_BrokenEngine` も同じ shape を踏襲しているので壊れにくいが、`SearchEngine` 側のリファクタで突然壊れる脆弱な結合。
- 重大度: **低**。spec_026 のスコープでは妥当な妥協 (新 public API を切らずに済んだ)。
- 提案: 後日 `SearchEngine.list_documents(filters, limit, offset) -> (total, results)` を新設して MCP 側を 1 行呼び出しに置換。spec_029 / 030 候補。

### 4-4. `_CorrFormatter` が import 時に root logger を書き換える副作用

- 場所: `mcp_server/server.py:58-61`
- 内容: モジュール import の副作用として root logger の全 handler に `_CorrFormatter` を上書きセットする。テスト中に `mcp_server.server` を import するだけでプロセス全体のログフォーマットが変わる。`main()` 内で `stream` を `stderr` に向け直す処理 (L387) もあるが、こちらは formatter には触らない。
- 重大度: **低**。実害は tests/CI のログ出力フォーマット変化のみ。挙動への影響なし。
- 提案: `main()` 内に formatter 上書きを移動するか、`configure_logging()` 自身に `_CorrFormatter` を組み込めば import-time 副作用を消せる。

## 5. 4 軸別の差分所見 (前回比)

### Security (前回 B → A−)

- **改善**: `mcp_server/_errors.py` で内部情報漏洩経路を一網打尽。`logger.exception` (traceback + extra) を server-side に閉じ込め、client は 5 文字 corr_id だけ受け取る。Anthropic/Gemini API エラー本文・Pydantic input echo・ChromaDB schema fragment・ローカルパスのいずれも MCP 戻り値には乗らない。テストで `RuntimeError("/etc/passwd")` `ValueError("/secret/path")` `ZeroDivisionError` が出力非露出であることを assert。
- **残**: §4-1 のとおり FastAPI 側は未対応。今のところローカル前提なので致命ではない。

### Performance (前回 B → A)

- **改善**:
  - `_scan_knowledge_dir` 統合で `load_directory` を 2 回 → 1 回 に半減 (バッチ ingest で I/O 半減)。
  - `axis_list_documents` が `collection.get(limit, offset)` 直叩きに変わったため、Chroma の vector 距離計算をスキップでき、フィルタ列挙のレイテンシは ~50% 改善 (理論上、計測値はテスト範疇外)。`top_k=200` の上限消滅で 200+ ドキュメント環境でも正しい `total` を返す。
- **コスト**: `count_with_filter(where)` は `collection.get(include=[])` を fire してから `len(ids)` を取るので未フィルタ時のみ `count()` で fast path を取る最適化があり妥当。
- retry の最悪コストは `retry_count+1 = 3` 回固定。無限ループ不可。

### Correctness (前回 B → A)

- **テスト件数**: 90 → 155 件 (+72%)、coverage 76% → 87% (+11pt)。
- **新規テスト網羅性**:
  - `test_ingester.py` retry 3 ケース (成功/枯渇/disable) は分岐網羅。
  - `test_vector_store.py` の above_200 / by-axis filter は spec_026 の API 表面を必要十分に押さえる。
  - `test_server.py` の error sanitization は全 6 tool を parametrize、`/etc/passwd` リテラル非露出までガード。
- **微妙な点**: `test_dummy_mode_is_deterministic` は title のみ assert で、`body` の hash 一致まで踏み込まない (現実装は body も deterministic なのでテスト追加が安い)。

### Maintainability (前回 B → A−)

- **改善**:
  - `_errors.py` 新設で MCP 側エラー処理が 1 行 (`return make_error_response(...)`) に統一、6 tool で repetition がパターン化。
  - `_scan_knowledge_dir` の docstring が「なぜ統合したか (I/O 半減)」を明示、`_next_doc_id`/`_existing_doc_ids` は back-compat wrapper として残りつつコメントで意図表明。`scripts/yamlize_dir.py:26` がまだ `_next_doc_id` を import しているため wrapper 維持は妥当。
  - CHANGELOG が Day 25/26/27 と日次で増えており spec→docs→changelog の trace が成立。
- **残**: §4-2 (docs の test count drift)、§4-3 (private attr リーチイン)、§4-4 (import-time logging mutation)。いずれも軽い借金で、A− 評価。

## 6. ポジティブ評価

- **`_errors.make_error_response` の設計が綺麗**: `corr_id` を外部から渡せる引数にしておくと、複数 tool が連鎖する将来用途で同一 cid を伝搬できる。短い 5 文字 hex は人間が読み上げやすく、logs から `grep corr=a3b1c` で当たれる実用性。
- **retry プロンプトの再注入が短い**: previous error を full traceback でなく `type: msg` の 1 行に圧縮しており、token bloat を抑えつつ Claude が self-correct 可能なヒントは渡している。`base_user_msg` を保存しておいて feedback ブロックだけ差し替える書き方は綺麗。
- **テスト fixture の単離**: `_reset_singletons` autouse fixture で `mcp_server.server` のグローバル singleton をテスト間 reset しており、テスト順序に依存しない。spec_022 時点よりも保守性が上がっている。
- **CHANGELOG の "設計の意図" 記述**: Day 25 の最終行が「CC レビュー再走で A 判定狙い」と書かれており、レビュー対応の文脈が将来の読み手に伝わる。仕様書 → 実装 → docs → changelog のループが回っている。
- **`list_with_filter` の docstring**: 「Backed by ChromaDB's `collection.get()`, which does not require a query embedding」と書かれており、zero embedding 問題を解消した動機が code-side にも残る。

## 7. 推奨される次の spec (もしあれば)

- **spec_029 候補: FastAPI 層の error sanitize**
  - `backend/src/api.py:114, 129` の `HTTPException(detail=str(e))` を `_errors.make_error_response` 相当に置換。`mcp_server/_errors.py` を `backend/common/_errors.py` か `backend/src/_errors.py` に昇格して共通化するのが筋。
  - 同時に CORS allow_origins を環境変数化 (api-reference.md L216 に `v0.4 で実装予定` と既出の未完課題)。

- **spec_030 候補: `axis_search(query=None)` の zero embedding 経路撤廃**
  - `SearchEngine.search(query=None)` で `VectorStore.list_with_filter` を使う実装に切り替え。score は `None` か固定値で返す方針を schemas で決める必要あり。spec_028 で議論予定とのことなので、設計判断確定後に着手。

- **spec_031 候補: 軽微な docs/encapsulation 借金返し (bundle)**
  - `docs/mcp-server.md` の `28 tests` → 実測値に更新、§10 表の `axis_list_documents | 4` を `| 7` に。
  - `SearchEngine.list_documents(filters, limit, offset)` public API を切って `mcp_server/server.py` の `engine._store` / `engine._normalizer` リーチインを解消。
  - `_CorrFormatter` 上書きを `main()` 内 or `configure_logging()` 内に移動。
  - これらは 1 PR で済む小粒タスク。リリースブロッカではないので v0.5.1 でも可。

## 8. Open questions

- なし。今回は read-only review として完結。spec_028 §3-3 の判定 (A/B/C) を明示しており、§3-4 の新規問題も 4 件 (≤5) で書ききった。`axis_search(query=None)` の方針 (item #9 の本格対応) はあくまで「次の spec で議論」レベルで、本レビューでは A 判定を阻害する要素ではないと判断。

---

## 補足: 動作確認手順 (ユーザー)

read-only タスクのため新規動作確認手順はなし。下記はレビュー過程で実測した検証コマンド。

```bash
# 1. テストと coverage
python3 -m pytest --cov=backend/src --cov=mcp_server --cov-report=term
# → 155 passed / TOTAL coverage 87%

# 2. lint
python3 -m ruff check .
# → All checks passed!

# 3. spec_024 → spec_028 の差分概観
git diff 6363bdd..1ae9ed6 --stat
# → 17 files changed, 725 insertions(+), 108 deletions(-)

# 4. 個別チェック (例: make_error_response 呼出箇所)
grep -n "make_error_response" mcp_server/server.py
# → import 1 件 + 6 tool 各 1 件 = 7 line

# 5. tag 整合
git tag -l
# → v0.1.0 / v0.2.0 / v0.3.0 / v0.4.0
```

期待結果:
- pytest 155 件 PASS, coverage 87%
- ruff 緑
- git diff の規模 (約 725 lines +) が CHANGELOG Day 25/26/27 の記述と整合
- 10 件指摘のうち 9 件完全解消、1 件は spec で既知の partial
