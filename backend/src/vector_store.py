"""ChromaDB wrapper for storing Documents with axis metadata.

Stores body embedding as the primary vector and full axis dict in metadata
so that downstream search.py can filter on axes before / alongside vector
similarity.
"""

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.src.config import COLLECTION_NAME
from backend.src.loader import Document

logger = logging.getLogger(__name__)


def _flatten_axes(axes: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Chroma metadata must be flat scalar values."""
    out: dict[str, str | int | float | bool] = {}
    for k, v in axes.items():
        key = f"axis_{k}"
        if isinstance(v, (str, int, float, bool)):
            out[key] = v
        else:
            out[key] = str(v)
    return out


class VectorStore:
    """ChromaDB-backed store for Document embeddings + axis metadata."""

    def __init__(self, path: Path | None = None, *, in_memory: bool = False) -> None:
        if in_memory:
            self._client = chromadb.EphemeralClient()
        else:
            db_path = path or Path("./.chromadb")
            db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(db_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)

    def upsert(self, doc: Document, embedding: list[float]) -> None:
        """Insert or update a single Document + embedding."""
        metadata: dict[str, Any] = {
            "title": doc.title,
            "path": str(doc.path),
            "tags": ",".join(doc.tags),
            "refs": ",".join(doc.refs),
            **_flatten_axes(doc.axes),
        }
        self._collection.upsert(
            ids=[doc.id],
            embeddings=[embedding],
            documents=[doc.body],
            metadatas=[metadata],
        )

    def upsert_many(
        self, docs: list[Document], embeddings: list[list[float]]
    ) -> None:
        """Batch upsert with length validation."""
        if len(docs) != len(embeddings):
            raise ValueError("docs and embeddings length mismatch")
        for d, e in zip(docs, embeddings):
            self.upsert(d, e)

    def count(self) -> int:
        return self._collection.count()

    def query(
        self,
        embedding: list[float],
        *,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Vector similarity query with optional axis filter."""
        return self._collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
        )

    def reset(self) -> None:
        """Drop and recreate the collection. Useful for rebuilding."""
        try:
            self._client.delete_collection(name=COLLECTION_NAME)
        except Exception:  # noqa: BLE001 — Chroma raises specific error if not exists
            pass
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)
