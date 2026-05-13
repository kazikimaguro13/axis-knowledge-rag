# API Reference

axis-knowledge-rag FastAPI HTTP layer — introduced in Day 15.

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
  "version": "unknown",
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

---

### `GET /api/axes`

`config.yml` で定義された軸一覧を返す。

**Response 200**

```json
{
  "axes": [
    {
      "name": "category",
      "type": "enum",
      "values": ["技術記事", "ノウハウ", "メモ"],
      "required": false
    }
  ]
}
```

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
| `query` | string \| null | `null` | 自然言語クエリ。null の場合は軸のみで絞り込む |
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
      "axes": {"category": "技術記事"},
      "body_snippet": "RAG (Retrieval-Augmented Generation) とは...",
      "path": "examples/knowledge/01-rag-patterns.md",
      "refs": ["doc_002"]
    }
  ]
}
```

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
| `question` | string | — | 質問文 |
| `filters` | object | `{}` | 軸フィルタ |
| `top_k` | integer | `5` | 検索件数 (1–20) |
| `max_tokens` | integer | `1024` | 回答の最大トークン数 (128–4096) |

**Response 200**

```json
{
  "text": "RAGとは...[doc_001]...",
  "cited_ids": ["doc_001"],
  "sources": [...],
  "is_dummy": false,
  "model": "claude-3-5-sonnet-20241022"
}
```

---

## 起動方法

```bash
# 依存インストール
pip install -e ".[dev]"

# 開発サーバー
uvicorn backend.src.api:app --reload --port 8000
```

## CORS

開発環境で許可しているオリジン:

- `http://localhost:3000` — Next.js dev server
- `http://localhost:8501` — Streamlit

本番デプロイ時の CORS 設定は Day 18 以降で検討。
