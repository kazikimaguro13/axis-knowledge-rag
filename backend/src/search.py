"""Hybrid search over the knowledge index.

Combines axis filtering (exact match on metadata) with vector similarity
(cosine on embeddings). The unique selling point of axis-knowledge-rag.

spec_031 adds the *parent-document* retrieval path: when
``parent_doc_enabled=True`` the engine searches over child sub-chunks,
deduplicates by ``parent_id`` and surfaces the H2 parent section as the
result. BM25 fusion still scores at the document (file) level — for
multi-parent documents we keep ``max(parent_score)`` so the best-matching
section dominates.

spec_035 adds optional time-weighted decay: when ``time_decay_config`` is
provided and enabled, each result's score is adjusted by an exponential
half-life factor derived from the document's frontmatter date field.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.src._decay import blend_score, decay_factor
from backend.src.bm25_index import BM25Index
from backend.src.chunker import ParentChunk
from backend.src.config import TimeDecayConfig
from backend.src.embedder import Embedder
from backend.src.graph import KnowledgeGraph
from backend.src.normalizer import Normalizer
from backend.src.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    id: str
    title: str
    score: float
    axes: dict[str, Any]
    body_snippet: str
    path: str
    refs: list[str] = field(default_factory=list)
    # spec_031: full parent body for RAG context construction. Empty in the
    # legacy file-level path (where ``body_snippet`` is already the whole
    # body, just truncated to 200 chars). Populated only by parent-doc mode.
    body_full: str = ""
    # spec_035: raw doc metadata (frontmatter fields) for time-decay lookup.
    metadata: dict[str, Any] = field(default_factory=dict)


def _build_where(filters: dict[str, Any]) -> dict[str, Any] | None:
    """Translate user-level filters to Chroma where-clause (raw axis values).

    Pre-Day 9 path, kept for tests that pre-date normalization.
    """
    if not filters:
        return None
    out = {f"axis_{k}": v for k, v in filters.items()}
    if len(out) == 1:
        return out
    # Chroma 0.5 requires explicit $and for multi-key
    return {"$and": [{k: v} for k, v in out.items()]}


def _build_where_norm(filters: dict[str, Any]) -> dict[str, Any] | None:
    """Same shape as `_build_where` but targets the `axis_*_norm` keys.

    User passes already-normalized values: {"category": "技術記事"}
    Chroma where: {"axis_category_norm": "技術記事"}
    """
    if not filters:
        return None
    out = {f"axis_{k}_norm": v for k, v in filters.items()}
    if len(out) == 1:
        return out
    return {"$and": [{k: v} for k, v in out.items()]}


def _snippet(body: str, max_chars: int = 200) -> str:
    body = body.strip().replace("\n", " ")
    if len(body) <= max_chars:
        return body
    return body[:max_chars] + "..."


def _to_results(raw: dict[str, Any]) -> list[SearchResult]:
    """Convert Chroma query() output to SearchResult list."""
    ids = raw.get("ids", [[]])[0]
    distances = raw.get("distances", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]
    documents = raw.get("documents", [[]])[0]

    out: list[SearchResult] = []
    for i, doc_id in enumerate(ids):
        md = metadatas[i] or {}
        dist = distances[i] if distances else 0.0
        score = max(0.0, min(1.0, 1.0 - dist))
        axes = {
            k.removeprefix("axis_"): v
            for k, v in md.items()
            if k.startswith("axis_") and not k.endswith("_norm")
        }
        refs = [r for r in (md.get("refs") or "").split(",") if r]
        out.append(
            SearchResult(
                id=doc_id,
                title=str(md.get("title", "")),
                score=score,
                axes=axes,
                body_snippet=_snippet(documents[i] if documents else ""),
                path=str(md.get("path", "")),
                refs=refs,
                metadata=dict(md),
            )
        )
    return out


def _apply_time_decay(
    results: list[SearchResult], td: TimeDecayConfig
) -> list[SearchResult]:
    """Reweight each result's score using exponential half-life decay.

    Docs without the configured date field get decay=1.0 (no penalty).
    """
    out = []
    for r in results:
        updated = r.metadata.get(td.date_field)
        d = decay_factor(updated, half_life_days=td.half_life_days)
        new_score = blend_score(r.score, d, td.weight)
        out.append(
            SearchResult(
                id=r.id,
                title=r.title,
                score=new_score,
                axes=r.axes,
                body_snippet=r.body_snippet,
                path=r.path,
                refs=r.refs,
                body_full=r.body_full,
                metadata=r.metadata,
            )
        )
    return out


class SearchEngine:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        normalizer: Normalizer | None = None,
        bm25_index: BM25Index | None = None,
        *,
        parent_doc_enabled: bool = False,
        top_k_children: int = 20,
        time_decay_config: TimeDecayConfig | None = None,
        graph: KnowledgeGraph | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._normalizer = normalizer or Normalizer()
        self._bm25_index = bm25_index
        self._parent_doc_enabled = parent_doc_enabled
        self._top_k_children = top_k_children
        self._time_decay_config = time_decay_config
        self._graph = graph
        if parent_doc_enabled and not store.parents:
            # Try lazy-load from sidecar so callers can build the engine
            # without remembering the load step.
            try:
                store.load_parents()
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to lazy-load parents.json: %s", e)

    @property
    def parent_doc_enabled(self) -> bool:
        return self._parent_doc_enabled

    @property
    def graph(self) -> KnowledgeGraph | None:
        return self._graph

    def search(
        self,
        query: str | None,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
        bm25_weight: float = 0.5,
        graph_expand: bool = False,
        graph_hop: int = 1,
        graph_max_neighbors: int = 10,
    ) -> list[SearchResult]:
        """Hybrid search (axis + vector + optional BM25 fusion + optional graph expand).

        Args:
            query: Natural-language query. If None, axis-only search (top_k arbitrary).
            filters: User-friendly axis filters (`{"category": "技術記事"}`).
            top_k: Maximum results to return.
            bm25_weight: Weight of the BM25 score in the weighted-sum fusion
                with the vector cosine score. ``0.0`` falls back to the v0.5
                vector-only behaviour, ``1.0`` ranks purely by BM25. Ignored
                when no ``bm25_index`` is wired into the engine or when the
                query is ``None``.
            graph_expand: spec_040. If True and the engine has a graph
                wired, merge 1-hop refs neighbours of the top 5 hits into
                the result set with a 0.7× score decay relative to their
                source.
            graph_hop: BFS depth for graph expansion (default 1).
            graph_max_neighbors: per-source neighbour cap.

        Query / filters are normalized before being passed to Chroma so that
        the index (which stores `axis_*_norm` keys) can match across writing
        variants (全角/半角・カタカナ/ひらがな・大文字小文字).
        """
        norm_filters = (
            {k: self._normalizer(str(v)) for k, v in filters.items()}
            if filters
            else None
        )
        where = _build_where_norm(norm_filters or {})
        use_bm25 = (
            query is not None
            and self._bm25_index is not None
            and bm25_weight > 0.0
        )

        if self._parent_doc_enabled:
            pd_results = self._search_parent_doc(
                query, where=where, top_k=top_k, bm25_weight=bm25_weight
            )
            if graph_expand:
                pd_results = self._expand_with_graph(
                    pd_results, hop=graph_hop, max_neighbors=graph_max_neighbors
                )
            return pd_results

        if query is None:
            # Axis-only path: use a zero embedding (Chroma will then sort by
            # distance from zero, which is arbitrary — but we mostly care about
            # the filter). top_k is bounded by collection size.
            n = min(top_k, max(self._store.count(), 1))
            embedding = [0.0] * 768
        else:
            q_norm = self._normalizer(query)
            embedding = self._embedder.embed(q_norm)
            # Over-fetch when fusing so BM25 can re-rank candidates that
            # ranked just outside the original vector top_k.
            n = max(top_k * 2, 20) if use_bm25 else top_k

        raw = self._store.query(embedding=embedding, n_results=n, where=where)
        results = _to_results(raw)

        if use_bm25:
            assert query is not None and self._bm25_index is not None
            bm25_scores = self._bm25_index.score(query)
            fused: list[SearchResult] = []
            for r in results:
                bm25 = bm25_scores.get(r.id, 0.0)
                final = (1.0 - bm25_weight) * r.score + bm25_weight * bm25
                fused.append(
                    SearchResult(
                        id=r.id,
                        title=r.title,
                        score=final,
                        axes=r.axes,
                        body_snippet=r.body_snippet,
                        path=r.path,
                        refs=r.refs,
                        metadata=r.metadata,
                    )
                )
            fused.sort(key=lambda r: r.score, reverse=True)
            results = fused[:top_k]

        # spec_035: apply time-weighted decay after fusion (re-sort needed).
        td = self._time_decay_config
        if td is not None and td.enabled and td.weight > 0:
            results = _apply_time_decay(results, td)
            results.sort(key=lambda r: r.score, reverse=True)
            results = results[:top_k]

        # spec_040: graph expansion (post-decay). Adds 1-hop refs neighbours
        # of the top hits with a 0.7× decay multiplier. Caller-opt-in only.
        if graph_expand:
            results = self._expand_with_graph(
                results, hop=graph_hop, max_neighbors=graph_max_neighbors
            )

        logger.info(
            "search(query=%r, filters=%s, bm25_weight=%.2f, graph_expand=%s) -> %d results",
            query,
            filters,
            bm25_weight,
            graph_expand,
            len(results),
        )
        return results

    # -----------------------------------------------------------------
    # spec_031: parent-document retrieval path
    # -----------------------------------------------------------------

    def _search_parent_doc(
        self,
        query: str | None,
        *,
        where: dict[str, Any] | None,
        top_k: int,
        bm25_weight: float,
    ) -> list[SearchResult]:
        """Child-level vector search → group by parent → optional BM25 fusion."""
        use_bm25 = (
            query is not None
            and self._bm25_index is not None
            and bm25_weight > 0.0
        )

        if query is None:
            # Axis-only: zero embedding, rely on the filter. top_k_children
            # is already a soft cap on the parent dedup pool.
            embedding = [0.0] * 768
            n_children = max(self._top_k_children, top_k)
        else:
            q_norm = self._normalizer(query)
            embedding = self._embedder.embed(q_norm)
            # Over-fetch children so BM25 / parent dedup has enough candidates.
            n_children = max(self._top_k_children, top_k * 4)

        # Pull *more* parents than top_k when fusing — BM25 may reorder.
        parent_pool = max(top_k * 2, top_k + 5) if use_bm25 else top_k
        ranked_parents = self._store.query_with_parents(
            embedding,
            top_k_children=n_children,
            top_n_parents=parent_pool,
            where=where,
        )
        results = [self._parent_to_result(p, score) for p, score in ranked_parents]

        if use_bm25:
            assert query is not None and self._bm25_index is not None
            bm25_scores = self._bm25_index.score(query)
            fused: list[SearchResult] = []
            for r in results:
                # BM25 is keyed by file-level doc_id (the chunker's doc_id).
                bm25 = bm25_scores.get(r.path, 0.0)
                if bm25 == 0.0:
                    bm25 = bm25_scores.get(r.id.split("#", 1)[0], 0.0)
                final = (1.0 - bm25_weight) * r.score + bm25_weight * bm25
                fused.append(
                    SearchResult(
                        id=r.id,
                        title=r.title,
                        score=final,
                        axes=r.axes,
                        body_snippet=r.body_snippet,
                        path=r.path,
                        refs=r.refs,
                        body_full=r.body_full,
                        metadata=r.metadata,
                    )
                )
            # Collapse multiple parents from the same doc — keep best score.
            by_doc: dict[str, SearchResult] = {}
            for r in sorted(fused, key=lambda x: x.score, reverse=True):
                if r.path not in by_doc:
                    by_doc[r.path] = r
            results = sorted(by_doc.values(), key=lambda r: r.score, reverse=True)[:top_k]
        else:
            results = results[:top_k]

        # spec_035: apply time-weighted decay after fusion (re-sort needed).
        td = self._time_decay_config
        if td is not None and td.enabled and td.weight > 0:
            results = _apply_time_decay(results, td)
            results.sort(key=lambda r: r.score, reverse=True)
            results = results[:top_k]

        logger.info(
            "search[parent_doc](query=%r, bm25_weight=%.2f) -> %d parents",
            query,
            bm25_weight,
            len(results),
        )
        return results

    def _parent_to_result(self, parent: ParentChunk, score: float) -> SearchResult:
        meta = parent.metadata or {}
        axes_raw = meta.get("axes") or {}
        axes = dict(axes_raw) if isinstance(axes_raw, dict) else {}
        refs = meta.get("refs") or []
        if not isinstance(refs, list):
            refs = []
        return SearchResult(
            id=parent.parent_id,
            title=parent.title,
            score=score,
            axes=axes,
            body_snippet=_snippet(parent.text),
            path=parent.doc_id,
            refs=list(refs),
            body_full=parent.text,
            metadata=dict(meta),
        )

    # -----------------------------------------------------------------
    # spec_040: graph-based retrieval expansion
    # -----------------------------------------------------------------

    _GRAPH_EXPANSION_DECAY = 0.7

    def _expand_with_graph(
        self,
        results: list[SearchResult],
        *,
        hop: int,
        max_neighbors: int,
    ) -> list[SearchResult]:
        """Append refs-graph neighbours of the top hits to ``results``.

        Neighbour score = source score × 0.7 (so direct hits always
        outrank graph-expanded ones for the same source). Deduplicates
        against already-present ids. Returns a re-sorted list, never
        truncated — the caller decides if/when to slice.
        """
        if self._graph is None:
            logger.warning(
                "graph_expand=True but no KnowledgeGraph wired into engine — skipping"
            )
            return results
        if not results:
            return results

        seen: set[str] = {r.id for r in results}
        # Top 5 seed sources for expansion (spec_040 §3-2).
        seeds = results[:5]
        expanded: list[SearchResult] = list(results)
        for src in seeds:
            seed_doc_id = self._seed_doc_id(src)
            if not seed_doc_id:
                continue
            neighbours = self._graph.neighbors_within_hop(
                seed_doc_id,
                hop=hop,
                max_neighbors=max_neighbors,
            )
            for nid in neighbours:
                if nid in seen:
                    continue
                neighbour = self._fetch_doc_as_result(
                    nid, score=src.score * self._GRAPH_EXPANSION_DECAY
                )
                if neighbour is None:
                    continue
                seen.add(nid)
                expanded.append(neighbour)
        expanded.sort(key=lambda r: r.score, reverse=True)
        return expanded

    @staticmethod
    def _seed_doc_id(result: SearchResult) -> str:
        """Pick the file-level doc id for graph lookup.

        Parent-doc results carry ``id = "doc_NNN#slug"`` so the path
        (== file-level doc id) is the right key. Legacy results put
        the doc id directly in ``id``.
        """
        if "#" in result.id and result.path:
            return result.path
        return result.id

    def _fetch_doc_as_result(
        self, doc_id: str, *, score: float
    ) -> SearchResult | None:
        """Build a SearchResult for a graph-neighbour ``doc_id``.

        Tries the file-level Chroma collection first; if the index is in
        parent-doc mode the file id isn't stored there directly, so we
        fall back to the first parent whose ``doc_id`` matches.
        """
        # File-level path: Chroma stores the doc directly under doc_id.
        try:
            raw = self._store._collection.get(  # noqa: SLF001 — internal use
                ids=[doc_id], include=["metadatas", "documents"]
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("graph fetch %s failed: %s", doc_id, e)
            raw = {}
        ids = raw.get("ids") or []
        if ids:
            md = (raw.get("metadatas") or [{}])[0] or {}
            documents = raw.get("documents") or [""]
            body = documents[0] if documents else ""
            axes = {
                k.removeprefix("axis_"): v
                for k, v in md.items()
                if k.startswith("axis_") and not k.endswith("_norm")
            }
            refs = [r for r in (md.get("refs") or "").split(",") if r]
            return SearchResult(
                id=doc_id,
                title=str(md.get("title", "")),
                score=score,
                axes=axes,
                body_snippet=_snippet(body),
                path=str(md.get("path", "")),
                refs=refs,
                body_full=body if body else "",
                metadata=dict(md),
            )

        # Parent-doc fallback: pick the first parent for this doc.
        for parent in self._store.parents.values():
            if parent.doc_id == doc_id:
                return self._parent_to_result(parent, score)
        logger.debug("graph neighbour %s not found in vector store", doc_id)
        return None


def _main(argv: list[str]) -> int:
    """CLI:
        python -m backend.src.search "<query>" [--category X] [--level Y] [--top 5]
    """
    import argparse

    from backend.src.config import (
        configure_logging,
        load_app_config,
        load_axes_config,
        settings,
    )

    configure_logging()
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--category")
    p.add_argument("--topic")
    p.add_argument("--level")
    p.add_argument("--author")
    p.add_argument("--year", type=int)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--bm25-weight", type=float, default=0.0)
    p.add_argument("--db-path", default=str(settings.chroma_db_path))
    args = p.parse_args(argv[1:])

    filters = {
        k: v
        for k, v in {
            "category": args.category,
            "topic": args.topic,
            "level": args.level,
            "author": args.author,
            "year": args.year,
        }.items()
        if v is not None
    }

    from pathlib import Path

    store = VectorStore(path=Path(args.db_path))
    embedder = Embedder()
    normalizer = Normalizer.from_config(load_axes_config())
    app_cfg = load_app_config()
    pd = app_cfg.retrieval.parent_doc
    parent_doc_enabled = pd.enabled and store.has_parents()
    engine = SearchEngine(
        store,
        embedder,
        normalizer,
        parent_doc_enabled=parent_doc_enabled,
        top_k_children=pd.top_k_children,
        time_decay_config=app_cfg.retrieval.time_decay,
    )
    results = engine.search(
        args.query,
        filters=filters,
        top_k=args.top,
        bm25_weight=args.bm25_weight,
    )

    print(f"\n=== {len(results)} results for query={args.query!r} filters={filters} ===\n")
    for r in results:
        print(f"[{r.score:.3f}] {r.id}  {r.title}")
        print(f"        axes: {r.axes}")
        print(f"        {r.body_snippet}\n")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
