"""Shared fixtures for the test suite."""

from pathlib import Path

import pytest

from backend.src.embedder import Embedder
from backend.src.loader import Document
from backend.src.search import SearchEngine
from backend.src.vector_store import VectorStore


@pytest.fixture
def dummy_embedder() -> Embedder:
    return Embedder(force_dummy=True)


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
