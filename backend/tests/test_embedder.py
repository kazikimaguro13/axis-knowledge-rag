"""Smoke tests for embedder."""

from unittest.mock import MagicMock, patch

import pytest

from backend.src.embedder import (
    _GEMINI_BATCH_SIZE,
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


# ---------------------------------------------------------------------------
# spec_055: Gemini batched embed_content
# ---------------------------------------------------------------------------


def test_gemini_embed_batch_dummy_mode_count_and_dim() -> None:
    """force_dummy=True: embed_batch returns one 768-dim vector per input,
    in input order, equal to per-call embed() outputs."""
    e = GeminiEmbedder(force_dummy=True)
    texts = ["alpha", "beta", "gamma"]
    out = e.embed_batch(texts)
    assert len(out) == len(texts)
    assert all(len(v) == EMBEDDING_DIM for v in out)
    # Order + value parity with per-element embed()
    expected = [e.embed(t) for t in texts]
    assert out == expected


def test_gemini_embed_batch_empty_input_returns_empty() -> None:
    assert GeminiEmbedder(force_dummy=True).embed_batch([]) == []


def test_gemini_embed_batch_calls_embed_content_with_list() -> None:
    """When not in dummy mode, embed_batch must issue ONE embed_content call
    per sub-batch with content=list[str] — not N single-string calls. This
    is the perf fix: 4694 child embeddings drop from ~60 min to a few mins."""
    fake_genai = MagicMock()
    fake_genai.embed_content.return_value = {
        "embedding": [[0.1] * EMBEDDING_DIM, [0.2] * EMBEDDING_DIM, [0.3] * EMBEDDING_DIM]
    }
    e = GeminiEmbedder(force_dummy=True)
    # Manually flip to "live" mode with the mocked client.
    e._use_dummy = False
    e._genai = fake_genai

    out = e.embed_batch(["x", "y", "z"])

    assert fake_genai.embed_content.call_count == 1
    kwargs = fake_genai.embed_content.call_args.kwargs
    assert kwargs["content"] == ["x", "y", "z"]
    assert kwargs["output_dimensionality"] == EMBEDDING_DIM
    assert len(out) == 3
    assert out[0] == [0.1] * EMBEDDING_DIM


def test_gemini_embed_batch_splits_into_sub_batches() -> None:
    """Inputs larger than _GEMINI_BATCH_SIZE must be split — verified by
    counting embed_content calls and total vectors returned."""
    n = _GEMINI_BATCH_SIZE * 2 + 5  # 3 sub-batches: 100 + 100 + 5

    def fake_embed_content(**kwargs: object) -> dict:
        sub = kwargs["content"]
        assert isinstance(sub, list)
        return {"embedding": [[0.0] * EMBEDDING_DIM for _ in sub]}

    fake_genai = MagicMock()
    fake_genai.embed_content.side_effect = fake_embed_content
    e = GeminiEmbedder(force_dummy=True)
    e._use_dummy = False
    e._genai = fake_genai

    out = e.embed_batch([f"t{i}" for i in range(n)])

    assert len(out) == n
    assert fake_genai.embed_content.call_count == 3
    # Sub-batch sizes are 100, 100, 5
    sizes = [len(c.kwargs["content"]) for c in fake_genai.embed_content.call_args_list]
    assert sizes == [_GEMINI_BATCH_SIZE, _GEMINI_BATCH_SIZE, 5]


def test_gemini_embed_batch_retries_on_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sub-batch failures retry with backoff and succeed on a later attempt."""
    monkeypatch.setattr("backend.src.embedder.time.sleep", lambda _s: None)

    calls = {"n": 0}

    def flaky(**kwargs: object) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient 503")
        return {"embedding": [[0.5] * EMBEDDING_DIM for _ in kwargs["content"]]}

    fake_genai = MagicMock()
    fake_genai.embed_content.side_effect = flaky
    e = GeminiEmbedder(force_dummy=True)
    e._use_dummy = False
    e._genai = fake_genai

    out = e.embed_batch(["a", "b"])
    assert len(out) == 2
    assert calls["n"] == 2  # one failure + one success
