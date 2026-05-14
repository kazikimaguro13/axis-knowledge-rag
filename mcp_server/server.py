"""axis_knowledge_rag MCP server (stdio transport, FastMCP-based).

Exposes the project's hybrid search + RAG capabilities as MCP tools so that
Claude Desktop / Cowork / any MCP-compatible client can query the knowledge
base directly.

Run with:
    python -m mcp_server
or via stdio invocation from a client's config file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from backend.src.config import (
    configure_logging,
    load_app_config,
    load_axes_config,
    settings,
)
from backend.src.embedder import Embedder
from backend.src.graph import KnowledgeGraph, build_default_graph
from backend.src.integrity import IntegrityChecker
from backend.src.loader import load_directory
from backend.src.normalizer import Normalizer
from backend.src.rag import RAGPipeline
from backend.src.search import SearchEngine, _build_where_norm
from backend.src.vector_store import VectorStore
from mcp_server._errors import make_error_response
from mcp_server._session import mcp_chat_store
from mcp_server.formatters import (
    format_answer_json,
    format_answer_md,
    format_axes_md,
    format_chat_json,
    format_chat_md,
    format_integrity_md,
    format_neighbors_json,
    format_neighbors_md,
    format_search_results_json,
    format_search_results_md,
)
from mcp_server.schemas import (
    AnswerInput,
    ChatInput,
    CheckIntegrityInput,
    IngestInput,
    ListAxesInput,
    ListDocumentsInput,
    NeighborsInput,
    ResponseFormat,
    SearchInput,
)

configure_logging()


class _CorrFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "corr_id"):
            record.corr_id = "-----"  # type: ignore[attr-defined]
        return super().format(record)


for _h in logging.getLogger().handlers:
    _h.setFormatter(_CorrFormatter(
        "[%(levelname)s] corr=%(corr_id)s %(name)s: %(message)s"
    ))


logger = logging.getLogger("axis_knowledge_rag_mcp")

mcp = FastMCP("axis_knowledge_rag_mcp")


# === lazy singletons (init on first tool call, persist for server lifetime) ===
_engine: SearchEngine | None = None
_rag: RAGPipeline | None = None
_axes_cfg: dict | None = None
_graph: KnowledgeGraph | None = None


def _get_graph() -> KnowledgeGraph:
    global _graph
    if _graph is None:
        app_cfg = load_app_config()
        if not app_cfg.graph.enabled:
            raise RuntimeError(
                "knowledge graph disabled in config.yml (graph.enabled=false)"
            )
        _graph = build_default_graph(app_cfg.graph.knowledge_dir)
        logger.info("KnowledgeGraph ready: %s", _graph.stats())
    return _graph


def _get_engine() -> SearchEngine:
    global _engine
    if _engine is None:
        store = VectorStore(path=settings.chroma_db_path)
        embedder = Embedder()
        normalizer = Normalizer.from_config(load_axes_config())
        app_cfg = load_app_config()
        pd = app_cfg.retrieval.parent_doc
        if pd.enabled and not store.has_parents():
            logger.warning(
                "parent_doc.enabled=true but parents.json is missing — "
                "falling back to legacy search. Run "
                "`python -m scripts.build_index <dir> --rebuild --mode parent_doc`."
            )
            parent_doc_enabled = False
        else:
            parent_doc_enabled = pd.enabled
        _engine = SearchEngine(
            store,
            embedder,
            normalizer,
            parent_doc_enabled=parent_doc_enabled,
            top_k_children=pd.top_k_children,
        )
        logger.info(
            "SearchEngine ready (embedder_mode=%s, parent_doc=%s)",
            "DUMMY" if embedder.is_dummy else "GEMINI",
            parent_doc_enabled,
        )
    return _engine


def _get_rag() -> RAGPipeline:
    global _rag
    if _rag is None:
        app_cfg = load_app_config()
        _rag = RAGPipeline(
            _get_engine(), context_max_chars=app_cfg.rag.context_max_chars
        )
        logger.info("RAGPipeline ready (rag_mode=%s)", "DUMMY" if _rag.is_dummy else "CLAUDE")
    return _rag


def _get_axes() -> dict:
    global _axes_cfg
    if _axes_cfg is None:
        _axes_cfg = load_axes_config()
    return _axes_cfg


# ============================================================================
# Tool 1: axis_search
# ============================================================================
@mcp.tool(
    name="axis_search",
    annotations=ToolAnnotations(
        title="Axis + Vector Hybrid Search",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def axis_search(params: SearchInput) -> str:
    """Search the knowledge base by axis filters + vector similarity (hybrid).

    Best when:
    - You have an exact axis constraint (e.g., category='技術記事') AND a fuzzy
      semantic query (e.g., "RAG architecture design")
    - You want a ranked list of Documents WITHOUT generated text answer

    Args:
        params (SearchInput): {
            query (str|None): natural-language query, optional
            filters (dict): axis filters like {"category": "技術記事"}
            top_k (int): 1-50, default 5
            bm25_weight (float): 0.0–1.0 weight of BM25 score in the 3-way
                fusion (axis filter + vector cosine + BM25). 0.0 = vector
                only (v0.5 behaviour), 1.0 = BM25 only. Default 0.5.
            response_format (markdown|json): output format
        }

    Returns:
        str: formatted list of search hits with id / title / score / axes / snippet.
    """
    try:
        engine = _get_engine()
        results = engine.search(
            params.query,
            filters=params.filters or None,
            top_k=params.top_k,
            bm25_weight=params.bm25_weight,
        )
        if params.response_format == ResponseFormat.JSON:
            return format_search_results_json(params.query, params.filters, results)
        return format_search_results_md(params.query, params.filters, results)
    except Exception as e:  # noqa: BLE001 — top-level safety net
        return make_error_response("axis_search", e)


# ============================================================================
# Tool 2: axis_answer
# ============================================================================
@mcp.tool(
    name="axis_answer",
    annotations=ToolAnnotations(
        title="RAG Answer with Citations",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,  # Claude API has nondeterministic output
        openWorldHint=True,    # Calls Anthropic API (external)
    ),
)
async def axis_answer(params: AnswerInput) -> str:
    """Generate an answer to a question, grounded in the knowledge base.

    Uses Claude API to compose a citation-bearing response from the top-k
    retrieved Documents. Citation format in the body: [N] (1-indexed,
    matching the position of the source in the `sources` list).

    Args:
        params (AnswerInput): {
            question (str): the natural-language question
            filters (dict): optional axis filters
            top_k (int): retrieved Documents count
            max_tokens (int): Claude reply max tokens
            response_format (markdown|json)
        }

    Returns:
        str: answer text + citations (markdown) or JSON wrapper.
    """
    try:
        rag = _get_rag()
        ans = rag.answer(
            params.question,
            filters=params.filters or None,
            top_k=params.top_k,
            max_tokens=params.max_tokens,
        )
        if params.response_format == ResponseFormat.JSON:
            return format_answer_json(params.question, ans)
        return format_answer_md(params.question, ans)
    except Exception as e:
        return make_error_response("axis_answer", e)


# ============================================================================
# Tool 3: axis_chat (spec_032)
# ============================================================================
@mcp.tool(
    name="axis_chat",
    annotations=ToolAnnotations(
        title="Conversational RAG (history-aware)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def axis_chat(params: ChatInput) -> str:
    """Conversational RAG. Pass back the returned ``session_id`` to keep history.

    Best when:
    - The user is having a multi-turn dialog ("RAG とは?" → "それの利点は?")
    - You want follow-up questions to be rewritten into standalone queries
      automatically via Gemini Flash

    NOTE: sessions live in the MCP process memory — they are lost when the
    MCP process restarts (e.g., Claude Desktop reload). Persisting to disk
    is a v0.8 candidate (spec_037). Cap: 20 sessions / 1h TTL.
    """
    try:
        rag = _get_rag()
        app_cfg = load_app_config()
        cfg = app_cfg.chat
        resp = rag.chat(
            params.question,
            session_id=params.session_id,
            filters=params.filters or None,
            top_k=params.top_k,
            max_tokens=params.max_tokens,
            store=mcp_chat_store,
            rewriter_enabled=cfg.rewriter.enabled,
            rewriter_model=cfg.rewriter.model,
            history_turns=cfg.max_history_turns,
        )
        if params.response_format == ResponseFormat.JSON:
            return format_chat_json(params.question, resp)
        return format_chat_md(params.question, resp)
    except Exception as e:
        return make_error_response("axis_chat", e)


# ============================================================================
# Tool 4: axis_list_axes
# ============================================================================
@mcp.tool(
    name="axis_list_axes",
    annotations=ToolAnnotations(
        title="List Configured Axes",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def axis_list_axes(params: ListAxesInput) -> str:
    """List axes defined in config.yml (name / type / values / required).

    Use this first to discover what filters axis_search / axis_answer accept.
    """
    try:
        cfg = _get_axes()
        axes = cfg.get("axes", [])
        if params.response_format == ResponseFormat.JSON:
            return json.dumps({"axes": axes}, ensure_ascii=False, indent=2)
        return format_axes_md(axes)
    except Exception as e:
        return make_error_response("axis_list_axes", e)


# ============================================================================
# Tool 4: axis_check_integrity
# ============================================================================
@mcp.tool(
    name="axis_check_integrity",
    annotations=ToolAnnotations(
        title="Reference Integrity Check",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def axis_check_integrity(params: CheckIntegrityInput) -> str:
    """Check the knowledge base for broken refs, orphan docs, and cycles."""
    try:
        docs = load_directory(Path(params.knowledge_dir))
        report = IntegrityChecker().check(docs)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(report.as_dict(), ensure_ascii=False, indent=2)
        return format_integrity_md(report)
    except Exception as e:
        return make_error_response("axis_check_integrity", e)


# ============================================================================
# Tool 5: axis_list_documents
# ============================================================================
@mcp.tool(
    name="axis_list_documents",
    annotations=ToolAnnotations(
        title="List Documents (with pagination)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def axis_list_documents(params: ListDocumentsInput) -> str:
    """List Documents in the knowledge base, with axis filters + pagination.

    Backed by `VectorStore.list_with_filter()` (Chroma `collection.get`), so the
    total reflects the real document count — no 200-row cap, no zero-vector
    similarity query.
    """
    try:
        engine = _get_engine()
        store = engine._store

        norm_filters = (
            {k: engine._normalizer(str(v)) for k, v in (params.filters or {}).items()}
            if params.filters
            else None
        )
        where = _build_where_norm(norm_filters or {})

        total = store.count_with_filter(where=where)
        result = store.list_with_filter(
            where=where, limit=params.limit, offset=params.offset
        )

        ids = result.get("ids", []) or []
        metadatas_raw = result.get("metadatas") or []
        metadatas = list(metadatas_raw) + [{}] * (len(ids) - len(metadatas_raw))

        has_more = (params.offset + len(ids)) < total
        next_offset = params.offset + len(ids) if has_more else None

        docs = []
        for i, doc_id in enumerate(ids):
            md = metadatas[i] or {}
            axes = {
                k.removeprefix("axis_"): v
                for k, v in md.items()
                if k.startswith("axis_") and not k.endswith("_norm")
            }
            docs.append(
                {
                    "id": doc_id,
                    "title": str(md.get("title", "")),
                    "axes": axes,
                    "path": str(md.get("path", "")),
                }
            )

        if params.response_format == ResponseFormat.JSON:
            payload = {
                "total": total,
                "count": len(docs),
                "offset": params.offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "documents": docs,
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        lines = [
            f"# Documents (total={total}, offset={params.offset}, count={len(docs)})"
        ]
        if has_more:
            lines.append(f"\n_next offset: {next_offset}_\n")
        for d in docs:
            lines.append(f"- `{d['id']}` — {d['title']} — axes: {d['axes']}")
        return "\n".join(lines)
    except Exception as e:
        return make_error_response("axis_list_documents", e)


# ============================================================================
# Tool 6: axis_ingest_memo
# ============================================================================
@mcp.tool(
    name="axis_ingest_memo",
    annotations=ToolAnnotations(
        title="Convert raw memo to YAML-frontmatter Markdown",
        readOnlyHint=True,  # Does not modify files; just returns the converted content
        destructiveHint=False,
        idempotentHint=False,  # Claude API is nondeterministic
        openWorldHint=True,  # Calls Anthropic API (external)
    ),
)
async def axis_ingest_memo(params: IngestInput) -> str:
    """Convert a raw memo text into axis-knowledge-rag YAML-frontmatter Markdown.

    Pipeline: read existing knowledge_dir → next doc_NNN id + existing ref list →
    Claude fills axes/tags/title/body under strict axes_constraints from config.yml.
    Returns rendered Markdown by default; pass `response_format='json'` for the
    structured `IngestResult` payload plus the rendered Markdown.

    DUMMY mode (no `ANTHROPIC_API_KEY`) returns a deterministic mock — useful
    for plumbing tests but not for actual ingestion.
    """
    try:
        from backend.src.ingester import Ingester, render_markdown
        from backend.src.ingester_schemas import IngestOptions

        ingester = Ingester()
        opts = IngestOptions(
            knowledge_dir=params.knowledge_dir,
            suggested_category=params.suggested_category,
            max_tokens=params.max_tokens,
        )
        result = ingester.ingest(params.raw_text, opts)
        md = render_markdown(result)

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(
                {
                    "id": result.id,
                    "title": result.title,
                    "axes": result.axes,
                    "tags": result.tags,
                    "refs": result.refs,
                    "rendered_md": md,
                    "is_dummy": ingester.is_dummy,
                },
                ensure_ascii=False,
                indent=2,
            )
        return md
    except Exception as e:
        return make_error_response("axis_ingest_memo", e)


# ============================================================================
# Tool 7: axis_neighbors (spec_040)
# ============================================================================
@mcp.tool(
    name="axis_neighbors",
    annotations=ToolAnnotations(
        title="Knowledge graph neighbours (refs)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def axis_neighbors(params: NeighborsInput) -> str:
    """Return knowledge-graph neighbours of a doc_id within N hops.

    Useful for follow-up exploration: after axis_search returns a doc, call
    axis_neighbors with that ``doc_id`` to surface related documents the
    YAML ``refs:`` chain connects to. Direction:
    - ``out``: docs referenced *by* the input (this doc's refs)
    - ``in``:  docs *referencing* the input (incoming refs)
    - ``both`` (default): union of the two

    Args:
        params: see :class:`NeighborsInput`.

    Returns:
        Markdown (or JSON) summary of the center node + its neighbours.
    """
    try:
        g = _get_graph()
        center = g.get_node(params.doc_id)
        if center is None:
            return make_error_response(
                "axis_neighbors", ValueError(f"doc_id {params.doc_id} not in graph")
            )
        neighbour_ids = g.neighbors_within_hop(
            params.doc_id,
            hop=params.hop,
            max_neighbors=params.max_neighbors,
            direction=params.direction,
        )
        neighbours = [g.get_node(nid) for nid in neighbour_ids]
        neighbours = [n for n in neighbours if n is not None]
        if params.response_format == ResponseFormat.JSON:
            return format_neighbors_json(center, neighbours, params.hop)
        return format_neighbors_md(center, neighbours, params.hop)
    except Exception as e:
        return make_error_response("axis_neighbors", e)


def main() -> None:
    """Entrypoint for `python -m mcp_server` / `axis-knowledge-rag-mcp`."""
    import sys

    # stdio transport — redirect all log handlers to stderr so the JSON-RPC
    # stream on stdout is never contaminated by log output.
    for h in logging.getLogger().handlers:
        h.stream = sys.stderr

    mcp.run()


if __name__ == "__main__":
    main()
