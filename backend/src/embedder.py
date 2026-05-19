"""Embedder backends (Gemini / Ollama / Dummy) behind a Protocol.

spec_045 introduced the Protocol + 3-backend layout to enable fully on-prem
operation through Ollama. The original v0.8.1 class is preserved as
``GeminiEmbedder`` and remains the default when ``backend="gemini"``.

If ``GEMINI_API_KEY`` is not configured (and no other backend is selected),
the factory falls back to ``DummyEmbedder`` — deterministic hash-derived
768-dim vectors so downstream code paths can be exercised in CI / offline
dev without hitting the network.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from backend.src.config import settings

if TYPE_CHECKING:
    from backend.src.config import EmbedderConfig

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768  # Gemini text-embedding-004 + DummyEmbedder default
_GEMINI_MODEL = "text-embedding-004"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Embedder(Protocol):
    """Protocol every embedder backend implements.

    Method names kept compatible with the v0.8.1 ``Embedder`` class so the
    existing call sites (``search.py``, ``rag.py``, ``ingester.py``) keep
    working without invasive renames.
    """

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]: ...

    @property
    def is_dummy(self) -> bool: ...

    @property
    def dim(self) -> int: ...


# ---------------------------------------------------------------------------
# DummyEmbedder
# ---------------------------------------------------------------------------


def _dummy_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic ``dim``-dim vector from text hash. NOT semantically meaningful."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    i = 0
    while len(out) < dim:
        out.append((h[i % len(h)] / 127.5) - 1.0)
        i += 1
    return out[:dim]


class DummyEmbedder:
    """Offline fallback — deterministic hash-derived embeddings."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    @property
    def is_dummy(self) -> bool:
        return True

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        return _dummy_embedding(text, self._dim)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


# ---------------------------------------------------------------------------
# GeminiEmbedder (v0.8.1 default)
# ---------------------------------------------------------------------------


class GeminiEmbedder:
    """Gemini ``text-embedding-004`` (768 dim). Default for v0.8.1 / spec_045."""

    DIM = EMBEDDING_DIM

    def __init__(self, *, force_dummy: bool = False) -> None:
        # ``force_dummy`` kept as a v0.8.1 compatibility shim: tests and a
        # handful of legacy call sites pass it. When set (or when no API key
        # is configured), this class no longer talks to Gemini — it returns
        # the hash-based dummy vectors instead. New code should prefer
        # ``DummyEmbedder()`` directly.
        self._use_dummy = force_dummy or not settings.gemini_api_key
        if self._use_dummy:
            logger.warning("Embedder running in DUMMY mode (no GEMINI_API_KEY)")
            self._genai = None
        else:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            self._genai = genai

    @property
    def is_dummy(self) -> bool:
        return self._use_dummy

    @property
    def dim(self) -> int:
        return self.DIM

    def embed(self, text: str) -> list[float]:
        if self._use_dummy:
            return _dummy_embedding(text)
        result = self._genai.embed_content(model=_GEMINI_MODEL, content=text)
        return list(result["embedding"])

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


# ---------------------------------------------------------------------------
# OllamaEmbedder (spec_045 — fully on-prem)
# ---------------------------------------------------------------------------


class OllamaEmbedder:
    """Ollama embedder backend (e.g. ``bge-m3``, 1024 dim).

    Talks to ``ollama`` via the official Python client. The package is
    ``optional`` — install with ``pip install -e ".[ollama]"``. If the
    import / network call fails at construction, ``make_embedder()`` falls
    back to ``DummyEmbedder`` and logs a warning.
    """

    DEFAULT_MODEL = "bge-m3"
    DEFAULT_URL = "http://localhost:11434"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        url: str = DEFAULT_URL,
    ) -> None:
        import ollama  # raises ImportError if optional extras not installed

        self._client = ollama.Client(host=url)
        self._model = model
        self._url = url
        # Probe once so we expose a stable ``dim`` for downstream code that
        # relies on it (e.g. vector store dimensionality checks).
        self._dim = self._probe_dim()

    @property
    def is_dummy(self) -> bool:
        return False

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings(model=self._model, prompt=text)
        return list(resp["embedding"])

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        # Ollama embeddings endpoint is single-prompt; loop sequentially.
        return [self.embed(t) for t in texts]

    def _probe_dim(self) -> int:
        resp = self._client.embeddings(model=self._model, prompt="probe")
        return len(resp["embedding"])


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_embedder(cfg: EmbedderConfig | None = None) -> Embedder:
    """Build an embedder backend from ``EmbedderConfig``.

    - ``cfg is None`` → load defaults (``backend="gemini"``).
    - ``backend="gemini"`` (default): Gemini API; auto-falls back to dummy
      vectors when ``GEMINI_API_KEY`` is missing (v0.8.1 behaviour).
    - ``backend="ollama"``: spec_045 fully on-prem path. If the optional
      ``ollama`` package is missing or the server is unreachable, logs a
      warning and falls back to ``DummyEmbedder`` so app startup doesn't
      block.
    - ``backend="dummy"``: force dummy vectors.
    """
    if cfg is None:
        from backend.src.config import EmbedderConfig as _EC

        cfg = _EC()
    backend = (cfg.backend or "gemini").lower()
    if backend == "ollama":
        try:
            return OllamaEmbedder(model=cfg.ollama.model, url=cfg.ollama.url)
        except Exception as e:  # noqa: BLE001 — never block startup
            logger.warning(
                "Ollama embedder failed (%s), falling back to DummyEmbedder", e
            )
            return DummyEmbedder()
    if backend == "dummy":
        return DummyEmbedder()
    if backend != "gemini":
        logger.warning("Unknown embedder backend %r, falling back to gemini", backend)
    return GeminiEmbedder()
