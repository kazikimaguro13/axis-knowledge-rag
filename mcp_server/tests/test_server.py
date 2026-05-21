"""Smoke tests for mcp_server tools (DUMMY mode, no API keys required)."""

import json
import logging
from pathlib import Path

import pytest

from backend.src.embedder import DummyEmbedder
from backend.src.loader import Document
from backend.src.normalizer import Normalizer
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore
from mcp_server import server as srv
from mcp_server.schemas import (
    AnswerInput,
    CheckIntegrityInput,
    IngestInput,
    ListAxesInput,
    ListDocumentsInput,
    ResponseFormat,
    SearchInput,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset lazy singletons between tests to prevent state leakage."""
    srv._engine = None
    srv._rag = None
    srv._axes_cfg = None
    yield
    srv._engine = None
    srv._rag = None
    srv._axes_cfg = None


@pytest.fixture
def tmp_chroma(tmp_path: Path, monkeypatch):
    """Patch settings so VectorStore uses a tmp directory."""

    from backend.src import config as cfg

    new_settings = cfg.Settings(chroma_db_path=tmp_path / "chroma")
    monkeypatch.setattr(cfg, "settings", new_settings)
    monkeypatch.setattr(srv, "settings", new_settings)
    return tmp_path


@pytest.fixture
def populated_engine(tmp_chroma: Path) -> SearchEngine:
    """Return a SearchEngine pre-populated with 6 sample docs."""
    store = VectorStore(path=tmp_chroma / "chroma")
    embedder = DummyEmbedder()
    normalizer = Normalizer.from_config({"axes": []})
    engine = SearchEngine(store, embedder, normalizer)

    docs = [
        Document(
            id=f"doc_{i:03d}",
            title=f"Test Document {i}",
            axes={"category": "技術記事", "level": "初級" if i % 2 == 0 else "中級"},
            tags=["test"],
            refs=[],
            body=f"This is body content for document {i}. RAG architecture design.",
            path=Path(f"/tmp/doc_{i}.md"),
        )
        for i in range(1, 7)
    ]
    # Index documents via VectorStore directly (same path as build_index.py)
    embeddings = embedder.embed_batch([d.body for d in docs])
    store.upsert_many(docs, embeddings)
    srv._engine = engine
    return engine


@pytest.fixture
def knowledge_dir_with_broken_ref(tmp_path: Path) -> Path:
    """Create a small knowledge dir that has 1 broken ref."""
    kdir = tmp_path / "knowledge"
    kdir.mkdir()

    doc_a = kdir / "doc_a.md"
    doc_a.write_text(
        "---\nid: doc_a\ntitle: Doc A\naxes:\n  category: test\nrefs:\n  - doc_999\n---\nBody A.\n",
        encoding="utf-8",
    )
    doc_b = kdir / "doc_b.md"
    doc_b.write_text(
        "---\nid: doc_b\ntitle: Doc B\naxes:\n  category: test\nrefs: []\n---\nBody B.\n",
        encoding="utf-8",
    )
    return kdir


# ---------------------------------------------------------------------------
# Test: lazy singleton initialisation
# ---------------------------------------------------------------------------

def test_get_engine_no_exception(tmp_chroma):
    engine = srv._get_engine()
    assert engine is not None
    # Second call returns cached instance
    assert srv._get_engine() is engine


def test_get_rag_no_exception(tmp_chroma):
    rag = srv._get_rag()
    assert rag is not None
    assert rag.is_dummy  # no ANTHROPIC_API_KEY in CI


# ---------------------------------------------------------------------------
# Test: axis_search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_axis_search_markdown(populated_engine):
    params = SearchInput(query="RAG architecture", top_k=3)
    result = await srv.axis_search(params)
    assert isinstance(result, str)
    assert "result" in result.lower() or "Search results" in result


@pytest.mark.asyncio
async def test_axis_search_json(populated_engine):
    params = SearchInput(query="design", top_k=2, response_format=ResponseFormat.JSON)
    result = await srv.axis_search(params)
    data = json.loads(result)
    assert "results" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_axis_search_no_query_filters_only(populated_engine):
    params = SearchInput(query=None, filters={"category": "技術記事"}, top_k=10)
    result = await srv.axis_search(params)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_axis_search_with_bm25_weight(populated_engine, monkeypatch):
    """`SearchInput.bm25_weight` is forwarded to `SearchEngine.search`."""
    captured: dict = {}

    real_search = populated_engine.search

    def _spy(query, *, filters=None, top_k=5, bm25_weight=0.5):
        captured["bm25_weight"] = bm25_weight
        captured["top_k"] = top_k
        return real_search(query, filters=filters, top_k=top_k, bm25_weight=bm25_weight)

    monkeypatch.setattr(populated_engine, "search", _spy)

    params = SearchInput(query="design", top_k=3, bm25_weight=0.7)
    result = await srv.axis_search(params)
    assert isinstance(result, str)
    assert captured["bm25_weight"] == pytest.approx(0.7)
    assert captured["top_k"] == 3


@pytest.mark.asyncio
async def test_axis_search_empty_query_normalised_to_none(populated_engine):
    params = SearchInput(query="   ", top_k=5)
    assert params.query is None
    result = await srv.axis_search(params)
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Test: axis_answer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_axis_answer_markdown_dummy(populated_engine, tmp_chroma):
    params = AnswerInput(question="What is RAG?")
    result = await srv.axis_answer(params)
    assert isinstance(result, str)
    assert "Answer" in result or "DUMMY" in result


@pytest.mark.asyncio
async def test_axis_answer_json_dummy(populated_engine, tmp_chroma):
    params = AnswerInput(question="RAG とは", response_format=ResponseFormat.JSON)
    result = await srv.axis_answer(params)
    data = json.loads(result)
    assert "answer" in data
    assert "cited_ids" in data
    assert data["is_dummy"] is True


# ---------------------------------------------------------------------------
# Test: axis_list_axes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_axis_list_axes_markdown():
    params = ListAxesInput()
    result = await srv.axis_list_axes(params)
    assert isinstance(result, str)
    # Result should reference axes or empty list message
    assert "axes" in result.lower() or "Available" in result


@pytest.mark.asyncio
async def test_axis_list_axes_json():
    params = ListAxesInput(response_format=ResponseFormat.JSON)
    result = await srv.axis_list_axes(params)
    data = json.loads(result)
    assert "axes" in data
    assert isinstance(data["axes"], list)


@pytest.mark.asyncio
async def test_axis_list_axes_from_real_config():
    """config.yml has axes: category, topic, level, author, year."""
    import os
    old_dir = os.getcwd()
    os.chdir(Path(__file__).parents[2])  # project root
    try:
        srv._axes_cfg = None
        params = ListAxesInput(response_format=ResponseFormat.JSON)
        result = await srv.axis_list_axes(params)
        data = json.loads(result)
        names = [a["name"] for a in data["axes"]]
        assert "category" in names
    finally:
        os.chdir(old_dir)
        srv._axes_cfg = None


# ---------------------------------------------------------------------------
# Test: axis_check_integrity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_axis_check_integrity_broken_ref_markdown(knowledge_dir_with_broken_ref: Path):
    params = CheckIntegrityInput(knowledge_dir=str(knowledge_dir_with_broken_ref))
    result = await srv.axis_check_integrity(params)
    assert isinstance(result, str)
    assert "doc_999" in result


@pytest.mark.asyncio
async def test_axis_check_integrity_broken_ref_json(knowledge_dir_with_broken_ref: Path):
    params = CheckIntegrityInput(
        knowledge_dir=str(knowledge_dir_with_broken_ref),
        response_format=ResponseFormat.JSON,
    )
    result = await srv.axis_check_integrity(params)
    data = json.loads(result)
    assert data["total_docs"] == 2
    assert len(data["broken_refs"]) == 1
    assert data["broken_refs"][0]["target_id"] == "doc_999"


@pytest.mark.asyncio
async def test_axis_check_integrity_no_errors(tmp_path: Path):
    kdir = tmp_path / "clean"
    kdir.mkdir()
    (kdir / "doc1.md").write_text(
        "---\nid: doc_001\ntitle: Clean\naxes:\n  category: test\nrefs: []\n---\nOK.\n",
        encoding="utf-8",
    )
    params = CheckIntegrityInput(knowledge_dir=str(kdir))
    result = await srv.axis_check_integrity(params)
    assert "broken" in result.lower() or "No broken" in result


# ---------------------------------------------------------------------------
# Test: axis_list_documents — pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_axis_list_documents_pagination_markdown(populated_engine):
    params = ListDocumentsInput(limit=3, offset=0)
    result = await srv.axis_list_documents(params)
    assert isinstance(result, str)
    assert "total=" in result


@pytest.mark.asyncio
async def test_axis_list_documents_pagination_json(populated_engine):
    params = ListDocumentsInput(limit=3, offset=0, response_format=ResponseFormat.JSON)
    result = await srv.axis_list_documents(params)
    data = json.loads(result)
    assert data["total"] == 6
    assert data["count"] == 3
    assert data["offset"] == 0
    assert data["has_more"] is True
    assert data["next_offset"] == 3


@pytest.mark.asyncio
async def test_axis_list_documents_last_page(populated_engine):
    params = ListDocumentsInput(limit=10, offset=4, response_format=ResponseFormat.JSON)
    result = await srv.axis_list_documents(params)
    data = json.loads(result)
    assert data["count"] == 2
    assert data["has_more"] is False
    assert data["next_offset"] is None


@pytest.mark.asyncio
async def test_axis_list_documents_filters(populated_engine):
    params = ListDocumentsInput(
        filters={"category": "技術記事"},
        limit=10,
        offset=0,
        response_format=ResponseFormat.JSON,
    )
    result = await srv.axis_list_documents(params)
    data = json.loads(result)
    assert data["total"] >= 0


# ---------------------------------------------------------------------------
# spec_026: axis_list_documents pagination above 200 (was previously capped)
# ---------------------------------------------------------------------------


@pytest.fixture
def large_engine(tmp_chroma: Path) -> SearchEngine:
    """Engine pre-populated with 250 docs to exercise the no-cap pagination."""
    store = VectorStore(path=tmp_chroma / "chroma")
    embedder = DummyEmbedder()
    normalizer = Normalizer.from_config({"axes": []})
    engine = SearchEngine(store, embedder, normalizer)

    docs = [
        Document(
            id=f"doc_{i:04d}",
            title=f"Document {i}",
            axes={"category": "bulk"},
            tags=["bulk"],
            refs=[],
            body=f"Body for document {i}.",
            path=Path(f"/tmp/doc_{i:04d}.md"),
        )
        for i in range(250)
    ]
    embeddings = embedder.embed_batch([d.body for d in docs])
    store.upsert_many(docs, embeddings)
    srv._engine = engine
    return engine


@pytest.mark.asyncio
async def test_axis_list_documents_total_above_200(large_engine):
    """Total must reflect the real count (250), not the old 200-row cap."""
    params = ListDocumentsInput(
        limit=10, offset=0, response_format=ResponseFormat.JSON
    )
    result = await srv.axis_list_documents(params)
    data = json.loads(result)
    assert data["total"] == 250
    assert data["count"] == 10
    assert data["has_more"] is True


@pytest.mark.asyncio
async def test_axis_list_documents_offset_above_200(large_engine):
    """Pagination must work past the previously-imposed 200-row ceiling."""
    params = ListDocumentsInput(
        limit=20, offset=210, response_format=ResponseFormat.JSON
    )
    result = await srv.axis_list_documents(params)
    data = json.loads(result)
    assert data["total"] == 250
    assert data["offset"] == 210
    assert data["count"] == 20
    assert data["has_more"] is True
    assert data["next_offset"] == 230


@pytest.mark.asyncio
async def test_axis_list_documents_error_message_is_sanitized(monkeypatch):
    """When an internal exception fires, the response must not leak details."""

    class _BrokenStore:
        def count_with_filter(self, where=None):
            raise RuntimeError("internal stack trace with sensitive path /etc/passwd")

    class _BrokenEngine:
        _store = _BrokenStore()
        _normalizer = Normalizer.from_config({"axes": []})

    monkeypatch.setattr(srv, "_get_engine", lambda: _BrokenEngine())
    params = ListDocumentsInput(limit=5, offset=0, response_format=ResponseFormat.JSON)
    result = await srv.axis_list_documents(params)
    assert "RuntimeError" not in result
    assert "/etc/passwd" not in result
    assert "Error" in result


# ---------------------------------------------------------------------------
# Test: axis_ingest_memo (DUMMY mode — no API key)
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_knowledge_dir(tmp_path: Path) -> Path:
    d = tmp_path / "kd"
    d.mkdir()
    return d


@pytest.mark.asyncio
async def test_axis_ingest_memo_markdown(empty_knowledge_dir: Path):
    params = IngestInput(
        raw_text="これは MCP 経由の DUMMY ingest テスト用のメモ本文です。",
        knowledge_dir=str(empty_knowledge_dir),
        live_ingest=False,
    )
    result = await srv.axis_ingest_memo(params)
    assert isinstance(result, str)
    assert result.startswith("---\n")
    assert "id: doc_001" in result
    assert "DUMMY mode" in result


@pytest.mark.asyncio
async def test_axis_ingest_memo_json(empty_knowledge_dir: Path):
    params = IngestInput(
        raw_text="JSON モードの DUMMY ingest テスト用のメモ本文サンプル。",
        knowledge_dir=str(empty_knowledge_dir),
        response_format=ResponseFormat.JSON,
        live_ingest=False,
    )
    result = await srv.axis_ingest_memo(params)
    data = json.loads(result)
    assert data["id"] == "doc_001"
    assert "rendered_md" in data
    assert data["is_dummy"] is True
    assert data["axes"]["category"] == "メモ"
    assert data["indexed"] is False


@pytest.mark.asyncio
async def test_axis_ingest_memo_input_validation():
    from pydantic import ValidationError

    # min_length=20 should be enforced by Pydantic
    with pytest.raises(ValidationError):
        IngestInput(raw_text="short")


# ---------------------------------------------------------------------------
# spec_056: live_ingest backend integration + fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_axis_ingest_memo_live_ingest_fallback_when_backend_down(
    empty_knowledge_dir: Path, monkeypatch
):
    """live_ingest=True against an unreachable backend → indexed=false, markdown still returned."""
    # Point at a port nothing should be listening on; the urllib call must
    # fail and the tool must degrade gracefully.
    params = IngestInput(
        raw_text="バックエンド未起動フォールバックのテスト本文サンプル。",
        knowledge_dir=str(empty_knowledge_dir),
        response_format=ResponseFormat.JSON,
        live_ingest=True,
        backend_url="http://127.0.0.1:1",
    )
    result = await srv.axis_ingest_memo(params)
    data = json.loads(result)
    assert data["indexed"] is False
    assert "rendered_md" in data
    assert data["id"] == "doc_001"


@pytest.mark.asyncio
async def test_axis_ingest_memo_live_ingest_success_path(
    empty_knowledge_dir: Path, monkeypatch
):
    """When the backend call succeeds (mocked), indexed=true is surfaced."""
    captured: dict = {}

    def _fake_call(md: str, url: str) -> dict:
        captured["url"] = url
        captured["md"] = md
        return {"indexed": True, "parents": 3, "children": 7, "doc_id": "doc_001"}

    monkeypatch.setattr(srv, "_live_ingest_via_backend", _fake_call)
    params = IngestInput(
        raw_text="バックエンド呼び出し成功時のテストメモ本文サンプル。",
        knowledge_dir=str(empty_knowledge_dir),
        response_format=ResponseFormat.JSON,
        live_ingest=True,
    )
    result = await srv.axis_ingest_memo(params)
    data = json.loads(result)
    assert data["indexed"] is True
    assert data["live_ingest"]["parents"] == 3
    assert captured["url"].endswith("8000")  # default backend URL


# ---------------------------------------------------------------------------
# Test: error sanitization — no internal details leak to MCP client
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_axis_search_error_is_sanitized(monkeypatch, caplog):
    """When search fails, the tool returns a sanitized string with a corr_id."""
    def boom(*a, **kw):
        raise ValueError("Internal value /secret/path leaked")
    monkeypatch.setattr(srv, "_get_engine", boom)

    with caplog.at_level(logging.ERROR):
        out = await srv.axis_search(SearchInput(query="x"))

    # Response must NOT contain internal details
    assert "secret" not in out
    assert "/path" not in out
    assert "ValueError" not in out

    # Response is the sanitized format
    assert "axis_search failed" in out
    assert "correlation id" in out

    # Full exception must appear in the logs
    assert "ValueError" in caplog.text or "Internal value" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,tool_callable,input_factory",
    [
        ("axis_search",          lambda: srv.axis_search,          lambda: SearchInput(query="x")),
        ("axis_answer",          lambda: srv.axis_answer,          lambda: AnswerInput(question="x")),
        ("axis_list_axes",       lambda: srv.axis_list_axes,       lambda: ListAxesInput()),
        ("axis_check_integrity", lambda: srv.axis_check_integrity, lambda: CheckIntegrityInput()),
        ("axis_list_documents",  lambda: srv.axis_list_documents,  lambda: ListDocumentsInput()),
        ("axis_ingest_memo",     lambda: srv.axis_ingest_memo,     lambda: IngestInput(raw_text="x" * 30)),
    ],
)
async def test_all_tools_error_sanitized(tool_name, tool_callable, input_factory, monkeypatch):
    """Every tool's error path returns a sanitized response without internal details."""
    def _bomb(*a, **kw):
        raise ZeroDivisionError("division by zero")

    # Patch all lazy singletons and loader so every tool path hits an error
    monkeypatch.setattr(srv, "_get_engine", _bomb)
    monkeypatch.setattr(srv, "_get_rag", _bomb)
    monkeypatch.setattr(srv, "_get_axes", _bomb)
    monkeypatch.setattr(srv, "load_directory", _bomb)

    # axis_ingest_memo uses a local import; patch at the source module
    import backend.src.ingester as _ingester_mod
    monkeypatch.setattr(_ingester_mod, "Ingester", _bomb)

    out = await tool_callable()(input_factory())

    assert "ZeroDivisionError" not in out
    assert "division by zero" not in out
    assert "failed" in out
    assert "correlation id" in out
