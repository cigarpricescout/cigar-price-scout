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

import { apiFetch, getAdminKey, scrapeActiveTab } from "./config.js";

const CACHE = new Map(); // url -> { fetchedAt, response }
const CACHE_TTL_MS = 5 * 60 * 1000;

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
      const resp = await refreshForTab(tab);
      sendResponse({ tab: { id: tab.id, url: tab.url, title: tab.title }, response: resp });
    })();
    return true; // async response
  }
  if (msg && msg.type === "invalidateCache") {
    if (msg.url) CACHE.delete(msg.url);
    sendResponse({ ok: true });
    return false;
  }
});
