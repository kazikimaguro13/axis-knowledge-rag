# Documentation Index

axis-knowledge-rag の `docs/` ディレクトリの目次。
README は入口、ここから先は「設計の深さ」に進むためのナビゲーション。

---

## Getting Started

- [README](../README.md) — プロジェクト概要、Quickstart、ロードマップ
- [spec-v2.md](spec-v2.md) — 3 週間開発計画 (内部資料)

## Architecture

- [architecture.md](architecture.md) — システム全体像、コンポーネント図、データフロー、デプロイ構成 (v0.3 Next.js + FastAPI 版)
- [design-decisions.md](design-decisions.md) — 主要な設計判断 (ADR) 15 件
- [api-reference.md](api-reference.md) — HTTP エンドポイント仕様 (FastAPI / v0.3 最終版)

## Features

- [normalizer.md](normalizer.md) — 日本語テキスト正規化 (NFKC + カナ統一 + lowercase)
- [integrity.md](integrity.md) — 参照整合性チェック (壊れリンク / 孤立 / 循環)
- [marker.md](marker.md) — `<!-- AUTO_GENERATED_*** -->` ブロック方式
- [mcp-server.md](mcp-server.md) — MCP server (stdio) — 5 tools、Claude Desktop / Cowork 組み込み手順

## Operations

- [deployment.md](deployment.md) — Local Docker / VPS / Cloud Run デプロイ手順、ChromaDB バックアップ
- _(TBD)_ knowledge-graph.md — v0.5 で追加予定 (Mermaid 形式の参照グラフ)

## Portfolio


---

## ドキュメントの位置づけ

| 読者 | 推奨経路 |
|---|---|
| 初めて見た人 | README → architecture.md → 興味のある Feature |
| 採用担当者 / レビュアー | README → design-decisions.md → architecture.md |
| 開発者 (PR 出す人) | api-reference.md → 該当 Feature doc → architecture.md |
| 機能を使いたい人 | README → 該当 Feature doc (normalizer / integrity / marker) |

## ドキュメントの種類別 役割

- **README**: 入口。何のプロジェクトかと、最初の起動方法
- **architecture.md**: 全体構成と責務分担。「コードを読む前に読む地図」
- **design-decisions.md** (ADR): なぜそう作ったかの根拠。代替案も含む
- **api-reference.md**: モジュール単位の使い方。シグネチャ + 短い例
- **<feature>.md**: 機能ごとの解説。背景・図・FAQ を含む詳細版
