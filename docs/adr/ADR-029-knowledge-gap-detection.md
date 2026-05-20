# ADR-029: Knowledge-gap detection (search misses → weekly report)

- **Status**: Accepted
- **Date**: 2026-05-20
- **Spec**: spec_048 (v0.9.0 marquee — bundle 6, after the feedback loop)

## Context

spec_047 (ADR-028) gave us a ground-truth stream of *what users felt*
about the answers we did produce — 👍 / 👎. But there's a second silent
failure mode the 👍 / 👎 path doesn't capture at all: **the user
searched, didn't find anything useful, and gave up**. That's a knowledge
gap, not a ranking miss — no amount of weight-tuning fixes a topic the
knowledge base simply doesn't contain.

Concretely, three signals tell us the system probably didn't have what
the user wanted:

1. `no_results` — search returned an empty hit list (axis filter too
   narrow, or genuinely nothing matches).
2. `low_score` — top hit's blended score is below the v0.8 RAGAS "weak
   hit" band (~0.35). The hit is technically present but the ranker
   barely believes it.
3. `llm_no_info` — the LLM, given the retrieved docs, answered
   "提供された資料には記載がありません" or similar. We *had* candidates
   but they weren't actually about the question.

Without these signals the only feedback channel is "the user didn't
click thumbs-up on anything", which is indistinguishable from "the user
got their answer and closed the tab." We need a directional signal that
points at **topics worth ingesting next** — that's the gap report.

## Decision

Ship a small **`GapStore` Protocol + `SqliteGapStore`** plus
**`GET /api/gap/report`** and a weekly markdown report renderer, mirroring
the spec_047 layout:

- `backend/src/gap_detection.py` — `GapRecord` dataclass, `GapStore`
  Protocol, `SqliteGapStore` (stdlib `sqlite3`, WAL mode, single shared
  connection under `threading.Lock`). Default DB path `~/.axis_gap.db`
  next to `~/.axis_feedback.db` (spec_047) and `~/.axis_chat.db`
  (spec_036). `make_gap_store(cfg)` returns `None` when disabled so
  every hook site can guard with a single `is None` check and pay
  literally zero cost when the feature is off.
