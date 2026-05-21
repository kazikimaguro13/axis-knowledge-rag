# ADR-032: GraphSidebar layout fix — flexbox + measured canvas

- **Status**: Accepted
- **Date**: 2026-05-21
- **Spec**: spec_053 (v0.9.1 patch)

## Context

After v0.9.0 the `/graph` page rendered the 3D force-directed graph but the
right-hand 320 px `GraphSidebar` was nowhere on screen — not even the
"🕸️ ノードをクリックすると…" placeholder. Backend (`/api/graph/{id}/neighbors`)
returned 200 OK, the click handler fired (two `direction=out` / `direction=in`
requests visible in DevTools Network), and the canvas itself displayed and
accepted drag/zoom. Symptom was purely layout: the aside was being painted off
the viewport.

The page used CSS Grid with arbitrary track sizing:

```tsx
<div className="grid h-[calc(100vh-120px)] grid-cols-[1fr_320px] overflow-hidden …">
  <div className="relative bg-[#0a0a0a]">…<Knowledge3DGraph /></div>
  <GraphSidebar … />
</div>
```

Hypotheses considered:

- **A. Tailwind JIT not generating `grid-cols-[1fr_320px]`.** Falsified:
  `tailwind.config.ts` content paths cover `./src/app/**` and
  `./src/components/**`, and the class appeared in the generated CSS.
- **B. `dynamic({ ssr: false })` hydration breaks grid sizing.** Falsified by
  inspection: hydration replaces the loading `<div>` with the canvas inside the
  same grid cell; CSS Grid recomputes on subtree change.
- **C. `overflow-hidden` clips an overflowing sidebar.** Partially true — it
  was the visible symptom — but the root cause was *why* the grid overflowed.
- **D. `GraphSidebar` returns null on `docId === null`.** Falsified by reading
  the component: both branches return an `<aside>…</aside>`.

The actual root cause is in `react-force-graph-3d` (verified in
`node_modules/3d-force-graph/node_modules/three-render-objects/dist/three-render-objects.mjs:175`):

```js
width:  { default: window.innerWidth },
height: { default: window.innerHeight },
```

When the consumer passes no `width` / `height` props, the canvas is sized to
the *full viewport* (e.g. 1920 × 1080), not to its parent container. In CSS
Grid, a `1fr` track resolves as `minmax(auto, 1fr)`, and `auto`'s min-track
size is `min-content`. A 1920 px-wide canvas forces the `1fr` column's
min-content to 1920 px, so the row becomes 1920 + 320 = 2240 px wide. The
`<main className="mx-auto max-w-6xl …">` ancestor is 1152 px, so the sidebar
is painted past the viewport and `overflow-hidden` clips it out of sight.

## Decision

Two complementary fixes, both kept minimal:

### 1. Page layout: flexbox with `min-w-0` + `shrink-0`

Replace the grid with a flex row in `frontend/src/app/graph/page.tsx`:

```tsx
<div className="flex h-[calc(100vh-120px)] overflow-hidden …">
  <div className="relative min-w-0 flex-1 bg-[#0a0a0a]">…</div>
  <div className="w-80 shrink-0">
    <GraphSidebar … />
  </div>
</div>
```

`min-w-0` on the canvas column allows the flex item to shrink below its
intrinsic min-content (cancelling the runaway from the oversized canvas);
`w-80 shrink-0` pins the sidebar at 320 px so it cannot be squeezed away.
Flexbox is preferred over grid here because it has explicit per-item
shrink/grow semantics, which the bug class needs.

`GraphSidebar` itself gains `h-full` on both aside branches so it fills the
wrapper height (the loaded-state's `overflow-y-auto` is meaningful only with
a bounded height).

### 2. Canvas component: measured size via `ResizeObserver`

In `frontend/src/components/Knowledge3DGraph.tsx` wrap `ForceGraph3D` in a
`absolute inset-0` div, observe its size with `ResizeObserver`, and pass
explicit `width` / `height` props to `ForceGraph3D`. The canvas then matches
the column instead of the viewport, fixing the underlying invariant rather
than only the visible symptom. This also makes the graph responsive to
sidebar collapse, browser resize, and devtools toggling.

The grid-column min-content fix (#1) alone would leave the canvas visually
overflowing-then-clipped; the measured-size fix (#2) alone would also work
but leaves the page one renaming away from re-breaking. Doing both makes the
fix defensive in depth.

## Alternatives considered

- **Tailwind `safelist: ['grid-cols-[1fr_320px]']`** — rejected, the class
  *was* being generated; safelisting would have changed nothing.
- **Add `min-w-0` to the grid column only** — works for layout but leaves the
  canvas overflowing the column and clipped, which looks broken and breaks
  click hit-testing near the right edge.
- **Pass a hard-coded `width={832}` / `height={600}` to `ForceGraph3D`** —
  trivially fragile; breaks on resize, on browsers other than 1920×1080, and
  on devtools open. Rejected.
- **Use `react-resize-detector` / `use-resize-observer` package** — same
  result as inline `ResizeObserver` for cost of one new dependency.
  Rejected; native `ResizeObserver` has had baseline browser support since
  2020.
- **Lift sidebar out of the flex row and absolutely position it** — moves the
  problem into z-index and pointer-event management, and breaks the simple
  "two-column page" mental model. Rejected.

## Consequences

### Positive

- Sidebar placeholder + loaded states now render reliably at 320 px on the
  right; canvas resizes correctly with the viewport.
- The fix is local: three files changed, no new dependencies, no config
  surgery. Existing 426 + tests untouched; `npm run build` + `tsc --noEmit`
  remain green.
- Future authors who add a third column or collapse the sidebar will work
  with explicit flex sizing instead of grid's implicit min-content math.

### Negative / follow-ups

- `Knowledge3DGraph` now needs the layout effect to commit before rendering
  the canvas (size starts at 0 and updates on the first observer callback).
  In practice this is a single extra frame; users see no flash because the
  parent `<Knowledge3DGraph>` is rendered only after `graphData` is loaded.
- `ResizeObserver` is not polyfilled. If we ever need to support older
  browsers (IE11, very old Safari), we'd add `@juggle/resize-observer`. The
  rest of the app already assumes evergreen.

### Guidelines for future arbitrary Tailwind values

When using `grid-cols-[…]` or other intrinsic-sized grid tracks alongside a
child that *itself* sets explicit pixel dimensions (canvas, image with
attribute width, embedded iframe), prefer flexbox with `min-w-0` + `shrink-0`,
or wrap the child in a measured container that overrides its intrinsic size.
CSS Grid's `auto` min-track-sizing is the right default for content-driven
columns but a footgun for fixed-sized children.
