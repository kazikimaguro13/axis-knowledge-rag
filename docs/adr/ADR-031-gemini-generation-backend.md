# ADR-031: Gemini generation backend + `auto` fallback chain

- **Status**: Accepted
- **Date**: 2026-05-21
- **Spec**: spec_052 (v0.9.1 patch)

## Context

After v0.9.0 the generation pipeline supported three backends:
`ClaudeBackend` (default), `OllamaBackend` (spec_045, fully on-prem), and
`DummyGenerationBackend` (offline / no-key fallback). The factory picked
based on `generation.backend` in `config.yml`; if the user kept the
default `"claude"` but had no `ANTHROPIC_API_KEY`, the pipeline silently
dropped to DUMMY and `axis_answer` / `axis_chat` returned a placeholder.

That hits two real audiences badly:

1. **Personal / student users** — Many users come into the Cowork plugin
   already holding a Gemini key (the embedder requires it). They have
   never paid for Anthropic and have no good reason to. With v0.9.0
   they got an offline-looking RAG even though a perfectly good LLM key
   was sitting right there.
2. **Cowork plugin onboarding** — The first-run experience is "drop in
   one API key, get answers". Requiring a second key purely for
   generation breaks that flow.

`google-generativeai` is already a hard dependency (for embeddings), so
adding a Gemini generation path costs zero new packages.

## Decision

Add a fourth backend (`GeminiBackend`) and a new `"auto"` mode that
picks the best available backend at runtime.

### `GeminiBackend` (`backend/src/rag.py`)

```python
class GeminiBackend:
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, *, model="gemini-2.5-flash", api_key=None): ...
    def generate(self, system, messages, *, max_tokens=1024) -> str: ...
    @property
    def model_name(self) -> str: ...
    @property
    def is_dummy(self) -> bool: ...  # False
```

Implementation notes:

- Reuses `google.generativeai.GenerativeModel(model).generate_content(...)`
  with `max_output_tokens` + `temperature=0.2`. Same low-temperature
  profile as `ClaudeBackend` so citation discipline is preserved.
- System prompt is folded into the prompt body as `[SYSTEM]\n...\n\n`
  rather than passed through the SDK's `system_instruction` parameter.
  Keeps the call site provider-agnostic and avoids per-SDK-version
  drift in how `system_instruction` is consumed.
- Raises `RuntimeError("GEMINI_API_KEY not set for GeminiBackend")` on
  construction when no key is reachable (explicit > `settings` >
  `os.environ`). The factory wraps construction in a `try/except` so the
  user-facing fallback is still DUMMY, never a crash.

### `"auto"` mode in `make_generation_backend`

```python
backend = (cfg.backend or "auto").lower()

if backend == "auto":
    if settings.anthropic_api_key:
        return ClaudeBackend(...)
    if settings.gemini_api_key:
        try: return GeminiBackend(...)
        except Exception: return DummyGenerationBackend()
    return DummyGenerationBackend()
```

The priority **Claude > Gemini > DUMMY** keeps existing paid Claude
users on Claude unchanged; only users without an Anthropic key see
behaviour change (DUMMY → real Gemini answers, which is the intended
improvement).

Explicit `backend="claude"` / `"gemini"` / `"ollama"` / `"dummy"` keep
their literal semantics — `"auto"` only fires when nothing more specific
is asked for.

### Config (`backend/src/config.py`, `config.yml`)

```python
@dataclass(frozen=True)
class GeminiGenConfig:
    model: str = "gemini-2.5-flash"

@dataclass(frozen=True)
class GenerationConfig:
    backend: str = "auto"          # was "claude"
    gemini: GeminiGenConfig = ...
    ollama: OllamaConfig = ...
```

```yaml
generation:
  backend: "auto"             # auto | claude | gemini | ollama | dummy
  gemini:
    model: "gemini-2.5-flash"
  ollama:
    model: "llama3"
    url: "http://localhost:11434"
```

## Alternatives considered

- **Make Gemini the default (drop Claude as default)** — Cleanest from a
  "minimum keys to get a real answer" perspective, but breaks every
  existing v0.9.0 deployment that relied on Claude without setting any
  config. `"auto"` is the same UX win without the behaviour change for
  paid users.
- **Ollama as the default fallback** — Requires Docker + a 4 GB model
  pull. Wrong default for the laptop / Cowork plugin audience the spec
  targets; opt-in via `backend="ollama"` is right.
- **Explicit-only (no auto)** — Forces every user to know about three
  backends and pick one. The whole point of this spec was to remove
  that friction.
- **Use Gemini's `system_instruction` parameter** — Slightly cleaner on
  paper, but the `google-generativeai` v0.x → v1.x rename window is
  still active (the SDK already prints a deprecation warning pointing at
  `google.genai`). Folding system into prompt body is one call site and
  zero SDK version coupling.

## Consequences

### Positive

- Single-key onboarding: Gemini key + `pip install` + `make ingest` →
  real RAG answers from Cowork plugin without touching `config.yml`.
- Paid Claude users see no behaviour change (Claude still wins under
  `auto`); explicit `backend="claude"` is also untouched.
- Adds one new backend class + one new `if` branch in the factory.
  No new dependencies. Five new tests, all offline-mockable.

### Negative — default behaviour shift for un-keyed users

Users on v0.9.0 with neither `ANTHROPIC_API_KEY` nor `GEMINI_API_KEY`
saw DUMMY answers; under v0.9.1 they still see DUMMY (no key, no
backend). Users who had only `GEMINI_API_KEY` set saw DUMMY under
v0.9.0; under v0.9.1 they see real Gemini answers. This is the intended
improvement but **does** silently change `/api/answer` output for that
cohort. Documented in CHANGELOG + `docs/configuration.md`; users wanting
the old DUMMY behaviour can pin `generation.backend: "dummy"`.

### Negative — Gemini quality on citation-heavy JP prompts

`gemini-2.5-flash` answers are below Claude on the citation-mark `[N]`
discipline in informal testing. Citation parsing in
`parse_and_validate_citations` already drops out-of-range / malformed
markers, so the worst case is fewer marked citations, not broken
output. Users wanting parity should set `backend: "claude"` explicitly.

### Negative — `google-generativeai` deprecation

The SDK emits a `FutureWarning` directing users to `google.genai`. We're
on the deprecated package because the embedder still uses it; migrating
both call sites to `google.genai` is parked for v0.10 (separate spec).
Until then, `GeminiBackend` uses the same SDK as `GeminiEmbedder` —
single deprecation path, single migration ahead.

## Migration

Existing deployments: **zero changes required**.

- Anyone with `generation.backend: "claude"` in their `config.yml` →
  unchanged.
- Anyone using the default (no `generation` key, or `backend: "claude"`
  from a fresh copy of `config.yml`) → now sees `"auto"`, which still
  resolves to `ClaudeBackend` when `ANTHROPIC_API_KEY` is set.
- Anyone with only `GEMINI_API_KEY` → new path: real Gemini answers
  instead of DUMMY.

To opt out, pin the backend explicitly:

```yaml
generation:
  backend: "claude"   # or "dummy" / "ollama"
```
