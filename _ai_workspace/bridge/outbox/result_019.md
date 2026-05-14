# result_019: Day 19 — Docker 分割 (backend / frontend) + E2E

- **Spec**: `inbox/spec_019.md`
- **Executor**: Claude Code (dev-b)
- **Started**: 2026-05-13 15:05
- **Finished**: 2026-05-13 15:18
- **Status**: partial (実装は完了、Docker 未インストール環境のため runtime E2E は user 側で要実施)

## 1. 要約

- 旧 `Dockerfile` (Streamlit 単一サービス) を `Dockerfile.streamlit` に rename (`git mv`、100% rename として記録) し、retreat 用に保持。
- `Dockerfile.backend` (FastAPI / `python:3.11-slim` / `HEALTHCHECK /api/health` / `EXPOSE 8000`) と `Dockerfile.frontend` (Next.js / `node:20-alpine` multi-stage / standalone runtime / 非 root `nextjs:1001` / `EXPOSE 3000`) を新規追加。
- `docker-compose.yml` を 2 サービス構成に書き直し (`backend` healthcheck → `frontend` が `service_healthy` で待つ、ChromaDB は named volume `chroma-data` で永続化)。
- `frontend/next.config.mjs` に `output: "standalone"` を有効化、ルート `.dockerignore` をモノレポ向けに更新、`frontend/.dockerignore` を新規作成。
- spec 通り 7 コミットに分割して `feat/spec_019-docker-split` ブランチに push 済み。`docker compose build/up` 自身は dev-b 環境に Docker が未インストールのため未実施 (詳細は §5 参照)。

## 2. 変更ファイル

```
 .dockerignore                      |  8 ++++++--
 CHANGELOG.md                       |  9 +++++++++
 Dockerfile.backend                 | 25 +++++++++++++++++++++++++
 Dockerfile.frontend                | 32 ++++++++++++++++++++++++++++++++
 Dockerfile => Dockerfile.streamlit |  0
 docker-compose.yml                 | 26 +++++++++++++++++++++++---
 frontend/.dockerignore             |  5 +++++
 frontend/next.config.mjs           |  5 ++++-
 8 files changed, 104 insertions(+), 6 deletions(-)
```

## 3. 主要な変更点（ハイライト）

### `Dockerfile.backend` (新規)

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

CMD ["sh", "-c", "python -m scripts.build_index ./examples/knowledge && uvicorn backend.src.api:app --host 0.0.0.0 --port 8000"]
```

旧 image との差分: `streamlit_app.py` を COPY しない / `curl` を入れて `HEALTHCHECK` を追加 / `EXPOSE` を 8501 → 8000 / CMD は streamlit ではなく uvicorn を起動。`build_index` は CMD の中で 1 回実行され、`chroma-data` ボリュームが永続化するので 2 回目以降は append/idempotent 動作。

### `Dockerfile.frontend` (新規 / multi-stage)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_API_BASE=http://backend:8000
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
```

意図: builder で `npm ci` + `next build` を実行し、runner には `.next/standalone` / `.next/static` / `public` だけを非 root user 所有でコピー → runtime に node_modules や build ツールを残さずスリム化。`HOSTNAME=0.0.0.0` は Next.js standalone server.js が listen 先に使う環境変数。

### `docker-compose.yml` (全面書き直し)

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports: ["8000:8000"]
    env_file: [.env]
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
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_BASE=http://localhost:8000
    depends_on:
      backend:
        condition: service_healthy
volumes:
  chroma-data:
```

意図: `depends_on.condition: service_healthy` により backend が `/api/health` で 200 を返すようになるまで frontend は起動しない → ブラウザが先に開いて fetch エラーを出す事故を防止。`NEXT_PUBLIC_API_BASE` はコンテナ内 service 名ではなく `localhost:8000` を渡す (ブラウザ JS は host 側で動くため)。

### `frontend/next.config.mjs`

```diff
 /** @type {import('next').NextConfig} */
-const nextConfig = {};
-export default nextConfig;
+const nextConfig = {
+  output: "standalone",
+  reactStrictMode: true,
+};
+export default nextConfig;
```

意図: standalone 出力を有効化 → `.next/standalone/` に `server.js` + 必要最小限の `node_modules` が出力され、Dockerfile.frontend がそれだけを runtime にコピー。

### `.dockerignore` (ルート) + `frontend/.dockerignore` (新規)

ルート: `frontend/node_modules` / `frontend/.next` / `.env.local` / `*.md` (README, CHANGELOG は `!` で除外解除) を追加して monorepo 向けに整理。`frontend/.dockerignore`: `node_modules` / `.next` / `out` / `.env*.local`。

## 4. テスト・品質チェック結果

```
$ python3 -c "import yaml; d=yaml.safe_load(open('docker-compose.yml')); ..."
OK services: ['backend', 'frontend']
OK volumes: ['chroma-data']
backend.ports: ['8000:8000']
frontend.depends_on: {'backend': {'condition': 'service_healthy'}}

