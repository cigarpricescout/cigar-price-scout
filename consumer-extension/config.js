// Shared config + helpers for the consumer Chrome extension.
//
// Differs from the operator extension in three ways:
//   1. No admin key. Every API call hits a public, no-auth endpoint.
//   2. Observation is GATED by an explicit user opt-in (set on first
//      install via consent.html, mutable via options.html).
//   3. Talks to /api/public/* and /api/community/* only — never /admin/*.

export const API_BASE = "https://cigarpricescout.com";

// ── Public no-auth API client ─────────────────────────────────────────

export async function publicFetch(path, { method = "GET", body, query } = {}) {
  let url = API_BASE + path;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  }
  const init = { method, headers: { "Content-Type": "application/json" } };
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

// ── Opt-in state (mandatory gate before any observation) ──────────────
// Three states:
//   "unset"     — never visited consent.html. Treated as opted-out.
//   "opted_in"  — user accepted observation on the consent screen.
//   "opted_out" — user declined or later turned it off.
// Stored in chrome.storage.local under "consentState".

const CONSENT_KEY = "consentState";

export async function getConsentState() {
  try {
    const out = await chrome.storage.local.get(CONSENT_KEY);
    return out[CONSENT_KEY] || "unset";
  } catch (_) {
    return "unset";
  }
}

export async function setConsentState(state) {
  if (!["unset", "opted_in", "opted_out"].includes(state)) {
    throw new Error(`invalid consent state: ${state}`);
  }
  await chrome.storage.local.set({ [CONSENT_KEY]: state });
}

export async function hasConsented() {
  return (await getConsentState()) === "opted_in";
}

// ── Stable, anonymous per-install observer id ─────────────────────────
// 24 random bytes -> 48 hex chars. No PII. Used as the rate-limit key
// on /api/community/observe and as the bearer key for "forget me"
// delete requests. Persisted in chrome.storage.local.

const OBSERVER_ID_KEY = "observerId";

export async function getObserverId() {
  const out = await chrome.storage.local.get(OBSERVER_ID_KEY);
  let id = out[OBSERVER_ID_KEY];
  if (!id) {
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    id = Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
    await chrome.storage.local.set({ [OBSERVER_ID_KEY]: id });
  }
  return id;
}

export async function rotateObserverId() {
  // Used by the "Forget me & rotate identity" button. The old id is left
  // in the wild but the user's next observation will be unlinkable.
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  const id = Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
  await chrome.storage.local.set({ [OBSERVER_ID_KEY]: id });
  return id;
}

// ── Optional ZIP for shipping/tax math in price comparison ────────────

const ZIP_KEY = "zip";

export async function getZip() {
  const out = await chrome.storage.local.get(ZIP_KEY);
  return out[ZIP_KEY] || "";
}

export async function setZip(value) {
  const v = String(value || "").replace(/\D/g, "").slice(0, 5);
  await chrome.storage.local.set({ [ZIP_KEY]: v });
  return v;
}

// ── Per-URL preferred CID (multi-cigar PDP picker) ─────────────────────
// Keyed by protocol+host+pathname so ?variant=… shares one preference.

const CID_PREF_PREFIX = "cidPref:v1:";

export function urlPickDedupeKey(rawUrl) {
  try {
    const u = new URL(rawUrl);
    return `${u.protocol}//${u.host}${u.pathname}`;
  } catch (_) {
    return rawUrl;
  }
}

export async function getPreferredCidForUrl(rawUrl) {
  try {
    const key = CID_PREF_PREFIX + urlPickDedupeKey(rawUrl);
    const out = await chrome.storage.local.get(key);
    return out[key] || "";
  } catch (_) {
    return "";
  }
}

export async function setPreferredCidForUrl(rawUrl, cigarId) {
  try {
    const key = CID_PREF_PREFIX + urlPickDedupeKey(rawUrl);
    if (!cigarId) await chrome.storage.local.remove(key);
    else await chrome.storage.local.set({ [key]: cigarId });
  } catch (_) {}
}

