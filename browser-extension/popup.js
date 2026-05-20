// axis-knowledge-rag — popup logic (vanilla JS, MV3).
// Captures the active tab, optionally pulls a user selection via
// chrome.scripting, and POSTs to `${endpoint}/api/ingest`.

const $ = (id) => document.getElementById(id);
const DEFAULT_ENDPOINT = "http://localhost:8000";
const MAX_BODY_CHARS = 5000;

let activeTab = null;
let endpoint = DEFAULT_ENDPOINT;

function setStatus(text, kind) {
  const el = $("status");
  el.textContent = text;
  el.classList.remove("ok", "error");
  if (kind) el.classList.add(kind);
}

async function init() {
  try {
    const stored = await chrome.storage.sync.get(["endpoint"]);
    if (stored.endpoint) {
      endpoint = stored.endpoint;
    }
    $("endpoint").value = endpoint;
  } catch (e) {
    // chrome.storage missing in some sandboxed contexts — fall through.
  }
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    activeTab = tab || null;
    if (activeTab) {
      $("url").textContent = activeTab.url || "";
      $("title").textContent = activeTab.title || "";
    } else {
      setStatus("No active tab", "error");
      $("save-btn").disabled = true;
    }
  } catch (e) {
    setStatus(`Tab query failed: ${e.message}`, "error");
    $("save-btn").disabled = true;
  }
}

async function captureBody() {
  if (!activeTab) return "";
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: activeTab.id },
      func: (maxChars) => {
        const sel = window.getSelection ? window.getSelection().toString() : "";
        const text = sel && sel.trim()
          ? sel
          : (document.body ? document.body.innerText : "");
        return (text || "").slice(0, maxChars);
      },
      args: [MAX_BODY_CHARS],
    });
    if (Array.isArray(results) && results.length && typeof results[0].result === "string") {
      return results[0].result;
    }
  } catch (e) {
    // Restricted pages (chrome://, Web Store, etc.) reject executeScript.
    // Fall back to an empty body so the URL+title still get saved.
    console.warn("axis-knowledge-rag: executeScript failed", e);
  }
  return "";
}

async function saveCurrentPage() {
  if (!activeTab) return;
  $("save-btn").disabled = true;
  setStatus("Saving...");
  const body = await captureBody();
  try {
    const resp = await fetch(`${endpoint.replace(/\/$/, "")}/api/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: activeTab.url,
        title: activeTab.title || activeTab.url,
        body,
        selected_text: null,
      }),
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const j = await resp.json();
        if (j && j.detail) detail = `${detail}: ${j.detail}`;
      } catch (_) {}
      throw new Error(detail);
    }
    const data = await resp.json();
    setStatus(`Saved: ${data.doc_id}`, "ok");
  } catch (e) {
    setStatus(`Error: ${e.message}`, "error");
  } finally {
    $("save-btn").disabled = false;
  }
}

async function saveSettings() {
  const value = ($("endpoint").value || "").trim();
  if (!value) {
    setStatus("Endpoint cannot be empty", "error");
    return;
  }
  endpoint = value;
  try {
    await chrome.storage.sync.set({ endpoint });
    setStatus("Settings saved", "ok");
  } catch (e) {
    setStatus(`Storage error: ${e.message}`, "error");
  }
}

$("save-btn").addEventListener("click", saveCurrentPage);
$("save-settings").addEventListener("click", saveSettings);

init();
