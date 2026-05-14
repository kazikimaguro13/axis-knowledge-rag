# spec_021: Day 21 — v0.3.0 リリース (フィナーレ)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: spec_001〜020, `docs/spec-v2.md` Day 21 行

## 1. 目的

```
[現状]
- Week 3 までで Next.js + FastAPI + Docker + 設計 docs 完成
- まだ v0.3.0 タグ未発行、リリースノートなし
- README は v0.3 版、デモ GIF は中島さん側で取得済み (前提)

[変更後]
- 最終バグスイープ (CLI / API / Frontend / Docker compose / CI 全部 green)
- CHANGELOG.md の `[Unreleased]` → `[0.3.0] - 2026-06-01` 確定
- `v0.3.0` annotated tag 発行
- GitHub Release v0.3.0 を作成 (CLI 不可なら手動手順)
- フューチャー ES 提出用の GitHub link が動く状態
- `_ai_workspace/bridge/outbox/release-notes-v0.3.0.md` を生成
- 3 週間プランの完走を CHANGELOG に記録
```

3 週間の **フィナーレ**。ここまで来ればフューチャー ES のポートフォリオが完成。

## 2. 制約

### 触ってよいファイル

- `CHANGELOG.md`
- `README.md` (バッジ更新、ロードマップで v0.3.0 を ✅ released に)
- 明らかなバグ修正 (lint, typo)
- `_ai_workspace/bridge/outbox/release-notes-v0.3.0.md`

### 触ってはいけないもの

- 仕様書 (`docs/spec-v2.md`)
- `_ai_workspace/bridge/inbox/`
- ソースの仕様変更 (バグ修正のみ)
- 既存 commit 履歴 (rebase / force push 禁止)

### コーディングルール

- バグ修正は 1 つにつき 1 コミット (`fix:` prefix)
- リリースコミット: `chore(release): v0.3.0`
- annotated tag: `git tag -a v0.3.0 -m "v0.3.0 — Next.js + FastAPI"`

## 3. やってほしいこと

### 3-1. 事前バグスイープ (フルパス)

```bash
cd ~/projects/axis-knowledge-rag

# 1. 全テスト
pytest -v --cov=backend/src
# 期待: 全 PASS、coverage 75%+

# 2. ruff
ruff check .

# 3. Backend CLI 一式
python -m backend.src.loader ./examples/knowledge
python -m backend.src.integrity ./examples/knowledge
python -m backend.src.marker examples/knowledge/01-rag-patterns.md --list
python -m scripts.build_index ./examples/knowledge --reset
python -m backend.src.search "RAGとは" --category 技術記事
python -m backend.src.search "ＲＡＧとは" --category 技術記事  # 表記ゆれ
python -m backend.src.rag "RAG の利点は何か?"

# 4. FastAPI
uvicorn backend.src.api:app --port 8000 &
sleep 3
curl -f http://localhost:8000/api/health
curl -f http://localhost:8000/api/axes
curl -X POST http://localhost:8000/api/search -H "Content-Type: application/json" -d '{"query":"RAG","top_k":3}'
kill %1

# 5. Streamlit (5 秒で kill)
timeout 8 streamlit run streamlit_app.py --server.headless=true || true

# 6. Frontend
cd frontend
npm install
npm run lint
npm run build
cd ..

# 7. Docker compose
docker compose build
docker compose up -d
sleep 30
curl -f http://localhost:3000
curl -f http://localhost:8000/api/health
docker compose down

# 8. LangChain / LlamaIndex 不使用確認
grep -RIn -E "langchain|llama_index|llama-index" backend/ frontend/src/ scripts/ \
  && echo "FORBIDDEN IMPORT" || echo "OK"

# 9. CI 状態確認 (GitHub Actions)
# CC が手動で curl https://api.github.com/repos/kazikimaguro13/axis-knowledge-rag/actions/runs?per_page=5
```

バグ発見したら `fix:` で修正、1 つにつき 1 コミット。修正不能なら Open question で停止。

### 3-2. CHANGELOG.md 確定

```markdown
## [0.3.0] - 2026-06-01

### 概要

3 週間プラン (2026-05-12 〜 2026-06-01) のフィナーレ。
Streamlit MVP → Next.js + FastAPI への移行完了、UI/UX 最終形。

### Added

- FastAPI HTTP layer (`backend/src/api.py`) — `/api/health`, `/api/axes`, `/api/search`, `/api/answer`
- Next.js 14 App Router フロントエンド (`frontend/`)
  - SearchBar, AxisFilter, ResultCard, AnswerPanel コンポーネント
  - 疑似ストリーミング (typewriter) で回答表示
  - 出典 `[doc_NNN]` のアンカーリンク
- `Dockerfile.backend` / `Dockerfile.frontend` で 2 サービス構成
- `docker-compose.yml` 2 サービス対応、healthcheck 付き
- Next.js standalone output で frontend image を slim 化
- `docs/architecture.md` を Week 3 構成で更新
- `docs/api-reference.md` HTTP endpoint 完全版
- `docs/deployment.md` 新規 (Docker / VPS / Cloud Run の手引き)
- `docs/portfolio-notes.md` (ES 提出用素材集)
- ADR-013, ADR-014, ADR-015

### Changed

- README が v0.3 版に (デモ GIF / バッジ群 / アーキ図更新)
- ロードマップで v0.1.0 / v0.2.0 / v0.3.0 全て ✅ released

### Removed / Deprecated

- 旧単一 `Dockerfile` を `Dockerfile.streamlit` に retreat (Streamlit UI を維持)

### Roadmap (v0.4+)

- プラグインシステム (embedder / LLM 差し替え)
- マルチユーザー対応
- クラウドデプロイ自動化
- mkdocs ドキュメントサイト
- 表記ゆれ吸収の拡張 (送り仮名 / 異体字)

### 3 週間プラン (個人記録)

- Week 1 (5/12〜5/18): v0.1.0 コア MVP
- Week 2 (5/19〜5/25): v0.2.0 差別化機能 + テスト + CI
- Week 3 (5/26〜6/1): v0.3.0 Next.js + FastAPI + デプロイ手順

Cowork (戦略・spec 起草) × Claude Code (実装・push) の bridge 運用で 21 spec を完走。
```

