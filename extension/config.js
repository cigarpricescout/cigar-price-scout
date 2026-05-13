// Shared config + storage helpers. Imported by background.js, popup.js, and
// options.js. Keep this small and dependency-free.

export const API_BASE = "https://cigarpricescout.com";

const ADMIN_KEY = "adminKey";

export async function getAdminKey() {
  const out = await chrome.storage.local.get(ADMIN_KEY);
  return out[ADMIN_KEY] || "";
}

export async function setAdminKey(value) {
  await chrome.storage.local.set({ [ADMIN_KEY]: value || "" });
}

export async function apiFetch(path, { method = "GET", body, query } = {}) {
  const key = await getAdminKey();
  if (!key) {
    const err = new Error("Admin key not configured");
    err.code = "NO_ADMIN_KEY";
    throw err;
  }
  let url = API_BASE + path;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  }
  const init = {
    method,
    headers: {
      "X-Admin-Key": key,
      "Content-Type": "application/json",
    },
  };
  if (body !== undefined) init.body = JSON.stringify(body);
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    const err = new Error(`${resp.status} ${resp.statusText}: ${text.slice(0, 200)}`);
    err.status = resp.status;
    throw err;
  }
  return resp.json();
}

// Best-effort scrape of the active tab. Returns { title } at minimum.
export async function scrapeActiveTab(tabId) {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        function txt(sel) {
          const el = document.querySelector(sel);
          return el ? (el.textContent || "").trim() : "";
        }
        function meta(name) {
          const el = document.querySelector(
            `meta[property="${name}"], meta[name="${name}"]`
          );
          return el ? (el.getAttribute("content") || "").trim() : "";
        }
        // JSON-LD product schema, if present (most Shopify sites have it).
        let jsonldName = "";
        let jsonldPrice = "";
        try {
          const blocks = document.querySelectorAll('script[type="application/ld+json"]');
          for (const b of blocks) {
            const data = JSON.parse(b.textContent || "{}");
            const items = Array.isArray(data) ? data : [data];
            for (const item of items) {
              if (!item) continue;
              const type = item["@type"];
              const types = Array.isArray(type) ? type : [type];
              if (types.includes("Product")) {
                jsonldName = item.name || jsonldName;
                if (item.offers) {
                  const off = Array.isArray(item.offers) ? item.offers[0] : item.offers;
                  if (off && off.price) jsonldPrice = String(off.price);
                }
              }
            }
          }
        } catch (_) {}
        return {
          title: txt("h1") || jsonldName || meta("og:title") || document.title || "",
          ogTitle: meta("og:title"),
          ogImage: meta("og:image"),
          ogDescription: meta("og:description"),
          jsonldName,
          jsonldPrice,
        };
      },
    });
    return (result && result.result) || { title: "" };
  } catch (e) {
    return { title: "", error: String(e && e.message || e) };
  }
}
