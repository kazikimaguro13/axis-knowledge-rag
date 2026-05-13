"""Gemini text-embedding-004 wrapper with a deterministic dummy fallback.

If GEMINI_API_KEY is not configured, returns hash-derived 768-dim vectors so
that downstream code paths can be exercised in CI / offline dev without
hitting the network.
"""

import hashlib
import logging
from collections.abc import Sequence

from backend.src.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768
_GEMINI_MODEL = "text-embedding-004"


def _dummy_embedding(text: str) -> list[float]:
    """Deterministic 768-dim vector from text hash. NOT semantically meaningful."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    i = 0
    while len(out) < EMBEDDING_DIM:
        out.append((h[i % len(h)] / 127.5) - 1.0)
        i += 1
    return out[:EMBEDDING_DIM]


class Embedder:
    """Wraps Gemini embeddings with a graceful offline fallback."""

    def __init__(self, *, force_dummy: bool = False) -> None:
        self._use_dummy = force_dummy or not settings.gemini_api_key
        if self._use_dummy:
            logger.warning("Embedder running in DUMMY mode (no GEMINI_API_KEY)")
        else:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            self._genai = genai

    @property
    def is_dummy(self) -> bool:
        return self._use_dummy

    def embed(self, text: str) -> list[float]:
        """Return a 768-dim embedding for a single text."""
        if self._use_dummy:
            return _dummy_embedding(text)
        result = self._genai.embed_content(model=_GEMINI_MODEL, content=text)
        return list(result["embedding"])

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Return embeddings for a batch of texts (sequential, one call each)."""
        return [self.embed(t) for t in texts]
