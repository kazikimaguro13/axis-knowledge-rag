# spec_024: 総合コードレビュー (v0.1.0 〜 v0.4.0 / main 全体)

- **Author**: Cowork (中島)
- **Created**: 2026-05-13
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Type**: code-review (no source modifications)

## 1. 目的

3 週間プラン (spec_001〜spec_021) + ボーナス 2 件 (spec_022 MCP server / spec_023 AI ingester) を経て、main は **v0.4.0** に到達。v0.1.0 / v0.2.0 / v0.3.0 / v0.4.0 の 4 タグ + 4 GitHub Release 公開済み。

ここで **第三者視点 (CC) による総合レビュー** を実施し、就職活動・ポートフォリオ公開状態として「現状のコード品質」「最終的な改善余地」を独立評価する。

**重要: 修正禁止。** 発見した問題は全て result_024.md の Open questions に書き出し、必要なら別 spec として dispatch する。

```
[現状]
- main HEAD: 6363bdd merge: spec_023 (bonus) — AI memo→YAML ingester
- 24 spec ぶんの commit が main に積まれている (~147 commits)
- GitHub Actions CI: 緑 (test 3.11/3.12 + ruff + Docker Build)
- pytest: 136 tests, coverage 76%+
- 全 docs 中立化済み (就活/採用関連表現を除去)

[このレビューでやること]
- main ブランチ全体を読んで品質を評価
- security / performance / correctness / maintainability の 4 軸
- 全体評価 (A: 引き渡し可能 / B: 要改善 / C: 重大な問題あり) を 1 つ出す
- 主要発見事項を最大 10 件、severity 付きで列挙
- 修正は絶対にしない (read-only)
```

## 2. 制約

### 触ってよいファイル

- なし。**完全 read-only**。
- `_ai_workspace/bridge/outbox/result_024.md` のみ書き込み可。

### 触ってはいけないもの

- ソースコード全部 (`backend/` `frontend/` `mcp_server/` `scripts/` `streamlit_app.py`)
- ドキュメント全部 (`README.md` `docs/`)
- 設定ファイル (`pyproject.toml` `package.json` `Dockerfile*` `.github/workflows/*`)
- git 操作 (commit / push / branch / tag いずれも禁止)
- `_ai_workspace/bridge/inbox/` (spec 自体への加筆禁止)

修正が必要と判断された箇所は、すべて result_024.md に提案として書く。実装は中島さんが別 spec で dispatch する。

## 3. やってほしいこと

### 3-1. リポジトリ全体把握

```bash
cd ~/projects/axis-knowledge-rag
git log --oneline | wc -l  # 全 commit 数
git log --merges --pretty=format:'%h %s' | head -20  # マイルストーン把握
ls -la backend/src/ mcp_server/ frontend/src/ scripts/
wc -l backend/src/*.py mcp_server/*.py scripts/*.py | tail -3
```

タグ一覧:

```bash
git tag -l
```

期待タグ: `v0.1.0 / v0.2.0 / v0.3.0 / v0.4.0`

### 3-2. 4 軸のレビュー

#### A. Security (セキュリティ)
- **API キー / シークレットの漏洩**: `grep -r "sk-" "AIza" "github_pat_"` で全リポジトリスキャン
- **ハードコードされた認証情報**: 設定ファイル、テスト、ドキュメント
- **Input validation**: FastAPI endpoints と CLI 引数の入力検証
- **Path traversal**: `loader.py` の Path 受け取り、`marker.py` の file 操作
- **Prompt injection 耐性**: `rag.py` `ingester.py` で、ユーザー入力がそのまま LLM プロンプトに混入していないか
- **CORS 設定**: `backend/src/api.py` の origin allow list が適切か
- **PAT scope の最小権限原則**: `.github/workflows/*.yml` で要求している権限

#### B. Performance (パフォーマンス)
- **N+1 / 過剰 I/O**: `load_directory` を search loop 内で呼んでないか、`ingester.py` で毎回 knowledge_dir を全 scan する箇所の影響
- **メモリ使用量**: ChromaDB に全結果を読み込んで Python 側で paginate する `axis_list_documents` の実装、大規模 KB でメモリ膨張する可能性
- **アルゴリズム複雑度**: `integrity.py` の cycle detection (DFS、O(V+E))、`normalizer.py` の文字単位ループ
- **キャッシング**: Streamlit / FastAPI / MCP server で SearchEngine / RAGPipeline が lazy singleton にされているか
- **不要な依存ロード時間**: import が重いか (anthropic, chromadb 等)、起動時間への影響

#### C. Correctness (正しさ)
- **エッジケース**: 空 knowledge_dir、broken refs だけの dir、巨大 body (10万字)、UTF-8 非対応 (絵文字)
- **エラーハンドリング**: `Embedder` / `RAGPipeline` / `Ingester` の DUMMY 判定が一貫しているか
- **並行性**: FastAPI の lifespan で初期化したシングルトンが thread-safe か (uvicorn workers > 1 の前提で)
- **type hints**: 全モジュールで type annotation 揃っているか、Pydantic V2 の `model_config` 使用一貫性
- **テスト網羅性**: `axis_check_integrity` の cycle 検出 / `marker.py` の nested block / `ingester.py` のリトライ
- **frontend の error boundary**: Next.js components で API エラー時の fallback UI

