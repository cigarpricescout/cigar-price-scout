// Consumer-extension background service worker.
//
// Responsibilities:
//   1. On install, open consent.html (one-time).
//   2. On any tab activate/update, scrape the page and (if the user has
//      opted in and the URL passes all gates) post an anonymous price
//      observation to /api/community/observe.
//   3. Maintain a short-lived per-tab cache of the public url-status
//      response so the popup opens instantly with the right state.
//
// Inherits every Sprint 1 guardrail:
//   * Consent gate     — hasConsented() must be true before any post.
//   * Registry gate    — host must be in /api/public/retailer-registry.
//   * Product-page gate — looksLikeProductPage() blocks homepages, etc.
//   * Dedupe           — persisted per-canonical-URL in chrome.storage.session.
//
// Adds no admin auth. Talks only to /api/public/* and /api/community/*.

import {
  publicFetch,
  scrapeActiveTab,
  postObservation,
  hasConsented,
  getRetailerRegistry,
  resolveRetailerKey,
  getZip,
} from "./config.js";

// ── First-run consent flow ─────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  if (reason !== "install") return;
  try {
    await chrome.tabs.create({
      url: chrome.runtime.getURL("consent.html"),
      active: true,
    });
  } catch (_) {}
});

// ── Persisted observation dedupe ───────────────────────────────────────
// One observation per canonical URL per session, regardless of which
// raw URL the user lands on (?variant=… variants collapse together).
// chrome.storage.session resets on browser restart, which is the right
// trade-off: keeps memory bounded while preserving dedupe across the
// service worker's aggressive ~30s idle eviction.

const OBSERVE_DEDUPE_KEY = "observeDedupe";
const OBSERVE_DEDUPE_MS = 60 * 60 * 1000;
const OBSERVE_DEDUPE_MAX = 200;

async function getObserveDedupe() {
  try {
    const out = await chrome.storage.session.get(OBSERVE_DEDUPE_KEY);
    return out[OBSERVE_DEDUPE_KEY] || {};
  } catch (_) {
    return {};
  }
}

async function setObserveDedupe(map) {
  try {
    await chrome.storage.session.set({ [OBSERVE_DEDUPE_KEY]: map });
  } catch (_) {}
}

