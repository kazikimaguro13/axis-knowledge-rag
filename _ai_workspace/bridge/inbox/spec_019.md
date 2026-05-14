# spec_019: Day 19 — Docker 分割 (backend / frontend) + E2E

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `~/projects/axis-knowledge-rag` (WSL Ubuntu)
- **Status**: pending
- **Bundles**: spec_001〜018, `docs/spec-v2.md` Day 19 行

## 1. 目的

```
[現状]
- Week 1 で作った Dockerfile は単一 (Streamlit + バックエンド)
- Week 3 では Next.js + FastAPI の 2 サービス構成
- 既存 Dockerfile は frontend を含まない

[変更後]
- `Dockerfile.backend` — FastAPI を 8000 ポートで起動
- `Dockerfile.frontend` — Next.js を 3000 ポートで起動
- `docker-compose.yml` を 2 サービスに更新 (backend + frontend)
- backend が起動した後 frontend が立ち上がる依存関係
- ChromaDB 永続化、build_index は backend 起動時に 1 回だけ実行
- `docker compose up` で localhost:3000 (UI) + :8000 (API) + :8000/api/docs (Swagger) 全部見える
- 旧 Week 1 Dockerfile は削除 or `Dockerfile.streamlit` にリネームして retreat 用
```

## 2. 制約

### 触ってよいファイル

- `Dockerfile.backend` — 新規
- `Dockerfile.frontend` — 新規
- `Dockerfile` — 削除 or `Dockerfile.streamlit` にリネーム
- `docker-compose.yml` — 全面書き直し
- `.dockerignore` — 確認 / 更新
- `frontend/.dockerignore` — 新規
- `frontend/next.config.js` — output: "standalone" を追加 (Docker image を軽くする)
- `CHANGELOG.md`

### 触ってはいけないもの

- backend / frontend のソース (除く next.config.js)
- `_ai_workspace/`、`docs/spec-v2.md`

### コーディングルール

- backend image は `python:3.11-slim`、frontend image は `node:20-alpine`
- multi-stage build を frontend で使用 (build → runtime)
- `EXPOSE 8000` / `EXPOSE 3000`
- compose の `depends_on` で backend を先に起動、healthcheck で backend が ready になるまで frontend を待つ
- chromadb の永続化は named volume `chroma-data`

## 3. やってほしいこと

### 3-1. `Dockerfile.backend`

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libstdc++6 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend
COPY scripts ./scripts
COPY examples ./examples
COPY config.yml ./

RUN pip install --no-cache-dir -e .

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -f http://localhost:8000/api/health || exit 1

# build_index は最初の起動で 1 回だけ、その後 uvicorn 起動
CMD ["sh", "-c", "python -m scripts.build_index ./examples/knowledge && uvicorn backend.src.api:app --host 0.0.0.0 --port 8000"]
```

### 3-2. `Dockerfile.frontend`

```dockerfile
# ===== Build stage =====
FROM node:20-alpine AS builder
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ===== Runtime stage =====
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_BASE=http://backend:8000

RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

# Use Next.js standalone output for slim runtime
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
```

### 3-3. `frontend/next.config.js` 更新

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
};
module.exports = nextConfig;
```

### 3-4. `docker-compose.yml`

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - chroma-data:/app/.chromadb
      - ./examples/knowledge:/app/examples/knowledge:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 20s

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_BASE=http://localhost:8000
    depends_on:
      backend:
        condition: service_healthy

volumes:
  chroma-data:
```

### 3-5. `.dockerignore` 更新

ルート:

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
.env.local
frontend/node_modules
frontend/.next
.venv
venv
*.md
!README.md
!CHANGELOG.md
```

`frontend/.dockerignore`:

```
node_modules
.next
out
.env
.env.local
```

### 3-6. 旧 Dockerfile の処理

`Dockerfile` を `Dockerfile.streamlit` にリネーム、`CMD` を `streamlit run` のままにして retreat 用に保持。

### 3-7. 動作確認

```bash
cd ~/projects/axis-knowledge-rag

docker compose build
# 期待: backend と frontend 両方ビルド成功

docker compose up -d
sleep 30  # backend health check 待ち

# Backend
curl http://localhost:8000/api/health
# 期待: {"status":"ok",...}

curl http://localhost:8000/api/axes
# 期待: 軸定義 JSON

# Frontend
curl -I http://localhost:3000
# 期待: 200 OK

# Swagger
curl -I http://localhost:8000/api/docs
# 期待: 200 OK

docker compose logs --tail 30

docker compose down
```

### 3-8. コミット

1. `feat: add Dockerfile.backend for FastAPI`
2. `feat: add Dockerfile.frontend with multi-stage Next.js standalone`
3. `feat: update docker-compose to two services (backend + frontend)`
4. `chore: enable Next.js standalone output mode`
5. `chore: rename old Dockerfile to Dockerfile.streamlit`
6. `chore: update .dockerignore for monorepo layout`
7. `docs: changelog Day 19`

`git push origin main` (dev-b)

### 3-9. result_019.md

- `docker compose build` の所要時間 (frontend が node_modules 含むので長い)
- 各 image のサイズ (`docker images axis-knowledge-rag*`)
- compose up 後の動作確認スクリプトの全結果
- frontend → backend の CORS が通っているか (`/api/answer` を叩いて確認)

## 4. 成功条件

- [ ] `docker compose up` で backend + frontend 両方起動
- [ ] `localhost:3000` で UI が見える
- [ ] `localhost:8000/api/docs` で Swagger UI
- [ ] CORS で frontend → backend 通信成功
- [ ] ChromaDB が named volume に永続化
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_019.md`

## 6. 質問

- **`NEXT_PUBLIC_API_BASE` の値**: `localhost:8000` でブラウザから叩く / `backend:8000` で frontend container から叩く。ブラウザ JS は browser context で動くので **`localhost:8000`** が正しい。container 内通信は使わない
- **frontend image size**: Next.js standalone でも 200MB 程度になる可能性、許容
- **backend の build_index タイミング**: CMD で build_index → uvicorn の順序。volume の chroma-data が空のときは 1 回だけ走る、既に index あれば skip するロジックを入れる選択肢 (今回は毎回 reset せず append)

## 7. 補足

### 設計の意図

- **multi-stage build**: 最終 image に build ツールを含めない、サイズ削減
- **standalone output**: Next.js の standalone モードで server.js を含むスリムな runtime
- **healthcheck**: frontend が backend より先に立ち上がって fetch エラーを出す事故を防ぐ
- **Dockerfile.streamlit を残す**: 採用面接で「2 種類の UI が用意されている、Week 1 → Week 3 の進化が辿れる」と説明できる

### Day 20 連携

Day 20 で README にデモ GIF を載せる。`docker compose up` で動かして OBS / ScreenToGif で録画する手順を README に書く。
