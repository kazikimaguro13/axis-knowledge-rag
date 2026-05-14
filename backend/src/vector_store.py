"""ChromaDB wrapper for storing Documents with axis metadata.

Stores body embedding as the primary vector and full axis dict in metadata
so that downstream search.py can filter on axes before / alongside vector
similarity.

spec_031 adds the parent-document path: ``add_chunks()`` embeds *child*
sub-blocks into the same Chroma collection while persisting the *parents*
to a SQLite sidecar (``parents.db``) — search-time lookups deduplicate
hits by ``parent_id`` and surface the parent text.

spec_037 migrates parent storage from ``parents.json`` (eager full-load)
to ``parents.db`` (SQLite, lazy SELECT per parent_id).  A ``parents.json``
sidecar found on first open is automatically migrated (one-time, warning
logged).  Use ``storage="json"`` to fall back to the v0.7 behaviour.
"""

import contextlib
import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.src.chunker import ChildChunk, ParentChunk
from backend.src.config import COLLECTION_NAME
from backend.src.loader import Document
from backend.src.parent_storage import (
    ParentStorage,
    SqliteParentStorage,
    make_parent_storage,
)

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


def _flatten_axes_with_norm(
    axes: dict[str, Any], normalized: dict[str, str]
) -> dict[str, str | int | float | bool]:
    """`_flatten_axes` の出力に `axis_<key>_norm` を併記したもの。

    生の値は UI 表示 / debug 用に残しつつ、normalize 後の値を where 句で
    使えるように別キーで持つ。
    """
    out = _flatten_axes(axes)
    for k, v in normalized.items():
        out[f"axis_{k}_norm"] = v
    return out


