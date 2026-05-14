# spec_015: Day 15 — FastAPI (`backend/src/api.py`)

- **Author**: Cowork (中島)
- **Created**: 2026-05-12
- **Target**: Claude Code (`dev-b`)
- **Project**: `C:\Users\cocor\Desktop\就活\axis-knowledge-rag`
- **Status**: pending
- **Bundles**: spec_001〜014 (v0.2.0 released), `docs/spec-v2.md` Day 15 行

## 1. 目的

```
[現状]
- backend のロジックは Streamlit (`streamlit_app.py`) から直接呼び出し
- HTTP API がない、フロントエンド (Next.js) から呼べない

[変更後]
- FastAPI で以下のエンドポイントを提供:
  - `GET  /api/health` — ヘルスチェック
  - `GET  /api/axes` — 軸定義の取得 (config.yml 由来)
  - `POST /api/search` — 軸 + ベクトル hybrid 検索
  - `POST /api/answer` — RAG 回答生成
  - `GET  /api/docs` — `/api/docs` (Swagger UI 自動生成、FastAPI 標準)
- Pydantic schemas で request / response を型付け
- `uvicorn backend.src.api:app --reload` で起動、`localhost:8000`
- Streamlit はそのまま残す (バックエンド直叩き、UI 比較用 v0.2 互換維持)
```

Week 3 のキックオフ。フロントが Next.js になっても backend が独立して使える形にする。

## 2. 制約

### 触ってよいファイル

- `backend/src/api.py` — 新規
- `backend/src/schemas.py` — 新規 (Pydantic models)
- `backend/requirements.txt` — fastapi + uvicorn 追加
- `pyproject.toml` — 同上
- `backend/tests/test_api.py` — 新規 (TestClient)
- `docs/api-reference.md` — エンドポイント仕様追記
- `CHANGELOG.md`

### 触ってはいけないもの

- `backend/src/{loader,embedder,vector_store,search,rag,normalizer,integrity,marker}.py` — Streamlit からも使われ続けるので API は変更しない
- `streamlit_app.py` (Streamlit はそのまま動く、deprecated にもしない)
- `_ai_workspace/`、`docs/spec-v2.md`、`frontend/` (まだ存在しないが、ここで作るのは Day 16)

### コーディングルール

- FastAPI 0.115+、uvicorn 0.30+
- Pydantic v2 (FastAPI のデフォルト)
- CORS は `localhost:3000` (Next.js dev) と `localhost:8501` (Streamlit) を許可
- `lifespan` で SearchEngine / RAGPipeline を 1 回だけ初期化、shutdown で解放
- API レスポンスは UTF-8 (FastAPI デフォルト)

