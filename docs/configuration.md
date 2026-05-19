# Configuration Reference

All configuration lives in `config.yml` at the project root.  Unknown keys
are silently ignored, so older config files keep working after upgrades.

---

## `retrieval.parent_doc`

Controls the Parent-Document (Small-to-Big) retrieval path introduced in
spec_031.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable parent-doc mode. `false` falls back to legacy file-level search. |
| `chunk_strategy` | string | `"h2"` | How to split Markdown into parent chunks. Currently only `"h2"` (split at H2 headings). |
| `max_child_tokens` | int | `256` | Approximate token cap per child chunk (~512 chars for JP text). |
| `top_k_children` | int | `20` | Number of child hits retrieved from ChromaDB before deduplication. |
| `top_n_parents` | int | `5` | Maximum parents returned after grouping children by `parent_id`. |
| `storage` | string | `"sqlite"` | Parent text storage backend. `"sqlite"` (default, v0.8+) or `"json"` (legacy v0.7). See [ADR-023](adr/ADR-023-parent-storage-sqlite.md). |

### `storage` — migration notes

#### `"sqlite"` (default, v0.8+)

- Parents are stored in `<chroma_dir>/parents.db` (SQLite).
- Connection is opened at startup; parent text is fetched **lazily** per
  query (no full-load penalty).
- If `parents.json` exists but `parents.db` does not, the first startup
  **auto-migrates** and logs one warning line.
- Manual migration: `python -m scripts.build_index --migrate-parents-json`.

#### `"json"` (legacy, v0.7 behaviour)

- Parents are stored in `<chroma_dir>/parents.json`.
- The entire file is loaded into memory at startup (eager load).
- Every `add_chunks()` call rewrites the full JSON file.
- Use this mode only when compatibility with v0.7 tooling is required.

```yaml
# config.yml — example: keep JSON mode
retrieval:
  parent_doc:
    storage: "json"
```

---

## `retrieval.time_decay`

Time-weighted recency boost introduced in spec_035.  Default **off** so
existing ranking is unchanged unless explicitly enabled.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Activate recency boost. |
| `half_life_days` | float | `180.0` | Age at which score × 0.5 (exponential decay). |
| `weight` | float | `0.15` | Maximum fraction of score influenced by recency. |
| `date_field` | string | `"updated"` | Frontmatter key to read as the reference date. |

---

## `rag`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `context_max_chars` | int | `8000` | Maximum characters of retrieved context fed to the LLM. |

---

## `chat`

Conversational RAG settings (spec_032).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable `/api/chat` endpoint. |
| `max_history_turns` | int | `6` | Turns of conversation kept per session (6 turns = 12 messages). |
| `ttl_seconds` | int | `86400` | Session expiry in seconds after last access (24 h). |
| `max_sessions` | int | `100` | LRU cap; oldest session is evicted when exceeded. |
| `rewriter.enabled` | bool | `true` | Rewrite follow-up questions using Gemini Flash before retrieval. |
| `rewriter.model` | string | `"gemini-1.5-flash"` | Gemini model used for question rewriting. |

---

## `graph`

GraphRAG + knowledge-graph settings (spec_040).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Build the refs graph and expose `/api/graph` endpoints. |
| `default_hop` | int | `1` | Default hop depth for neighbor queries. |
| `max_neighbors_per_query` | int | `20` | Cap on neighbors returned per query. |
| `expand_on_search` | bool | `false` | Automatically expand search results with 1-hop graph neighbors. |
| `knowledge_dir` | string | `"./examples/knowledge"` | Directory scanned at startup to build the graph. |

---

## `embedder` (spec_045)

Selects the embedder backend. See [ADR-026](adr/ADR-026-ollama-integration.md)
and `docs/deployment.md` for the on-prem setup.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `backend` | string | `"gemini"` | `"gemini"` (v0.8.1 default, 768-dim) / `"ollama"` (fully on-prem) / `"dummy"` (deterministic hash, offline). |
| `ollama.model` | string | `"bge-m3"` | Ollama model name. `bge-m3` is multilingual JP/EN, 1024-dim. |
| `ollama.url` | string | `"http://localhost:11434"` | Ollama daemon URL. |

> **Dim mismatch warning**: switching `backend` between `gemini` (768-dim)
> and `ollama` with `bge-m3` (1024-dim) requires rebuilding the index:
> `python -m scripts.build_index ./examples/knowledge --rebuild`. The
> ChromaDB collection's dim is fixed at create-time.

> **Ollama unavailable**: when `backend="ollama"` but the `ollama` Python
> package is missing or the daemon is unreachable, the factory logs a
> warning and falls back to `DummyEmbedder` so app startup never blocks.
> Install with `pip install -e ".[ollama]"`.

```yaml
# config.yml — example: fully on-prem
embedder:
  backend: "ollama"
  ollama:
    model: "bge-m3"
    url: "http://localhost:11434"
```

---

## `generation` (spec_045)

Selects the LLM backend used by the RAG pipeline.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `backend` | string | `"claude"` | `"claude"` (v0.8.1 default, Anthropic SDK) / `"ollama"` (fully on-prem) / `"dummy"`. |
| `ollama.model` | string | `"llama3"` | Ollama chat model. Try `llama3:70b` / `qwen2.5:14b` for higher quality. |
| `ollama.url` | string | `"http://localhost:11434"` | Ollama daemon URL. |

When `backend="claude"` but `ANTHROPIC_API_KEY` is unset, the pipeline
falls back to deterministic DUMMY answers (v0.8.1 behaviour preserved).
Same applies to Ollama on connection failure — the user-facing UX never
blocks; check logs for the warning if answers look unexpectedly dummy.

```yaml
# config.yml — example: Claude embedder, Ollama generation
embedder:
  backend: "gemini"
generation:
  backend: "ollama"
  ollama:
    model: "qwen2.5:14b"
```

---

## Environment variables

### `EVAL_OVERRIDE_FLAG` (spec_042)

Used by `evaluation/run_abtest.py` to flip one or more config keys at load
time without editing `config.yml`. Read once at the end of
`load_app_config()`; format is `dotted.key=value` pairs separated by `;`.

```bash
# A/B test time_decay enabled vs disabled
EVAL_OVERRIDE_FLAG="retrieval.time_decay.enabled=true" \
  python -m evaluation.run_abtest \
    --dataset evaluation/datasets/qa_v1.json \
    --flag time_decay.enabled \
    --output evaluation/runs/abtest.json

# Flip multiple keys at once
EVAL_OVERRIDE_FLAG="retrieval.time_decay.enabled=true;chat.enabled=false" \
  python -m backend.src.api
```

Value coercion: `"true"`/`"false"` → bool, integer-like → int, float-like
→ float, otherwise string. Unknown keys are silently warning-logged so a
stale env var can't take the API down.

> **Note**: values containing `;` (e.g. URLs with query strings) are not
> currently supported. Use a single override in that case.
