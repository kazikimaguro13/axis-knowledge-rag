# ADR-030: Bidirectional refs in GraphSidebar (Obsidian-style backlinks)

- **Status**: Accepted
- **Date**: 2026-05-20
- **Spec**: spec_049 (v0.9 minor)

## Context

`spec_040` built the knowledge graph and shipped `GET
/api/graph/{doc_id}/neighbors?direction=in|out|both`. The backend already
distinguishes incoming refs (this doc is referenced *by* N) from outgoing
refs (this doc references *to* N), but the frontend `GraphSidebar` was
calling the endpoint with the default `direction=both` and rendering the
result as a single flat `🔗 隣接 (N)` list.

In practice that flat list loses the most useful piece of information a
knowledge graph carries: **which way the citation goes**. When the user
clicks `doc_001` they want to know:

- which docs `doc_001` itself refers to (its declared sources / parents),
- which docs reach back to `doc_001` (its derived / dependent notes).

Obsidian's "Linked mentions" pane splits these into *outgoing links* and
*backlinks* for exactly this reason. Without the split, the sidebar
hides the asymmetry the graph data already encodes.

## Decision

Split the sidebar into two sections, "→ 参照している" (forwardlinks,
`direction=out`) and "← 参照されている" (backlinks, `direction=in`), and
fetch them in parallel from the existing endpoint. Specifically:

- `frontend/src/lib/graphClient.ts` gains `fetchNeighborsBidirectional`,
  which calls `fetchNeighbors(..., "out")` and `fetchNeighbors(..., "in")`
  inside a single `Promise.all`. Wall-clock latency stays equivalent to
  the single-direction call.
- `frontend/src/components/GraphSidebar.tsx` renders each side as its
  own `<section>` with an explicit `aria-label`. A side that is empty is
  hidden entirely so the sidebar stays compact for leaf nodes. If both
  sides are empty we surface "このドキュメントは独立ノードです (リンク
  無し)。" so the user is never left wondering whether the panel is
  loading or genuinely empty.
- `backend/src/api.py`: `GET /api/graph/{doc_id}/neighbors` exposes
  `direction` as a `Query(..., pattern="^(in|out|both)$")` parameter
  with default `"both"`. The underlying graph layer (`graph.py`) already
  supported it, so this is just plumbing the existing capability through
  the HTTP shape.
- `mcp_server` (`axis_neighbors` tool): adds a `bidirectional` boolean
  flag (default `false`). Old callers see the unchanged single-direction
  payload; new callers can opt in to the split forwardlinks/backlinks
  shape via `format_neighbors_md_bidirectional` /
  `format_neighbors_json_bidirectional`.

## Alternatives considered

1. **Single flat list with arrow icons per entry.** Cheaper visually but
   the user has to scan the icons to count "how many docs cite me?".
   Section headers with counts answer that at a glance.
2. **Render bidirectional arrows on the 3D graph itself.** The graph
   already shows directed edges; the *sidebar* is where users go for the
   list view. Encoding the direction split twice doesn't help.
3. **Single API call returning both arrays.** Would save one HTTP round
   trip but requires a new response schema. Two parallel calls reuse the
   existing endpoint, which we already need for legacy callers, and the
   browser executes them concurrently — measured latency in dev is
   indistinguishable from one call.

## Consequences

- **Pro**: the sidebar now reads like an Obsidian backlinks pane. Users
  can immediately tell which side of the citation graph a node sits on.
- **Pro**: zero backend logic change — only the HTTP surface (one new
  query param with a default that preserves the old behaviour).
- **Pro**: MCP `axis_neighbors` stays backward-compatible. Pre-spec_049
  agents see the unchanged shape; spec_049-aware agents can pass
  `bidirectional=true` to receive both sides at once.
- **Con**: the sidebar now issues two HTTP requests instead of one.
  Latency is unchanged (parallel) but in serverless environments each
  request bills separately. Acceptable for v0.9; revisit if cost becomes
  visible (would batch into a single `/neighbors?direction=both&split=true`
  response).
- **Con**: one more failure mode — either request can fail
  independently. The current implementation surfaces the first error
  from `Promise.all`; we keep `Loading...` until both resolve. Good
  enough for v0.9.

## Open questions

- **Sort order within each section.** Currently BFS order from the graph
  layer. May want to sort by `in_degree` (most-cited first) for
  backlinks, mirroring Obsidian. Deferred until we have user feedback.
- **Hop > 1 semantics.** The split is only meaningful at hop=1; at
  hop≥2 "forwardlinks" includes "docs that doc_001 refs that ref X",
  which conflates direct vs. transitive references. The sidebar pins
  `hop=1` for now; if we ever expose a hop slider we'll need to label
  this carefully.
