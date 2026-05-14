# ADR-023: Parent Storage — SQLite as Default Backend

- **Status**: Accepted
- **Date**: 2026-05-14
- **Spec**: spec_037
- **Author**: Cowork (中島)

## Context

spec_031 introduced `parents.json` as a sidecar file next to the ChromaDB
directory.  `VectorStore` loads the entire JSON into memory at startup and
rewrites the whole file on every `add_chunks()` call.

This approach works well up to ~200 documents but has two scaling problems:

1. **Startup latency** — the full JSON is read and parsed on every process
   start.  At 1 000 parents with rich metadata, this adds hundreds of
   milliseconds before the first request can be served.

2. **Write amplification** — a single parent text update requires
   serialising and writing the entire file.  At 1 000 parents the file
   reaches ~500 KB; at 10 000 parents it becomes impractical.

## Decision

Replace `parents.json` with a **SQLite database** (`parents.db`) stored in
the same Chroma directory.

- **Default storage**: `sqlite` (the `retrieval.parent_doc.storage` config
  key defaults to `"sqlite"`).
- **Legacy storage**: `json` (accessible via `storage: "json"` in
  `config.yml` or `--parent-storage json` CLI flag) reproduces v0.7
  behavior exactly.
- **Lazy migration**: on first open, if `parents.db` is absent and
  `parents.json` is present, the factory function `make_parent_storage()`
  automatically migrates and logs one warning line.  No user action
  required.
- **Manual migration**: `python -m scripts.build_index --migrate-parents-json`
  is idempotent and prints a summary.
- **No auto-delete**: `parents.json` is retained after migration so users
  can revert by setting `storage: "json"`.

### Schema

```sql
CREATE TABLE IF NOT EXISTS parents (
    parent_id TEXT PRIMARY KEY,
    doc_id    TEXT NOT NULL,
    title     TEXT NOT NULL,
    text      TEXT NOT NULL,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_parents_doc_id ON parents(doc_id);
```

### Thread-safety

`PRAGMA journal_mode=WAL` is set at connection open.  The connection uses
`check_same_thread=False` so the store can be shared across request threads
in a uvicorn worker.

## Alternatives Considered

### (a) Parquet

- Pro: columnar, efficient for analytics.
- Con: requires `pyarrow` (~20 MB dependency); no row-level upsert API;
  overkill for a primary-key lookup table.

### (b) LMDB

- Pro: fast single-writer key–value store.
- Con: requires `lmdb` native library; harder to introspect; over-engineered
  for personal-scale knowledge base.

### (c) SQLite ← adopted

- Zero new dependencies (Python stdlib `sqlite3`).
- Primary-key lookup via index is O(log n) vs. O(n) full-JSON scan.
- WAL mode supports concurrent readers without blocking writers.
- Built-in SQL makes future extensions (FTS5, versioning) straightforward.

### (d) Keep JSON

- No migration cost.
- Fails at scale (problem stated in Context).

## Consequences

### Positive

- Startup time improves for large corpora: only a SQLite connection is
  opened at init; parent text is fetched on demand per query.
- Write I/O is proportional to the number of changed rows, not total DB
  size.
- `parents.db` is easily inspectable with `sqlite3` CLI.
- Future specs (FTS5 full-text search, parent versioning) can extend the
  schema without format changes.

### Negative / Trade-offs

- `parents.db` is added to the `data/chroma/` directory.
- `parents.json` is no longer written by default (existing monitoring or
  backup scripts that reference it need updating).
- In-memory SQLite (`:memory:`) is used for ephemeral/test stores —
  data does not survive process restart, but this matches previous
  behavior.

## Open Questions

- **VACUUM after clear()**: `reset()` calls `clear()` (DELETE rows) but
  does not VACUUM.  The SQLite file may retain allocated pages until the
  OS reclaims them.  For v0.8 this is acceptable given the expected DB
  size (~30 KB / 50 parents).  A VACUUM call can be added in a follow-up
  spec if needed.

- **Parent versioning**: a future `history` table could track text changes
  per parent_id.  The current schema does not prevent this addition.
  Candidate: spec_047 (v0.9).

- **FTS5 full-text search on parent text**: SQLite's built-in FTS5 virtual
  table could replace or augment the BM25 index for parent-level retrieval.
  Candidate: spec_048 (v0.9).
