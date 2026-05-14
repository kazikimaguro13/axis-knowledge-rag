# spec_007: Day 7 — v0.1.0 リリース (タグ + Release Notes + public 化)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜006 完成前提, `docs/spec-v2.md` Day 7 行

## 1. 目的

```
[現状]
- Day 6 までで Docker 起動可能、README v0.1、10本サンプル、Streamlit UI、CLI、RAG パイプライン揃っている
- リポジトリはまだ private (clone 初期状態のまま)、タグなし

[変更後]
- バグ修正、コミット履歴の整理 (rebase は不要、明らかな typo / lint 違反のみ)
- `CHANGELOG.md` の Unreleased セクションを `[0.1.0] - 2026-05-18` に確定
- annotated tag `v0.1.0` を打って push
- GitHub Release v0.1.0 を作成、Release Notes を生成
- リポジトリを **public** に切り替え
- 最後に `git log --oneline -20` と `git tag` の出力を result に貼る
```

3 週間プランの **第 1 マイルストーン**。ここを 5/18 までに通過することが「絶対死守ライン」(仕様書 11 章)。

## 2. 制約

### 触ってよいファイル / 新規作成

- `CHANGELOG.md` — Unreleased → 0.1.0 に確定
- `README.md` — リリース時点の最終調整 (バッジに `v0.1.0` を追加、ロードマップで v0.1.0 を「✅ 完了」マーク)
- 既存ソースの **明確なバグ修正のみ** (lint 違反、typo)
- `_ai_workspace/bridge/outbox/result_007.md`

### 触ってはいけないもの

- `_ai_workspace/bridge/inbox/` 以下 (read-only)
- `docs/spec-v2.md`
- 既存の commit 履歴 (rebase / amend / force-push 禁止)
- リポジトリ削除、collaborator 操作

### コーディングルール

- バグ修正は **1 つにつき 1 コミット**、`fix: ...` prefix
- リリース確定コミット: `chore(release): v0.1.0` で CHANGELOG + README バッジを 1 つにまとめる
- annotated tag: `git tag -a v0.1.0 -m "v0.1.0 — Core MVP"`

## 3. やってほしいこと

### 3-1. 事前バグスイープ

以下を順に実行し、問題が見つかったら修正:

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"

# 1. 全 CLI 動作確認
python -m backend.src.loader ./examples/knowledge
python -m scripts.build_index ./examples/knowledge --reset
python -m backend.src.search "RAG" --category 技術記事
python -m backend.src.rag "RAGとは"

# 2. 全テスト
python -m backend.tests.test_loader
python -m backend.tests.test_embedder
python -m backend.tests.test_vector_store
python -m backend.tests.test_search
python -m backend.tests.test_rag

# 3. Streamlit 起動チェック (5 秒で kill して OK)
timeout 10 streamlit run streamlit_app.py --server.headless=true 2>&1 || true

# 4. Docker build (push 不要、ローカル build だけ)
docker compose build

# 5. LangChain / LlamaIndex を import していないか確認
grep -RIn -E "langchain|llama_index|llama-index" backend/ streamlit_app.py scripts/ || echo "OK: no forbidden imports"

# 6. ruff があれば実行 (なければスキップ)
which ruff && ruff check . || echo "ruff not installed, skipping"
```

エラーが出たら `fix: ...` コミットで修正。1 件 1 コミット。

### 3-2. CHANGELOG.md 確定

```markdown
# Changelog

## [0.1.0] - 2026-05-18

初回リリース。コア MVP。

### Added
- Markdown + YAML frontmatter loader (`backend/src/loader.py`)
- Gemini text-embedding-004 wrapper + ChromaDB vector store
- Hybrid search (axis filter + vector similarity) — `backend/src/search.py`
- Claude API RAG pipeline with source citations — `backend/src/rag.py`
- Streamlit UI (`streamlit_app.py`)
- Docker / docker-compose for one-shot run
- 10 sample knowledge documents under `examples/knowledge/`
- DUMMY mode (works offline without API keys)

### Roadmap
- v0.2.0 (2026-05-25): 表記ゆれ吸収、参照整合性チェック、マーカー方式、pytest + CI
- v0.3.0 (2026-06-01): Next.js + FastAPI 移行、UI/UX 最終形