#### D. Maintainability (保守性)
- **ネーミング**: `_make_doc` / `_build_where_norm` 等の private API の命名が読みやすいか
- **DRY 違反**: `format_search_results_md` と Streamlit の result card 表示で formatter 重複してないか
- **dead code**: 使われていない関数 / import が残っていないか
- **ドキュメントとコードの整合性**: `docs/api-reference.md` の HTTP endpoint シグネチャと実装が一致しているか
- **ADR と実装の整合性**: `docs/design-decisions.md` の 15 ADR と現実のコードが矛盾していないか
- **test naming**: `test_*.py` の関数名で意図が読めるか

#### E. v0.1〜v0.4 累積で気になるアーキ判断
- Streamlit + FastAPI + Next.js + MCP server の **4 form factor 並存** は管理コスト上 OK か (`Dockerfile.streamlit` 残置の妥当性)
- `mcp_server/` と `backend/` の責務分離は綺麗か、import の方向が一方向になっているか
- `frontend/src/lib/api.ts` の型が `backend/src/schemas.py` (Pydantic) と一致しているか (手動同期、自動生成 OpenAPI client への移行余地)
- `examples/raw_memos/` (spec_023 で追加) と `examples/knowledge/` の役割分担が README で明示されているか

### 3-3. 全体評価 (1 つだけ)

以下のいずれか 1 つ、明確な根拠と共に:

- **A: 引き渡し可能・問題なし** — このまま採用ポートフォリオ / ES に貼って問題ないレベル
- **B: 軽微な改善あり** — Critical 0、Suggestion 多数。リリース後でも対応可能
- **C: リリース前に修正必要** — security or correctness で Critical があり、現状で見せるのは推奨しない

### 3-4. 主要発見事項 (最大 10 件)

severity 別に整理:

| # | File | Line | Issue | Severity | Category |
|---|---|---|---|---|---|
| 1 | ... | ... | ... | 🔴 Critical / 🟡 Warning / 🔵 Info | Security/Perf/Correctness/Maintainability |

10 件を超える場合は重要度上位のみ。10 件未満なら無理に増やさない。

### 3-5. ポジティブ評価 (What looks good)

採用面接でアピールできる強みを 5 個程度。コードと docs 双方から:

- 「LangChain 不使用、自前実装」が ADR-001 で明確に説明されている、等
- pytest-asyncio + auto モードで MCP tool テストがシンプル、等

### 3-6. 結果を `outbox/result_024.md` に書く

`templates/result_template.md` の構造で:

- 1. 要約 (CC の総合評価 1 行 + 主要観察 3-5 文)
- 2. 全体評価 (A/B/C と根拠)
- 3. 主要発見事項テーブル
- 4. 4 軸別の詳細所見
- 5. ポジティブ評価
- 6. 推奨される次の spec (もし Critical / Major があれば、修正用 spec を提案)
- 7. Open questions (中島さん判断が必要なもの)

### 3-7. 修正は絶対にしない

このタスクは **read-only**。気になる点があっても commit / edit せず、すべて result に書き出す。

## 4. 成功条件

- [ ] 4 軸全てに対するレビュー所見が result_024.md に記載されている
- [ ] 全体評価 (A/B/C) が 1 つ明示されている
- [ ] 主要発見事項 0〜10 件が表形式で出ている
- [ ] ポジティブ評価が記載されている
- [ ] ファイル変更 0、commit 0 (read-only 遵守)
- [ ] result_024.md が outbox に書かれている

## 5. 出力先

`~/projects/axis-knowledge-rag/_ai_workspace/bridge/outbox/result_024.md`

## 6. 質問があるとき

レビュー中に「これは bug なのか意図なのか」「security 上 OK なのか NG なのか」迷ったら Open questions に書く。Cowork が後で中島さんと判断する。

## 7. 補足

### レビューの所要時間

main の commits 約 147 件、コードベース backend + mcp_server + frontend で **約 6000 行 (テスト除く)**。
全部読むと CC 視点で 15〜40 分。優先順位を付けて、main の最終形 (v0.4.0 = 6363bdd) を中心に読む。

### 過去に dispatch で見つかった既知の問題

(中島さんの記憶ベース)

- ChromaDB が Windows で segfault (WSL2 で解決済み、`docs/troubleshooting.md` 候補)
- 過去の `feat/spec_006-docker` ブランチが Travel アカウントで一時汚染 (force-push で復旧、`docs/portfolio-notes.md` も削除済み)
- CI が 3 回 fail → fix のサイクル: (UP035 / test fixture / pytest-asyncio)

これらは既に解消済みなので、レビュー対象には含めない (Open questions で言及するのは OK)。
