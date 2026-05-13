# axis-knowledge-rag

YAML frontmatter 付き Markdown ナレッジに対する、**軸メタデータ検索 + ベクトル検索 + RAG** のローカル Web アプリ OSS。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-0.4.0-brightgreen.svg)](#ロードマップ)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![Status: v0.4](https://img.shields.io/badge/Status-v0.4-orange.svg)](#ロードマップ)

---

<!-- DEMO_GIF_HERE -->
![demo](examples/screenshots/demo.gif)

> _デモ GIF は Day 20 に中島さんが撮影予定。撮影後 `<!-- DEMO_GIF_HERE -->` 行を削除してください。_

---

## ✨ 特徴

- 🎯 **軸メタデータ + ベクトル検索の hybrid** — `category` / `topic` / `level` などの構造化軸で絞り込みつつ、自然文クエリで意味検索
- 🇯🇵 **日本語ナレッジ特化** — 表記ゆれ吸収 (NFKC + カナ統一 + lowercase) 標準搭載
- 🔌 **LangChain / LlamaIndex 不使用、自前実装** — 依存が薄く、内部挙動が読める。Embedder / VectorStore / RAG Pipeline を必要最小限の薄いラッパで構成
- 🏠 **Local-first 設計** — ChromaDB はローカル永続、API キー未設定でも DUMMY モードで動作確認可能。個人ナレッジを外部送信しない

---

## 🚀 Quickstart (Docker)

```bash
git clone https://github.com/kazikimaguro13/axis-knowledge-rag
cd axis-knowledge-rag
docker compose up
# → Frontend: http://localhost:3000
# → Backend API: http://localhost:8000/api/docs
```

> 初回ビルド時は ChromaDB 関連で 5〜10 分かかる場合あり。  
> `.env` ファイルが必要 (`cp .env.example .env` でひな形を作成)。  
> **API キー未設定でも DUMMY モードで UI / 検索動作の確認は可能。**

---

## 🤖 メモを自動 YAML 化

既存メモ (Slack 抜粋 / 議事録 / Apple Notes / プレーン Markdown など) を
axis-knowledge-rag 用の YAML frontmatter 付き Markdown に AI 変換できます。

```bash
# 単発変換 (stdout)
python -m scripts.yamlize examples/raw_memos/sample_memo_01.txt

# ファイル出力 + カテゴリヒント
python -m scripts.yamlize meeting.txt \
    --output examples/knowledge/doc_011.md \
    --suggested-category 議事録

# バッチ変換
python -m scripts.yamlize_dir ./examples/raw_memos/ -o /tmp/converted/

# Claude Desktop / MCP から
#   tool: axis_ingest_memo  params: { raw_text: "...", ... }
```

`ANTHROPIC_API_KEY` 未設定でも DUMMY モードで動作 (構造確認用)。
詳細: [`docs/ingester.md`](docs/ingester.md)

---

## 🔌 MCP server として使う

Claude Desktop / Cowork / 任意の MCP 対応クライアントから、本リポジトリのナレッジを直接検索 / 質問できます。

### Claude Desktop 設定例

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) または `%APPDATA%\Claude\claude_desktop_config.json` (Windows) に追記:

```json
{
  "mcpServers": {
    "axis-knowledge-rag": {
      "command": "python3",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/axis-knowledge-rag",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "GEMINI_API_KEY": "AIza..."
      }
    }
  }
}
```

サンプル設定ファイル: [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json)

### 提供される tools

| Tool | 役割 |
|---|---|
| `axis_search` | 軸フィルタ + ベクトル hybrid 検索 |
| `axis_answer` | RAG (Claude API + 出典) |
| `axis_list_axes` | 軸定義の取得 |
| `axis_check_integrity` | 参照整合性チェック |
| `axis_list_documents` | ドキュメント一覧 (pagination) |
| `axis_ingest_memo` | 生メモ → YAML frontmatter Markdown 変換 |

詳細: [docs/mcp-server.md](docs/mcp-server.md)

---

## 🛠 手動セットアップ (Docker 不使用)

### Backend (Python)

```bash
# 依存インストール
pip install -e .

# サンプルナレッジから index ビルド
python -m scripts.build_index ./examples/knowledge --reset

# FastAPI 起動
uvicorn backend.src.api:app --reload --port 8000
# → http://localhost:8000/api/docs
```

### Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### Streamlit (レガシー UI / 後退路用)

```bash
streamlit run streamlit_app.py
# → http://localhost:8501
```

---

## 🏗 アーキテクチャ概要

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

詳細は [docs/architecture.md](docs/architecture.md) を参照。

---

## 📝 ナレッジ Markdown の書き方

`examples/knowledge/` に YAML frontmatter 付き Markdown を置くだけ。

```markdown
---
id: "doc_001"
title: "RAGアーキテクチャの設計判断"
axes:
  category: "技術記事"     # config.yml で定義された軸
  topic: "RAG"
  level: "中級"
  author: "Nakashima"
  year: 2026
tags: ["llm", "vector-search"]   # 自由タグ (検索の補助)
refs: ["doc_002"]                # 他ドキュメントへの参照
created: 2026-05-12
updated: 2026-05-12
---

# RAGアーキテクチャの設計判断

本文をここに記述...
```

