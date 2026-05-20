# Deployment Guide

axis-knowledge-rag のデプロイ手順。ローカル Docker から VPS / クラウドまでを順に説明する。

---

## Local Docker (推奨・最も簡単)

### 前提

- Docker Desktop または Docker Engine + Docker Compose Plugin がインストール済み
- `.env` ファイルが存在する (`cp .env.example .env` で作成)

### 起動

```bash
# リポジトリクローン
git clone https://github.com/kazikimaguro13/axis-knowledge-rag
cd axis-knowledge-rag

# (任意) リリースタグを手元に取り込む — clone 直後はタグが未取得の場合がある
git fetch --tags origin
git tag -l                       # v0.1.0 〜 v0.5.0 が表示されれば OK

# 環境変数ファイルを作成 (API キーは optional)
cp .env.example .env

# 起動 (初回ビルド: 5〜10 分)
docker compose up -d

# ログ確認
docker compose logs -f
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000/api/docs`

### 停止

```bash
docker compose down
```

ChromaDB データは `chroma-data` named volume に永続化されるため、`down` してもデータは消えない。

### 完全リセット (index 再構築)

```bash
docker compose down -v   # volume も削除
docker compose up -d
```

---

## Docker Compose 構成 (v0.3)

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - chroma-data:/app/.chromadb
      - ./examples/knowledge:/app/examples/knowledge:ro

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_BASE=http://backend:8000
    depends_on:
      - backend

volumes:
  chroma-data:
```

### ポイント

- `chroma-data` named volume で ChromaDB を永続化
- `examples/knowledge` はホスト側から read-only マウント (ホストで編集→コンテナに即反映)
- `NEXT_PUBLIC_API_BASE` を backend サービス名で指定 (Docker ネットワーク内で名前解決)

---

## ChromaDB の永続化とバックアップ

### バックアップ

```bash
# chroma-data volume を tar でアーカイブ
docker run --rm \
  -v chroma-data:/data \
  -v $(pwd):/backup \
  alpine \
  tar czf /backup/chroma-backup-$(date +%Y%m%d).tar.gz /data
```

### リストア

```bash
# volume を再作成してリストア
docker volume create chroma-data
docker run --rm \
  -v chroma-data:/data \
  -v $(pwd):/backup \
  alpine \
  tar xzf /backup/chroma-backup-YYYYMMDD.tar.gz -C /
```

---

## Security — `/api/ingest` token (spec_051)

`POST /api/ingest` (browser-extension の入口) は **デフォルトで無認証**です。
ローカル (`127.0.0.1`) で立てている限りはこれで十分ですが、LAN 越し /
外部公開する場合は必ず `AXIS_INGEST_TOKEN` を設定してください。設定が
ある場合のみ、リクエストごとに `X-Axis-Token` ヘッダで送られた値が
照合され、不一致は 401 になります。

```bash
# 推奨: localhost にだけ bind して uvicorn を立てる
export AXIS_INGEST_TOKEN="$(openssl rand -hex 32)"
uvicorn backend.src.api:app --host 127.0.0.1 --port 8000

# Browser Extension の Settings に同じ token を貼り、X-Axis-Token で送る
```

`AXIS_INGEST_TOKEN` を未設定にすると v0.8 互換の挙動 (無認証許容) に
なります — 互換性のために残しています。外部公開時は **必ず** 設定する
こと。CORS は `chrome-extension://*` と `localhost`/`127.0.0.1`
にしか許可していないため、デフォルトでは Web フロントから直接叩く
攻撃面はありませんが、サーバを `--host 0.0.0.0` で公開する場合は
リバースプロキシ / トークン両方を組み合わせるのが安全です。

---

## VPS / Cloud (リファレンス)

> **注意**: 以下は参考手順。v0.3 では実機検証していない。本番運用は v0.4 で対応予定。

### 前提 (共通)

環境変数を secret として外部から注入する。平文で `.env` をコンテナに含めないこと。

| 変数 | 説明 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API キー |
| `GEMINI_API_KEY` | Gemini Embedding API キー |
| `NEXT_PUBLIC_API_BASE` | Backend の公開 URL (例: `https://api.example.com`) |

---

### Fly.io

```bash
# CLI インストール
curl -L https://fly.io/install.sh | sh

# backend アプリ作成・デプロイ
fly launch --name axis-rag-backend --dockerfile Dockerfile.backend
fly secrets set ANTHROPIC_API_KEY=sk-ant-... GEMINI_API_KEY=AIza...
fly deploy

# frontend アプリ作成・デプロイ
cd frontend
fly launch --name axis-rag-frontend
fly secrets set NEXT_PUBLIC_API_BASE=https://axis-rag-backend.fly.dev
fly deploy
```

ChromaDB の永続化には Fly.io の Volume (`fly volumes create`) を使う。

---

### Google Cloud Run

```bash
# backend
gcloud run deploy axis-knowledge-rag-backend \
  --source backend/ \
  --region asia-northeast1 \
  --set-env-vars ANTHROPIC_API_KEY=sk-ant-...,GEMINI_API_KEY=AIza...

# frontend
gcloud run deploy axis-knowledge-rag-frontend \
  --source frontend/ \
  --region asia-northeast1 \
  --set-env-vars NEXT_PUBLIC_API_BASE=https://axis-knowledge-rag-backend-xxxx-an.a.run.app
```

> Cloud Run はステートレスなため、ChromaDB の永続化に Cloud Storage (GCS) または Cloud SQL + pgvector が必要 (v0.4 で検討)。

---

### TLS / リバースプロキシ

