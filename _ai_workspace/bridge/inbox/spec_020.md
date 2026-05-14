# spec_020: Day 20 — README 完全版 + デモ GIF + 設計ドキュメント最終整理

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: spec_001〜019, `docs/spec-v2.md` Day 20 行

## 1. 目的

```
[現状]
- README は v0.2 時点で「特徴 / Quickstart / ロードマップ」
- スクショ・GIF が無い
- 設計 docs (architecture/design-decisions/api-reference) は v0.2 で書いたが、Next.js / FastAPI 移行後の最新状態が反映されていない

[変更後]
- README が「30 秒で価値が伝わる」最終版に
- デモ GIF (8〜15 秒) を `examples/screenshots/demo.gif` として埋める **手順** を CC は提供 (実録画は中島さん側)
- スクショ 3 枚程度のチェックリストを書く (ヘッダ / 検索画面 / 回答パネル)
- 設計 docs を v0.3 内容に更新 (Next.js + FastAPI のアーキ図、デプロイ章追加)
- `docs/deployment.md` 新規 (Docker compose を本番に近い形で動かす手順)
- 履歴書記述用テンプレ (`docs/spec-v2.md` セクション 13 の内容) を `docs/portfolio-notes.md` に独立化
```

## 2. 制約

### 触ってよいファイル

- `README.md` — 全面改稿 (v0.3 版)
- `docs/architecture.md` — Next.js + FastAPI 反映
- `docs/design-decisions.md` — ADR を Week 3 ぶん追加 (ADR-013〜015)
- `docs/api-reference.md` — HTTP endpoint 最終版
- `docs/deployment.md` — 新規
- `docs/portfolio-notes.md` — 新規
- `examples/screenshots/` — checklist (チェックボックス Markdown) を `README.md` に書く
- `CHANGELOG.md`

### 触ってはいけないもの

- ソース本体 (バグ修正なら spec_021 で)
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- README は 250〜350 行目安 (長すぎず短すぎず)
- 絵文字バッジ、shields.io バッジを冒頭に
- ASCII 図優先、補足で Mermaid

## 3. やってほしいこと

### 3-1. README.md v0.3 構成

1. **タイトル + 1 行説明 + バッジ群**
   - shields.io: License: MIT, Version: 0.3.0, Python 3.11+, Next.js 14
2. **デモ GIF** (placeholder `![demo](examples/screenshots/demo.gif)`)
3. **特徴 (4 個 + 絵文字)**
4. **30 秒 Quickstart**
   ```bash
   git clone https://github.com/kazikimaguro13/axis-knowledge-rag
   cd axis-knowledge-rag
   docker compose up
   # → http://localhost:3000
   ```
5. **手動セットアップ** (Docker 不使用、Python + Node 両方)
6. **アーキテクチャ概要** (Next.js + FastAPI + ChromaDB の ASCII 図)
7. **ナレッジ Markdown の書き方** (frontmatter サンプル)
8. **環境変数** (両 API キーは optional、DUMMY モード明記)
9. **ロードマップ** (v0.1 / v0.2 / v0.3 全て ✅、v0.4+ は計画)
10. **Documentation** リンク集 (docs/INDEX.md 参照)
11. **Contribution / License / Author**

### 3-2. デモ GIF 取得チェックリスト

README 末尾 or 別ファイルに:

```markdown
## デモ GIF 取得チェックリスト

中島さんが Day 20 中に手動で撮る:

- [ ] `docker compose up` で backend + frontend 起動
- [ ] OBS Studio or ScreenToGif (Windows) で録画開始 (1280x720, 30fps 推奨)
- [ ] http://localhost:3000 でブラウザ画面を全画面表示
- [ ] サイドバーで `category=技術記事` を選択
- [ ] 質問入力: 「RAG アーキテクチャの設計判断は?」
- [ ] 検索ボタン押下、回答が typewriter で表示される
- [ ] 出典 `[doc_001]` をクリックして該当カードへスクロール
- [ ] 録画停止
- [ ] GIF 化、`examples/screenshots/demo.gif` として保存 (< 5MB 目安)
- [ ] README の `<!-- DEMO_GIF_HERE -->` を `![demo](examples/screenshots/demo.gif)` に置換
- [ ] 念のため main-view.png / with-answer.png のスクショも撮る
```

### 3-3. `docs/architecture.md` 更新

Week 3 構成の図に置き換え:

```
┌─ Browser (localhost:3000) ──────────────────────────────┐
│  Next.js 14 App Router                                  │
│  ├─ SearchBar, AxisFilter, ResultCard, AnswerPanel       │
│  └─ lib/api.ts (fetch)                                   │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP/JSON (CORS)
┌──────────────────────▼───────────────────────────────────┐
│  FastAPI (localhost:8000)                                │
│  /api/{health, axes, search, answer, docs(Swagger)}      │
│  ├─ schemas.py (Pydantic)                                │
│  └─ Lifespan: SearchEngine, RAGPipeline, Embedder         │
└──────────────────────┬───────────────────────────────────┘
                       │
        ┌──────────────┼───────────────┐
        ▼              ▼               ▼
   loader.py     SearchEngine      RAGPipeline
   (Markdown +   (axis filter +    (Claude API,
    YAML)         vector hybrid)    citations)
        │              │               │
        └──────────────┼───────────────┘
                       ▼
                ChromaDB (.chromadb/, persistent)
                       │
                       ▼
                  Embedder
                  (Gemini text-embedding-004)
```

データフロー (index time / query time) のフロー図、コンポーネント責務一覧も更新。

