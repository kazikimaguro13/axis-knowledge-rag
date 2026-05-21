"""Shared fixtures for the test suite."""

import os
from pathlib import Path

import pytest

from backend.src.embedder import DummyEmbedder, Embedder
from backend.src.loader import Document
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore

# spec_054: tests must read their corpus from this isolated fixture dir, so the
# user can freely swap `examples/knowledge/` for personal notes without breaking
# the suite. ID-pinned assertions (e.g. neighbors expecting `doc_001`) rely on
# the demo files copied here.
TEST_KNOWLEDGE_DIR = Path(__file__).parent / "fixtures" / "knowledge"


@pytest.fixture(autouse=True, scope="session")
def _pin_knowledge_dir_to_fixtures() -> None:
    """Force `app_cfg.graph.knowledge_dir` → fixtures/knowledge for the suite.

    `load_app_config()` honours `AXIS_KNOWLEDGE_DIR` (spec_054), so every
    `TestClient(app)` lifespan picks up the fixture corpus regardless of what
    the developer has dropped into `examples/knowledge/`.
    """
    os.environ["AXIS_KNOWLEDGE_DIR"] = str(TEST_KNOWLEDGE_DIR)


@pytest.fixture
def dummy_embedder() -> Embedder:
    return DummyEmbedder()


@pytest.fixture
def in_memory_store(tmp_path: Path) -> VectorStore:
    # Use a unique tmp_path per test to guarantee ChromaDB isolation.
    return VectorStore(path=tmp_path / "chroma")


@pytest.fixture
def search_engine(in_memory_store: VectorStore, dummy_embedder: Embedder) -> SearchEngine:
    return SearchEngine(in_memory_store, dummy_embedder)


@pytest.fixture
def sample_documents() -> list[Document]:
    return [
        Document(
            id=f"doc_{i:03d}",
            title=f"Title {i}",
            axes={"category": "技術記事", "level": "中級"},
            tags=["a"],
            refs=[],
            body=f"Body content for document {i}.",
            path=Path(f"/tmp/doc_{i}.md"),
        )
        for i in range(1, 6)
    ]
