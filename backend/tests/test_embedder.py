"""Smoke tests for embedder."""

from unittest.mock import MagicMock, patch

import pytest

from backend.src.embedder import (
    EMBEDDING_DIM,
    DummyEmbedder,
    Embedder,
    GeminiEmbedder,
    OllamaEmbedder,
    make_embedder,
)


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


# ---------------------------------------------------------------------------
# spec_045: Protocol + factory + OllamaEmbedder
# ---------------------------------------------------------------------------


def test_protocol_runtime_check() -> None:
    """All 3 concrete embedders satisfy the ``Embedder`` Protocol."""
    assert isinstance(DummyEmbedder(), Embedder)
    # GeminiEmbedder always force-dummies when no key — still satisfies Protocol.
    assert isinstance(GeminiEmbedder(force_dummy=True), Embedder)


def test_dummy_embedder_dim_property() -> None:
    e = DummyEmbedder()
    assert e.dim == EMBEDDING_DIM
    assert e.is_dummy is True


def test_make_embedder_default_gemini() -> None:
    """Default cfg (backend=gemini, no key) → GeminiEmbedder in dummy mode."""
    from backend.src.config import EmbedderConfig

    e = make_embedder(EmbedderConfig())
    assert isinstance(e, GeminiEmbedder)
    # No GEMINI_API_KEY in CI → dummy-mode Gemini
    assert e.is_dummy is True


def test_make_embedder_dummy_backend() -> None:
    from backend.src.config import EmbedderConfig

    e = make_embedder(EmbedderConfig(backend="dummy"))
    assert isinstance(e, DummyEmbedder)
    assert e.is_dummy is True


def test_make_embedder_unknown_backend_falls_back_to_gemini() -> None:
    from backend.src.config import EmbedderConfig

    e = make_embedder(EmbedderConfig(backend="not-a-real-backend"))
    assert isinstance(e, GeminiEmbedder)


def test_make_embedder_ollama_import_failure_falls_back() -> None:
    """spec_045: when the ``ollama`` package can't be imported, fall back to dummy."""
    from backend.src.config import EmbedderConfig, OllamaConfig

    # Patch the class to raise on construction → factory must catch + warn.
    with patch.object(
        OllamaEmbedder, "__init__", side_effect=ImportError("ollama not installed")
    ):
        e = make_embedder(EmbedderConfig(backend="ollama", ollama=OllamaConfig()))
    assert isinstance(e, DummyEmbedder)


def test_ollama_embedder_embed_uses_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """OllamaEmbedder.embed() POSTs through the ollama client and returns the vector."""
    fake_client = MagicMock()
    fake_client.embeddings.return_value = {"embedding": [0.1, 0.2, 0.3, 0.4]}
    fake_ollama = MagicMock()
    fake_ollama.Client.return_value = fake_client

    monkeypatch.setitem(__import__("sys").modules, "ollama", fake_ollama)
    e = OllamaEmbedder(model="bge-m3", url="http://localhost:11434")

    assert e.is_dummy is False
    assert e.dim == 4  # from the probe response
    v = e.embed("hello")
    assert v == [0.1, 0.2, 0.3, 0.4]
    # 1 probe + 1 embed call
    assert fake_client.embeddings.call_count == 2


def test_ollama_embedder_embed_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = MagicMock()
    fake_client.embeddings.return_value = {"embedding": [0.0, 1.0]}
    fake_ollama = MagicMock()
    fake_ollama.Client.return_value = fake_client

    monkeypatch.setitem(__import__("sys").modules, "ollama", fake_ollama)
    e = OllamaEmbedder()

    out = e.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(v == [0.0, 1.0] for v in out)
