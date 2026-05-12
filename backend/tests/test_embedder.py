"""Smoke tests for embedder. Run via: python -m backend.tests.test_embedder"""

import sys

from backend.src.embedder import EMBEDDING_DIM, Embedder


def test_dummy_returns_correct_dim() -> None:
    e = Embedder(force_dummy=True)
    assert e.is_dummy
    v = e.embed("hello world")
    assert isinstance(v, list)
    assert len(v) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in v)
    assert all(-1.0 <= x <= 1.0 for x in v)


def test_dummy_is_deterministic() -> None:
    e = Embedder(force_dummy=True)
    v1 = e.embed("same text")
    v2 = e.embed("same text")
    assert v1 == v2


def test_dummy_differs_across_texts() -> None:
    e = Embedder(force_dummy=True)
    v1 = e.embed("alpha")
    v2 = e.embed("beta")
    assert v1 != v2


def test_embed_batch_shape() -> None:
    e = Embedder(force_dummy=True)
    out = e.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == EMBEDDING_DIM for v in out)
    assert out[0] != out[1]


if __name__ == "__main__":
    tests = [
        test_dummy_returns_correct_dim,
        test_dummy_is_deterministic,
        test_dummy_differs_across_texts,
        test_embed_batch_shape,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    sys.exit(1 if failed else 0)
