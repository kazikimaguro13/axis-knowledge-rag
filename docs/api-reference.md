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
  "version": "0.5.0",
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
      "values": ["技術記事", "メモ", "議事録", "ToDo"],
      "required": true
    },
    {
      "name": "topic",
      "type": "string",
      "required": true
    },
    {
      "name": "level",
      "type": "enum",
      "values": ["初級", "中級", "上級"],
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
  "text": "RAGとは Retrieval-Augmented Generation の略です[1]。BM25 とベクトル検索のハイブリッドが推奨されます[2]。",
  "cited_ids": ["doc_001", "doc_002"],
  "sources": [
    {
      "id": "doc_001",
      "title": "RAG パターン入門",
      "score": 0.87,
      "axes": {"category": "技術記事"},
      "body_snippet": "...",
      "path": "examples/knowledge/01-rag-patterns.md",
      "refs": ["doc_002"]
    },
    {
      "id": "doc_002",
      "title": "ハイブリッド検索",
      "score": 0.81,
      "axes": {"category": "技術記事"},
      "body_snippet": "...",
      "path": "examples/knowledge/02-hybrid-search.md",
      "refs": []
    }
  ],
  "is_dummy": false,
  "model": "claude-3-5-sonnet-20241022"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `text` | string | 生成された回答文。出典に基づく文末に `[N]` (1-indexed) インライン引用マーカーが付く。`N` は `sources[N-1]` を指す ([ADR-020](adr/ADR-020-citation-highlighting.md)) |
| `cited_ids` | array | 回答中で実際に引用された `sources[].id` の一覧 (`[N]` を解決した後のもの) |
| `sources` | array | 検索結果一覧 (SearchResult と同形式)。`[N]` の N は `sources` のインデックス + 1 |
| `is_dummy` | boolean | DUMMY モードで生成された場合 true |
| `model` | string | 使用した Claude モデル名。DUMMY 時は `"dummy"` |

> **出典の出ない回答**: LLM が `[N]` を出さなかった場合 (例: 「資料には記載がありません」) は
> `cited_ids` が空配列になる。テキスト自体は valid。

> **out-of-range marker**: LLM が誤って `[9]` のような範囲外の N を返した場合、
> サーバ側で silently strip される (警告ログのみ)。クライアントに届くテキストには
> 有効な `[N]` のみが残る。

**Errors**: 422 — バリデーションエラー (question が空など) / 500 — RAG pipeline failure

---

### `POST /api/chat`  (spec_032, v0.7)

履歴を保持した対話的 RAG。`session_id` を返すので、次のターンに再投入すれば follow-up が成立する。
代名詞 (「それの利点は?」) は Gemini Flash で自動的に standalone クエリへ書き換えられる
(失敗時は元クエリにフォールバックして UX は止まらない)。

**Request body**

```json
{
  "question": "それの利点は？",
  "session_id": "a1b2c3d4-...",
  "filters": {"category": "技術記事"},
  "top_k": 5,
  "max_tokens": 1024
}
```

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `question` | string | — | 質問文 (1〜1000 字、必須) |
| `session_id` | string \| null | `null` | 既存の session id。null/未指定で新規発番 |
| `filters` | object | `{}` | 軸フィルタ (search と同形式) |
| `top_k` | integer | `5` | 検索件数 (1–20) |
| `max_tokens` | integer | `1024` | 回答の最大トークン数 (128–4096) |

**Response 200**

```json
{
  "session_id": "a1b2c3d4-7e8f-...",
  "question": "それの利点は？",
  "rewritten_question": "RAG の利点は？",
  "answer": "RAG の主な利点は...[1]...",
  "cited_ids": ["doc_001"],
  "sources": [ /* SearchResult と同形式 */ ],
  "is_dummy": false,
  "model": "claude-3-5-sonnet-20241022"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `session_id` | string | このターンで使われた / 新規発番された session id |
| `rewritten_question` | string \| null | rewrite が実際に起きた場合のみ非 null |

**Errors**: 422 — バリデーション失敗 / 500 — 内部エラー / 503 — `config.yml > chat.enabled=false`

> **Single worker 前提**: session はサーバプロセス内 memory に置かれる。
> `uvicorn --workers >1` で動かすと worker 間で session が共有されず、
> 同じ session_id でも別履歴を見ることになる。v0.7 では `--workers 1` を維持してほしい
> (Redis 永続化は v0.8 候補 — spec_037)。

---

### `GET /api/chat/{session_id}`  (spec_032)

セッションの履歴 (全メッセージ) を取得する。

**Response 200**

```json
{
  "session_id": "a1b2c3d4-...",
  "messages": [
    {"role": "user", "content": "RAG とは?", "sources": [], "timestamp": "2026-05-14T05:00:00+00:00"},
    {"role": "assistant", "content": "RAG とは...", "sources": [...], "timestamp": "..."}
  ]
}
```

**Errors**: 404 — session_id が存在しない (TTL 切れ / 未作成 / DELETE 済み)

---

### `DELETE /api/chat/{session_id}`  (spec_032)

セッションをリセットする。成功時は `204 No Content`。

**Errors**: 404 — session_id が存在しない

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
