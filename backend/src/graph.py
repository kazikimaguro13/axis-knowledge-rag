"""Knowledge graph constructed from YAML frontmatter ``refs:`` fields.

spec_040 (v0.8 marquee). Builds a directed graph (source → target means
``source.refs`` contains ``target``) once at startup and exposes BFS-based
neighbour lookups for retrieval expansion + 3D visualization. The graph is
treated as immutable: callers rebuild it explicitly when knowledge changes.

Broken refs (target id not present in the doc set) and self-loops are
logged + skipped so a single bad reference can never crash the server.
Circular references are allowed — networkx is not DAG-strict.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphNode:
    """Graph node representing a single document."""

    doc_id: str
    title: str
    axes: dict[str, Any] = field(default_factory=dict)
    in_degree: int = 0   # how many docs reference this
    out_degree: int = 0  # how many docs this references


@dataclass(frozen=True)
class GraphEdge:
    """Directed edge: ``source`` references ``target``."""

    source: str
    target: str


class KnowledgeGraph:
    """Wrapper over ``networkx.DiGraph`` for knowledge document refs."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self._g = graph
        self._node_cache: dict[str, GraphNode] = {}

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def build_from_docs(cls, docs: Iterable[dict[str, Any]]) -> KnowledgeGraph:
        """Build a graph from an iterable of frontmatter-like dicts.

        Each dict must have an ``id`` field. ``refs`` is optional (defaults
        to ``[]``). Refs pointing to ids missing from the set are skipped
        and aggregated into a single warning log line. Self-loops are
        silently dropped.
        """
        docs_list = list(docs)
        g: nx.DiGraph = nx.DiGraph()
        doc_ids: set[str] = {d["id"] for d in docs_list if d.get("id")}
        for d in docs_list:
            doc_id = d.get("id")
            if not doc_id:
                continue
            g.add_node(
                doc_id,
                title=str(d.get("title", "")),
                axes=dict(d.get("axes", {}) or {}),
            )

        broken: list[tuple[str, str]] = []
        for d in docs_list:
            src = d.get("id")
            if not src:
                continue
            for tgt in (d.get("refs") or []):
                if tgt == src:
                    continue  # self-loop
                if tgt not in doc_ids:
                    broken.append((src, tgt))
                    continue
                g.add_edge(src, tgt)
        if broken:
            preview = ", ".join(f"{s}->{t}" for s, t in broken[:5])
            suffix = "..." if len(broken) > 5 else ""
            logger.warning(
                "knowledge graph: %d broken ref(s) skipped: %s%s",
                len(broken),
                preview,
                suffix,
            )
        return cls(g)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def neighbors_within_hop(
        self,
        doc_id: str,
        *,
        hop: int = 1,
        max_neighbors: int = 20,
        direction: str = "both",
    ) -> list[str]:
        """Return neighbour ids within ``hop`` BFS levels (deduplicated).

        ``direction`` is one of ``"out"`` (successors only), ``"in"``
        (predecessors only) or ``"both"`` (default; combines them).
        Returns up to ``max_neighbors`` ids in BFS order; the search
        center itself is never included.
        """
        if hop < 1 or max_neighbors < 1:
            return []
        if doc_id not in self._g:
            return []
        visited: set[str] = {doc_id}
        frontier: list[str] = [doc_id]
        results: list[str] = []
        for _ in range(hop):
            next_frontier: list[str] = []
            for node in frontier:
                for n in self._collect_neighbors(node, direction):
                    if n in visited:
                        continue
                    visited.add(n)
                    results.append(n)
                    next_frontier.append(n)
                    if len(results) >= max_neighbors:
                        return results
            frontier = next_frontier
            if not frontier:
                break
        return results

    def _collect_neighbors(self, node: str, direction: str) -> Iterator[str]:
        if direction not in ("in", "out", "both"):
            raise ValueError(f"direction must be 'in' | 'out' | 'both', got {direction!r}")
        if direction in ("out", "both"):
            yield from self._g.successors(node)
        if direction in ("in", "both"):
            yield from self._g.predecessors(node)

    def get_node(self, doc_id: str) -> GraphNode | None:
        if doc_id in self._node_cache:
            return self._node_cache[doc_id]
        if doc_id not in self._g:
            return None
        data = self._g.nodes[doc_id]
        node = GraphNode(
            doc_id=doc_id,
            title=str(data.get("title", "")),
            axes=dict(data.get("axes", {}) or {}),
            in_degree=self._g.in_degree(doc_id),
            out_degree=self._g.out_degree(doc_id),
        )
        self._node_cache[doc_id] = node
        return node

    def get_all_nodes(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[GraphNode]:
        """Return all nodes with optional pagination."""
        all_ids = list(self._g.nodes())
        if offset > 0:
            all_ids = all_ids[offset:]
        if limit is not None:
            all_ids = all_ids[:limit]
        out: list[GraphNode] = []
        for d in all_ids:
            n = self.get_node(d)
            if n is not None:
                out.append(n)
        return out

    def get_all_edges(self) -> list[GraphEdge]:
        return [GraphEdge(source=u, target=v) for u, v in self._g.edges()]

    def find_path(
        self,
        source: str,
        target: str,
        *,
        max_length: int = 5,
    ) -> list[str] | None:
        """Return shortest directed path or ``None`` if not reachable.

        ``find_path(x, x)`` returns ``[x]`` if the node exists, else ``None``.
        Returns ``None`` when the path exceeds ``max_length`` (in edges).
        """
        if source not in self._g or target not in self._g:
            return None
        try:
            path: list[str] = nx.shortest_path(self._g, source=source, target=target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        if len(path) - 1 > max_length:
            return None
        return path

    def stats(self) -> dict[str, int]:
        return {
            "nodes": int(self._g.number_of_nodes()),
            "edges": int(self._g.number_of_edges()),
            "isolated": len(list(nx.isolates(self._g))),
            "weakly_connected_components": int(
                nx.number_weakly_connected_components(self._g)
            ),
        }

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def __contains__(self, doc_id: object) -> bool:
        return doc_id in self._g

    def __len__(self) -> int:
        return self._g.number_of_nodes()


def build_default_graph(knowledge_dir: str | Path | None = None) -> KnowledgeGraph:
    """Convenience: load Markdown frontmatter from disk and build a graph.

    Reads every ``*.md`` under ``knowledge_dir`` (default
    ``./examples/knowledge``). Skips files that fail to parse rather
    than aborting — the graph layer should never break server startup.
    """
    from backend.src.loader import load_directory

    base = Path(knowledge_dir or "./examples/knowledge")
    if not base.exists():
        logger.warning("build_default_graph: %s does not exist — empty graph", base)
        return KnowledgeGraph(nx.DiGraph())
    docs = load_directory(base, pattern="*.md", strict=False)
    payloads = [
        {
            "id": d.id,
            "title": d.title,
            "axes": d.axes,
            "refs": d.refs,
        }
        for d in docs
    ]
    return KnowledgeGraph.build_from_docs(payloads)