- `detect_no_info(answer_text)` — narrow regex over the LLM's response,
  matching the exact phrasings the SYSTEM_PROMPT instructs Claude to
  emit ("提供された資料には記載がありません", "わかりません", "no
  information available", "I don't have the information", …). Erring on
  the side of *not* firing — a false negative (real don't-know slipping
  through) is far cheaper than a false positive (a normal cited answer
  landing in the gap report).
- **Hook in `search.py`** — post-hoc, after the existing fusion / decay
  / graph expansion finishes. Empty results → `no_results`; non-empty
  top score below `gap.low_score_threshold` → `low_score`. Skipped when
  `query is None` (axis-only listing calls) and when no store is wired.
  Wrapped in `try / except` + `logger.warning` so the gap path can
  *never* fail a real search.
- **Hook in `rag.py`** — post-hoc, after `parse_and_validate_citations`
  produced the final text. Runs `detect_no_info(text)` and records
  `llm_no_info` with the question + top score + n_results when it fires.
  Same `try / except` guard. The chat path goes through the same helper
  with the *user-facing* question (not the rewritten query) so the
  report is actionable.
- `GET /api/gap/report?days=N` renders the markdown that the Makefile
  target writes — surface-ready for an admin dashboard later.
  `_require_gap_store()` → 503 when disabled.
- `evaluation/gap_report.py` — pure-function `generate_report(store, days=7)`
  + `save_report_to_file(...)` which drops
  `evaluation/gap_reports/YYYY-WW.md`. Sections: total counts per
  reason, top-10 unsatisfied queries (count desc, stable tie-break on
  the query string), and a 推奨アクション block pointing at
  `examples/knowledge/` + the browser extension from spec_046.
- `make gap-report` — one-liner shelling into the renderer with the
  default `~/.axis_gap.db` path.

### Schema

```sql
CREATE TABLE gaps (
    gap_id     TEXT PRIMARY KEY,
    query      TEXT NOT NULL,                -- the user query
    reason     TEXT NOT NULL,                -- "no_results" | "low_score" | "llm_no_info"
    top_score  REAL,                         -- nullable: null for no_results
    n_results  INTEGER NOT NULL,             -- how many hits the search returned
    timestamp  REAL NOT NULL                 -- UTC epoch seconds
);
CREATE INDEX idx_gaps_ts    ON gaps(timestamp);
CREATE INDEX idx_gaps_query ON gaps(query);
```

`reason` is a free-form text column rather than an enum so we can add
new gap signals (e.g. `"citation_unverified"` from spec_049) without a
schema migration.

### Config surface

```yaml
gap:
  enabled: true                  # false → all hooks no-op + /api/gap/report returns 503
  db_path: "~/.axis_gap.db"      # SQLite file, lives next to axis_feedback.db
  low_score_threshold: 0.35      # top score below this → low_score event
```

## Alternatives considered

- **Clickstream-only (extend spec_047).** The feedback store already
  captures 👍 / 👎 — couldn't we infer gaps from "searched but never
  thumbs-upped"? In principle yes, in practice we have no
  thumbs-down-after-search-with-no-results event at all (the user just
  closes the tab — there's nothing to vote on). The feedback loop and
  gap detection answer *different* questions: spec_047 = "did the user
  like what we returned?", spec_048 = "did we return anything worth
  liking?". Adopted both, kept the stores separate.
- **LLM self-evaluation only (drop the search-side hook).** Just use
  `detect_no_info` on the answer text. Simpler, but conflates "no
  relevant docs" with "docs present but LLM refused to commit" — the
  recommended action differs (ingest a new doc vs. tune the prompt /
  re-chunk the existing one). Adopted both signals.
- **LLM-suggested topic ingestion at write-time.** Feed the gap query
  back into Gemini, ask it to produce a frontmatter skeleton, drop it
  under `examples/knowledge/` automatically. Rejected for v0.9 because
  (a) it gives the LLM a write path into the knowledge dir, which is a
  trust boundary we haven't reviewed, and (b) noisy queries would create
  noisy memos. Listed in §6 Open Q for v0.10.
- **Histogram of distance values (Gemini suggestion).** Instead of a
  hard `low_score_threshold`, keep a rolling histogram of cosine scores
  per query and surface outliers. More signal-rich, more storage cost,
  and (crucially) harder to explain in a report — "this query was in
  the 12th percentile" reads worse than "this query scored 0.22". Kept
  the simple threshold; the threshold itself is in `config.yml` so it's
  tunable without a redeploy.

## Consequences

### Positive

- **Closes the "silent failure" gap in the feedback loop.** The two
  stores combined now capture both "I didn't like what you returned"
  (spec_047) and "you didn't return anything I could like" (spec_048).
- **Zero new dependencies.** stdlib `sqlite3` + the existing FastAPI /
  Pydantic stack. No telemetry SDK to vet.
- **Zero hot-path cost when disabled.** Every hook site short-circuits
  on `gap_store is None`, which is the case when `gap.enabled=false`.
  No regex run, no SQLite write, no measurable difference on search /
  answer latency.
- **Actionable output.** The weekly report's "top unsatisfied queries"
  list maps 1:1 to "memos we should write or web pages we should ingest
  via spec_046's `/api/ingest`." A team running the report weekly has a
  concrete punch list every Monday.

### Negative — `detect_no_info` false positives

The regex is broad enough that an answer like *"Note that the document
doesn't specifically say X, but it does explain Y [1]…"* could trip the
`資料(に|には)?(は)?(記載|情報|該当)(が)?(ない|...)` pattern even though it's
a real, cited answer. The mitigation is:

1. The regex is anchored on the exact phrasings the SYSTEM_PROMPT
   *tells* Claude to use for genuine "I don't know" answers — so
   well-behaved Claude responses don't hit it.
2. The gap report shows the query + count, not the answer text — a
   weekly review naturally catches the obviously-not-a-gap cases.
3. The `false_positive_rate` is something the weekly review should
   eyeball; if it climbs above ~10% we tighten the regex (the
   `NO_INFO_PATTERNS` list is the single source of truth, no test
   matrix to refactor).

Listed in spec_048 §6 as an Open Q; not solved in v0.9.

### Negative — query strings can carry PII

Same story as spec_047 (ADR-028 §Negative — query strings can carry
PII). `query` is stored verbatim in `~/.axis_gap.db`. For the local-
first single-user MVP that's acceptable; a future `gap.anonymize_queries:
true` knob can hash the column with keyed BLAKE2 before storage. Not
implemented in v0.9.

### Negative — schema overlap with spec_047

We now have two SQLite files in `~/.axis_*.db` with very similar
shapes. Tempting to merge into one. We didn't because (a) the two
events have distinct lifecycle (feedback survives a knowledge re-ingest;
gap events are tied to a specific point-in-time index quality) and
(b) the analysis queries are different — feedback reports group by
`doc_id`, gap reports group by `query`. Two specialised tables stay
clearer than one denormalised one. Both behind the same Protocol
pattern means a future PostgreSQL backend can host both as separate
tables in the same database without further refactor.

## Migration

No migration. The endpoint is purely additive and the table is created
on first write (`CREATE TABLE IF NOT EXISTS`). Existing deployments
serve `/api/gap/report` immediately after `git pull` + restart. The
first low-score search creates `~/.axis_gap.db` and its WAL sidecar.
The weekly report target does nothing useful until at least one record
exists — by design, an empty store yields the "No knowledge gaps
detected" placeholder rather than an error.
