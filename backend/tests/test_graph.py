"""Tests for backend/src/graph.py (spec_040)."""

import logging

import pytest

from backend.src.graph import GraphEdge, GraphNode, KnowledgeGraph


def _doc(doc_id: str, refs: list[str] | None = None, **extra) -> dict:
    base = {"id": doc_id, "title": f"Title {doc_id}", "axes": {}, "refs": refs or []}
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# build_from_docs
# ---------------------------------------------------------------------------


def test_build_from_empty_docs() -> None:
    g = KnowledgeGraph.build_from_docs([])
    s = g.stats()
    assert s["nodes"] == 0
    assert s["edges"] == 0


def test_build_with_single_doc_no_refs() -> None:
    g = KnowledgeGraph.build_from_docs([_doc("a")])
    s = g.stats()
    assert s["nodes"] == 1
    assert s["edges"] == 0
    assert g.get_node("a") is not None


def test_build_directed_edges() -> None:
    g = KnowledgeGraph.build_from_docs(
        [_doc("a", ["b"]), _doc("b")]
    )
    edges = g.get_all_edges()
    assert edges == [GraphEdge(source="a", target="b")]
    # a points to b → out_degree(a)=1, in_degree(b)=1
    assert g.get_node("a").out_degree == 1
    assert g.get_node("b").in_degree == 1


def test_self_loop_skipped() -> None:
    g = KnowledgeGraph.build_from_docs([_doc("a", ["a"])])
    assert g.stats()["edges"] == 0


def test_broken_ref_logged_and_skipped(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="backend.src.graph"):
        g = KnowledgeGraph.build_from_docs(
            [_doc("a", ["does_not_exist"]), _doc("b")]
        )
    assert g.stats()["edges"] == 0
    assert any("broken ref" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# neighbors_within_hop
# ---------------------------------------------------------------------------


@pytest.fixture
def chain_graph() -> KnowledgeGraph:
    """a -> b -> c -> d  (linear chain)."""
    return KnowledgeGraph.build_from_docs(
        [_doc("a", ["b"]), _doc("b", ["c"]), _doc("c", ["d"]), _doc("d")]
    )


def test_neighbors_within_hop_1(chain_graph: KnowledgeGraph) -> None:
    n = chain_graph.neighbors_within_hop("a", hop=1, direction="out")
    assert n == ["b"]


def test_neighbors_within_hop_2(chain_graph: KnowledgeGraph) -> None:
    n = chain_graph.neighbors_within_hop("a", hop=2, direction="out")
    assert set(n) == {"b", "c"}


def test_neighbors_max_limit(chain_graph: KnowledgeGraph) -> None:
    n = chain_graph.neighbors_within_hop("a", hop=3, max_neighbors=2, direction="out")
    assert len(n) == 2


def test_neighbors_direction_out_only() -> None:
    g = KnowledgeGraph.build_from_docs([_doc("a", ["b"]), _doc("c", ["a"]), _doc("b")])
    n = g.neighbors_within_hop("a", hop=1, direction="out")
    assert n == ["b"]


def test_neighbors_direction_in_only() -> None:
    g = KnowledgeGraph.build_from_docs([_doc("a", ["b"]), _doc("c", ["a"]), _doc("b")])
    n = g.neighbors_within_hop("a", hop=1, direction="in")
    assert n == ["c"]


def test_neighbors_direction_both() -> None:
    g = KnowledgeGraph.build_from_docs([_doc("a", ["b"]), _doc("c", ["a"]), _doc("b")])
    n = g.neighbors_within_hop("a", hop=1, direction="both")
    assert set(n) == {"b", "c"}


def test_neighbors_unknown_doc_returns_empty() -> None:
    g = KnowledgeGraph.build_from_docs([_doc("a")])
    assert g.neighbors_within_hop("z") == []


# ---------------------------------------------------------------------------
# get_node / get_all_nodes / pagination / stats
# ---------------------------------------------------------------------------


def test_get_node_unknown_returns_none() -> None:
    g = KnowledgeGraph.build_from_docs([_doc("a")])
    assert g.get_node("z") is None


def test_get_node_in_out_degree() -> None:
    g = KnowledgeGraph.build_from_docs(
        [_doc("a", ["b", "c"]), _doc("b"), _doc("c"), _doc("d", ["a"])]
    )
    n_a = g.get_node("a")
    assert n_a is not None
    assert n_a.out_degree == 2
    assert n_a.in_degree == 1
    assert isinstance(n_a, GraphNode)


def test_pagination_get_all_nodes() -> None:
    g = KnowledgeGraph.build_from_docs([_doc(f"d{i}") for i in range(10)])
    first = g.get_all_nodes(limit=3, offset=0)
    second = g.get_all_nodes(limit=3, offset=3)
    assert len(first) == 3
    assert len(second) == 3
    assert {n.doc_id for n in first}.isdisjoint({n.doc_id for n in second})


def test_stats_counts() -> None:
    g = KnowledgeGraph.build_from_docs(
        [_doc("a", ["b"]), _doc("b"), _doc("c"), _doc("d", ["e"]), _doc("e")]
    )
    s = g.stats()
    assert s["nodes"] == 5
    assert s["edges"] == 2
    # c is isolated (no in / out edges)
    assert s["isolated"] == 1
    # 3 weakly connected components: {a,b} {c} {d,e}
    assert s["weakly_connected_components"] == 3


# ---------------------------------------------------------------------------
# find_path
# ---------------------------------------------------------------------------


def test_find_path_exists(chain_graph: KnowledgeGraph) -> None:
    p = chain_graph.find_path("a", "d")
    assert p == ["a", "b", "c", "d"]


def test_find_path_no_path() -> None:
    g = KnowledgeGraph.build_from_docs([_doc("a"), _doc("b")])
    assert g.find_path("a", "b") is None


def test_find_path_self_returns_single_node(chain_graph: KnowledgeGraph) -> None:
    assert chain_graph.find_path("a", "a") == ["a"]


def test_find_path_exceeds_max_length(chain_graph: KnowledgeGraph) -> None:
    assert chain_graph.find_path("a", "d", max_length=2) is None


# ---------------------------------------------------------------------------
# circular refs
# ---------------------------------------------------------------------------


def test_circular_refs_allowed() -> None:
    """A→B→A should not raise and BFS should still terminate."""
    g = KnowledgeGraph.build_from_docs([_doc("a", ["b"]), _doc("b", ["a"])])
    assert g.stats()["edges"] == 2
    n = g.neighbors_within_hop("a", hop=5, max_neighbors=10, direction="out")
    # a -> b -> (a already visited, stop)
    assert n == ["b"]