// Dedupe is keyed by canonicalized URL (path-only, no query) so that
// switching variants on a Shopify page doesn't trigger redundant posts.
// This is intentionally aggressive — the backend will still record
// price + box_qty differences as separate observations if the dedupe
// window expires.
function dedupeKey(url) {
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.host}${u.pathname}`;
  } catch (_) {
    return url;
  }
}

async function shouldObserve(rawUrl) {
  const key = dedupeKey(rawUrl);
  const map = await getObserveDedupe();
  const last = map[key] || 0;
  if (Date.now() - last < OBSERVE_DEDUPE_MS) return false;
  map[key] = Date.now();
  const entries = Object.entries(map);
  if (entries.length > OBSERVE_DEDUPE_MAX) {
    entries.sort((a, b) => a[1] - b[1]);
    const keep = entries.slice(-OBSERVE_DEDUPE_MAX);
    await setObserveDedupe(Object.fromEntries(keep));
  } else {
    await setObserveDedupe(map);
  }
  return true;
}

// ── Product-page gate (mirrors Sprint 1's operator extension) ─────────

const NON_PRODUCT_PATH_PATTERNS = [
  /^\/?$/,                      // homepage
  /^\/collections(\/|$)/,
  /^\/categories(\/|$)/,
  /^\/category(\/|$)/,
  /^\/search(\/|$)/,
  /^\/cart(\/|$)/,
  /^\/checkout(\/|$)/,
  /^\/account(\/|$)/,
  /^\/login(\/|$)/,
  /^\/pages\//,
  /^\/blogs?\//,
  /^\/policies?\//,
  /^\/sitemap/,
  /^\/api\//,
];

function looksLikeProductPage(rawUrl, state) {
  if (state === "matched") return true; // already in retailer CSV → definitely a product
  try {
    const path = (new URL(rawUrl).pathname || "/").toLowerCase();
    for (const re of NON_PRODUCT_PATH_PATTERNS) {
      if (re.test(path)) return false;
    }
    return true;
  } catch (_) {
    return false;
  }
}

// ── Per-tab url-status cache (powers the popup) ────────────────────────

const STATUS_CACHE = new Map(); // url -> { fetchedAt, response, scraped }
const STATUS_TTL_MS = 60 * 1000;

async function fetchUrlStatus(url) {
  const zip = await getZip();
  return publicFetch("/api/public/url-status", { query: { url, zip } });
}

async function refreshForTab(tab) {
  if (!tab || !tab.url || !tab.id) return null;
  if (!/^https?:/.test(tab.url)) {
    await setBadgeForTab(tab.id, null);
    return null;
  }

  // Cheap host gate: skip everything when the registry doesn't know
  // this host. Saves a backend round-trip on every non-cigar page.
  let host = "";
  try { host = new URL(tab.url).hostname.toLowerCase(); } catch (_) {}
  const registry = await getRetailerRegistry();
  const retailerKey = resolveRetailerKey(host, registry);
  if (!retailerKey) {
    await setBadgeForTab(tab.id, "off");
    STATUS_CACHE.delete(tab.url);
    return null;
  }

  // Fresh status + scrape, in parallel.
  let response, scraped;
  try {
    const [s, sc] = await Promise.all([
      fetchUrlStatus(tab.url).catch(() => null),
      scrapeActiveTab(tab.id).catch(() => null),
    ]);
    response = s;
    scraped = sc;
  } catch (e) {
    response = { state: "error", error: String(e) };
  }
  if (!response) response = { state: "error", error: "no_response" };

  STATUS_CACHE.set(tab.url, {
    fetchedAt: Date.now(),
    response,
    scraped,
  });
  await setBadgeForTab(tab.id, response.state);

  // Passive observe — every gate must pass.
  if (
    scraped && (scraped.price != null || scraped.title) &&
    response.state && response.state !== "no_scraper" &&
    response.state !== "error" && response.state !== "non_product" &&
    looksLikeProductPage(tab.url, response.state) &&
    await hasConsented() &&
    await shouldObserve(tab.url)
  ) {
    postObservation({
      url: tab.url,
      scraped_title: scraped.title || scraped.jsonldName || null,
      price: scraped.price ?? null,
      currency: scraped.currency || "USD",
      in_stock: scraped.inStock,
      quantity_type: scraped.quantityType || "unknown",
      box_qty: scraped.boxQty || null,
      jsonld: scraped.jsonldRaw || null,
    }).catch(() => {});
  }

  return response;
}

// ── Badge: tiny visual indicator on the toolbar icon ───────────────────

async function setBadgeForTab(tabId, state) {
  const map = {
    matched:    { text: "$", color: "#16a34a" }, // green = comparison available
    candidate:  { text: "?", color: "#f59e0b" }, // amber = help us identify
    seen:       { text: "·", color: "#6b7280" }, // gray = under review
    no_scraper: { text: "",  color: "#000000" },
    non_product:{ text: "",  color: "#000000" },
    off:        { text: "",  color: "#000000" },
    error:      { text: "!", color: "#dc2626" },
  };
  const cfg = map[state] || { text: "", color: "#000000" };
  try {
    await chrome.action.setBadgeText({ tabId, text: cfg.text });
    if (cfg.text) {
      await chrome.action.setBadgeBackgroundColor({ tabId, color: cfg.color });
    }
  } catch (_) {}
}

// ── Tab event wiring ──────────────────────────────────────────────────

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  refreshForTab(tab);
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    refreshForTab(tab);
  } catch (_) {}
});

// ── Message bridge: popup asks for cached status ──────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return false;
  if (msg.type === "getStatusForTab") {
    (async () => {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const tab = tabs[0];
      if (!tab) { sendResponse({ tab: null, response: null, scraped: null }); return; }
      const cached = STATUS_CACHE.get(tab.url);
      if (cached && (Date.now() - cached.fetchedAt) < STATUS_TTL_MS) {
        sendResponse({ tab, response: cached.response, scraped: cached.scraped });
        return;
      }
      const response = await refreshForTab(tab);
      const fresh = STATUS_CACHE.get(tab.url);
      sendResponse({
        tab,
        response,
        scraped: fresh ? fresh.scraped : null,
      });
    })();
    return true; // async
  }
  if (msg.type === "invalidateCache") {
    if (msg.url) STATUS_CACHE.delete(msg.url);
    sendResponse({ ok: true });
    return false;
  }
  return false;
});
