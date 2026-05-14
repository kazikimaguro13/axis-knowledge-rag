# spec_006: Day 6 — Docker 化 + サンプル 10 本拡充 + README v0.1

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜005 完成前提, `docs/spec-v2.md` Day 6 行

## 1. 目的

```
[現状]
- streamlit_app.py が動作する
- examples/knowledge/ には 5 本しかサンプルがない
- README は spec_001 時点の Day 1 版で、特徴の説明が薄い
- Docker 化されていない (採用担当者が試しづらい)

[変更後]
- `Dockerfile` で Streamlit + バックエンドを 1 コンテナで起動
- `docker-compose.yml` で `docker compose up` 一発起動 (`.env` を mount)
- examples/knowledge を 5本 → 10本に拡充、テーマの多様性を増やす (差別化アピール材料)
- README v0.1 版が「30秒で価値が伝わる」構成: 概要 / 特徴 / Quickstart (3 行) / スクショ / ロードマップ
- `docker compose up` → `localhost:8501` で UI が動作
```

Day 7 で v0.1.0 タグを打つ準備の総仕上げ。

## 2. 制約

### 触ってよいファイル / 新規作成

- `Dockerfile` — 新規 (Week 3 で `Dockerfile.backend` / `Dockerfile.frontend` に分割する。Week 1 では単一で OK)
- `docker-compose.yml` — 新規
- `.dockerignore` — 新規
- `examples/knowledge/06-*.md` 〜 `10-*.md` — 5 本追加
- `README.md` — 全面改稿 (v0.1 版)
- `CHANGELOG.md`

### 触ってはいけないもの

- `_ai_workspace/`、`docs/spec-v2.md`
- 既存の backend コード (バグなければ)
- 既存サンプル 01〜05 (refs 関係を壊さない、必要なら追記のみ)

### コーディングルール

- Dockerfile は Python 3.11-slim ベース、multi-stage 不要 (Week 3 で frontend と分けたら multi-stage 検討)
- `chromadb` 永続化のために `/app/.chromadb` を named volume にマウント
- Streamlit はコンテナ内で `--server.address=0.0.0.0 --server.port=8501` で起動
- `.dockerignore` で `_ai_workspace/`、`docs/`、`__pycache__/`、`.chromadb/`、`.git/`、`.env` を除外
- README はマークダウン素のまま、画像は `examples/screenshots/` を参照

## 3. やってほしいこと

### 3-1. Dockerfile

```dockerfile
FROM python:3.11-slim

# System deps (chromadb wants libstdc++, sqlite3)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend
COPY scripts ./scripts
COPY examples ./examples
COPY config.yml ./
COPY streamlit_app.py ./

RUN pip install --no-cache-dir -e .

EXPOSE 8501

# 起動時に index をビルドしてから streamlit 起動
CMD ["sh", "-c", "python -m scripts.build_index ./examples/knowledge && streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501"]
```

### 3-2. docker-compose.yml

```yaml
services:
  app:
    build: .
    ports:
      - "8501:8501"
    env_file:
      - .env
    volumes:
      - chroma-data:/app/.chromadb
      - ./examples/knowledge:/app/examples/knowledge:ro

volumes:
  chroma-data:
```

### 3-3. .dockerignore

```
.git
.gitignore
_ai_workspace
docs
__pycache__
*.pyc
*.egg-info
.chromadb
.env
node_modules
.next
.venv
venv
```

### 3-4. examples/knowledge/ 拡充 (5 本 → 10 本)

追加 5 本のテーマ例 (重複しすぎず、軸を多様に):

- `06-prompt-injection.md` (id: doc_006, category: 技術記事, topic: セキュリティ, level: 上級, refs: [doc_005])
- `07-evaluation-metrics.md` (id: doc_007, category: メモ, topic: 評価指標, level: 中級, refs: [doc_001])
- `08-tooling-comparison.md` (id: doc_008, category: 議事録, topic: ツール比較, level: 初級)
- `09-cost-estimation.md` (id: doc_009, category: メモ, topic: コスト試算, level: 中級, year: 2026)
- `10-future-roadmap.md` (id: doc_010, category: ToDo, topic: ロードマップ, level: 初級, refs: [doc_002, doc_008])

それぞれ 300〜600 字、技術一般論で OK。**doc_999 への壊れリンクは既存 05 のままにする** (Week 2 のネタ)。

### 3-5. README.md v0.1 版

構成 (上から):

