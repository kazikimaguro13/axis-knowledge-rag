# Browser Extension (Chrome MV3)

One-click capture of the page you're reading into your
`examples/knowledge/` directory. Sends `URL + title + body (or selection)`
to the local backend's `POST /api/ingest` endpoint, which writes a fresh
`web_YYYYMMDD_HHMMSS_<slug>.md` file.

> v0.9.0 ships the **Chrome** unpacked extension only. Firefox / Safari
> are out of scope for the v0.9 spec (the manifest signing flow differs);
> see ADR-027 for the rationale.

---

## Install (unpacked, dev)

1. Start the backend on `localhost:8000`:
   ```bash
   cd <repo-root>
   PYTHONPATH=. python3 -m uvicorn backend.src.api:app --port 8000
   ```
2. Open `chrome://extensions` in Chrome.
3. Toggle **Developer mode** (top-right).
4. Click **Load unpacked** → pick `browser-extension/` in this repo.
5. Pin the new extension from the puzzle-piece menu so the icon stays in
   the toolbar.

---

## Usage

1. Open any article / docs page you want to save.
2. (Optional) Select the paragraph(s) you care about. If a selection
   exists, the popup saves *only* the selection; otherwise it captures
   the first ~5,000 characters of `document.body.innerText`.
3. Click the extension icon → **Save to knowledge**.
4. The popup shows `Saved: web_<timestamp>_<slug>` on success. The file
   lands at `examples/knowledge/web_YYYYMMDD_HHMMSS_<slug>.md`.

To re-index so the new file appears in `/api/search` results:

```bash
python -m scripts.build_index ./examples/knowledge
```

---

## Settings

Click **Settings** in the popup to change the API endpoint. The value is
saved to `chrome.storage.sync` and survives browser restarts. Defaults to
`http://localhost:8000`. If you run the backend on a different port or a
proxy, point it here.

---

## What gets written

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

# Smoke Test

source: https://example.com/test

hello world
```

The `axes.category = "Web"` keeps captured documents in their own bucket,
separated from curated `技術記事` / `議事録` entries. Edit `topic` / `level`
by hand after capture if you want them surfaced via axis filtering. A
future iteration may LLM-suggest these values at capture time
([roadmap → v0.10](#roadmap)).

---

## Permissions

| Permission | Why |
| --- | --- |
| `activeTab` | Read the current tab's URL + title |
| `scripting` | Execute a small snippet to grab `document.body.innerText` / `window.getSelection()` |
| `storage` | Persist the API endpoint setting |
| `host_permissions` (`http://localhost/*`, `http://127.0.0.1/*`) | Allow `fetch()` to the local backend |

No `tabs` permission → the extension never sees the user's broader
browsing history.

---

## CORS

The backend's CORS middleware uses a regex that matches:

- `chrome-extension://<any-id>`
- `http://localhost(:port)?`
- `http://127.0.0.1(:port)?`

`allow_credentials` is `False`, so the existing frontend (which never set
`fetch({credentials:"include"})`) continues to work identically. Tightening
the regex for production deployments is documented in
[`docs/configuration.md`](configuration.md).

---

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `Error: HTTP 0` / network error | Backend isn't running, or Settings → API endpoint disagrees with the port |
| `Error: HTTP 422` | Page had no URL or title (only happens on `chrome://` pages, which Chrome blocks scripts on anyway) |
| Saved file body is empty | `executeScript` was rejected by the page (`chrome://`, Web Store, file://). URL + title still get saved |
| CORS error in DevTools | Backend regex was overridden in `backend/src/api.py`; restore the default or add the extension ID literally |
| Duplicate save | `POST /api/ingest` is intentionally non-idempotent — every click creates a new file. Delete the older one if you want only the latest |

Logs to look at:

- **Extension console** → `chrome://extensions` → "Inspect views: popup"
- **Backend** → `uvicorn` stdout (each `POST /api/ingest` shows up as
  `200 OK` with the saved path in the response)

---

## Roadmap

These are explicitly out of scope for v0.9.0 (spec_046) and parked for
v0.10:

- Right-click context menu ("Save this selection")
- Mercury / Readability.js for actual main-content extraction
- LLM-based axes suggestion (auto-guess `topic` / `level`)
- Per-domain endpoint overrides
- Firefox WebExtensions + Safari App Extensions
- Production icon set (the current `icon-*.png` are PIL placeholders)
