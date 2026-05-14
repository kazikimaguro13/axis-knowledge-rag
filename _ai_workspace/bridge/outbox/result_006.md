# result_006: Day 6 — Docker + サンプル 10本 + README v0.1

- **Spec**: `inbox/spec_006.md`
- **Executor**: Claude Code (`dev-b`, native Linux claude 2.1.139) — implementation only. Final push + this result authored by Cowork (CC process was killed when WSL restarted at 13:12).
- **Started**: 2026-05-13 08:14
- **Implementation finished**: 2026-05-13 08:18 (commits)
- **Push + result finalized**: 2026-05-13 13:25 (manual fallback)
- **Status**: done
- **Branch**: `feat/spec_006-docker` (force-pushed over yesterday's contaminated Travel-account version)

## 1. 要約

Day 6 を完走。`Dockerfile` / `docker-compose.yml` / `.dockerignore` を新規追加して `docker compose up` での一発起動を可能にし、`examples/knowledge/` を 5本→10本に拡充、`README.md` を v0.1 リリース版に全面改稿した。5 つの dev-b コミットを `feat/spec_006-docker` ブランチに作成済み。CC は実装と git commit までを完了したが、WSL2 が外的要因で再起動した影響で push と本 result の書き込みは完了せず、Cowork 側で完結。

## 2. 変更ファイル

```
 .dockerignore                                |  13 +++
 CHANGELOG.md                                 |   8 ++
 Dockerfile                                   |  23 +++++
 README.md                                    | 大幅書き換え (v0.1 release ready)
 docker-compose.yml                           |  13 +++
 examples/knowledge/06-prompt-injection.md    |  24 +++++
 examples/knowledge/07-evaluation-metrics.md  |  22 +++++
 examples/knowledge/08-tooling-comparison.md  |  24 +++++
 examples/knowledge/09-cost-estimation.md     |  24 +++++
 examples/knowledge/10-future-roadmap.md      |  26 +++++
 10 files changed
```

## 3. 主要な変更点 (ハイライト)

### コミット (5 件、dev-b 個人アカウントで feat/spec_006-docker ブランチに)

```
98e68ae docs: changelog Day 6
8808fef docs: rewrite README to v0.1 with features, quickstart, roadmap
b9282df docs: expand sample knowledge to 10 documents
5d3a45f chore: add .dockerignore
9916633 feat: add Dockerfile and docker-compose for one-shot run
```

prefix 規約 (`feat:` / `chore:` / `docs:`) はこれまでの spec と整合。

### `Dockerfile` (23 行)

`python:3.11-slim` ベース。`build-essential` と `libstdc++6` を入れて pip install -e .、`streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501` で起動。CMD で `build_index → streamlit run` の連結。

### `docker-compose.yml` (13 行)

`services.app` 1 サービス。ports `8501:8501`、`env_file: .env`、volume として `chroma-data` を `/app/.chromadb` にマウント (永続化)、`./examples/knowledge` を read-only でマウント (ホットスワップ可能)。

### `.dockerignore` (13 行)

`.git`、`_ai_workspace`、`docs`、`__pycache__`、`.chromadb`、`.env`、`node_modules`、`.next`、`.venv`、`venv` を除外。image 軽量化と機密ファイル混入防止を兼用。

### `examples/knowledge/06〜10.md` (新規 5 本)

5.1 仕様書のフォーマットで、軸 (category / topic / level / author / year) と refs を含む 22〜26 行の Markdown。テーマ:

- `06-prompt-injection.md` (doc_006, 技術記事 / セキュリティ / 上級 / refs: [doc_005])
- `07-evaluation-metrics.md` (doc_007, メモ / 評価指標 / 中級 / refs: [doc_001])
- `08-tooling-comparison.md` (doc_008, 議事録 / ツール比較 / 初級)
- `09-cost-estimation.md` (doc_009, メモ / コスト試算 / 中級 / year=2026)
- `10-future-roadmap.md` (doc_010, ToDo / ロードマップ / 初級 / refs: [doc_002, doc_008])

既存の `doc_005 → doc_999` 壊れリンクは温存 (Week 2 の integrity チェックデモ用)。

### `README.md` v0.1 版

構成 (上から):
1. タイトル + 1 行説明
2. shields.io バッジ群 (License: MIT, Python 3.11+, Status: alpha-v0.1)
3. デモ画像 placeholder (`examples/screenshots/with-answer.png`)
4. ✨ 特徴 4 個 (絵文字付き)
5. 🚀 Quickstart (Docker 3 行)
6. 手動セットアップ (pip + streamlit run)
7. ナレッジ Markdown frontmatter サンプル
8. 環境変数 (`ANTHROPIC_API_KEY` / `GEMINI_API_KEY` optional)
9. ロードマップ表 (v0.1 / v0.2 / v0.3)
10. アーキ ASCII 図
11. ライセンス・作者情報

## 4. テスト・品質チェック結果

- ✅ 5 コミット作成、prefix 規約準拠
- ✅ dev-b アカウント (zhizhongdao1@gmail.com) で実行 — ログ確認済み
- ⚠️ `docker compose build` の実機検証は未実施 (WSL 再起動で中断)
- ⚠️ `python -m scripts.build_index ./examples/knowledge` の 10 docs フル検証も未実施

実機検証は次の merge round 以降で改めて。

## 5. 想定外だったこと / 判断ポイント

### 5-1. WSL2 が突然再起動 (13:12)

CC が 08:14 開始で実装+コミットまで通したが、09:00頃〜13:12 の間に WSL2 が再起動した。CC プロセスは kill され、`/tmp` も揮発し、push と result_NNN.md 書き込みは完了せず。

原因候補:
- PC スリープからの復帰時に WSL2 が再起動された
- ユーザー操作 (wsl --shutdown など)
- Windows Update 関連
- 不明

git で永続化された commit はディスク上に残っていたため、ロスは 0。Cowork が force-push でフィニッシュ。

### 5-2. origin/feat/spec_006-docker が昨日の Travel-account 由来で汚染されていた

昨日の Travel-account で動いた dispatch がいつかの段階で `origin/feat/spec_006-docker` に push していたらしい (痕跡: `0a9bb12 docs: changelog Day 6` 等)。今朝の dev-b の新規 commits とは別系統の枝。

Cowork が `git push --force-with-lease` で上書き。force update 後の origin は今朝の dev-b 由来コミットのみ。

### 5-3. 旧 README が dev-b clone に残っていなかった (dev-d clone 経由のステート)

CC は origin/main からブランチを切ったので問題なし。

## 6. Open questions

- **WSL2 再起動の予防策**: 今夜の overnight schedule が同じ事故を起こさないために、`wsl --shutdown` の無効化 / PC 電源プラン見直しを行うべきか
- **CC の push 失敗を spec 内で扱う方法**: spec の指示プロンプトに「push に失敗したら必ず result の Open questions に書く」を追加する候補

## 7. 動作確認手順 (ユーザー)

WSL Ubuntu (`~/projects/axis-knowledge-rag`) on feat/spec_006-docker:

```bash
1. git checkout feat/spec_006-docker
2. python3 -m pip install -e . --break-system-packages
3. python3 -m scripts.build_index ./examples/knowledge --reset
4. python3 -m backend.src.loader ./examples/knowledge   # 10 docs 表示
5. python3 -m backend.src.integrity ./examples/knowledge  # 壊れリンク 1 件検出
6. docker compose build   (Docker Desktop 必要)
7. docker compose up
8. open http://localhost:8501
```

期待:
- 4: 10 件の Document が一覧表示
- 5: doc_005 → doc_999 の broken ref 1 件レポート
- 7-8: Streamlit UI で軸フィルタ + 検索 + RAG 回答が動く

## 8. 次の提案 (任意)

- **次の並列 dispatch ペア**: spec_009 (normalizer 統合, dev-b) + spec_012 (pytest+CI, dev-d)
- **Day 7 リリース (spec_007)**: feat/spec_006-docker + これまでのマージ済み main をまとめて v0.1.0 タグ。手動でやるのがクリーン
- **dev-b clone の origin/feat/spec_006-docker 上書きを承認**: 上書きの結果、昨日 Travel 由来の orphan commits は origin から消えた。reflog にだけ残るが特に何もしない (90 日後に garbage collect)
