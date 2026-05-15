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
  getObserverId,
  getPreferredCidForUrl,
  withTimeout,
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

async function fetchUrlStatus(url, zip, cid) {
  const query = { url, zip };
  if (cid) query.cid = cid;
  return publicFetch("/api/public/url-status", { query });
}

async function refreshForTab(tab) {
  if (!tab || !tab.url || !tab.id) return null;
  if (!/^https?:/.test(tab.url)) {
    await setBadgeForTab(tab.id, null);
    return null;
  }

  // Cheap host gate: skip the backend call when the registry doesn't
  // know this host AND the URL doesn't look cigar-shaped at all.
  // Previously this returned null unconditionally on unknown hosts,
  // which made the popup render "Couldn't reach the price database"
  // — wrong message, the network was fine, the registry just hadn't
  // refreshed (or the operator's CSV was missing). Now we still try
  // the server: it returns state="no_scraper" with the hostname,
  // which the popup turns into a "New retailer — request to be
  // added?" UI. Saves the bad error state.
  let host = "";
  try { host = new URL(tab.url).hostname.toLowerCase(); } catch (_) {}
  const registry = await getRetailerRegistry();
  const retailerKey = resolveRetailerKey(host, registry);
  if (!retailerKey) {
    await setBadgeForTab(tab.id, "off");
    // Don't fully short-circuit — still hit the public endpoint so
    // the popup can render the proper no_scraper UI. The badge stays
    // off (we don't want every random tab lit up) but if the user
    // actually clicks the icon they get a real response.
  }

  const zip = await getZip();
  const prefCid = await getPreferredCidForUrl(tab.url);
  // Fresh status + scrape, in parallel.
  let response, scraped;
  try {
    const [s, sc] = await Promise.all([
      withTimeout(fetchUrlStatus(tab.url, zip, prefCid), 15000, null),
      withTimeout(scrapeActiveTab(tab.id), 12000, null),
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
      cigar_id: prefCid || undefined,
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

// ── Requested-retailer notifications ──────────────────────────────────
// When a user lands on an unknown retailer and clicks "Request this
// retailer", popup.js posts to /api/community/request-retailer with their
// observer_id. The operator later onboards the retailer (adds it to
// RETAILERS, deploys). The next time the consumer's background worker
// polls /api/community/my-requests, the backend lazily marks the request
// fulfilled; this code detects the new transition and fires a
// chrome.notification.
//
// Why client-side dedupe: chrome.notifications has no "have I shown this
// already" history accessible to extensions. We keep the set of hostnames
// we've notified about in chrome.storage.local and only fire for fresh
// transitions.
//
// Polling cadence: once on service-worker startup, then every 6h via a
// chrome.alarms timer. Cheap GET, no auth.

const NOTIFIED_KEY = "notifiedFulfilledHosts";
const REQUEST_CHECK_ALARM = "checkRetailerRequests";

async function getNotifiedHosts() {
  try {
    const out = await chrome.storage.local.get(NOTIFIED_KEY);
    return new Set(out[NOTIFIED_KEY] || []);
  } catch (_) {
    return new Set();
  }
}

async function setNotifiedHosts(set) {
  try {
    await chrome.storage.local.set({ [NOTIFIED_KEY]: Array.from(set) });
  } catch (_) {}
}

async function checkRequestedRetailers() {
  // Skip if the user is opted out — they may not want any extension chatter.
  if (!(await hasConsented())) return;
  let observerId;
  try { observerId = await getObserverId(); } catch (_) { return; }
  if (!observerId) return;

  let data;
  try {
    data = await publicFetch("/api/community/my-requests", {
      query: { observer_id: observerId },
    });
  } catch (_) {
    return;
  }
  if (!data || !Array.isArray(data.requests)) return;

  const notified = await getNotifiedHosts();
  let dirty = false;
  for (const req of data.requests) {
    if (req.status !== "fulfilled" || !req.hostname) continue;
    if (notified.has(req.hostname)) continue;
    notified.add(req.hostname);
    dirty = true;
    try {
      // iconUrl is required by chrome.notifications. Until we ship a real
      // icon128.png with the extension, the create() call may fail at the
      // OS level (user just doesn't see the toast). The hostname is still
      // added to the notified set so we don't re-attempt every poll, and
      // the registry refresh below still fires — the next time the user
      // browses the retailer, the popup will surface comparison data.
      await chrome.notifications.create(`retailer-live-${req.hostname}`, {
        type: "basic",
        iconUrl: chrome.runtime.getURL("icon128.png"),
        title: "Cigar Price Scout",
        message: `${req.hostname} is now tracked! Browse it to see comparison prices.`,
        priority: 1,
      });
    } catch (_) {
      // Notifications disabled at the OS level, or icon missing. Soft-fail.
    }
    // Also refresh the registry cache so the badge updates on next visit.
    try { await getRetailerRegistry({ forceRefresh: true }); } catch (_) {}
  }
  if (dirty) await setNotifiedHosts(notified);
}

chrome.runtime.onStartup.addListener(() => {
  checkRequestedRetailers().catch(() => {});
});

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === "update" || reason === "install") {
    checkRequestedRetailers().catch(() => {});
  }
  try {
    chrome.alarms.create(REQUEST_CHECK_ALARM, { periodInMinutes: 60 * 6 });
  } catch (_) {}
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === REQUEST_CHECK_ALARM) {
    checkRequestedRetailers().catch(() => {});
  }
});

chrome.notifications.onClicked.addListener((notifId) => {
  const prefix = "retailer-live-";
  if (notifId.startsWith(prefix)) {
    const host = notifId.slice(prefix.length);
    chrome.tabs.create({ url: `https://${host}` });
    chrome.notifications.clear(notifId);
  }
});

// ── Message bridge: popup asks for cached status ──────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return false;
  if (msg.type === "getStatusForTab") {
    (async () => {
      let payload = {
        tab: null,
        response: { state: "error", error: "Could not load tab status." },
        scraped: null,
      };
      try {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        const tab = tabs[0];
        if (!tab) {
          payload = { tab: null, response: null, scraped: null };
        } else {
          const cached = STATUS_CACHE.get(tab.url);
          if (cached && (Date.now() - cached.fetchedAt) < STATUS_TTL_MS) {
            payload = { tab, response: cached.response, scraped: cached.scraped };
          } else {
            const response = await refreshForTab(tab);
            const fresh = STATUS_CACHE.get(tab.url);
            payload = {
              tab,
              response,
              scraped: fresh ? fresh.scraped : null,
            };
          }
        }
      } catch (e) {
        payload = {
          tab: null,
          response: { state: "error", error: String(e) },
          scraped: null,
        };
      }
      try {
        sendResponse(payload);
      } catch (_) {}
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
