"""Integration tests for the Ollama backends (spec_045).

These tests require:
- The optional ``ollama`` Python package (``pip install -e ".[ollama]"``).
- A reachable Ollama server (``docker compose --profile ollama up -d ollama``)
  with ``bge-m3`` and a small chat model (``llama3`` or ``qwen2.5``) pulled.

Both gates use ``pytest.importorskip`` / a connection probe so the file
silently skips in CI / on dev boxes without Ollama running. Run locally
with ``AXIS_OLLAMA_INTEGRATION=1 pytest backend/tests/test_ollama_backend.py``
to opt in.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass

ollama = pytest.importorskip("ollama")

_OPT_IN_ENV = "AXIS_OLLAMA_INTEGRATION"
_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
_GEN_MODEL = os.getenv("OLLAMA_GEN_MODEL", "llama3")


def _server_reachable() -> bool:
    try:
        client = ollama.Client(host=_OLLAMA_URL)
        # ``list()`` is the cheapest health probe; only succeeds when the
        # daemon is reachable AND responsive.
        client.list()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not os.getenv(_OPT_IN_ENV) or not _server_reachable(),
    reason=(
        f"set {_OPT_IN_ENV}=1 and run a local Ollama "
        f"(`docker compose --profile ollama up -d ollama`) to enable"
    ),
)


def test_ollama_embedder_real_round_trip() -> None:
    """OllamaEmbedder.embed() returns a non-zero vector from the live model."""
    from backend.src.embedder import OllamaEmbedder

    e = OllamaEmbedder(model=_EMBED_MODEL, url=_OLLAMA_URL)
    v = e.embed("hello world")
    assert isinstance(v, list)
    assert len(v) > 0
    assert e.dim == len(v)
    assert any(x != 0 for x in v)


def test_ollama_backend_chat_real_round_trip() -> None:
    """OllamaBackend.generate() returns a non-empty string from the live model."""
    from backend.src.rag import OllamaBackend

    b = OllamaBackend(model=_GEN_MODEL, url=_OLLAMA_URL)
    out = b.generate(
        system="You answer in one short sentence.",
        messages=[{"role": "user", "content": "What is 2+2?"}],
        max_tokens=32,
    )
    assert isinstance(out, str)
    assert out.strip()
