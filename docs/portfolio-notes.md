# Portfolio Notes (履歴書 / ES 用素材集)

就職活動における ES・履歴書・面接での説明に使える素材集。
企業名は ES 本体に書くため、ここでは一般化した記述にする。

---

## 使用技術

```
Python / FastAPI / Next.js (TypeScript) / Tailwind CSS /
ChromaDB / Claude API (Anthropic) / Gemini Embedding (Google) /
YAML frontmatter / Docker / Docker Compose / Git / GitHub Actions
```

---

## 個人開発 / OSS

**個人開発 (OSS 公開, 2026-05〜)**  
GitHub: `github.com/kazikimaguro13/axis-knowledge-rag`

---

## 成果物概要

個人や小チーム向けの Markdown ナレッジに対する RAG 検索 Web App フレームワーク (OSS)。
ユーザーが YAML frontmatter 付き Markdown ファイルをローカルに配置し、
Docker 一発で起動する Web UI から自然言語問い合わせ・軸検索ができる。

- バックエンド: **FastAPI** (Python)
- フロントエンド: **Next.js 14** (TypeScript + Tailwind CSS)
- ベクトル検索: **ChromaDB** (ローカル永続)
- 埋め込み: **Gemini text-embedding-004** (768 次元)
- 回答生成: **Claude API** (claude-3-5-sonnet)
- Local-first 設計 — 個人データを外部送信しない

---

## 背景

業務で営業の暗黙知を 5 軸ナレッジ化し、新人エージェントの初提案完成時間を
1.5 日 → 27 分 (98% 短縮) に短縮した経験から、その設計思想を汎用 OSS として再構築。
個人ブロガー、研究者、学生団体など、構造化ナレッジを必要とする誰もが使える形に汎用化する。

---

## 工夫した点

### メタデータ駆動設計

YAML frontmatter で軸タグ付け (`category` / `topic` / `level` など)。
後方互換性を担保した段階導入を可能にし、既存の Markdown ライブラリとも共存できる設計。

### 表記ゆれ吸収

NFKC 正規化 + カタカナ→ひらがな変換で、日本語検索精度を実用レベルに引き上げ。
normalize 後の値と生の値を両方保持し、検索は norm で、表示は生の値を使う二重管理方式。

### 参照整合性チェック

ナレッジ間の `refs:` 参照を自動検証。broken refs / orphan docs / 循環参照を検出し、
`--strict-integrity` フラグでインデックスビルドを中断できる。

### マーカー方式の自動生成保護

`<!-- AUTO_GENERATED_START: summary --> ... <!-- AUTO_GENERATED_END: summary -->` で
人間記述部分と AI 自動生成部分を共存させ、再生成時の上書き事故を防止。

### マルチ LLM オーケストレーション

Claude API (回答生成) + Gemini Embedding (埋め込み) を役割分担。
両 API キー未設定でも DUMMY モードで動作確認できる設計。

### LangChain / LlamaIndex を意図的に不使用

RAG アーキテクチャを自前実装。`embedder` / `vector_store` / `search` / `rag` の
各モジュールが独立して差し替え可能な薄いラッパ構成で、設計理解の深さを担保。

### DUMMY モード設計でテストコストゼロ

`Embedder(force_dummy=True)` と `RAGPipeline(force_dummy=True)` を一級市民として提供。
API キーなしで CI / ローカルのパイプライン全体が走る。
SHA256 ハッシュ由来の決定的 768 次元ベクトルで再現性も確保。

### 12 + 3 ADR で設計判断を全て言語化

「なぜそれを選んだか」を ADR 形式で 15 件記録。
採用面接で設計の根拠を論理的に説明できる状態を維持。

---

## 数字でまとめる (面接・ES 向け)

| 指標 | 値 |
|---|---|
| 実装期間 | 3 週間 (Day 1〜21) |
| コミット数 | 30+ |
| テスト数 | 90 テスト |
| テストカバレッジ | 72.49% |
| ADR 数 | 15 件 |
| サポート言語 | 日本語 (NFKC 正規化) |
| UI 種類 | Next.js (メイン) + Streamlit (レガシー) |
| HTTP エンドポイント | 4 (health / axes / search / answer) |

---

## 開発プロセスで学んだこと (面接で話せるネタ)

### AI 協業ワークフローの設計と運用

Cowork (仕様作成 AI) × Claude Code (実装 AI) の bridge 運用で、
21 日のロードマップを加速して実装。`_ai_workspace/bridge/` に spec と result を
文書化し、AI ↔ AI の引き継ぎを完全にトレース可能にした。

### 環境依存問題への対処 (Windows → WSL2 移行)

Windows 上で chromadb の segfault が発生し、WSL2 (Ubuntu) 環境に移行して解決。
問題の根本原因 (shared library の ABI 不整合) を特定し、環境移行を選択した判断プロセスを説明できる。

### フレームワーク移行の設計

Streamlit から Next.js + FastAPI へリファクタする際、共通の `SearchEngine` インターフェイスで
両 UI を支える設計を採用。移行後も Streamlit を後退路として残し、段階的移行を実現。

### テスト戦略の整備

pytest への移行、conftest.py による fixture 共通化、DUMMY モードの一級市民化、
ruff による lint 統合を Week 2 でまとめて整備。CI matrix (py311/py312) で互換性担保。

### ドキュメンテーション駆動開発

ADR / architecture.md / api-reference.md を実装と並行して書き続けることで、
「なぜそうしたか」の文書が実装と乖離しない状態を維持した。

---

## 面接想定 Q&A

**Q: なぜ LangChain を使わなかったのか?**  
A: 「RAG を自分で組める」ことを示したかったため。LangChain の abstraction に乗ると内部挙動が隠れ、
面接で設計を説明できなくなる。また、依存が薄いほど長期メンテナンス性が上がる。

**Q: ChromaDB を選んだ理由は?**  
A: Local-first 要件 (外部サーバ不要、ファイル永続) と、軸メタデータの where 句フィルタが
標準で使える点が決め手。大規模化時は Qdrant / Weaviate への移行を想定している。

**Q: Gemini と Claude を使い分けた理由は?**  
A: Gemini は Embedding API の無料枠が充実しており開発コストを抑えられる。
Claude は日本語生成の品質が高く、ユーザー体験を優先した。役割分担で両者の強みを活かした。

**Q: DUMMY モードの設計意図は?**  
A: API キーなしで CI とローカル開発が回ることが最優先。外部 API 依存をテストから分離し、
コストゼロでパイプライン全体を検証できる。採用担当者が clone してすぐ動かせる体験も重要。