$ git log --oneline 9c5c57b..HEAD
74c6b80 docs: changelog Day 19
5a03ae3 chore: update .dockerignore for monorepo layout
d90e774 chore: rename old Dockerfile to Dockerfile.streamlit
5ff3f0d chore: enable Next.js standalone output mode
bab2195 feat: update docker-compose to two services (backend + frontend)
49f3c9b feat: add Dockerfile.frontend with multi-stage Next.js standalone
98878db feat: add Dockerfile.backend for FastAPI

$ git push -u origin feat/spec_019-docker-split
 * [new branch]      feat/spec_019-docker-split -> feat/spec_019-docker-split
branch 'feat/spec_019-docker-split' set up to track 'origin/feat/spec_019-docker-split'.
```

⚠️ **`docker compose build/up` 実機検証は実施できず** (本 dev-b 環境に Docker が未インストール、`/usr/bin/docker` 不在 / `/var/run/docker.sock` 不在を確認)。spec §3-7 の検証スクリプトは §7 に転記したので user 側で実行をお願いしたい。

## 5. 想定外だったこと / 判断ポイント

- **Docker が dev-b 環境に未インストール**: `which docker` も `/var/run/docker.sock` も存在せず、image build / image size 計測 / compose up は実施不能。実装ファイル群は spec 通り作成して push 済みで、user 側 (host の Docker Desktop / WSL Docker) での実行を前提に §7 の手順を残した。
- **frontend/next.config.js → next.config.mjs**: spec §3-3 は `next.config.js` (CommonJS) 形式を指示していたが、既存ファイルは `next.config.mjs` (Next.js 14 デフォルトの ESM 形式)。両方が存在すると Next.js は警告を出すため、新規 `.js` 作成ではなく既存 `.mjs` を ESM 構文 (`export default`) で更新する方を採用した (commit `5ff3f0d` のメッセージにも明記)。
- **Dockerfile rename の commit 順序**: spec の commit 順 (新 Dockerfile.backend → ... → 旧 Dockerfile rename) では `git mv` が一旦中断する形になるが、`git restore --staged` で stage を一旦 reset → 各 commit ごとに `git add` する方式で対応。結果として commit `d90e774` は `Dockerfile => Dockerfile.streamlit (100%)` と git が rename 認識した状態で記録されている。
- **push 先**: spec §3-8 は `git push origin main` (dev-b) と書かれていたが、user 指示の通り `feat/spec_019-docker-split` フィーチャーブランチに push (`-u` で upstream 設定)。main には直接 push していない。

## 6. Open questions

なし (実装完了、runtime 検証だけ user 側で残)

## 7. 動作確認手順（ユーザー）

Docker が動く host (Docker Desktop / WSL Docker / Linux host) で以下を実行:

```bash
cd ~/projects/axis-knowledge-rag
git fetch origin
git checkout feat/spec_019-docker-split

# .env が無ければ .env.example をコピーして API キー埋める
[ -f .env ] || cp .env.example .env

# 1. build
time docker compose build
# 期待: backend + frontend 両方ビルド成功

# 2. up (バックグラウンド)
docker compose up -d
sleep 30   # backend healthcheck 待ち

# 3. backend エンドポイント
curl -s http://localhost:8000/api/health
# 期待: {"status":"ok",...}

curl -s http://localhost:8000/api/axes | head -20
# 期待: 軸定義 JSON

curl -I http://localhost:8000/api/docs
# 期待: HTTP/1.1 200 OK (Swagger UI)

# 4. frontend (UI)
curl -I http://localhost:3000
# 期待: HTTP/1.1 200 OK

# 5. CORS / frontend → backend の通信確認 (RAG answer)
curl -s -X POST http://localhost:8000/api/answer \
  -H "Content-Type: application/json" \
  -d '{"query":"RAG とは?","top_k":3,"axes":{}}' | head -40
# 期待: answer / cited_ids / dummy_mode フィールドが返る

# 6. ブラウザで http://localhost:3000 を開く → 検索 + answer toggle が動く

# 7. image size 計測
docker images | grep -E 'axis-knowledge-rag|<none>'
# 期待: backend ~400-600MB / frontend ~150-250MB (standalone)

# 8. 後片付け
docker compose logs --tail 30
docker compose down
# ChromaDB を消したいときは: docker compose down -v
```

期待結果:
- `docker compose up` で backend + frontend 両方起動
- `localhost:3000` で Next.js UI、`localhost:8000/api/docs` で Swagger UI が表示
- frontend → backend の CORS 通信が成功 (`/api/answer` で answer が返る)
- ChromaDB は named volume `chroma-data` に永続化 (`docker compose down` → `up` で index が残る)

## 8. 次の提案（任意）

- **spec_020 候補**: 検証が通った時点で `docker compose build` の所要時間と各 image のサイズを `docs/deployment.md` に追記 (Day 20 の README デモ GIF と一緒に portfolio 用の数字として残すと面接で使える)。
- **改善案**: `Dockerfile.backend` の `build_index` を毎回起動時に実行している。1000 ドキュメント超で起動が遅くなる場合は entrypoint で `[ -d /app/.chromadb/<collection> ]` 判定で skip するロジックを追加 (今は数十ドキュメントなので不要)。
- **改善案**: GHA `docker.yml` を 2 サービス対応に拡張 (backend / frontend それぞれビルドできるか CI で検証)。現状は旧 single Dockerfile 想定のまま。
