# ADR-025: 3D knowledge-graph visualization

- **Status**: Accepted
- **Date**: 2026-05-14
- **Spec**: spec_040 (companion to ADR-024)

## Context

ADR-024 introduces the `KnowledgeGraph` for backend retrieval. The same
data structure — a directed graph of refs between Markdown documents —
is also a natural canvas for the user-facing experience: "what does my
knowledge base look like, structurally?"

The existing UI surfaces (Next.js `/`, Next.js `/chat`, Streamlit
tabs) all present knowledge as **lists**. Lists hide topological
features (clusters, hubs, isolated docs) that frontmatter authors
already encoded through their `refs:` choices.

## Decision

Add a `/graph` route in the Next.js frontend rendered with
**react-force-graph-3d**. The route is a thin shell:

```
/graph/page.tsx
  └─ Knowledge3DGraph    (react-force-graph-3d wrapper)
  └─ GraphFilterBar      (category/level dropdowns)
  └─ GraphSidebar        (clicked-node detail + neighbours)
```

Server-side rendering is disabled (`dynamic({ ssr: false })`) because
react-force-graph-3d depends on `window` and a WebGL context that don't
exist during Next.js SSR.

A lighter-weight 2D version backed by `networkx + matplotlib` is added
as a third Streamlit tab — useful when running headless / Docker-only
and to confirm the same stats the FastAPI `/api/graph` endpoint returns.

## Alternatives considered

(a) **sigma.js (2D)** — rejected. Mature library but 2D-only; the
visual differentiation against the existing list views is weaker.

(b) **Cytoscape.js** — rejected. Powerful but biology-skewed defaults
(node shapes, color palettes) require a lot of overrides to look
modern, and the API surface is large.

(c) **Three.js raw + custom force layout** — rejected. Hand-rolling a
force-directed layout in 3D is a multi-week effort that adds little
value over react-force-graph-3d, which is exactly this layered on top
of three.js + d3-force-3d.

(d) **react-force-graph-3d** — chosen. ~5 KB API surface, MIT,
maintained, supports node/link click handlers + arrow markers + custom
colour functions out of the box.

## Consequences

- Frontend dependency tree gains `three (~600 KB), react-force-graph-3d
  (~150 KB), d3-force-3d (~30 KB)`. `npm run build` still passes.
- WebGL required → mobile Safari ≤ 14 and IE see a black canvas. The
  page leaves the surrounding chrome (header, filter bar, sidebar)
  intact so users on incompatible browsers can still read text rather
  than getting a blank screen.
- For graphs > ~1000 nodes the force-directed layout becomes visibly
  jittery; `/api/graph` is paginated (`limit` ≤ 2000, default 500) and
  the filter bar lets users carve out a sub-graph, which is the
  recommended path for large knowledge bases.
- The Streamlit tab uses matplotlib's `spring_layout` and Japanese
  fonts may fall back to Tofu if Hiragino Sans is not installed; this
  is a soft visual issue, not a functional break.
