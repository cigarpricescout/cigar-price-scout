// Service worker. On every tab navigation, look up the URL's status from the
// backend and update the action badge so the user can see at-a-glance whether
// a CID has been proposed (popup is just confirmation).
//
// Badge states:
//   "?"   candidate (proposed CID, awaiting approval)
//   "OK"  already matched/published (in live retailer CSV)
//   "..." seen in extension staging (pending / superseded)
//   "+"   no scraper for this hostname (offer to queue)
//   ""    unknown URL (not a retailer) or admin key missing

import { apiFetch, getAdminKey, scrapeActiveTab, postObservation } from "./config.js";

const CACHE = new Map(); // url -> { fetchedAt, response }
const CACHE_TTL_MS = 5 * 60 * 1000;

// Master vocabulary cache (one-hour TTL). Refetched lazily on popup open.
let VOCAB = null;
let VOCAB_FETCHED_AT = 0;
const VOCAB_TTL_MS = 60 * 60 * 1000;

// Per-URL passive-observation dedupe. Without this, every status refresh
// (popup open, tab activation, tab update) would re-post the same reading.
const OBSERVE_DEDUPE = new Map(); // url -> last posted timestamp
const OBSERVE_DEDUPE_MS = 60 * 60 * 1000; // one fresh observation per URL per hour

async function ensureVocab(force = false) {
  if (!force && VOCAB && (Date.now() - VOCAB_FETCHED_AT) < VOCAB_TTL_MS) {
    return VOCAB;
  }
  try {
    VOCAB = await apiFetch("/api/admin/master-vocab");
    VOCAB_FETCHED_AT = Date.now();
  } catch (e) {
    if (e.code === "NO_ADMIN_KEY") return null;
    // Keep any stale value if we have one.
  }
  return VOCAB;
}

function isInspectableUrl(url) {
  if (!url) return false;
  return /^https?:\/\//i.test(url) && !/^https?:\/\/(localhost|127\.|0\.0\.0\.0)/i.test(url);
}

function badgeFor(state) {
  switch (state) {
    case "matched":     return { text: "OK", color: "#2e7d32" };
    case "seen":        return { text: "...", color: "#888888" };
    case "candidate":   return { text: "?",  color: "#1565c0" };
    case "no_scraper":  return { text: "+",  color: "#e65100" };
    default:            return { text: "",   color: "#000000" };
  }
}

async function setBadgeForTab(tabId, state) {
  const { text, color } = badgeFor(state);
  try {
    await chrome.action.setBadgeText({ tabId, text });
    if (text) await chrome.action.setBadgeBackgroundColor({ tabId, color });
  } catch (_) {}
}

async function refreshForTab(tab) {
  if (!tab || !isInspectableUrl(tab.url)) {
    if (tab) await setBadgeForTab(tab.id, null);
    return null;
  }
  const adminKey = await getAdminKey();
  if (!adminKey) {
    await setBadgeForTab(tab.id, null);
    return null;
  }

  const cached = CACHE.get(tab.url);
  if (cached && (Date.now() - cached.fetchedAt) < CACHE_TTL_MS) {
    await setBadgeForTab(tab.id, cached.response.state);
    return cached.response;
  }

  let scraped = { title: "" };
  try {
    scraped = await scrapeActiveTab(tab.id);
  } catch (_) {}

  let response;
  try {
    response = await apiFetch("/api/admin/url-status", {
      query: { url: tab.url, title: scraped.title || "" },
    });
  } catch (e) {
    if (e.code === "NO_ADMIN_KEY") {
      await setBadgeForTab(tab.id, null);
      return null;
    }
    response = { state: "error", error: e.message || String(e) };
  }

  // Stash the scraped title onto the response for the popup.
  response._scraped = scraped;
  CACHE.set(tab.url, { fetchedAt: Date.now(), response });
  await setBadgeForTab(tab.id, response.state);

  // Passive observation: any retailer page we land on, write a row to
  // observed_prices so the operator extension is the first contributor
  // to the community data pipeline. Skipped for no_scraper/unknown URLs
  // and for repeat visits inside the dedupe window.
  if (
    scraped && (scraped.price != null || scraped.title) &&
    response.state && response.state !== "no_scraper" && response.state !== "error" &&
    response.retailer_key
  ) {
    const last = OBSERVE_DEDUPE.get(tab.url) || 0;
    if (Date.now() - last > OBSERVE_DEDUPE_MS) {
      OBSERVE_DEDUPE.set(tab.url, Date.now());
      // Fire-and-forget; never block the popup on this.
      postObservation({
        url: tab.url,
        scraped_title: scraped.title || scraped.jsonldName || null,
        price: scraped.price ?? null,
        currency: scraped.currency || "USD",
        in_stock: scraped.inStock,
        quantity_type: scraped.quantityType || "unknown",
        box_qty: scraped.boxQty || null,
        jsonld: scraped.jsonldRaw || null,
        observer_source: "operator",
      }).catch(() => {});
    }
  }

  return response;
}

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

// Allow the popup to ask for the latest status (forces a re-fetch when needed).
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "getStatusForTab") {
    (async () => {
      const tab = msg.tabId
        ? await chrome.tabs.get(msg.tabId).catch(() => null)
        : (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
      if (!tab) return sendResponse({ error: "no active tab" });
      if (msg.forceRefresh) CACHE.delete(tab.url);
      const [resp, vocab] = await Promise.all([
        refreshForTab(tab),
        ensureVocab(),
      ]);
      sendResponse({
        tab: { id: tab.id, url: tab.url, title: tab.title },
        response: resp,
        vocab,
      });
    })();
    return true; // async response
  }
  if (msg && msg.type === "refreshVocab") {
    ensureVocab(true).then(v => sendResponse({ vocab: v })).catch(() => sendResponse({ vocab: null }));
    return true;
  }
  if (msg && msg.type === "invalidateCache") {
    if (msg.url) CACHE.delete(msg.url);
    sendResponse({ ok: true });
    return false;
  }
});
