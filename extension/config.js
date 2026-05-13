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

// Best-effort scrape of the active tab. Returns:
//   {
//     title, ogTitle, ogImage, ogDescription,
//     jsonldName, jsonldPrice, jsonldCurrency, jsonldAvailability, jsonldRaw,
//     price        (number | null, dollars),
//     currency     (string, "USD" default),
//     inStock      (boolean | null),
//     quantityType ("box" | "pack5" | "pack10" | "pack20" | "single" | "unknown"),
//     boxQty       (number | null)
//   }
// All extraction is best-effort; missing fields just come back null/"unknown".
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

        // ── JSON-LD product extraction ────────────────────────────────
        let jsonldName = "";
        let jsonldPriceStr = "";
        let jsonldCurrency = "";
        let jsonldAvailability = "";
        let jsonldRaw = null;
        try {
          const blocks = document.querySelectorAll('script[type="application/ld+json"]');
          for (const b of blocks) {
            let data;
            try { data = JSON.parse(b.textContent || "{}"); } catch (_) { continue; }
            const items = Array.isArray(data) ? data : [data];
            for (const item of items) {
              if (!item) continue;
              const type = item["@type"];
              const types = Array.isArray(type) ? type : [type];
              if (types.includes("Product")) {
                jsonldName = item.name || jsonldName;
                if (item.offers) {
                  const off = Array.isArray(item.offers) ? item.offers[0] : item.offers;
                  if (off) {
                    if (off.price) jsonldPriceStr = String(off.price);
                    if (off.priceCurrency) jsonldCurrency = String(off.priceCurrency);
                    if (off.availability) jsonldAvailability = String(off.availability);
                  }
                }
                // Capture a trimmed copy of the Product blob for backend
                // debugging; cap size so a megabyte of schema doesn't ship.
                if (!jsonldRaw) {
                  try {
                    jsonldRaw = {
                      name: item.name,
                      sku: item.sku,
                      gtin: item.gtin || item.gtin13 || item.gtin12 || item.gtin8,
                      brand: item.brand && (item.brand.name || item.brand),
                      offers: item.offers,
                      description: typeof item.description === "string"
                        ? item.description.slice(0, 500) : undefined,
                    };
                  } catch (_) {}
                }
              }
            }
          }
        } catch (_) {}

        // ── Price normalization ───────────────────────────────────────
        // Prefer JSON-LD; fall back to common DOM selectors. Returns a
        // number in dollars (NOT cents) — the backend converts.
        function parsePriceString(s) {
          if (!s) return null;
          const m = String(s).replace(/,/g, "").match(/(\d+(?:\.\d+)?)/);
          if (!m) return null;
          const n = parseFloat(m[1]);
          return isFinite(n) && n > 0 && n < 100000 ? n : null;
        }
        let price = parsePriceString(jsonldPriceStr);
        let currency = (jsonldCurrency || "USD").toUpperCase();
        if (price == null) {
          // Common DOM fallbacks (Shopify, WooCommerce, Magento patterns).
          const domSel = [
            '[itemprop="price"]',
            '.product__price .price',
            '.product-price',
            '.price--main',
            '.price-item--sale',
            '.price-item--regular',
            '.product-info-price .price',
            '[data-product-price]',
          ];
          for (const sel of domSel) {
            const el = document.querySelector(sel);
            if (el) {
              const cand = parsePriceString(
                el.getAttribute("content") || el.getAttribute("data-price") || el.textContent
              );
              if (cand) { price = cand; break; }
            }
          }
        }

        // ── Availability / in_stock ───────────────────────────────────
        let inStock = null;
        if (jsonldAvailability) {
          const a = jsonldAvailability.toLowerCase();
          if (a.includes("instock") || a.includes("in_stock") || a.endsWith("/instock")) {
            inStock = true;
          } else if (
            a.includes("outofstock") || a.includes("out_of_stock") ||
            a.includes("soldout") || a.endsWith("/outofstock")
          ) {
            inStock = false;
          }
        }
        if (inStock === null) {
          // Heuristic DOM fallback: any visible "out of stock" / "sold out"
          // text near the buy button overrides default-True.
          const body = (document.body && document.body.innerText || "").toLowerCase();
          if (/out\s*of\s*stock|sold\s*out|unavailable/.test(body)) {
            inStock = false;
          } else if (/add\s*to\s*cart|buy\s*now|add\s*to\s*bag/.test(body)) {
            inStock = true;
          }
        }

        // ── Quantity type detection ──────────────────────────────────
        // Cigars are sold as singles, 5-packs, 10-packs, 20-packs, or boxes
        // (10/20/24/25/30/etc.). We try, in order:
        //   1. JSON-LD product name regex (most reliable on Shopify)
        //   2. Page H1 / og:title
        //   3. Active variant label in select/radio controls
        // and bucket into box | pack5 | pack10 | pack20 | single | unknown.
        function detectQty(haystack) {
          if (!haystack) return { type: "unknown", qty: null };
          const h = String(haystack).toLowerCase();
          // Box of N / N count box / box(25)
          let m = h.match(/box\s*(?:of\s*)?(\d{2,3})/);
          if (m) return { type: "box", qty: parseInt(m[1], 10) };
          m = h.match(/(\d{2,3})\s*(?:ct|count|cigars?|pack)\s*box/);
          if (m) return { type: "box", qty: parseInt(m[1], 10) };
          // N-pack / pack of N (smaller groupings)
          m = h.match(/(\d{1,2})\s*[- ]?pack\b/);
          if (m) {
            const n = parseInt(m[1], 10);
            if (n === 1) return { type: "single", qty: 1 };
            if (n === 5) return { type: "pack5", qty: 5 };
            if (n === 10) return { type: "pack10", qty: 10 };
            if (n === 20) return { type: "pack20", qty: 20 };
            return n >= 24 ? { type: "box", qty: n } : { type: "unknown", qty: n };
          }
          m = h.match(/pack\s*of\s*(\d{1,2})/);
          if (m) {
            const n = parseInt(m[1], 10);
            if (n === 5)  return { type: "pack5", qty: 5 };
            if (n === 10) return { type: "pack10", qty: 10 };
            if (n === 20) return { type: "pack20", qty: 20 };
            if (n === 1)  return { type: "single", qty: 1 };
            return { type: "unknown", qty: n };
          }
          // Single / each / individual
          if (/\b(single|individual)\b/.test(h) || /\beach\b/.test(h)) {
            return { type: "single", qty: 1 };
          }
          return { type: "unknown", qty: null };
        }

        // Try the JSON-LD name first since it's normalized.
        let qt = detectQty(jsonldName);
        if (qt.type === "unknown") qt = detectQty(txt("h1"));
        if (qt.type === "unknown") qt = detectQty(meta("og:title"));
        if (qt.type === "unknown") {
          // Look at any selected variant control.
          const sel = document.querySelector("select option[selected]") ||
                      document.querySelector("input[type=radio]:checked");
          if (sel) qt = detectQty(sel.textContent || sel.value || "");
        }

        return {
          title: txt("h1") || jsonldName || meta("og:title") || document.title || "",
          ogTitle: meta("og:title"),
          ogImage: meta("og:image"),
          ogDescription: meta("og:description"),
          jsonldName,
          jsonldPrice: jsonldPriceStr,
          jsonldCurrency,
          jsonldAvailability,
          jsonldRaw,
          price,
          currency,
          inStock,
          quantityType: qt.type,
          boxQty: qt.qty,
        };
      },
    });
    return (result && result.result) || { title: "" };
  } catch (e) {
    return { title: "", error: String(e && e.message || e) };
  }
}


// ── Stable per-install observer id ────────────────────────────────────
// Anonymous; persisted in chrome.storage.local. Used to rate-limit the
// public /api/community/observe endpoint without forcing accounts.

const OBSERVER_ID_KEY = "observerId";

export async function getObserverId() {
  const out = await chrome.storage.local.get(OBSERVER_ID_KEY);
  let id = out[OBSERVER_ID_KEY];
  if (!id) {
    // 24 random bytes hex-encoded -> 48 chars. No PII.
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    id = Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
    await chrome.storage.local.set({ [OBSERVER_ID_KEY]: id });
  }
  return id;
}


// ── Public observe call (no admin key required) ───────────────────────
// Fire-and-forget; failures are swallowed because passive observation
// must never break a user's browsing.

export async function postObservation(payload) {
  try {
    const observerId = await getObserverId();
    const body = { observer_id: observerId, ...payload };
    await fetch(API_BASE + "/api/community/observe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      // keepalive lets the request finish even if the tab/popup closes.
      keepalive: true,
    });
  } catch (_) {
    /* swallow; passive collection must not affect the user */
  }
}
