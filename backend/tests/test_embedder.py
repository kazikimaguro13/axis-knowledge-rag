"""Smoke tests for embedder."""

from backend.src.embedder import EMBEDDING_DIM, Embedder


def test_dummy_returns_correct_dim(dummy_embedder: Embedder) -> None:
    assert dummy_embedder.is_dummy
    v = dummy_embedder.embed("hello world")
    assert isinstance(v, list)
    assert len(v) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in v)
    assert all(-1.0 <= x <= 1.0 for x in v)


def test_dummy_is_deterministic(dummy_embedder: Embedder) -> None:
    v1 = dummy_embedder.embed("same text")
    v2 = dummy_embedder.embed("same text")
    assert v1 == v2


def test_dummy_differs_across_texts(dummy_embedder: Embedder) -> None:
    v1 = dummy_embedder.embed("alpha")
    v2 = dummy_embedder.embed("beta")
    assert v1 != v2


def test_embed_batch_shape(dummy_embedder: Embedder) -> None:
    out = dummy_embedder.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == EMBEDDING_DIM for v in out)
    assert out[0] != out[1]