class VectorStore:
    """ChromaDB-backed store for Document embeddings + axis metadata."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        in_memory: bool = False,
        storage: str = "sqlite",
    ) -> None:
        if in_memory:
            self._client = chromadb.EphemeralClient()
            self._chroma_dir: Path | None = None
            self._parent_storage: ParentStorage = SqliteParentStorage(":memory:")
        else:
            db_path = path or Path("./.chromadb")
            db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(db_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._chroma_dir = db_path
            self._parent_storage = make_parent_storage(db_path, storage=storage)
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)
        # in-memory cache; populated by add_chunks() or load_parents()
        self._parents: dict[str, ParentChunk] = {}

    def upsert(self, doc: Document, embedding: list[float]) -> None:
        """Insert or update a single Document + embedding."""
        metadata: dict[str, Any] = {
            "title": doc.title,
            "title_norm": doc.normalized_title,
            "path": str(doc.path),
            "tags": ",".join(doc.tags),
            "tags_norm": ",".join(doc.normalized_tags),
            "refs": ",".join(doc.refs),
            **_flatten_axes_with_norm(doc.axes, doc.normalized_axes),
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
        for d, e in zip(docs, embeddings, strict=False):
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

    def list_with_filter(
        self,
        *,
        where: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List documents by axis filter with pagination — no top_k cap.

        Backed by ChromaDB's `collection.get()`, which does not require a
        query embedding (unlike `query()`) and accepts arbitrary limit/offset.
        Returns the raw Chroma payload (`ids`, `metadatas`, `documents`).
        """
        return self._collection.get(
            where=where,
            include=["metadatas", "documents"],
            limit=limit,
            offset=offset,
        )

    def count_with_filter(self, where: dict[str, Any] | None = None) -> int:
        """Count documents matching the filter.

        Uses `collection.get(include=[])` so only IDs are fetched. For an
        unfiltered total, `count()` is cheaper; this is the filtered variant.
        """
        if where is None:
            return self._collection.count()
        result = self._collection.get(where=where, include=[])
        return len(result.get("ids", []))

    def reset(self) -> None:
        """Drop and recreate the collection. Useful for rebuilding."""
        with contextlib.suppress(Exception):
            self._client.delete_collection(name=COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)
        self._parents = {}
        self._parent_storage.clear()

    # -----------------------------------------------------------------
    # spec_031 / spec_037: parent-document retrieval
    # -----------------------------------------------------------------

    def add_chunks(
        self,
        parents: list[ParentChunk],
        children: list[ChildChunk],
        child_embeddings: list[list[float]],
    ) -> None:
        """Persist parents + embed children for parent-document retrieval.

        Children are stored in the same Chroma collection as legacy
        Documents (different id namespace — child ids carry ``#``), keyed
        by their ``child_id``. ``parent_id`` is written into each child's
        metadata so search can deduplicate and look up the parent text.

        Parents are persisted via ``_parent_storage`` (SQLite by default)
        and also cached in-memory.
        """
        if len(children) != len(child_embeddings):
            raise ValueError("children and embeddings length mismatch")

        self._parents = {p.parent_id: p for p in parents}
        self._parent_storage.upsert_many(parents)

        if not children:
            return

        ids = [c.child_id for c in children]
        metadatas: list[dict[str, Any]] = []
        documents: list[str] = []
        for c in children:
            md: dict[str, Any] = {
                "parent_id": c.parent_id,
                "doc_id": c.doc_id,
                "kind": "child",
                "token_estimate": c.token_estimate,
            }
            md.update(_flatten_axes(c.metadata.get("axes", {}) or {}))
            normalized_axes = c.metadata.get("normalized_axes") or {}
            for k, v in normalized_axes.items():
                md[f"axis_{k}_norm"] = v
            title = c.metadata.get("title")
            if isinstance(title, str):
                md["title"] = title
            metadatas.append(md)
            documents.append(c.text)

        self._collection.add(
            ids=ids,
            embeddings=child_embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query_children(
        self,
        embedding: list[float],
        *,
        n_results: int = 20,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Raw child-level query — search.py uses this then dedup'es by parent."""
        return self._collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
        )

    def query_with_parents(
        self,
        embedding: list[float],
        *,
        top_k_children: int = 20,
        top_n_parents: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[ParentChunk, float]]:
        """Retrieve children, dedup by ``parent_id``, return top N parents.

        Score per parent is the best (max) cosine similarity among its
        matched children — gives the parent its strongest hit's score.
        """
        raw = self.query_children(
            embedding, n_results=top_k_children, where=where
        )
        metadatas = raw.get("metadatas", [[]])[0] or []
        distances = raw.get("distances", [[]])[0] or []

        best: dict[str, float] = {}
        for md, dist in zip(metadatas, distances, strict=True):
            pid = (md or {}).get("parent_id")
            if not pid:
                continue
            score = max(0.0, min(1.0, 1.0 - float(dist)))
            if pid not in best or score > best[pid]:
                best[pid] = score

        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        top_pids = [pid for pid, _ in ranked]
        fetched = {p.parent_id: p for p in self._parent_storage.get_many(top_pids)}

        out: list[tuple[ParentChunk, float]] = []
        for pid, score in ranked:
            parent = fetched.get(pid)
            if parent is None:
                logger.warning("parent_id %s referenced by a child has no entry in parents", pid)
                continue
            out.append((parent, score))
            if len(out) >= top_n_parents:
                break
        return out

    def load_parents(self) -> int:
        """Populate the in-memory parents cache from storage. Returns count loaded.

        For SQLite storage this issues a SELECT * to fill the cache, keeping
        backward-compat with callers that access ``self.parents`` after this
        call.  In-memory stores start fresh and have nothing to load.
        """
        if self._chroma_dir is None:
            return 0
        if hasattr(self._parent_storage, "list_all"):
            parents = self._parent_storage.list_all()  # type: ignore[attr-defined]
            self._parents = {p.parent_id: p for p in parents}
        return len(self._parents)

    @property
    def parents(self) -> dict[str, ParentChunk]:
        return self._parents

    def has_parents(self) -> bool:
        """True if the storage backend contains at least one parent."""
        return self._parent_storage.count() > 0
