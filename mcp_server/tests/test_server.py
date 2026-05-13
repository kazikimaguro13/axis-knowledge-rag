"""Smoke tests for mcp_server tools (DUMMY mode, no API keys required)."""

import json
from pathlib import Path

import pytest

from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.normalizer import Normalizer
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore
from mcp_server import server as srv
from mcp_server.schemas import (
    AnswerInput,
    CheckIntegrityInput,
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
    embedder = Embedder(force_dummy=True)
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
