# API Reference

axis-knowledge-rag FastAPI HTTP layer — introduced in Day 15 (v0.3).

Base URL: `http://localhost:8000`

Interactive docs (Swagger UI): `http://localhost:8000/api/docs`

---

## Endpoints

### `GET /api/health`

ヘルスチェック。embedder / RAG の動作モードを返す。

**Response 200**

```json
{
  "status": "ok",
  "version": "0.3.0",
  "embedder_mode": "DUMMY",
  "rag_mode": "DUMMY"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `status` | string | 常に `"ok"` |
| `version` | string | パッケージバージョン (pip install 済みなら semver) |
| `embedder_mode` | string | `"DUMMY"` または `"GEMINI"` |
| `rag_mode` | string | `"DUMMY"` または `"CLAUDE"` |

**Errors**: なし (常に 200 を返す)

---

### `GET /api/axes`

`config.yml` で定義された軸一覧を返す。フロントエンドの AxisFilter が起動時に呼ぶ。

**Response 200**

```json
{
  "axes": [
    {
      "name": "category",
      "type": "enum",
      "values": ["技術記事", "ノウハウ", "メモ"],
      "required": false
    },
    {
      "name": "level",
      "type": "enum",
      "values": ["入門", "中級", "上級"],
      "required": false
    }
  ]
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `axes` | array | 軸定義の配列 |
| `axes[].name` | string | 軸名 (config.yml の `axes:` キー) |
| `axes[].type` | string | `"enum"` / `"string"` / `"integer"` |
| `axes[].values` | array \| null | `enum` 型の場合の選択肢一覧 |
| `axes[].required` | boolean | 必須かどうか |

**Errors**: 500 — config.yml の読み込み失敗

---

### `POST /api/search`

軸フィルタ + ベクトル類似度によるハイブリッド検索。

**Request body**

```json
{
  "query": "RAGとは",
  "filters": {"category": "技術記事"},
  "top_k": 5
}
```

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `query` | string \| null | `null` | 自然言語クエリ。null の場合は軸フィルタのみで絞り込む |
| `filters` | object | `{}` | 軸フィルタ (key: 軸名, value: 値) |
| `top_k` | integer | `5` | 取得件数 (1–50) |

**Response 200**

```json
{
  "results": [
    {
      "id": "doc_001",
      "title": "RAG パターン入門",
      "score": 0.87,
      "axes": {"category": "技術記事", "level": "中級"},
      "body_snippet": "RAG (Retrieval-Augmented Generation) とは...",
      "path": "examples/knowledge/01-rag-patterns.md",
      "refs": ["doc_002"]
    }
  ]
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `results` | array | 検索結果の配列 (score 降順) |
| `results[].id` | string | ドキュメント ID (`doc_NNN` 形式) |
| `results[].title` | string | ドキュメントタイトル |
| `results[].score` | float | ベクトル類似度スコア (0.0〜1.0) |
| `results[].axes` | object | メタデータ軸 (生の値) |
| `results[].body_snippet` | string | 本文の先頭 200 文字程度のスニペット |
| `results[].path` | string | ソースファイルパス |
| `results[].refs` | array | 参照 ID 一覧 |

**Errors**: 500 — search engine failure

---

### `POST /api/answer`

RAG 回答生成。検索 + Claude による回答文を返す。`ANTHROPIC_API_KEY` が未設定の場合は DUMMY 回答。

**Request body**

```json
{
  "question": "RAGとは何ですか？",
  "filters": {},
  "top_k": 5,
  "max_tokens": 1024
}
```

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `question` | string | — | 質問文 (必須) |
| `filters` | object | `{}` | 軸フィルタ |
| `top_k` | integer | `5` | 検索件数 (1–20) |
| `max_tokens` | integer | `1024` | 回答の最大トークン数 (128–4096) |

**Response 200**

```json
{
  "text": "RAGとは Retrieval-Augmented Generation の略で...[doc_001]...",
  "cited_ids": ["doc_001"],
  "sources": [
    {
      "id": "doc_001",
      "title": "RAG パターン入門",
      "score": 0.87,
      "axes": {"category": "技術記事"},
      "body_snippet": "...",
      "path": "examples/knowledge/01-rag-patterns.md",
      "refs": ["doc_002"]
    }
  ],
  "is_dummy": false,
  "model": "claude-3-5-sonnet-20241022"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `text` | string | 生成された回答文 (`[doc_NNN]` 形式の出典 ID を含む) |
| `cited_ids` | array | 回答中で引用された ID 一覧 |
| `sources` | array | 検索結果一覧 (SearchResult と同形式) |
| `is_dummy` | boolean | DUMMY モードで生成された場合 true |
| `model` | string | 使用した Claude モデル名。DUMMY 時は `"dummy"` |

**Errors**: 422 — バリデーションエラー (question が空など) / 500 — RAG pipeline failure

---

### `GET /api/docs`

Swagger UI (自動生成)。ブラウザで `http://localhost:8000/api/docs` を開くとインタラクティブに試せる。

---

## 起動方法

```bash
# 依存インストール
pip install -e ".[dev]"

# 開発サーバー (ホットリロード付き)
uvicorn backend.src.api:app --reload --port 8000

# Docker 経由
docker compose up backend
```

## CORS

開発環境で許可しているオリジン:

- `http://localhost:3000` — Next.js dev server
- `http://localhost:8501` — Streamlit (レガシー)

本番デプロイ時は `CORS_ORIGINS` 環境変数で追加のオリジンを設定する (v0.4 で実装予定)。

## エラーレスポンス形式

FastAPI 標準の `HTTPException` を使用:

```json
{
  "detail": "エラーの詳細メッセージ"
}
```

| HTTP ステータス | 意味 |
|---|---|
| 422 Unprocessable Entity | Pydantic バリデーションエラー (request body 不正) |
| 500 Internal Server Error | SearchEngine / RAGPipeline の予期しないエラー |
