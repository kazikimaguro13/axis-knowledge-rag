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
git tag -l                       # v0.1.0 〜 v0.4.0 が表示されれば OK

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