本番では frontend と backend の前段に TLS ターミネーションプロキシを置く。

#### Caddy (推奨・自動 Let's Encrypt)

```caddyfile
api.example.com {
    reverse_proxy backend:8000
}

example.com {
    reverse_proxy frontend:3000
}
```

#### nginx

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

> Caddy / nginx による前段プロキシの完全な設定は v0.4 で実装予定。

---

## Session Persistence (spec_036)

Chat session storage is now pluggable. `config.yml > chat.storage.backend`
picks the implementation:

| Backend  | When                                                | Restart-safe | Multi-worker | Multi-host |
|----------|-----------------------------------------------------|--------------|--------------|------------|
| `sqlite` (default) | Personal / single-host deployments        | Yes          | Yes (WAL)    | No         |
| `memory` | Tests, ephemeral local runs                         | No           | No           | No         |
| `redis`  | Multi-worker / multi-host production                | Yes          | Yes          | Yes        |

### SQLite default — single worker no longer required

v0.7 required `uvicorn --workers 1` (sessions lived in one process).
v0.8+ defaults to a SQLite file (`~/.axis_chat.db` by default) which is
safe across workers thanks to WAL journal mode:

```bash
# now safe
uvicorn backend.src.api:app --workers 4 --port 8000

# pick the path with config.yml
# chat:
#   storage:
#     backend: "sqlite"
#     sqlite_path: "./data/chat.db"    # or absolute path
```

Restart persistence:

```bash
SID=$(curl -s -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question": "Persistence test"}' | jq -r .session_id)

# kill + restart
pkill -f uvicorn && sleep 2
uvicorn backend.src.api:app --port 8000 &
sleep 3

curl -s "http://localhost:8000/api/chat/$SID" | jq '.messages | length'
# → 2 (history survived)
```

### Redis backend (optional)

Use when you need cross-host or unlimited horizontal scale.

```bash
# 1. install the optional dependency
pip install -e ".[redis]"

# 2. start Redis via the docker-compose profile
docker compose --profile redis-backend up -d redis

# 3. flip the backend in config.yml
cat >> config.yml <<'EOF'
chat:
  storage:
    backend: "redis"
    redis_url: "redis://localhost:6379/0"
EOF

# 4. boot the API
uvicorn backend.src.api:app --workers 4
```

Recommended Redis config for production:

```
maxmemory 256mb
maxmemory-policy allkeys-lru
appendonly yes
```

`docker-compose.yml` already passes these via `command:` in the
`redis-backend` profile.

### Privacy mode (no disk)

For ephemeral or privacy-sensitive deployments:

```yaml
chat:
  storage:
    backend: "memory"
```

Sessions live only in the worker process and are gone on restart. This
is the v0.7 behaviour.

---

## Fully On-Prem with Ollama (spec_045)

v0.9.0 added an Ollama-backed path for **embedding + generation** so the
RAG pipeline can run with zero outbound traffic. Suitable for in-house
deployments where docs cannot leave the network.

### One-time setup

```bash
# 1. Install the optional Python client (host side)
pip install -e ".[ollama]"

# 2. Bring up the Ollama daemon (off by default — gated by profile)
docker compose --profile ollama up -d ollama

# 3. Pull the models. bge-m3 = embedder (1024-dim multilingual JP/EN);
#    llama3 / qwen2.5 / etc = generator. First pull is multi-GB; subsequent
#    starts are instant.
docker exec axis-ollama ollama pull bge-m3
docker exec axis-ollama ollama pull llama3        # try llama3:70b for quality

# 4. Flip backends in config.yml
#    embedder.backend: "ollama"
#    generation.backend: "ollama"

# 5. Rebuild the index — bge-m3 (1024) and Gemini (768) are dim-incompatible,
#    so an existing ChromaDB built against Gemini cannot read Ollama vectors.
PYTHONPATH=. python3 -m scripts.build_index ./examples/knowledge --rebuild

# 6. Restart the backend
docker compose restart backend
```

### Choosing a model

| Use case | Recommended `generation.ollama.model` | Notes |
|---|---|---|
| CPU-only laptop | `llama3` (8B) | ~5 s per answer, parity well below Claude on JP |
| 1× consumer GPU (24GB) | `qwen2.5:14b` or `llama3:8b-instruct-q8_0` | Best mid-tier |
| Workstation (≥ 48GB VRAM) | `llama3:70b` or `qwen2.5:32b` | Approaches Claude for short, citation-heavy answers |

`bge-m3` is the default embedder (1024-dim, multilingual including JP).
Swap for `nomic-embed-text` (768-dim, English-only) if you want to keep
the Gemini-compatible dimensionality and only switch the generator.

### Health-check

```bash
# Should report embedder_mode=OLLAMA, rag_mode=OLLAMA
curl -s http://localhost:8000/api/health | jq
```

### Disabling Ollama

Set `embedder.backend` back to `"gemini"` (or `"dummy"`) and
`generation.backend` to `"claude"` (or `"dummy"`), rebuild the index if
the embedder changed, and restart. The optional `[ollama]` extra can stay
installed — the factory short-circuits when `backend != "ollama"`.

---

## CI / CD (GitHub Actions)

現在の CI 構成:

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `.github/workflows/ci.yml` | push / PR | ruff check + pytest (py311/py312 matrix) |
| `.github/workflows/docker.yml` | push / PR | Docker build-only (GHA layer cache) |

v0.4 予定:

- GHCR (GitHub Container Registry) への image push
- `v*` タグ push で GitHub Release 自動作成
- Fly.io / Cloud Run への自動デプロイ