// ── Best-effort page scrape (executed in target tab via scripting API) ─
// Identical extraction logic to the operator extension's scrapeActiveTab.
// Kept in lockstep so a consumer install + an operator install observing
// the same page produce comparable data.

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

        let jsonldName = "";
        let jsonldPriceStr = "";
        let jsonldCurrency = "";
        let jsonldAvailability = "";
        let jsonldBrand = "";
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
                jsonldBrand = jsonldBrand || (item.brand && (item.brand.name || item.brand)) || "";
                if (item.offers) {
                  const off = Array.isArray(item.offers) ? item.offers[0] : item.offers;
                  if (off) {
                    if (off.price) jsonldPriceStr = String(off.price);
                    if (off.priceCurrency) jsonldCurrency = String(off.priceCurrency);
                    if (off.availability) jsonldAvailability = String(off.availability);
                  }
                }
                if (!jsonldRaw) {
                  try {
                    jsonldRaw = {
                      name: item.name,
                      sku: item.sku,
                      gtin: item.gtin || item.gtin13 || item.gtin12 || item.gtin8,
                      brand: jsonldBrand,
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
          const body = (document.body && document.body.innerText || "").toLowerCase();
          if (/out\s*of\s*stock|sold\s*out|unavailable/.test(body)) {
            inStock = false;
          } else if (/add\s*to\s*cart|buy\s*now|add\s*to\s*bag/.test(body)) {
            inStock = true;
          }
        }

        function detectQty(haystack) {
          if (!haystack) return { type: "unknown", qty: null };
          const h = String(haystack).toLowerCase();
          let m = h.match(/box\s*(?:of\s*)?(\d{2,3})/);
          if (m) return { type: "box", qty: parseInt(m[1], 10) };
          m = h.match(/(\d{2,3})\s*(?:ct|count|cigars?|pack)\s*box/);
          if (m) return { type: "box", qty: parseInt(m[1], 10) };
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
          if (/\b(single|individual)\b/.test(h) || /\beach\b/.test(h)) {
            return { type: "single", qty: 1 };
          }
          return { type: "unknown", qty: null };
        }

        let qt = detectQty(jsonldName);
        if (qt.type === "unknown") qt = detectQty(txt("h1"));
        if (qt.type === "unknown") qt = detectQty(meta("og:title"));
        if (qt.type === "unknown") {
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
          jsonldBrand,
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

// ── Fire-and-forget observation post ──────────────────────────────────
// Gated by hasConsented() at every call site. Failures swallowed because
// passive observation must never break a user's browsing.

export async function postObservation(payload) {
  if (!(await hasConsented())) return;
  try {
    const observerId = await getObserverId();
    const body = { observer_id: observerId, observer_source: "consumer", ...payload };
    await fetch(API_BASE + "/api/community/observe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepalive: true,
    });
  } catch (_) {
    /* swallow */
  }
}

// ── Retailer registry (cached, refreshed lazily) ──────────────────────
// Used by background.js to short-circuit observation on unknown hosts
// without round-tripping the backend on every tab activation.

const REGISTRY_KEY = "retailerRegistry";
const REGISTRY_TTL_MS = 6 * 60 * 60 * 1000;  // 6h

export async function getRetailerRegistry({ forceRefresh = false } = {}) {
  if (!forceRefresh) {
    try {
      const out = await chrome.storage.local.get(REGISTRY_KEY);
      const cached = out[REGISTRY_KEY];
      if (cached && (Date.now() - cached.fetchedAt) < REGISTRY_TTL_MS) {
        return cached.registry;
      }
    } catch (_) {}
  }
  try {
    const data = await publicFetch("/api/public/retailer-registry");
    const registry = {
      hostnames: new Set((data.retailers || []).map(r => r.hostname.toLowerCase())),
      byHost: Object.fromEntries(
        (data.retailers || []).map(r => [r.hostname.toLowerCase(), r.retailer_key])
      ),
    };
    await chrome.storage.local.set({
      [REGISTRY_KEY]: {
        fetchedAt: Date.now(),
        registry: {
          hostnames: Array.from(registry.hostnames),
          byHost: registry.byHost,
        },
      },
    });
    return { hostnames: registry.hostnames, byHost: registry.byHost };
  } catch (_) {
    return { hostnames: new Set(), byHost: {} };
  }
}

export function resolveRetailerKey(hostname, registry) {
  if (!hostname || !registry) return null;
  const h = hostname.toLowerCase();
  const hostnames = registry.hostnames instanceof Set
    ? registry.hostnames
    : new Set(registry.hostnames || []);
  const byHost = registry.byHost || {};
  if (hostnames.has(h)) return byHost[h];
  // Strip leading 'www.' to match canonical entry.
  if (h.startsWith("www.")) {
    const stripped = h.slice(4);
    if (hostnames.has(stripped)) return byHost[stripped];
  } else {
    const prefixed = "www." + h;
    if (hostnames.has(prefixed)) return byHost[prefixed];
  }
  return null;
}
