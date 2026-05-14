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