## [Unreleased]

(empty)
```

### 3-3. README 最終調整

- 冒頭に `![Version](https://img.shields.io/badge/version-0.1.0-blue)` 相当の badge を追加
- ロードマップ表で v0.1.0 を `✅ released` に変更

### 3-4. リリースコミット + タグ + push

```bash
git add CHANGELOG.md README.md
git commit -m "chore(release): v0.1.0"

git tag -a v0.1.0 -m "v0.1.0 — Core MVP

軸検索 + ベクトル検索 + RAG 生成が Streamlit UI で動作する初回リリース。
詳細は CHANGELOG.md と README.md 参照。
"

git push origin main
git push origin v0.1.0
```

### 3-5. GitHub Release を作成

`gh` CLI が dev-b 環境にあれば:

```bash
gh release create v0.1.0 \
  --title "v0.1.0 — Core MVP" \
  --notes-file _ai_workspace/bridge/outbox/release-notes-v0.1.0.md
```

無ければ Release Notes をファイルに書き出し、ユーザーが手動で GitHub UI から create する手順を result に記載。

Release Notes の内容は CHANGELOG の `[0.1.0]` セクションをそのまま + 末尾に Quickstart 抜粋:

```markdown
## Quickstart

```bash
git clone https://github.com/kazikimaguro13/axis-knowledge-rag
cd axis-knowledge-rag
docker compose up
# → http://localhost:8501
```

## 動作確認モード

`ANTHROPIC_API_KEY` / `GEMINI_API_KEY` が未設定でも **DUMMY モード** で動きます。
API キーを入れると Claude / Gemini が実際に使われます。
```

### 3-6. リポジトリを public に

`gh repo edit kazikimaguro13/axis-knowledge-rag --visibility public --accept-visibility-change-consequences` を実行。

`gh` が無いなら **手動操作の手順を result に書いて停止** (CC は勝手に public 化しない、これは重要な操作なので)。

### 3-7. result_007.md

```
- 修正したバグの一覧
- 全テスト / 全 CLI / Docker build の最終ログ抜粋
- `git log --oneline -20` の出力
- `git tag` の出力
- リリース URL (https://github.com/kazikimaguro13/axis-knowledge-rag/releases/tag/v0.1.0)
- リポジトリが public になったかの確認
- 残課題リスト (Week 2 で潰すバグ)
```

## 4. 成功条件

- [ ] 全 CLI / Streamlit / Docker build がエラーなく完走
- [ ] LangChain / LlamaIndex の import がゼロ
- [ ] CHANGELOG が `[0.1.0] - 2026-05-18` で確定
- [ ] `v0.1.0` annotated tag が GitHub に push されている
- [ ] GitHub Release v0.1.0 が作成されている (CLI 不可なら手動手順を result に)
- [ ] リポジトリが public (CLI 不可なら手動手順を result に)
- [ ] dev-b アカウントで全 push 完了

## 5. 出力先

`_ai_workspace/bridge/outbox/result_007.md`

## 6. 質問

- **public 化のタイミング**: 仕様書では Day 7 で public 化と書かれている。中島さんの判断で「リリースだけ Day 7、public 化は Day 21」にしたい場合は、その方針を確認したい。判断つかなければ **public 化は実施せず、Open question で停止**
- **`gh` CLI の有無**: 中島さん環境に gh CLI が無い場合は Release / 公開操作はユーザー手元で実施、CC は手順だけ result に書く
- **タグ確認**: `git tag` で `v0.1.0` が既にある場合 (テスト等で誤って打った)、削除してから打ち直すか質問する

## 7. 補足

### 設計の意図

- **annotated tag**: lightweight tag だと GitHub Release 連携で挙動が違うことがあるので annotated を使う
- **public 化は慎重に**: 一度 public にすると履歴が全世界に見える、フォーク・スター取消は可能でも history は cache されるリスクあり。「これは本当に出していい状態か?」を CC 自身が確認する
- **`chore(release): v0.1.0` という単独コミット**: あとから release コミットを探しやすくする慣例

### Week 2 への引き継ぎ

`spec_008.md` (Day 8) では `normalizer.py` (NFKC + カタカナ→ひらがな)。result_007 で見つかった既知バグや改善点は spec_008 の冒頭で参照する。