1. **タイトル** + 1 行説明 + バッジ (License: MIT, Python 3.11+)
2. **デモ画像** (1 枚、`examples/screenshots/with-answer.png`、未撮影なら placeholder で OK)
3. **特徴** (4 個、絵文字 + 1 行):
   - 🎯 軸メタデータ + ベクトル検索の hybrid
   - 🇯🇵 日本語ナレッジ特化 (表記ゆれ吸収予定: v0.2)
   - 🔌 LangChain/LlamaIndex 不使用、自前実装
   - 🏠 Local-first 設計
4. **Quickstart (3 行)**:
   ```bash
   git clone https://github.com/kazikimaguro13/axis-knowledge-rag
   cd axis-knowledge-rag
   docker compose up
   # → http://localhost:8501
   ```
5. **手動セットアップ (Docker 不使用)**: `pip install -e .` → `python -m scripts.build_index ./examples/knowledge` → `streamlit run streamlit_app.py`
6. **ナレッジ Markdown の書き方**: YAML frontmatter の例 (`id`, `title`, `axes`, `tags`, `refs`)
7. **環境変数**: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (両方 optional、未設定なら DUMMY モード)
8. **ロードマップ**:
   | バージョン | 目標日 | 内容 |
   | --- | --- | --- |
   | v0.1.0 | 2026-05-18 | コア MVP (Streamlit) ← **これ** |
   | v0.2.0 | 2026-05-25 | 表記ゆれ吸収 / 参照整合性 / マーカー方式 |
   | v0.3.0 | 2026-06-01 | Next.js + FastAPI 移行 |
   | v0.4+ | 未定 | プラグイン (embedder/LLM 差し替え)、マルチユーザー、クラウドデプロイ |
9. **アーキテクチャ概要** (短い ASCII 図):
   ```
   Markdown → loader → embedder (Gemini) → ChromaDB
                  ↓                            ↑
              SearchEngine (axis filter + vector) ← query
                  ↓
              RAGPipeline (Claude)
                  ↓
              Streamlit UI
   ```
10. **ライセンス**: MIT
11. **作者**: 中島 (GitHub: kazikimaguro13)

ボリュームは 200〜300 行程度、長すぎず短すぎず。

### 3-6. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"

# Docker ビルド
docker compose build

# 起動
docker compose up

# 別ターミナルで
curl -I http://localhost:8501
# → 200 OK

# ブラウザで http://localhost:8501 を開いて 10 件サンプルが検索できるか確認
```

### 3-7. コミット

1. `feat: add Dockerfile and docker-compose for one-shot run`
2. `chore: add .dockerignore`
3. `docs: expand sample knowledge to 10 documents`
4. `docs: rewrite README to v0.1 with features, quickstart, roadmap`
5. `docs: changelog Day 6`

`git push origin main` (dev-b)

### 3-8. result_006.md

特に:

- `docker compose build` の所要時間 (chromadb は重いので確認)
- `docker compose up` 後の起動ログ抜粋
- 10 件サンプルで build_index が正常完了したか
- README の最終文字数

## 4. 成功条件

- [ ] `docker compose up` で起動 → `localhost:8501` が見える
- [ ] examples/knowledge が 10 本ある (壊れリンク doc_999 は 1 箇所のみ残す)
- [ ] README v0.1 が roadmap / quickstart / 特徴 / アーキ図を含む
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_006.md`

## 6. 質問

- **Docker desktop が中島さん環境にあるか**: 未確認なら build まで CC 側で完走、`docker compose up` の検証はユーザー手元で行う前提に切り替え、result に明記
- **chromadb の libstdc++ 依存**: slim イメージで足りなければ `python:3.11-bookworm` に切り替え、image サイズが膨らむ旨を result に記載
- **サンプルの内容**: 技術一般論で OK。中島さんの実体験 (サムライ施策、VEXUM) を反映したい場合は質問

## 7. 補足

### 設計の意図

- **Dockerfile 単一**: Week 1 はバックエンドのみ、Week 3 で frontend と分割
- **chroma-data volume**: コンテナ再起動で再 build されるが、host に永続化するなら `./.chromadb:/app/.chromadb` でもよい。named volume の方が host 側を汚さない
- **README 30秒ルール**: タイトル / 特徴 / quickstart までスクロールせず読める長さ、デモ画像をすぐ上の方に置く

### Day 7 連携

Day 7 で v0.1.0 タグ付与、リリースノート作成、GitHub Release 公開。