軸の種類 (`enum` / `string` / `integer`) と必須・任意は `config.yml` の `axes:` セクションで定義する。

---

## ⚙️ 環境変数

| 変数 | 必須 | 説明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | optional | Claude API キー。未設定なら RAG が DUMMY モードで動作 |
| `GEMINI_API_KEY` | optional | Gemini Embedding API キー。未設定なら埋め込みが DUMMY モードで動作 |
| `NEXT_PUBLIC_API_BASE` | optional | Frontend から見た Backend URL (既定: `http://localhost:8000`) |
| `CHROMA_DB_PATH` | optional | ChromaDB の永続ディレクトリ (既定: `./.chromadb`) |
| `CLAUDE_MODEL` | optional | Claude モデル名 (既定: `claude-3-5-sonnet-20241022`) |
| `LOG_LEVEL` | optional | ログレベル (既定: `INFO`) |

**両 API キー未設定でも、DUMMY モードで UI と検索の動作確認は可能。**

---

## 🗺 ロードマップ

| バージョン | 日付 | 内容 |
|---|---|---|
| ✅ **v0.1.0** | 2026-05-12 | コア MVP (Streamlit UI + 軸検索 + RAG + Docker) |
| ✅ **v0.2.0** | 2026-05-13 | 表記ゆれ吸収 / 参照整合性チェック / マーカー方式 / pytest CI |
| ✅ **v0.3.0** | 2026-05-13 | Next.js + FastAPI 移行、UI/UX 全面刷新、README 完全版 |
| ✅ **v0.4.0** | 2026-05-13 | MCP server (stdio) — 6 tools (5 read + 1 ingest)、Claude Desktop / Cowork 対応 |
| 🔜 **v0.5+** | 未定 | Streamable HTTP transport、write tools (index_add / reindex)、OAuth 2.1 |

---

## 📚 Documentation

詳細な設計は [`docs/`](docs/) を参照:

| ドキュメント | 内容 |
|---|---|
| [Architecture](docs/architecture.md) | システム全体像、コンポーネント図、データフロー |
| [Design Decisions](docs/design-decisions.md) | 主要な設計判断 (ADR) 15 件 |
| [API Reference](docs/api-reference.md) | HTTP エンドポイント仕様 (FastAPI) |
| [Deployment Guide](docs/deployment.md) | Docker / Fly.io / Cloud Run デプロイ手順 |
| [Documentation Index](docs/INDEX.md) | `docs/` 全体の目次 |

機能ごとの詳細: [normalizer](docs/normalizer.md) / [integrity](docs/integrity.md) / [marker](docs/marker.md)

---

## 🔧 トラブルシューティング

### Docker が起動しない / ChromaDB エラー

```bash
# ログ確認
docker compose logs backend

# index を完全リセットして再起動
docker compose down -v
docker compose up -d
```

### API キーが正しく読み込まれない

```bash
# .env の内容確認
cat .env

# コンテナに渡っているか確認
docker compose exec backend env | grep -E "ANTHROPIC|GEMINI"
```

### DUMMY モードで動作確認したい

両 API キーを設定しないか、`.env` でコメントアウトするだけ:

```
# ANTHROPIC_API_KEY=sk-ant-...
# GEMINI_API_KEY=AIza...
```

`http://localhost:8000/api/health` にアクセスして `"embedder_mode": "DUMMY"` / `"rag_mode": "DUMMY"` が返れば OK。

### Windows (WSL2 なし) で chromadb がクラッシュする

ChromaDB は Windows ネイティブ環境で segfault する既知の問題がある。
WSL2 (Ubuntu) 環境に移行して実行することを推奨。

---

## 📸 デモ GIF 取得チェックリスト

中島さんが Day 20 中に手動で撮る:

- [ ] `docker compose up` で backend + frontend 起動
- [ ] OBS Studio or ScreenToGif (Windows) で録画開始 (1280x720, 30fps 推奨)
- [ ] `http://localhost:3000` でブラウザ画面を全画面表示
- [ ] サイドバーで `category=技術記事` を選択
- [ ] 質問入力: 「RAG アーキテクチャの設計判断は?」
- [ ] 検索ボタン押下、回答が typewriter で表示される
- [ ] 出典 `[doc_001]` をクリックして該当カードへスクロール
- [ ] 録画停止 (8〜15 秒を目安)
- [ ] GIF 化、`examples/screenshots/demo.gif` として保存 (5MB 以下目安、超える場合は 854x480 に落とす)
- [ ] README の `<!-- DEMO_GIF_HERE -->` 行を削除
- [ ] 念のため `main-view.png` / `with-answer.png` のスクショも撮る

---

## 🤝 Contribution / License / Author

- PR / Issues 歓迎。バグ報告・機能提案はお気軽に。
- License: [MIT](LICENSE)
- Author: 中島 (GitHub: [@kazikimaguro13](https://github.com/kazikimaguro13))

> 個人ナレッジ運用ツールとして開発中。
> Streamlit (レガシー UI) と Next.js (メイン UI) の 2 種類の UI が試せる独自設計です。
