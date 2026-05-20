# ADR-028: Active-learning feedback loop (👍 / 👎 capture)

- **Status**: Accepted
- **Date**: 2026-05-20
- **Spec**: spec_047 (v0.9.0 marquee — bundle 5, after the browser extension)

## Context

Through v0.8 search and chat results landed on screen and… stopped. The
backend never learned which docs the user found useful and which they
quietly dismissed. Two problems followed from that:

1. **No ground truth.** Anything we'd want to do later — re-rank with a
   learned weight, blacklist a chronically-misleading doc, surface a
   "queries that hit nothing useful" report — needs at least a stream of
   thumbs-up / thumbs-down events. We had zero.
2. **No visibility.** "Has the quality of search dropped since the last
   embedding swap?" was answerable only by re-running the eval set, not
   by looking at what real usage actually said.

A capture path needs to be: **one click per source, write to local
SQLite, never block the request path.** The MVP scope is intentionally
just *logging* — automatic weight-tuning over the captured signals is
parked for v0.10.

## Decision

Ship a small **`FeedbackStore` Protocol + `SqliteFeedbackStore`** plus a
**`POST /api/feedback`** endpoint and a **weekly markdown report**:

- `backend/src/feedback.py` — `FeedbackRecord` dataclass, `FeedbackStore`
  Protocol, `SqliteFeedbackStore` (stdlib `sqlite3`, WAL mode, single
  shared connection under a `threading.Lock`), and a
  `make_feedback_store(cfg)` factory that returns `None` when disabled.
- `POST /api/feedback` accepts `{query?, doc_id?, rating, session_id?, note?}`
  with `rating` constrained to `[-1, 1]` and returns the new
  `feedback_id` (uuid4). When the store is disabled (config
  `feedback.enabled=false`), the endpoint returns **503** rather than
  silently swallowing writes.
- `GET /api/feedback/report?days=N` renders the same markdown the
  Makefile target writes — easy to surface in an admin dashboard later
  without a second renderer.
- `evaluation/feedback_report.py` — pure-function `generate_report(store, days=N)`
  plus `save_report_to_file(...)` which drops `evaluation/feedback_reports/YYYY-WW.md`.
  Aggregations are intentionally simple: total counts, top queries by
  frequency, top-5 unpopular docs (net 👎 over 👍), top-5 popular docs.
- `make feedback-report` — one-liner shelling into the renderer with the
  default `~/.axis_feedback.db` path.
- Frontend (Next.js): `feedbackClient.ts` (single `postFeedback` helper),
  buttons added to `ResultCard.tsx` (per source) and `ChatMessage.tsx`
  (one pair for the whole answer + per-source pair under the sources
  expander). Optimistic UI — visual state flips on click; the only way
  it reverts is the API rejecting the write.
- Streamlit (`streamlit_app.py`): `_send_feedback(...)` helper + 👍 / 👎
  buttons under every source card in both the Search and Chat tabs,
  plus a whole-answer 👍 / 👎 pair under the live chat reply. Toast on
  success / failure / disabled.

### Schema

```sql
CREATE TABLE feedback (
    feedback_id TEXT PRIMARY KEY,
    query       TEXT,            -- nullable: search tab anonymous capture
    doc_id      TEXT,            -- nullable: feedback on the whole answer
    rating      INTEGER NOT NULL,-- +1 / -1 / 0
    session_id  TEXT,            -- nullable: only chat tab carries one
    note        TEXT,            -- nullable: future free-text follow-up
    timestamp   REAL NOT NULL    -- UTC epoch seconds
);
CREATE INDEX idx_feedback_ts  ON feedback(timestamp);
CREATE INDEX idx_feedback_doc ON feedback(doc_id);
```

`session_id` ties multiple signals together for chat turns but is null
for the search tab — that's intentional, the search tab is anonymous.
`doc_id IS NULL` means "rating applies to the whole assistant answer."

### Config surface

```yaml
feedback:
  enabled: true                  # false → /api/feedback returns 503
  db_path: "~/.axis_feedback.db" # next to ~/.axis_chat.db from spec_036
```

## Alternatives considered

- **Clickstream auto-collection (Gemini suggestion ①).** Tracking every
  scroll, hover, expand-toggle gives a richer signal but produces a
  much noisier dataset and roughly 10× the write volume. For a
  local-first MVP we'd be optimising weights against noise. Parked
  until we have a real user base to amortise the storage cost.
- **5-star rating.** Per-doc star rating has more resolution than
  👍 / 👎 but the empirical effort-vs-signal trade is poor — most users
  pick either "3 stars" (neutral default) or 5, and the rest of the
  scale is rarely used. ±1 is the resolution we can actually act on.
- **External analytics provider (Plausible / PostHog / Mixpanel).** A
  third-party endpoint would absolve us of the storage problem but
  introduces a network dependency on the hot path, and a data-egress
  concern for an OSS local-first project. Rejected.
- **Automatic weight tuning at write-time.** Tempting — every 👎 lowers
  the doc's rerank weight, every 👍 raises it. Cuts out the report-
  reading step entirely. Rejected for v0.9 because (a) without rate-
  limiting, a few angry clicks can permanently bury a useful doc, and
  (b) the tuning algorithm wants to be evaluated against the existing
  RAGAS suite, which means we want the signal layer in place before we
  start tuning anything. Parked for v0.10.

## Consequences

### Positive

- **Ground-truth capture starts immediately.** From day 47 onwards the
  local SQLite has real evidence to point at when retrieval quality
  questions come up.
- **Zero new dependencies.** stdlib `sqlite3` + the existing FastAPI /
  Pydantic stack. No telemetry SDK to vet.
- **Reversible.** Flipping `feedback.enabled` to `false` makes the API
  return 503 and the frontend buttons turn into no-ops (the toast
  surfaces "feedback is disabled"). Removing the feature entirely is
  one config flag + a future ADR.

### Negative — no dedup yet

The frontend disables the button after the first click in the same
component instance, but a refresh / second tab / another browser
session lets the same user re-submit. The backend stores every signal
as a fresh row with a new uuid. For v0.9 that's fine — the reports
treat duplicates as evidence of strong opinion — but if we ever ship
automatic weight tuning, a server-side dedup window (e.g. one
(session, doc_id, rating) within 5 min) becomes a hard requirement.
Tracked for v0.10.

### Negative — query strings can carry PII

`query` is stored verbatim. A user pasting their email address into the
search box leaves it in `~/.axis_feedback.db`. For the local-first MVP
that's acceptable (the file lives in the user's home directory and the
default deployment is single-user), but a future option
`feedback.anonymize_queries: true` should hash the query column with a
keyed BLAKE2 before storage. Listed in spec_047 §6 as Open Q; not
implemented in v0.9.

### Negative — single SQLite file ≠ horizontal scaling

The store is a file-backed SQLite under `~/.axis_feedback.db`. Fine for
the local-first deployment model; under a multi-worker uvicorn + load
balancer it would either (a) be sharded per worker (loses correctness)
or (b) move to PostgreSQL via the same Protocol. Same story as the
spec_036 chat store — we kept the Protocol so the swap is a single new
class, not a refactor.

## Migration

No migration. The endpoint is purely additive and the table is created
on first write (`CREATE TABLE IF NOT EXISTS`). Existing deployments
serve `/api/feedback` immediately after `git pull` + restart. The first
👍 click creates `~/.axis_feedback.db` and the WAL sidecar files. The
weekly report target does nothing useful until at least one record
exists — by design, an empty store yields the "No feedback recorded"
placeholder rather than an error.
