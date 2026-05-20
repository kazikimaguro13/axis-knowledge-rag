// MV3 service worker — currently a placeholder. spec_046 keeps the extension
// minimal (popup-only); future scopes (right-click "Save this selection",
// per-domain endpoints, etc.) will hook in here.

chrome.runtime.onInstalled.addListener(() => {
  // Seed the default endpoint so the popup's "Settings → Save" step is
  // optional on first launch.
  chrome.storage.sync.get(["endpoint"], (stored) => {
    if (!stored.endpoint) {
      chrome.storage.sync.set({ endpoint: "http://localhost:8000" });
    }
  });
});
