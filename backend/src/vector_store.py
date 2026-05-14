"""ChromaDB wrapper for storing Documents with axis metadata.

Stores body embedding as the primary vector and full axis dict in metadata
so that downstream search.py can filter on axes before / alongside vector
similarity.

spec_031 adds the parent-document path: ``add_chunks()`` embeds *child*
sub-blocks into the same Chroma collection while persisting the *parents*
to a JSON sidecar (``parents.json``) — search-time lookups deduplicate
hits by ``parent_id`` and surface the parent text.
"""

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.src.chunker import ChildChunk, ParentChunk
from backend.src.config import COLLECTION_NAME
from backend.src.loader import Document

logger = logging.getLogger(__name__)

PARENTS_SIDECAR_FILENAME = "parents.json"
PARENTS_SIDECAR_VERSION = 1


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

    def __init__(self, path: Path | None = None, *, in_memory: bool = False) -> None:
        if in_memory:
            self._client = chromadb.EphemeralClient()
            self._sidecar_path: Path | None = None
        else:
            db_path = path or Path("./.chromadb")
            db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(db_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._sidecar_path = db_path / PARENTS_SIDECAR_FILENAME
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)
        # parent_id -> ParentChunk; populated by add_chunks() or load_parents().
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
        if self._sidecar_path is not None and self._sidecar_path.exists():
            with contextlib.suppress(OSError):
                self._sidecar_path.unlink()

    # -----------------------------------------------------------------
    # spec_031: parent-document retrieval
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

        Parents are kept in memory and mirrored to ``parents.json`` next
        to the Chroma directory — embeddings are not needed for them.
        """
        if len(children) != len(child_embeddings):
            raise ValueError("children and embeddings length mismatch")

        self._parents = {p.parent_id: p for p in parents}
        self._persist_parents()

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
        out: list[tuple[ParentChunk, float]] = []
        for pid, score in ranked:
            parent = self._parents.get(pid)
            if parent is None:
                logger.warning("parent_id %s referenced by a child has no entry in parents", pid)
                continue
            out.append((parent, score))
            if len(out) >= top_n_parents:
                break
        return out

    def load_parents(self) -> int:
        """Load ``parents.json`` (if any). Returns the count loaded."""
        if self._sidecar_path is None or not self._sidecar_path.exists():
            return 0
        try:
            payload = json.loads(self._sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("parents.json is unreadable (%s) — ignoring", e)
            return 0
        entries = (payload or {}).get("parents", {}) or {}
        self._parents = {
            pid: ParentChunk(
                parent_id=pid,
                doc_id=str(entry.get("doc_id", "")),
                title=str(entry.get("title", "")),
                text=str(entry.get("text", "")),
                metadata=dict(entry.get("metadata") or {}),
            )
            for pid, entry in entries.items()
        }
        return len(self._parents)

    @property
    def parents(self) -> dict[str, ParentChunk]:
        return self._parents

    def has_parents(self) -> bool:
        """True if the in-memory parents dict OR the sidecar file is populated."""
        if self._parents:
            return True
        return self._sidecar_path is not None and self._sidecar_path.exists()

    def _persist_parents(self) -> None:
        if self._sidecar_path is None:
            return  # in-memory store — nothing to write
        payload = {
            "version": PARENTS_SIDECAR_VERSION,
            "parents": {
                pid: {
                    "doc_id": p.doc_id,
                    "title": p.title,
                    "text": p.text,
                    "metadata": p.metadata,
                }
                for pid, p in self._parents.items()
            },
        }
        self._sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        self._sidecar_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