### 3-3. README v0.3 → v0.3.0 final 微調整

- バッジ: `Version: 0.3.0 (released)`
- ロードマップで v0.3.0 行を ✅ released に
- デモ GIF パスが `examples/screenshots/demo.gif` (中島さんがアップしている前提)

### 3-4. リリースコミット + タグ

```bash
git add CHANGELOG.md README.md
git commit -m "chore(release): v0.3.0"

git tag -a v0.3.0 -m "v0.3.0 — Next.js + FastAPI

3 週間プランのフィナーレ。

- Next.js 14 App Router + Tailwind UI
- FastAPI バックエンド
- Docker compose 2 サービス構成
- 12+ ADR を含む設計 docs 完全版
- DUMMY モードでオフライン動作

詳細は CHANGELOG.md の [0.3.0] セクション参照。
"

git push origin main
git push origin v0.3.0
```

### 3-5. GitHub Release

`gh` CLI:

```bash
gh release create v0.3.0 \
  --title "v0.3.0 — Next.js + FastAPI (final 3-week plan release)" \
  --notes-file _ai_workspace/bridge/outbox/release-notes-v0.3.0.md
```

`gh` 不可なら手動手順を result に。

### 3-6. release-notes-v0.3.0.md

CHANGELOG `[0.3.0]` セクションをコピー + 末尾に Quickstart:

```markdown
## Quickstart

```bash
git clone https://github.com/kazikimaguro13/axis-knowledge-rag
cd axis-knowledge-rag
docker compose up
# → http://localhost:3000
```

## What's next?

- v0.4: プラグインシステム
- v0.5: マルチユーザー対応
- v0.6: クラウドデプロイ自動化
- v1.0: ドキュメントサイト、ロゴ、ブランディング

このリリースは個人 OSS の 3 週間スプリントの結果です。詳しい開発記録は `_ai_workspace/bridge/` (オプション公開) と `docs/` を参照。
```

### 3-7. リポジトリの最終状態確認

```bash
git log --oneline | head -25
git tag
git remote -v
gh repo view kazikimaguro13/axis-knowledge-rag
```

リポジトリが public 状態か確認、private のままなら public 化操作 (spec_007 と同じく慎重に)。

### 3-8. result_021.md

- 全テスト / 全 CLI / Docker 起動の最終ログ
- `git log --oneline -25` 抜粋 (3 週間で何コミット作ったか)
- `git tag` 出力
- Release URL
- 残課題リスト (v0.4 で潰すべきもの)
- 中島さんへの一言メッセージ (この 3 週間で作ったポートフォリオがどんな価値を持っているか、CC の感想)

## 4. 成功条件

- [ ] 全テスト / lint / CLI / Streamlit / Docker / Frontend build / Docker compose で動作
- [ ] LangChain / LlamaIndex 不使用維持
- [ ] CHANGELOG `[0.3.0] - 2026-06-01` 確定
- [ ] `v0.3.0` annotated tag 発行 + push
- [ ] GitHub Release v0.3.0 (CLI 不可なら手動手順を result に)
- [ ] リポジトリ public
- [ ] dev-b で push 完了
- [ ] フューチャー ES に提出可能な URL: `https://github.com/kazikimaguro13/axis-knowledge-rag`

## 5. 出力先

`_ai_workspace/bridge/outbox/result_021.md`

## 6. 質問

- **public 化のタイミング**: spec_007 で既に public 化していれば skip。private なら Day 21 で public 化、判断つかなければ停止
- **GitHub Release のアセット添付**: `examples/screenshots/demo.gif` を release asset として上げるか、または `examples/screenshots/main-view.png`。CLI で添付 (`--asset`) するか、UI で。判断つかなければ Open question
- **`gh` CLI が無い場合**: WSL に `apt install gh` で入れて auth してから実行、または Release は手動操作

## 7. 補足

### 設計の意図

- **annotated tag**: GitHub Release との連携で挙動が安定
- **`chore(release): vX.Y.Z` の単独コミット**: 後から探しやすい
- **public 化を Day 21 で確実に**: フューチャー ES 提出のタイミングで「URL を踏んだら 404」事故を防ぐ

### このプロジェクトを終えて

中島さんの 3 週間が「動く OSS」「言語化された設計判断」「採用担当者が読める履歴」として残る。フューチャー ES 提出後、面接で:

- 「LangChain を使わなかった理由を 5 ADR で説明できる」
- 「Windows + chromadb の wheel バグを WSL2 で乗り越えた経験」
- 「Cowork × Claude Code の bridge 運用を 21 spec で完走させた」

がアピールできる材料。

果報を期待しています 🚀
