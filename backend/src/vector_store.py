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


_KATAKANA_RANGE = (0x30A1, 0x30F6)
_HIRAGANA_RANGE = (0x3041, 0x3096)


def _warn_if_parents_look_normalized(parents: list[ParentChunk]) -> None:
    """Heuristic check (spec_043) for legacy parents indexed before the bugfix.

    v0.8.1 and earlier ran chunker on ``normalized_body`` (NFKC + katakana →
    hiragana + lowercase), so stored parent text was unreadable for the UI.
    If we sample a handful of parents and they have plenty of hiragana but
    *zero* katakana and *zero* uppercase ASCII, the index was almost certainly
    built with the old code path. Log a warning recommending a rebuild — we
    do NOT auto-rebuild to avoid surprising data loss.
    """
    if not parents:
        return
    suspicious = 0
    sample = parents[: min(5, len(parents))]
    for p in sample:
        text = p.text or ""
        if not text:
            continue
        has_hira = any(_HIRAGANA_RANGE[0] <= ord(c) <= _HIRAGANA_RANGE[1] for c in text)
        has_kata = any(_KATAKANA_RANGE[0] <= ord(c) <= _KATAKANA_RANGE[1] for c in text)
        has_upper = any(c.isascii() and c.isupper() for c in text)
        # A genuine JP doc with this much hiragana almost always carries some
        # katakana too; pure hiragana + no uppercase ASCII is the smoking gun.
        if has_hira and not has_kata and not has_upper:
            suspicious += 1
    if suspicious >= 2:  # at least two of five samples → likely normalized
        logger.warning(
            "parents.db looks normalized (no katakana / no uppercase in sampled text). "
            "v0.8.2 (spec_043) stores parent text as the original body — please rebuild "
            "with: python -m scripts.build_index <knowledge_dir> --rebuild"
        )


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

    def probe_dim(self) -> int | None:
        """Return the stored embedding dim, or ``None`` if the store is empty.

        spec_051 HIGH-1: used by ``api.lifespan`` to detect embedder /
        index dim mismatch on startup. Pulls a single row with
        ``include=["embeddings"]`` so the cost is independent of
        collection size. Chroma returns embeddings as a numpy array,
        so guard with ``len()`` rather than ``or`` truthiness which
        raises on multi-element arrays.
        """
        try:
            raw = self._collection.get(limit=1, include=["embeddings"])
        except Exception as e:  # noqa: BLE001
            logger.debug("probe_dim failed: %s", e)
            return None
        embs = raw.get("embeddings")
        if embs is None:
            return None
        try:
            if len(embs) == 0:
                return None
            first = embs[0]
        except TypeError:
            return None
        if first is None:
            return None
        try:
            return int(len(first))
        except TypeError:
            return None

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

    def delete_doc(self, doc_id: str) -> int:
        """Remove every chunk + parent belonging to ``doc_id``. Returns deleted child count.

        Used by the live-ingest path (spec_056) to make memo re-ingest behave
        as upsert: re-chunking with the same ``doc_id`` produces deterministic
        ``parent_id`` / ``child_id`` (v0.9.3, spec_055), so a plain ``add``
        would trip Chroma's DuplicateIDError. We drop both sides — children
        from the Chroma collection (matched on the ``doc_id`` metadata) and
        parents from the SQLite sidecar — so the next ``add_chunks`` is a
        clean insert. No-op on unknown ids; safe to call before every add.
        """
        deleted = 0
        try:
            existing = self._collection.get(where={"doc_id": doc_id}, include=[])
            ids = list(existing.get("ids") or [])
            if ids:
                self._collection.delete(ids=ids)
                deleted = len(ids)
        except Exception as e:  # noqa: BLE001
            logger.warning("delete_doc: chroma delete failed for %s: %s", doc_id, e)
        try:
            removed_parents = self._parent_storage_delete_by_doc(doc_id)
            if removed_parents:
                self._parents = {
                    pid: p for pid, p in self._parents.items() if p.doc_id != doc_id
                }
        except Exception as e:  # noqa: BLE001
            logger.warning("delete_doc: parent storage delete failed for %s: %s", doc_id, e)
        return deleted

    def _parent_storage_delete_by_doc(self, doc_id: str) -> int:
        """Best-effort delete of parents owned by ``doc_id``.

        Sqlite backend has a doc_id index — issue a direct DELETE. JSON
        backend has no index but the dict is small enough to filter
        in-process. Returns the number of parents removed.
        """
        store = self._parent_storage
        if isinstance(store, SqliteParentStorage):
            conn = store._conn  # noqa: SLF001 — single-package boundary
            cur = conn.execute("DELETE FROM parents WHERE doc_id = ?", (doc_id,))
            conn.commit()
            return int(cur.rowcount or 0)
        # Fallback for JsonParentStorage / future backends: list_all + filter
        if hasattr(store, "list_all"):
            all_parents = store.list_all()  # type: ignore[attr-defined]
            to_keep = [p for p in all_parents if p.doc_id != doc_id]
            removed = len(all_parents) - len(to_keep)
            if removed:
                store.clear()
                store.upsert_many(to_keep)
            return removed
        return 0

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
            _warn_if_parents_look_normalized(list(self._parents.values()))
        return len(self._parents)

    @property
    def parents(self) -> dict[str, ParentChunk]:
        return self._parents

    def has_parents(self) -> bool:
        """True if the storage backend contains at least one parent."""
        return self._parent_storage.count() > 0
