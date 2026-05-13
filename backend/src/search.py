"""Hybrid search over the knowledge index.

Combines axis filtering (exact match on metadata) with vector similarity
(cosine on embeddings). The unique selling point of axis-knowledge-rag.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.src.embedder import Embedder
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
            )
        )
    return out


class SearchEngine:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        normalizer: Normalizer | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._normalizer = normalizer or Normalizer()

    def search(
        self,
        query: str | None,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Hybrid search.

        Args:
            query: Natural-language query. If None, axis-only search (top_k arbitrary).
            filters: User-friendly axis filters (`{"category": "技術記事"}`).
            top_k: Maximum results to return.

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

        if query is None:
            # Axis-only path: use a zero embedding (Chroma will then sort by
            # distance from zero, which is arbitrary — but we mostly care about
            # the filter). top_k is bounded by collection size.
            n = min(top_k, max(self._store.count(), 1))
            embedding = [0.0] * 768
        else:
            q_norm = self._normalizer(query)
            embedding = self._embedder.embed(q_norm)
            n = top_k

        raw = self._store.query(embedding=embedding, n_results=n, where=where)
        results = _to_results(raw)
        logger.info(
            "search(query=%r, filters=%s) -> %d results", query, filters, len(results)
        )
        return results


def _main(argv: list[str]) -> int:
    """CLI:
        python -m backend.src.search "<query>" [--category X] [--level Y] [--top 5]
    """
    import argparse

    from backend.src.config import configure_logging, load_axes_config, settings

    configure_logging()
    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--category")
    p.add_argument("--topic")
    p.add_argument("--level")
    p.add_argument("--author")
    p.add_argument("--year", type=int)
    p.add_argument("--top", type=int, default=5)
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
    engine = SearchEngine(store, embedder, normalizer)
    results = engine.search(args.query, filters=filters, top_k=args.top)

    print(f"\n=== {len(results)} results for query={args.query!r} filters={filters} ===\n")
    for r in results:
        print(f"[{r.score:.3f}] {r.id}  {r.title}")
        print(f"        axes: {r.axes}")
        print(f"        {r.body_snippet}\n")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
