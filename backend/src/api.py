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
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
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
    return AxesResponse(axes=[AxisDef(**a) for a in cfg.get("axes", [])])


@app.post("/api/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    engine: SearchEngine = _state["engine"]
    try:
        results = engine.search(req.query, filters=req.filters or None, top_k=req.top_k)
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
