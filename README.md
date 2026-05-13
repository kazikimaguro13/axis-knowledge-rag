# axis-knowledge-rag

YAML frontmatter 付き Markdown ナレッジに対する、**軸メタデータ検索 + ベクトル検索 + RAG** のローカル Web アプリ OSS。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Status: alpha](https://img.shields.io/badge/Status-alpha--v0.1-orange.svg)](#ロードマップ)

![demo](examples/screenshots/with-answer.png)

> _スクリーンショット未撮影の場合は placeholder。Day 7 で差し替え予定。_

---

## ✨ 特徴

- 🎯 **軸メタデータ + ベクトル検索の hybrid** — `category` / `topic` / `level` などの構造化軸で絞り込みつつ、自然文クエリで意味検索
- 🇯🇵 **日本語ナレッジ特化** — 表記ゆれ吸収 (NFKC + カナ統一 + lowercase) を v0.2 で標準搭載予定
- 🔌 **LangChain / LlamaIndex 不使用、自前実装** — 依存が薄く、内部挙動が読める。Embedder / VectorStore / RAG Pipeline を必要最小限の薄いラッパで構成
- 🏠 **Local-first 設計** — ChromaDB はローカル永続、API キー未設定でも DUMMY モードで動作確認可能。個人ナレッジを外部送信しない

## 🚀 Quickstart (Docker)

```bash
git clone https://github.com/kazikimaguro13/axis-knowledge-rag
cd axis-knowledge-rag
docker compose up
# → http://localhost:8501
```

> 初回ビルド時は ChromaDB 関連で 5〜10 分ほど時間がかかる場合あり。
> `.env` ファイルが必要 (`cp .env.example .env` でひな形を作成)。
> API キー未設定でも DUMMY モードで UI / 検索動作の確認は可能。

## 🛠 手動セットアップ (Docker 不使用)

```bash
# 依存インストール
pip install -e .

# サンプルナレッジから index ビルド
python -m scripts.build_index ./examples/knowledge --reset

# Streamlit 起動
streamlit run streamlit_app.py
# → http://localhost:8501
```

## 📝 ナレッジ Markdown の書き方

`examples/knowledge/*.md` のような形式で、YAML frontmatter 付き Markdown を `examples/knowledge/` (または任意ディレクトリ) に置く。

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

軸の種類 (enum / string / integer) と必須・任意は `config.yml` の `axes:` セクションで定義する。

## ⚙️ 環境変数

| 変数 | 必須 | 説明 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | optional | Claude API キー。未設定なら RAG が DUMMY モードで動作 |
| `GEMINI_API_KEY` | optional | Gemini Embedding API キー。未設定なら埋め込みが DUMMY モードで動作 |
| `CHROMA_DB_PATH` | optional | ChromaDB の永続ディレクトリ (既定: `./.chromadb`) |
| `LOG_LEVEL` | optional | ログレベル (既定: `INFO`) |

両 API キー未設定でも、DUMMY モードで UI と検索の動作確認は可能。

## 🗺 ロードマップ

| バージョン | 目標日 | 内容 |
| --- | --- | --- |
| **v0.1.0** | 2026-05-18 | コア MVP (Streamlit UI + 軸検索 + RAG + Docker)  ← **これ** |
| v0.2.0 | 2026-05-25 | 表記ゆれ吸収 / 参照整合性チェック / マーカー方式ハイライト |
| v0.3.0 | 2026-06-01 | Next.js + FastAPI 移行、UI/UX 全面刷新 |
| v0.4+ | 未定 | プラグイン (Embedder / LLM 差し替え)、マルチユーザー、クラウドデプロイ |

詳細仕様は `docs/spec-v2.md` を参照。

## 🏗 アーキテクチャ概要

```
Markdown → loader → embedder (Gemini) → ChromaDB
              ↓                            ↑
          SearchEngine (axis filter + vector) ← query
              ↓
          RAGPipeline (Claude)
              ↓
          Streamlit UI
```

- **loader** — YAML frontmatter + 本文を `Document` データクラスにパース (`backend/src/loader.py`)
- **embedder** — Gemini text-embedding-004 ラッパ (DUMMY フォールバック付き) (`backend/src/embedder.py`)
- **vector_store** — ChromaDB PersistentClient ラッパ、軸メタデータをフラット化して保存 (`backend/src/vector_store.py`)
- **search** — 軸フィルタ + ベクトル検索の hybrid SearchEngine (`backend/src/search.py`)
- **rag** — Claude API 呼び出し + 出典 ID 抽出 (`backend/src/rag.py`)
- **streamlit_app.py** — サイドバー軸フィルタ + 質問入力 + 回答パネル

## 📚 Documentation

詳細な設計は [`docs/`](docs/) を参照:

- [Architecture](docs/architecture.md) — システム全体像、コンポーネント図、データフロー
- [Design Decisions](docs/design-decisions.md) — 主要な設計判断 (ADR) 12 件
- [API Reference](docs/api-reference.md) — モジュール別 public API
- [Documentation Index](docs/INDEX.md) — `docs/` 全体の目次

機能ごとの詳細: [normalizer](docs/normalizer.md) / [integrity](docs/integrity.md) / [marker](docs/marker.md)

## 📜 ライセンス

[MIT](LICENSE)

## 👤 作者

中島 (GitHub: [@kazikimaguro13](https://github.com/kazikimaguro13))

> 就活ポートフォリオ兼、個人ナレッジ運用ツールとして開発中。
> フィードバック・PR 歓迎。
