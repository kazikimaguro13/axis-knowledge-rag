# ADR-026: Ollama integration for fully on-prem RAG

- **Status**: Accepted
- **Date**: 2026-05-19
- **Spec**: spec_045 (v0.9.0 marquee — first of bundle 4)

## Context

Through v0.8.1 the RAG pipeline reaches three external services:

- **Embedder** — Google Gemini `text-embedding-004` (768-dim)
- **Generation** — Anthropic Claude (`claude-3-5-sonnet`)
- **Rewriter (chat)** — Gemini Flash

Every question + retrieved context block leaves the network. That blocks
adoption for the two use cases driving v0.9:

1. **In-house deployment** — Legal / Infra cannot send internal-only docs
   (HR memos, incident reports, sales decks) through US-region SaaS LLMs.
2. **Personal / confidential corpora** — A user feeding their journal /
   private notes into the system has no good answer to "where does this
   text go?"

A *full* on-prem path needs both embedder and generator to be replaceable.
Embedder alone is not enough: the LLM still sees every retrieved doc.

## Decision

Introduce a **Protocol + factory** layout for both halves of the LLM call
and ship Ollama as the on-prem implementation.

### Embedder (`backend/src/embedder.py`)

```python
@runtime_checkable
class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]: ...
    @property
    def is_dummy(self) -> bool: ...
    @property
    def dim(self) -> int: ...
```

Three concrete backends:

- `GeminiEmbedder` — v0.8.1 default, 768-dim.
- `OllamaEmbedder` — `/api/embeddings`. Default model `bge-m3` (1024-dim,
  multilingual JP/EN). Dim probed once at construction.
- `DummyEmbedder` — deterministic hash-based fallback. Replaces the old
  `Embedder(force_dummy=True)` pattern.

A `make_embedder(EmbedderConfig)` factory selects one. Test code uses
`DummyEmbedder()` directly; runtime code uses `make_embedder(app_cfg.embedder)`.

### Generation (`backend/src/rag.py`)

```python
@runtime_checkable
class GenerationBackend(Protocol):
    def generate(self, system, messages, *, max_tokens) -> str: ...
    @property
    def model_name(self) -> str: ...
    @property
    def is_dummy(self) -> bool: ...
```

Three concrete backends:

- `ClaudeBackend` — wraps `anthropic.Anthropic.messages.create`.
- `OllamaBackend` — wraps `ollama.Client.chat`. Translates the
  Claude-style `(system, messages)` pair into a single
  `[{"role":"system", ...}, ...messages]` list.
- `DummyGenerationBackend` — sentinel; `RAGPipeline.answer()` short-circuits
  to `_dummy_answer()` before reaching `generate()`.

`make_generation_backend(GenerationConfig)` selects one. `RAGPipeline` no
longer talks to the Anthropic SDK directly — it goes through
`self._backend.generate(...)` (with a small legacy shim for tests that
monkey-patched `_client` directly).

### Config

```yaml
embedder:
  backend: "gemini"   # gemini | ollama | dummy
  ollama:
    model: "bge-m3"
    url: "http://localhost:11434"

generation:
  backend: "claude"   # claude | ollama | dummy
  ollama:
    model: "llama3"
    url: "http://localhost:11434"
```

Both keys default to their v0.8.1 backend so existing deployments are
unchanged. The `ollama` Python client is `optional` (`pip install -e
".[ollama]"`); the factory catches `ImportError` / connection errors and
falls back to `DummyEmbedder` / `DummyGenerationBackend` so app startup
never blocks on a misconfigured Ollama.

### Question rewriter

`question_rewriter.py` gained a `backend="gemini"|"ollama"` argument so
the chat-rewrite step can also avoid the network. The signature default
preserves v0.8.1 behaviour.

## Alternatives considered

- **vLLM** — Faster than Ollama for batch, but the Docker image is ~5GB
  and the operator UX is "edit YAML + nvidia-smi". Out of scope for the
  "single container, one CLI to pull a model" goal of v0.9.
- **llama.cpp Python bindings (`llama-cpp-python`)** — Native bindings
  are fragile across glibc / CUDA versions; the build step is a real
  blocker. Ollama hides this behind a Docker image and a daemon.
- **OpenAI-compatible local server (FastChat / LM Studio)** — Would have
  let us reuse the OpenAI SDK call site, but adds another moving piece
  and the JSON schema is brittle in practice.
- **DIY HTTP calls against `/api/embeddings`** — Cuts the optional
  dependency but loses connection pooling, retries, and the upstream
  fix stream. The `ollama` Python package is a thin wrapper around
  `httpx`; staying on it costs ~30 LoC and a single optional extra.

## Consequences

### Positive

- A flip of two config keys turns the deployment fully on-prem. The same
  Markdown + ChromaDB + FastAPI surface works untouched.
- Three Protocol-shaped backends each side make adding more LLM providers
  (OpenAI / Azure / Bedrock) one new class.
- DummyEmbedder is now a first-class type, removing the ambiguity of
  "GeminiEmbedder in dummy mode" — tests can be explicit.

### Negative — index dim mismatch

`bge-m3` returns 1024-dim vectors; `text-embedding-004` returns 768-dim.
ChromaDB rejects writes whose dim disagrees with the collection at
creation. **Switching `embedder.backend` from gemini → ollama (or back)
requires `python -m scripts.build_index ... --rebuild`.** The startup
path does not auto-rebuild — silently dropping a corpus is worse than a
clear error. `VectorStore.load_parents()` already warns on dim/encoding
mismatches (spec_043); a similar check on the live embedding dim is
planned for spec_046.

### Negative — model UX

`llama3` (8B) is the default generation model so the `docker pull`
finishes in minutes on a typical laptop; the answer quality is below
Claude on Japanese citation-heavy prompts. Users wanting parity should
pull `llama3:70b` or `qwen2.5:32b` and update `generation.ollama.model`.

### Negative — latency

Local Ollama with `llama3:8b` on a CPU-only laptop is roughly 3-10x
slower than Claude for our prompt sizes. GPU users get 1-2x of Claude.
Documented in `docs/deployment.md`; chat UX feels noticeably different.

## Migration

Existing deployments need **zero changes**. `config.yml > embedder` and
`config.yml > generation` are new keys; their defaults reproduce v0.8.1.

To opt in:

```bash
pip install -e ".[ollama]"
docker compose --profile ollama up -d ollama
docker exec axis-ollama ollama pull bge-m3
docker exec axis-ollama ollama pull llama3
# config.yml: embedder.backend: "ollama" + generation.backend: "ollama"
python -m scripts.build_index ./examples/knowledge --rebuild
```