### 3-4. `docs/design-decisions.md` に ADR 追加

- ADR-013: 疑似ストリーミング (typewriter) を採用、SSE/WS は v0.4 へ
- ADR-014: Streamlit を deprecated せず残す (retreat 用)
- ADR-015: Docker multi-stage で frontend image を slim 化

### 3-5. `docs/api-reference.md` 最終版

各 HTTP endpoint について:

```markdown
### POST /api/search

検索リクエスト。

**Request**:
```json
{
  "query": "RAGとは",
  "filters": {"category": "技術記事"},
  "top_k": 5
}
```

**Response**:
```json
{
  "results": [{ "id": "doc_001", "title": "...", "score": 0.85, ... }]
}
```

**Errors**: 500 — search engine failure
```

全 5 endpoint (health, axes, search, answer, docs) で同じフォーマット。

### 3-6. `docs/deployment.md` 新規

```markdown
# Deployment Guide

## Local Docker

```bash
docker compose up -d
```

Backend: localhost:8000, Frontend: localhost:3000

## VPS / Cloud (リファレンス)

### Fly.io

```bash
fly launch
fly deploy
```

### Google Cloud Run

```bash
gcloud run deploy axis-knowledge-rag-backend \
  --source backend/ \
  --region asia-northeast1
```

### 環境変数の渡し方

- `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` を secret として注入
- `NEXT_PUBLIC_API_BASE` を backend の URL に設定

## ChromaDB の永続化

named volume `chroma-data` を使う。バックアップは `docker run --rm -v chroma-data:/data ...` で tar 化。

## TLS / リバースプロキシ

Caddy or nginx で前段に置く構成例 (v0.4 で実装予定)。
```

### 3-7. `docs/portfolio-notes.md` 新規

`docs/spec-v2.md` セクション 13 (履歴書記述用テンプレ) を移植 + Week 3 で得た学びを追記:

```markdown
# Portfolio Notes (履歴書 / ES 用素材集)

## 使用技術

Python / FastAPI / Next.js (TypeScript) / Tailwind CSS / ChromaDB / Claude API / Gemini Embedding / YAML frontmatter / Docker / Docker Compose / Git / GitHub Actions

## 個人開発 / OSS

個人開発 (OSS 公開, 2026-05〜)

## 成果物概要

(spec-v2 セクション 13 から)

## 工夫した点

- メタデータ駆動設計
- 表記ゆれ吸収
- 参照整合性チェック
- マーカー方式
- マルチ LLM オーケストレーション
- LangChain / LlamaIndex 不使用

## 開発プロセスで学んだこと (面接で話せるネタ)

- Cowork × Claude Code の bridge 運用で 21 日のロードマップを 7 日で実装
- Windows + chromadb の segfault に当たり、WSL2 環境に移行
- Streamlit から Next.js へリファクタする際、共通の SearchEngine インターフェイスで両 UI を支える設計
- DUMMY モード設計でテストコストゼロ
- 12 ADR で「なぜそれを選んだか」を全部言語化
```

### 3-8. 動作確認

```bash
cd ~/projects/axis-knowledge-rag
wc -l README.md docs/*.md

# リンク切れチェック (簡易)
grep -rn "\](" README.md docs/ | grep -v "://" | head -20

docker compose up -d  # ヘルスチェック含めて全部動くか
sleep 30
curl http://localhost:3000
curl http://localhost:8000/api/health
docker compose down
```

### 3-9. コミット

1. `docs: rewrite README to v0.3 with demo placeholder`
2. `docs: update architecture.md for Next.js + FastAPI`
3. `docs: add ADR-013, ADR-014, ADR-015`
4. `docs: finalize api-reference.md HTTP section`
5. `docs: add deployment.md`
6. `docs: add portfolio-notes.md from spec-v2 section 13`
7. `docs: add demo GIF checklist`
8. `docs: changelog Day 20`

`git push origin main` (dev-b)

### 3-10. result_020.md

- 各 docs の行数 (target: README 250〜350, architecture 200+, design-decisions 400+, api-reference 250+, deployment 100+, portfolio-notes 150+)
- リンク切れチェック結果
- デモ GIF は撮れない、checklist がきれいに書けているか自己評価

## 4. 成功条件

- [ ] README v0.3 が「30 秒で価値が伝わる」構成
- [ ] docs/ 全更新、リンク切れなし
- [ ] portfolio-notes.md が ES 記述に使える形
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_020.md`

## 6. 質問

- **GIF のサイズ目安**: 5MB 以下に収めるためにフレームレート 15fps / 解像度 1280x720 推奨。それでも 5MB 超えたら 854x480 に落とす
- **portfolio-notes.md の公開**: フューチャー ES 提出時に企業名が出るのは差し障りある可能性。一般化した記述にして、企業名は履歴書本体に書く方針 (CC はこれで進めて OK)
- **deployment.md の Fly.io / Cloud Run**: 実機検証していない、リファレンスのみ。動作確認は v0.4 で

## 7. 補足

### 設計の意図

- **README は入口、深い情報は docs/**: スキャナビリティ重視
- **portfolio-notes は中島さん資産**: 他社 ES にも流用できる素材集
- **Streamlit を残す**: README で「2 種類の UI が試せる」と書ける独自性
- **デモ GIF 撮影は人間タスク**: CC は手順だけ書く、画面録画は中島さんの担当

### Day 21 連携

Day 21 で最終バグ修正 + v0.3.0 タグ + GitHub Release + フューチャー ES 提出。