### 依存追加

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
```

## 3. やってほしいこと

### 3-1. `backend/src/schemas.py`

```python
"""Pydantic schemas for the FastAPI layer."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    embedder_mode: str
    rag_mode: str


class AxisDef(BaseModel):
    name: str
    type: str
    values: list[str] | None = None
    required: bool = False


class AxesResponse(BaseModel):
    axes: list[AxisDef]


class SearchRequest(BaseModel):
    query: str | None = Field(default=None, description="Natural-language query")
    filters: dict[str, str | int] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=50)


class SearchResultPayload(BaseModel):
    id: str
    title: str
    score: float
    axes: dict[str, str | int]
    body_snippet: str
    path: str
    refs: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    results: list[SearchResultPayload]


class AnswerRequest(BaseModel):
    question: str
    filters: dict[str, str | int] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=20)
    max_tokens: int = Field(default=1024, ge=128, le=4096)


class AnswerResponse(BaseModel):
    text: str
    cited_ids: list[str]
    sources: list[SearchResultPayload]
    is_dummy: bool
    model: str | None
```

### 3-2. `backend/src/api.py`

```python
"""FastAPI surface for axis-knowledge-rag."""

import logging
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.src.config import configure_logging, load_axes_config, settings
from backend.src.embedder import Embedder
from backend.src.normalizer import Normalizer
from backend.src.rag import RAGPipeline
from backend.src.schemas import (
    AnswerRequest,
    AnswerResponse,
    AxesResponse,
    AxisDef,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultPayload,
)
from backend.src.search import SearchEngine, SearchResult
from backend.src.vector_store import VectorStore

logger = logging.getLogger(__name__)


_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Initializing axis-knowledge-rag API...")
    store = VectorStore(path=settings.chroma_db_path)
    embedder = Embedder()
    normalizer = Normalizer.from_config(load_axes_config())
    engine = SearchEngine(store, embedder, normalizer)
    rag = RAGPipeline(engine)
    _state["engine"] = engine
    _state["rag"] = rag
    _state["embedder"] = embedder
    _state["axes_cfg"] = load_axes_config()
    yield
    _state.clear()


app = FastAPI(
    title="axis-knowledge-rag",
    description="軸検索 + RAG over YAML frontmatter Markdown",
    version="0.3.0.dev0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _pkg_version() -> str:
    try:
        return version("axis-knowledge-rag")
    except PackageNotFoundError:
        return "unknown"


def _to_payload(r: SearchResult) -> SearchResultPayload:
    return SearchResultPayload(
        id=r.id,
        title=r.title,
        score=r.score,
        axes=r.axes,  # type: ignore[arg-type]
        body_snippet=r.body_snippet,
        path=r.path,
        refs=r.refs,
    )


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=_pkg_version(),
        embedder_mode="DUMMY" if _state["embedder"].is_dummy else "GEMINI",
        rag_mode="DUMMY" if _state["rag"].is_dummy else "CLAUDE",
    )


@app.get("/api/axes", response_model=AxesResponse)
async def get_axes() -> AxesResponse:
    cfg = _state.get("axes_cfg", {"axes": []})
    return AxesResponse(
        axes=[AxisDef(**a) for a in cfg.get("axes", [])]
    )


@app.post("/api/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    engine: SearchEngine = _state["engine"]
    try:
        results = engine.search(
            req.query, filters=req.filters or None, top_k=req.top_k
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return SearchResponse(results=[_to_payload(r) for r in results])


@app.post("/api/answer", response_model=AnswerResponse)
async def answer(req: AnswerRequest) -> AnswerResponse:
    rag: RAGPipeline = _state["rag"]
    try:
        ans = rag.answer(
            req.question,
            filters=req.filters or None,
            top_k=req.top_k,
            max_tokens=req.max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return AnswerResponse(
        text=ans.text,
        cited_ids=ans.cited_ids,
        sources=[_to_payload(s) for s in ans.sources],
        is_dummy=ans.is_dummy,
        model=ans.model,
    )
```

### 3-3. `backend/tests/test_api.py`

```python
from fastapi.testclient import TestClient

from backend.src.api import app


def test_health() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "embedder_mode" in body


def test_search_empty() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/search",
            json={"query": "test", "top_k": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body


def test_answer_dummy() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/answer",
            json={"question": "test", "top_k": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "text" in body
        assert "cited_ids" in body
        assert "sources" in body


def test_axes() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/axes")
        assert resp.status_code == 200
        body = resp.json()
        assert "axes" in body
```

### 3-4. 動作確認

```bash
cd "C:\Users\cocor\Desktop\就活\axis-knowledge-rag"
pip install -e ".[dev]"

# サーバー起動
uvicorn backend.src.api:app --reload --port 8000 &
sleep 3

# ヘルスチェック
curl http://localhost:8000/api/health

# 軸取得
curl http://localhost:8000/api/axes

# 検索
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"RAGとは","top_k":3}'

# 回答
curl -X POST http://localhost:8000/api/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"RAGとは","top_k":3}'

# Swagger UI
curl http://localhost:8000/api/docs

# 停止
kill %1
```

### 3-5. コミット

1. `chore: add fastapi and uvicorn to dependencies`
2. `feat: add Pydantic schemas for the API layer`
3. `feat: implement FastAPI endpoints (health/axes/search/answer)`
4. `test: add FastAPI TestClient tests`
5. `docs: update api-reference.md with HTTP endpoints`
6. `docs: changelog Day 15`

`git push origin main` (dev-b)

### 3-6. result_015.md

特に:

- 起動ログ抜粋
- 4 endpoint の curl 出力
- TestClient 4 件 PASS
- Swagger UI スクショは取れない、URL のみ記載
- Streamlit と API が共存できる確認

## 4. 成功条件

- [ ] `uvicorn backend.src.api:app --reload` が起動
- [ ] 4 endpoint 全て 200 OK
- [ ] Swagger UI `/api/docs` がアクセス可能
- [ ] TestClient テスト全 PASS
- [ ] Streamlit が壊れていない (`streamlit run streamlit_app.py` 起動確認)
- [ ] dev-b で push 成功

## 5. 出力先

`_ai_workspace/bridge/outbox/result_015.md`

## 6. 質問

- **CORS allow_origins**: 開発は localhost、本番デプロイ時にどう設定するかは Week 3 後半で考える
- **rate limit**: 入れない (local-first OSS なので外部呼び出しを保護する意味は薄い)
- **WebSocket / streaming**: Week 3 では同期 API のみ、ストリーミング (SSE) は Day 18 で導入を検討

## 7. 補足

### 設計の意図

- **lifespan で 1 回 init**: SearchEngine / RAGPipeline は重い、リクエストごとに作らない
- **Pydantic を schemas.py に集約**: 型変更時の影響を 1 ファイルに閉じる
- **`_to_payload` helper**: dataclass → Pydantic 変換を 1 箇所に
- **Streamlit を残す**: Next.js 移行が間に合わなかった時の retreat 用 (仕様書 11 章の遅延時 fallback)

### Day 16 連携

Next.js が `lib/api.ts` で fetch するときの型は schemas.py と一致させる。Day 16 で `/api/axes` を叩いて軸フィルタ UI を動的生成する。
