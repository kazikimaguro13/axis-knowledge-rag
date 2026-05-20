# ADR-027: Browser extension MVP for one-click web-page capture

- **Status**: Accepted
- **Date**: 2026-05-20
- **Spec**: spec_046 (v0.9.0 marquee — bundle 4, follow-on after Ollama)

## Context

Through v0.8 the knowledge feed is "edit a Markdown file in
`examples/knowledge/`, re-run `scripts.build_index`." That works for the
curated baseline corpus but is heavy for the most common addition the
author actually makes day-to-day: **"I just read this article and want
to keep it."** The current friction is roughly:

1. Switch to a memo app, paste the URL + a snippet
2. Open the repo, write a YAML frontmatter Markdown by hand
3. `git add` + `python -m scripts.build_index ...`

Four steps and ~3 minutes per article. The result is that web reading
rarely lands in the corpus at all — the structured knowledge graph drifts
away from where the author's *current* thinking actually is.

A capture path needs to be: **one click, no context switch, no
hand-formatting.**

## Decision

Ship a **Chrome Manifest V3 extension** that posts the current tab to a
new local backend endpoint:

- `POST /api/ingest` — accepts `{url, title, body, selected_text?}` and
  writes `examples/knowledge/web_<timestamp>_<slug>.md` with a minimal
  YAML frontmatter (axes preset to `Web / 未分類 / 中級`).
- The extension popup shows the active tab's URL + title and a single
  "Save to knowledge" button.
- The backend's CORS middleware widens to allow
  `chrome-extension://*` + any `localhost` / `127.0.0.1` port via a
  regex match (the existing literal allow-list rejected MV3 origins
  outright).
- Endpoint URL is configurable per-install via `chrome.storage.sync`,
  defaulting to `http://localhost:8000`.

### File layout

```
browser-extension/
├── manifest.json          # MV3, action popup + service worker
├── popup.html / .css / .js
├── background.js          # seeds default endpoint on install
├── icon-{16,48,128}.png   # placeholder, indigo (#4f46e5)
└── README.md              # install + troubleshooting
backend/src/
├── ingest_web.py          # save_web_page(url, title, body, ...) → Path
└── api.py                 # +POST /api/ingest, +CORSMiddleware regex
backend/src/schemas.py     # +IngestRequest, +IngestResponse
```

### Filename + frontmatter contract

```
web_YYYYMMDD_HHMMSS_<slug>.md   (UTC timestamp)
```

`<slug>` is NFKC-normalised → lowercased → non-`[\w\s-]` stripped → spaces
& dashes collapsed. Japanese kana/kanji survive (Python's Unicode `\w`).
Timestamp suffixed-by-the-second so concurrent saves don't collide; the
endpoint is intentionally non-idempotent.

```yaml
---
id: web_20260520_023804_smoke-test
title: Smoke Test
source: browser-extension
url: https://example.com/test
captured_at: 2026-05-20T02:38:04.692346+00:00
axes:
  category: Web
  topic: 未分類
  level: 中級
refs: []
---

# <title>

source: <url>

<selected_text or body>
```

`axes.category = "Web"` keeps the captured doc out of the curated
"技術記事" / "議事録" buckets the rest of the corpus uses, so the existing
search UX is unaffected — `Web` users can opt in via filter.

## Alternatives considered

- **Tampermonkey / Greasemonkey userscript** — Zero install of a real
  extension, but each user needs Tampermonkey + a per-domain `@grant`
  list, and the script can't get the active tab's title without DOM
  scraping. Loses the MV3 lifecycle (service worker, storage sync).
- **Bookmarklet** — Simplest possible, but CORS preflight from a
  `javascript:` URL is browser-vendor-specific and the user has to drag
  it to the bookmark bar. Friction parity with "copy a curl command."
- **Native messaging host** — Lets the extension write files directly
  with no HTTP round-trip, but binds the install to a specific OS path
  and ships a per-platform binary. Massive over-engineering for v0.9.
- **Firefox WebExtensions / Safari App Extensions in v0.9** — Same code
  shape as MV3 in 90% of cases, but the manifest + signing flow differs
  and the marquee user (the author) is on Chrome. Deferred to v0.10.

## Consequences

### Positive

- **One-click capture.** The 3-step / 3-minute path collapses to ~2 s.
- **Knowledge dir is the single source of truth.** Files written by the
  extension are picked up by the existing `loader.py` / `build_index.py`
  with no schema migration — the YAML shape is what they already expect.
- **Backend surface grows by one endpoint** with full Pydantic validation
  + a tmp-dir test path; CORS is now regex-driven, which makes adding
  future origins (e.g. a packaged desktop wrapper) a one-line change.

### Negative — CORS opens up

The previous allow-list was two literal localhost ports. The new regex
allows any `chrome-extension://...` ID and any `localhost` / `127.0.0.1`
port. Because `allow_credentials=False`, the existing frontend and
Streamlit app keep working (they never relied on cookies/credentials on
cross-origin requests). Production deployments behind a reverse proxy
should override the regex with an explicit allow-list — documented in
`docs/configuration.md`.

### Negative — main-content extraction is crude

`document.body.innerText` is the entirety of the page minus `<style>` /
`<script>`, capped at 5,000 chars in the popup. Nav bars, footers, and
cookie banners land in the saved file. The user can opt out per-capture
by **selecting** the article body before clicking — the popup prefers
the active selection over the full body. A Mercury / Readability.js
extraction pass is parked for v0.10.

### Negative — placeholder icons

`icon-{16,48,128}.png` are PIL-generated solid-indigo squares. Good
enough for an unpacked-extension install; rejected by the Chrome Web
Store. Replacement before any store submission, deferred to v0.10.

## Migration

No migration. The endpoint is purely additive; existing deployments
serve `/api/ingest` immediately after `git pull` + restart. Capturing
the first page creates `examples/knowledge/web_*.md`; running
`scripts.build_index` indexes it like any other doc.
