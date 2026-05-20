# axis-knowledge-rag — Chrome MV3 Extension

Save the currently-open web page to your `axis-knowledge-rag` knowledge
directory in one click. Targets the local backend's `POST /api/ingest`
endpoint (spec_046).

## Install (unpacked, dev)

1. Start the backend:
   ```bash
   cd ..   # repo root
   PYTHONPATH=. python3 -m uvicorn backend.src.api:app --port 8000
   ```
2. Open Chrome → `chrome://extensions`.
3. Enable **Developer mode** (top-right toggle).
4. Click **Load unpacked** → select this `browser-extension/` directory.
5. Pin the extension icon to the toolbar (puzzle-piece menu).

## Use

1. Open any article / page you want to capture.
2. Click the extension icon — the popup shows the URL + title.
3. Click **Save to knowledge**.
4. The popup shows `Saved: web_<timestamp>_<slug>` on success.
5. The file appears at
   `examples/knowledge/web_YYYYMMDD_HHMMSS_<slug>.md`.

If a region of the page is selected, that selection is captured as the
body. Otherwise the first ~5,000 characters of `document.body.innerText`
are used.

## Settings

Click **Settings** in the popup to change the API endpoint (default
`http://localhost:8000`). The value is stored in `chrome.storage.sync`
so it persists across browser restarts.

## Files

| File | Purpose |
| --- | --- |
| `manifest.json` | MV3 manifest (action popup + service worker) |
| `popup.html`/`popup.css`/`popup.js` | The toolbar popup UI |
| `background.js` | Service worker; seeds default endpoint on install |
| `icon-16.png` / `icon-48.png` / `icon-128.png` | Toolbar / store icons (placeholder) |

## Permissions

| Permission | Why |
| --- | --- |
| `activeTab` | Read the current tab's URL + title |
| `scripting` | Run a tiny snippet to read `document.body.innerText` / selection |
| `storage` | Persist the API endpoint setting |
| `host_permissions: http://localhost/*`, `http://127.0.0.1/*` | Allow `fetch()` to the local backend |

## Troubleshooting

- **`Error: HTTP 0` / network error** — Backend not running, or the
  endpoint in Settings doesn't match. Defaults to `http://localhost:8000`.
- **`Error: HTTP 422`** — The page had no title or URL (rare; only
  happens on `chrome://` pages, which the extension cannot scrape).
- **Saved file is empty** — `executeScript` was blocked by the page
  (`chrome://`, Web Store, file://). The URL + title still get saved;
  body capture requires a normal `http(s)://` page.
- **CORS error in the console** — The backend's CORS allow-regex needs
  to match the extension origin. The default regex covers
  `chrome-extension://*`; if you changed it, restore the default in
  `backend/src/api.py`.

## Future work (out of scope for v0.9)

- Right-click context menu ("Save this selection")
- Per-domain endpoint overrides
- Better main-content extraction (Mercury / Readability.js)
- LLM-based axes auto-suggestion (level / topic)
- Firefox & Safari builds
