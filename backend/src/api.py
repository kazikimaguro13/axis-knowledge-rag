"""FastAPI surface for axis-knowledge-rag."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.src.config import (
    configure_logging,
    load_app_config,
    load_axes_config,
    settings,
)
from backend.src.conversation import (
    ConversationStore,
    configure_default_store,
    make_conversation_store,
)
from backend.src.embedder import make_embedder
from backend.src.feedback import FeedbackStore, make_feedback_store
from backend.src.gap_detection import GapStore, make_gap_store
from backend.src.graph import KnowledgeGraph, build_default_graph
from backend.src.normalizer import Normalizer
from backend.src.rag import RAGPipeline, make_generation_backend
from backend.src.schemas import (
    AnswerRequest,
    AnswerResponse,
    AxesResponse,
    AxisDef,
    ChatHistoryResponse,
    ChatMessagePayload,
    ChatRequest,
    ChatResponseModel,
    FeedbackReportResponse,
    FeedbackRequest,
    FeedbackResponse,
    GapReportResponse,
    GraphEdgeModel,
    GraphNodeModel,
    GraphResponse,
    GraphStats,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    NeighborResponse,
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
    app_cfg = load_app_config()
    embedder = make_embedder(app_cfg.embedder)
    normalizer = Normalizer.from_config(load_axes_config())
    # spec_051 HIGH-1: detect embedder ↔ index dim mismatch at startup.
    # Empty store (probe returns None) skips silently — first ingest will
    # set the dim. A mismatch is fatal because every subsequent query
    # would crash inside Chroma with an opaque shape error.
    try:
        store_dim = store.probe_dim()
    except Exception as e:  # noqa: BLE001
        logger.warning("dim verification skipped: %s", e)
        store_dim = None
    if store_dim is not None and store_dim != embedder.dim:
        raise RuntimeError(
            f"Embedding dim mismatch: chroma store has dim={store_dim}, "
            f"embedder ({type(embedder).__name__}) reports dim={embedder.dim}. "
            f"config.yml で embedder.backend を変更した場合は "
            f"`PYTHONPATH=. python3 -m scripts.build_index examples/knowledge --rebuild` "
            f"を実行して index を rebuild してください。"
        )
    pd = app_cfg.retrieval.parent_doc
    if pd.enabled and not store.has_parents():
        logger.warning(
            "parent_doc.enabled=true but parents.json is missing — falling back "
            "to legacy file-level search. Run scripts/build_index.py --rebuild "
            "--mode parent_doc to populate it."
        )
        parent_doc_enabled = False
    else:
        parent_doc_enabled = pd.enabled
    graph: KnowledgeGraph | None = None
    if app_cfg.graph.enabled:
        # spec_042 LOW #5: building the graph walks the knowledge dir + parses
        # frontmatter, which can stall lifespan for seconds on 1000+ doc
        # corpora. Run it on the default executor so the event loop stays
        # responsive (e.g. for liveness probes).
        loop = asyncio.get_running_loop()
        try:
            graph = await loop.run_in_executor(
                None, build_default_graph, app_cfg.graph.knowledge_dir
            )
            logger.info("knowledge graph stats: %s", graph.stats())
        except Exception as e:  # noqa: BLE001
            logger.warning("failed to build knowledge graph: %s — disabling /api/graph", e)
            graph = None
    # spec_048: build the gap store first so both the search engine
    # (no_results / low_score) and the RAG pipeline (llm_no_info) can
    # share the same backing SQLite. Disabled config → both hooks become
    # no-ops without any further conditionals at the call sites.
    gap_store = make_gap_store(app_cfg.gap)
    if gap_store is not None:
        logger.info("gap store: %s", type(gap_store).__name__)
    else:
        logger.info("gap store: disabled (gap.enabled=false)")
    engine = SearchEngine(
        store,
        embedder,
        normalizer,
        parent_doc_enabled=parent_doc_enabled,
        top_k_children=pd.top_k_children,
        graph=graph,
        gap_store=gap_store,
        gap_low_score_threshold=app_cfg.gap.low_score_threshold,
    )
    rag = RAGPipeline(
        engine,
        context_max_chars=app_cfg.rag.context_max_chars,
        backend=make_generation_backend(app_cfg.generation),
        gap_store=gap_store,
    )
    chat_store = make_conversation_store(app_cfg.chat)
    configure_default_store(chat_store)
    logger.info(
        "chat store: %s (backend=%s)",
        type(chat_store).__name__,
        app_cfg.chat.storage.backend,
    )
    feedback_store = make_feedback_store(app_cfg.feedback)
    if feedback_store is not None:
        logger.info("feedback store: %s", type(feedback_store).__name__)
    else:
        logger.info("feedback store: disabled (feedback.enabled=false)")
    _state["engine"] = engine
    _state["rag"] = rag
    _state["embedder"] = embedder
    _state["axes_cfg"] = load_axes_config()
    _state["chat_store"] = chat_store
    _state["chat_cfg"] = app_cfg.chat
    _state["graph"] = graph
    _state["graph_cfg"] = app_cfg.graph
    _state["knowledge_dir"] = app_cfg.graph.knowledge_dir
    _state["feedback_store"] = feedback_store
    _state["feedback_cfg"] = app_cfg.feedback
    _state["gap_store"] = gap_store
    _state["gap_cfg"] = app_cfg.gap
    try:
        yield
    finally:
        try:
            chat_store.close()
        except Exception:  # noqa: BLE001
            logger.warning("chat store close failed", exc_info=True)
        if feedback_store is not None:
            try:
                feedback_store.close()
            except Exception:  # noqa: BLE001
                logger.warning("feedback store close failed", exc_info=True)
        if gap_store is not None:
            try:
                gap_store.close()
            except Exception:  # noqa: BLE001
                logger.warning("gap store close failed", exc_info=True)
        _state.clear()


def _pkg_version() -> str:
    try:
        return version("axis-knowledge-rag")
    except PackageNotFoundError:
        return "unknown"


def _describe_embedder(e) -> str:
    if e.is_dummy:
        return "DUMMY"
    from backend.src.embedder import OllamaEmbedder

    if isinstance(e, OllamaEmbedder):
        return "OLLAMA"
    return "GEMINI"


def _describe_rag(r) -> str:
    if r.is_dummy:
        return "DUMMY"
    backend = getattr(r, "backend_name", None)
    return backend or "CLAUDE"


app = FastAPI(
    title="axis-knowledge-rag",
    description="軸検索 + RAG over YAML frontmatter Markdown",
    version=_pkg_version(),
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# spec_046: allow the Chrome MV3 extension (chrome-extension://<id>) plus any
# localhost port for dev (frontend on :3000, Streamlit on :8501, etc.). Starlette
# CORSMiddleware does not support wildcards in ``allow_origins`` literally, so
# we use ``allow_origin_regex``. ``allow_credentials`` must be False whenever
# the matched origin set is open (browsers reject credentials + wildcard-like
# matches anyway).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?)$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


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
        embedder_mode=_describe_embedder(_state["embedder"]),
        rag_mode=_describe_rag(_state["rag"]),
    )


@app.get("/api/axes", response_model=AxesResponse)
async def get_axes() -> AxesResponse:
    cfg = _state.get("axes_cfg", {"axes": []})
    return AxesResponse(axes=[AxisDef(**a) for a in cfg.get("axes", [])])


# ---------------------------------------------------------------------------
# spec_046: /api/ingest — browser-extension capture
# spec_051 MID-1: opt-in token auth — when AXIS_INGEST_TOKEN is set in the
# environment, every request must carry a matching ``X-Axis-Token`` header.
# When unset, behaviour is the v0.8 default (no auth) so existing local-only
# deployments keep working without config changes.
# ---------------------------------------------------------------------------


def _require_ingest_token(x_axis_token: str | None) -> None:
    """401 when AXIS_INGEST_TOKEN is configured and the header doesn't match.

    Read at call-time (not at import) so tests can monkey-patch
    ``os.environ`` after the app has been built.
    """
    expected = (os.environ.get("AXIS_INGEST_TOKEN", "") or "").strip()
    if not expected:
        return
    if x_axis_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-Axis-Token")


@app.post("/api/ingest", response_model=IngestResponse)
async def post_ingest(
    req: IngestRequest,
    x_axis_token: str | None = Header(default=None, alias="X-Axis-Token"),
) -> IngestResponse:
    """Persist a captured web page as YAML+Markdown under ``knowledge_dir``.

    The browser extension posts URL + title + body (+ optional user
    selection); we write a fresh ``web_<timestamp>_<slug>.md`` file. The
    operation is intentionally non-idempotent — every call yields a new
    timestamped file, which is also how name collisions are avoided.
    """
    _require_ingest_token(x_axis_token)

    # Lazy import keeps the ingest_web module out of the cold-start path for
    # deployments that never use the browser extension.
    from backend.src.ingest_web import save_web_page

    knowledge_dir = _state.get("knowledge_dir", "./examples/knowledge")
    try:
        path = save_web_page(
            url=req.url,
            title=req.title,
            body=req.body,
            selected_text=req.selected_text,
            knowledge_dir=knowledge_dir,
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"failed to write file: {e}") from e
    return IngestResponse(saved_path=str(path), doc_id=path.stem)


@app.post("/api/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    engine: SearchEngine = _state["engine"]
    graph_cfg = _state.get("graph_cfg")
    # config-level default (expand_on_search) is OR'd with the request flag,
    # so admins can flip the default without touching callers.
    do_expand = req.graph_expand or bool(graph_cfg and graph_cfg.expand_on_search)
    try:
        results = engine.search(
            req.query,
            filters=req.filters or None,
            top_k=req.top_k,
            graph_expand=do_expand,
            graph_hop=req.graph_hop,
            graph_max_neighbors=req.graph_max_neighbors,
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


# ---------------------------------------------------------------------------
# spec_032: /api/chat — conversational RAG
# ---------------------------------------------------------------------------


@app.post("/api/chat", response_model=ChatResponseModel)
async def post_chat(req: ChatRequest) -> ChatResponseModel:
    rag: RAGPipeline = _state["rag"]
    store: ConversationStore = _state["chat_store"]
    chat_cfg = _state["chat_cfg"]
    if not chat_cfg.enabled:
        raise HTTPException(status_code=503, detail="chat is disabled in config.yml")
    try:
        resp = rag.chat(
            req.question,
            session_id=req.session_id,
            filters=req.filters or None,
            top_k=req.top_k,
            max_tokens=req.max_tokens,
            store=store,
            rewriter_enabled=chat_cfg.rewriter.enabled,
            rewriter_model=chat_cfg.rewriter.model,
            history_turns=chat_cfg.max_history_turns,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return ChatResponseModel(
        session_id=resp.session_id,
        question=resp.question,
        rewritten_question=resp.rewritten_question,
        answer=resp.answer,
        cited_ids=resp.cited_ids,
        sources=[_to_payload(s) for s in resp.sources],
        is_dummy=resp.is_dummy,
        model=resp.model,
    )


@app.get("/api/chat/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(session_id: str) -> ChatHistoryResponse:
    store: ConversationStore = _state["chat_store"]
    # We deliberately treat "unknown id" as 404 — auto-creating on GET would
    # confuse clients that use it to probe whether a session is still alive.
    if not _store_has(store, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    session = store.get_or_create(session_id)
    return ChatHistoryResponse(
        session_id=session.session_id,
        messages=[
            ChatMessagePayload(
                role=m.role,
                content=m.content,
                sources=m.sources,
                timestamp=m.timestamp,
            )
            for m in session.messages
        ],
    )


def _store_has(store: ConversationStore, session_id: str) -> bool:
    """Existence check that works across all backends.

    All three implementations expose a ``has()`` method; Protocol doesn't
    require it so we duck-type. Falls back to ``get_history``-truthy as a
    last resort, which is fine because the only callers (404 probes) tolerate
    a slight performance hit on unknown sessions.
    """
    has = getattr(store, "has", None)
    if callable(has):
        return bool(has(session_id))
    return bool(store.get_history(session_id, last_n_turns=1))


@app.delete("/api/chat/{session_id}", status_code=204)
async def delete_chat(session_id: str) -> None:
    store: ConversationStore = _state["chat_store"]
    if not store.delete(session_id):
        raise HTTPException(status_code=404, detail="session not found")


# ---------------------------------------------------------------------------
# spec_040: /api/graph — refs-driven knowledge graph
# ---------------------------------------------------------------------------


def _require_graph() -> KnowledgeGraph:
    graph = _state.get("graph")
    if graph is None:
        raise HTTPException(
            status_code=503,
            detail="knowledge graph is disabled (config.yml graph.enabled=false)",
        )
    return graph


@app.get("/api/graph", response_model=GraphResponse)
async def get_graph(
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    axes_category: str | None = Query(None),
    axes_level: str | None = Query(None),
) -> GraphResponse:
    graph = _require_graph()
    nodes = graph.get_all_nodes(limit=limit, offset=offset)
    if axes_category:
        nodes = [n for n in nodes if str(n.axes.get("category", "")) == axes_category]
    if axes_level:
        nodes = [n for n in nodes if str(n.axes.get("level", "")) == axes_level]
    node_ids = {n.doc_id for n in nodes}
    edges = [
        e
        for e in graph.get_all_edges()
        if e.source in node_ids and e.target in node_ids
    ]
    stats_dict = graph.stats()
    return GraphResponse(
        nodes=[GraphNodeModel.from_node(n) for n in nodes],
        edges=[GraphEdgeModel(source=e.source, target=e.target) for e in edges],
        stats=GraphStats(**stats_dict),
    )


# ---------------------------------------------------------------------------
# spec_047: /api/feedback — 👍 / 👎 capture + weekly report
# ---------------------------------------------------------------------------


def _require_feedback_store() -> FeedbackStore:
    store = _state.get("feedback_store")
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="feedback is disabled (config.yml feedback.enabled=false)",
        )
    return store


@app.post("/api/feedback", response_model=FeedbackResponse)
async def post_feedback(req: FeedbackRequest) -> FeedbackResponse:
    store = _require_feedback_store()
    fid = store.record(
        query=req.query,
        doc_id=req.doc_id,
        rating=req.rating,
        session_id=req.session_id,
        note=req.note,
    )
    return FeedbackResponse(feedback_id=fid)


@app.get("/api/feedback/report", response_model=FeedbackReportResponse)
async def get_feedback_report(
    days: int = Query(7, ge=1, le=365),
) -> FeedbackReportResponse:
    # Import locally so the evaluation package stays out of the cold-start path.
    from evaluation.feedback_report import generate_report

    store = _require_feedback_store()
    return FeedbackReportResponse(markdown=generate_report(store, days=days))


# ---------------------------------------------------------------------------
# spec_048: /api/gap/report — knowledge-gap weekly summary
# ---------------------------------------------------------------------------


def _require_gap_store() -> GapStore:
    store = _state.get("gap_store")
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="gap detection is disabled (config.yml gap.enabled=false)",
        )
    return store


@app.get("/api/gap/report", response_model=GapReportResponse)
async def get_gap_report(
    days: int = Query(7, ge=1, le=365),
) -> GapReportResponse:
    from evaluation.gap_report import generate_report

    store = _require_gap_store()
    return GapReportResponse(markdown=generate_report(store, days=days))


@app.get("/api/graph/{doc_id}/neighbors", response_model=NeighborResponse)
async def get_neighbors(
    doc_id: str,
    hop: int = Query(1, ge=1, le=3),
    max_neighbors: int = Query(20, ge=1, le=100),
    direction: str = Query(
        "both",
        pattern="^(in|out|both)$",
        description="'out' = docs this refs, 'in' = docs that ref this, 'both' = union (spec_049).",
    ),
) -> NeighborResponse:
    graph = _require_graph()
    node = graph.get_node(doc_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"doc_id {doc_id} not in graph")
    neighbour_ids = graph.neighbors_within_hop(
        doc_id, hop=hop, max_neighbors=max_neighbors, direction=direction
    )
    neighbours: list[GraphNodeModel] = []
    for nid in neighbour_ids:
        n = graph.get_node(nid)
        if n is not None:
            neighbours.append(GraphNodeModel.from_node(n))
    return NeighborResponse(
        center=GraphNodeModel.from_node(node),
        neighbors=neighbours,
        hop=hop,
    )
