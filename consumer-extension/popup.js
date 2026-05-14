import {
  publicFetch,
  hasConsented,
  getObserverId,
  getZip,
} from "./config.js";

const root = document.getElementById("root");

// Map brand+line → /cigars/{brand-slug}/{line-slug} URL on
// cigarpricescout.com. Mirrors the server's normalize_line_slug() and
// brand slugifier so the URL hits the SEO landing page (HTML)
// rather than the /compare JSON endpoint, which would look like a
// 404 to a regular user.
//
// Keep this in sync with normalize_line_slug() in app/main.py — the
// server adds new special-cases as catalog edge cases come up.
const LINE_SLUG_SPECIAL_CASES = {
  "opusx":   "opus-x",
  "opus x": "opus-x",
};
function slugify(s) {
  return String(s || "")
    .toLowerCase()
    .trim()
    .replace(/&/g, "and")
    .replace(/\//g, "-")
    .replace(/\s+/g, "-");
}
function buildCigarLandingUrl(brand, line) {
  if (!brand || !line) return "https://cigarpricescout.com";
  const lineLower = String(line).toLowerCase().trim();
  const lineSlug = LINE_SLUG_SPECIAL_CASES[lineLower] || slugify(line);
  const brandSlug = slugify(brand);
  if (!brandSlug || !lineSlug) return "https://cigarpricescout.com";
  return `https://cigarpricescout.com/cigars/${brandSlug}/${lineSlug}`;
}

// ── Bootstrap ──────────────────────────────────────────────────────────

(async () => {
  // Hard gate: if the user hasn't consented yet, send them to the
  // consent screen instead of showing the comparison UI.
  if (!(await hasConsented())) {
    return renderNeedConsent();
  }

  let payload;
  try {
    payload = await new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "getStatusForTab" }, (resp) => {
        resolve(resp || { tab: null, response: null, scraped: null });
      });
    });
  } catch (e) {
    return renderError(String(e));
  }

  const { tab, response, scraped } = payload;
  if (!tab || !tab.url) return renderEmpty("Open a cigar retailer page to see prices.");
  if (!response) return renderError("Couldn't reach the price database. Check your connection.");

  switch (response.state) {
    case "matched":     return renderMatched(tab, response, scraped);
    case "candidate":   return renderCandidate(tab, response, scraped);
    case "seen":        return renderSeen(tab, response, scraped);
    case "no_scraper":  return renderNoScraper(tab, response);
    case "non_product": return renderEmpty("Browse a cigar product page to see comparisons.");
    case "error":       return renderError(response.error || "Unknown error");
    default:            return renderError(`Unexpected state: ${response.state}`);
  }
})();

// ── Renderers ──────────────────────────────────────────────────────────

function renderHeader(tab, response, label = "") {
  return `
    <div class="header">
      <div class="brand">
        <span>Cigar Price Scout</span>
        <span class="meta">${escapeHtml(response.retailer_key || tab.hostname || "")}</span>
      </div>
    </div>
  `;
}

function renderEmpty(message) {
  root.innerHTML = `
    <div class="empty-state">
      <div class="big">🚬</div>
      <div>${escapeHtml(message)}</div>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
    </div>
  `;
  wireFooter();
}

function renderError(message) {
  root.innerHTML = `
    <div class="banner error">${escapeHtml(message)}</div>
    <div class="empty-state">
      <div>Something went wrong. Try reloading the page.</div>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
    </div>
  `;
  wireFooter();
}

function renderNeedConsent() {
  root.innerHTML = `
    <div class="banner info">Welcome — set up to continue.</div>
    <div class="empty-state">
      <div style="margin-bottom: 12px;">
        Cigar Price Scout needs a one-time consent before it can show
        prices.
      </div>
      <button class="approve" id="open-consent" style="padding:8px 16px;font-size:13px;border:none;border-radius:4px;background:#1f2937;color:white;cursor:pointer;">
        Get started
      </button>
    </div>
  `;
  document.getElementById("open-consent").addEventListener("click", () => {
    chrome.tabs.create({ url: chrome.runtime.getURL("consent.html") });
    window.close();
  });
}

// ── State: matched (live comparison data available) ───────────────────

function renderMatched(tab, response, scraped) {
  const comparison = response.comparison;
  const scrapedBoxQty = (scraped && scraped.boxQty) || null;
  const scrapedQtyType = (scraped && scraped.quantityType) || "unknown";

  // Special-case box-only restriction: if the user is looking at a
  // pack/single variant, the comparison data is for the BOX CID and
  // doesn't match what they're seeing. Show a soft redirect.
  if (scrapedQtyType !== "box" && scrapedQtyType !== "unknown") {
    // Action-first phrasing: lead with what the user should do (click
    // the box variant on the retailer's page), then explain context.
    // The previous wording ("We track box prices only" + "switch to the
    // box-of-25 variant") read as a system limitation; users skipped it.
    const boxQtyHint = comparison?.box_qty
      ? `'Box of ${comparison.box_qty}'`
      : "the Box";
    root.innerHTML = `
      ${renderHeader(tab, response)}
      <div class="banner info">👉 Select ${escapeHtml(boxQtyHint)} on this page to see prices</div>
      <div class="section">
        <div class="cigar-name">${escapeHtml(comparison?.cigar_name || "This cigar")}</div>
        <div class="cigar-meta">
          You're currently viewing the
          ${escapeHtml(quantityLabel(scrapedQtyType, scrapedBoxQty))} variant.
          We compare box prices across retailers — click the box option on
          the page, then reopen this popup.
        </div>
      </div>
      <div class="actions">
        <button id="view-compare">View box comparison</button>
        <button id="close">Close</button>
      </div>
      <div class="footer">
        <a href="#" id="open-options">Settings</a>
        <a href="https://cigarpricescout.com" target="_blank">cigarpricescout.com</a>
      </div>
    `;
    document.getElementById("view-compare").addEventListener("click", () => {
      chrome.tabs.create({
        url: buildCigarLandingUrl(comparison?.brand, comparison?.line),
      });
      window.close();
    });
    document.getElementById("close").addEventListener("click", () => window.close());
    wireFooter();
    return;
  }

  if (!comparison || !comparison.results || comparison.results.length === 0) {
    root.innerHTML = `
      ${renderHeader(tab, response)}
      <div class="banner matched">✓ We track this cigar</div>
      <div class="section">
        <div class="empty-state" style="padding: 16px 0;">
          ${escapeHtml(comparison?.reason || "Not enough retailers yet to compare.")}
        </div>
      </div>
      <div class="footer">
        <a href="#" id="open-options">Settings</a>
        <a href="https://cigarpricescout.com" target="_blank">cigarpricescout.com</a>
      </div>
    `;
    wireFooter();
    return;
  }

  const cheapest = comparison.results[0];
  const cheapestDeliv = cheapest.delivered_cents;
  const currentPageRetailer = response.retailer_key;
  const currentRow = comparison.results.find(r => r.retailer_key === currentPageRetailer);
  const savingsCents = (currentRow && currentRow.delivered_cents > cheapestDeliv)
    ? currentRow.delivered_cents - cheapestDeliv
    : 0;

  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner matched">✓ Cheapest: ${formatMoney(cheapestDeliv)} at ${escapeHtml(cheapest.retailer_name)}</div>
    <div class="section">
      <div class="cigar-name">${escapeHtml(comparison.cigar_name || "")}</div>
      <div class="cigar-meta">
        ${escapeHtml(comparison.wrapper || "")} · ${escapeHtml(comparison.vitola || "")} · ${escapeHtml(comparison.size || "")} · Box of ${comparison.box_qty || "?"}
      </div>
      <div class="results">
        ${comparison.results.map((r, i) => renderResultRow(r, i, cheapestDeliv)).join("")}
      </div>
      ${savingsCents > 0 ? `
        <div class="savings">
          You'd save ${formatMoney(savingsCents)} by buying from ${escapeHtml(cheapest.retailer_name)}.
        </div>
      ` : ""}
    </div>
    <div class="actions">
      <button id="view-all">See all ${comparison.total_retailers || comparison.results.length} retailers</button>
      <button id="close">Close</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
      <a href="https://cigarpricescout.com" target="_blank">cigarpricescout.com</a>
    </div>
  `;
  document.getElementById("view-all").addEventListener("click", () => {
    chrome.tabs.create({
      url: buildCigarLandingUrl(comparison.brand, comparison.line),
    });
    window.close();
  });
  document.getElementById("close").addEventListener("click", () => window.close());
  wireFooter();
}

function renderResultRow(r, idx, cheapestDeliv) {
  const cheapestClass = (r.delivered_cents === cheapestDeliv) ? "cheapest" : "";
  const oosClass = r.in_stock ? "" : "out-of-stock";
  const authBadge = r.authorized ? `<span class="auth-badge">authorized</span>` : "";
  const oosBadge = r.in_stock ? "" : `<span class="stock-badge">out of stock</span>`;
  const shipTax = (r.shipping_cents + r.tax_cents) > 0
    ? `<span class="ship-tax">+${formatMoney(r.shipping_cents + r.tax_cents)} ship/tax</span>`
    : "";
  // Anti-bot retailers don't have live scrapers — their prices come from
  // other shoppers' observations. Show an absolute "Last observed" date
  // so users know how fresh the data is. ("Some retailers don't change
  // prices often" — staleness is informational, not a hard cutoff.)
  const isObserved = r.price_source === "observed";
  const observedStamp = isObserved && r.observed_at
    ? `<span class="observed-badge" title="Crowd-sourced from shoppers">📊 Last seen ${formatDateAbs(r.observed_at)}</span>`
    : "";
  return `
    <a href="${escapeAttr(r.url || '#')}" target="_blank" rel="noopener" class="result-row ${cheapestClass} ${oosClass}">
      <div class="result-rank">${idx + 1}</div>
      <div class="result-name">
        ${escapeHtml(r.retailer_name)}
        ${authBadge}${oosBadge}
        ${observedStamp}
      </div>
      <div class="result-price">
        ${formatMoney(r.delivered_cents)}
        ${shipTax}
      </div>
    </a>
  `;
}

// ── State: candidate (URL unknown — propose metadata) ─────────────────

function renderCandidate(tab, response, scraped) {
  const scrapedQty = (scraped && scraped.quantityType) || "unknown";
  const isBox = scrapedQty === "box" || scrapedQty === "unknown";

  if (!isBox) {
    // Action-first phrasing for the candidate (unmatched) state. The
    // user is on a page we don't have a CID for; we need them to first
    // narrow to the box variant before they can contribute metadata.
    root.innerHTML = `
      ${renderHeader(tab, response)}
      <div class="banner info">👉 Select the Box option on this page to continue</div>
      <div class="empty-state" style="padding: 20px 14px;">
        You're currently viewing the
        ${escapeHtml(quantityLabel(scrapedQty, scraped?.boxQty))} variant.
        We compare box prices only — click the box option on the page,
        then reopen this popup to add your listing.
      </div>
      <div class="footer">
        <a href="#" id="open-options">Settings</a>
      </div>
    `;
    wireFooter();
    return;
  }

  // Pre-fill all fields from the scraper. User can edit any of them.
  const guesses = guessFromScrape(tab.url, scraped);
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner candidate">? Help us identify this cigar</div>
    <div class="section">
      <div class="scraper-chip">
        Detected on page: <b>${escapeHtml(scraped?.title || scraped?.jsonldName || tab.title || "(no title)")}</b>
      </div>
      <div class="fields" id="cid-form">
        <div class="field">
          <label for="f-brand">Brand</label>
          <input type="text" id="f-brand" value="${escapeAttr(guesses.brand)}" placeholder="e.g. Arturo Fuente" />
        </div>
        <div class="field">
          <label for="f-line">Line</label>
          <input type="text" id="f-line" value="${escapeAttr(guesses.line)}" placeholder="e.g. Hemingway" />
        </div>
        <div class="field">
          <label for="f-vitola">Vitola</label>
          <input type="text" id="f-vitola" value="${escapeAttr(guesses.vitola)}" placeholder="e.g. Signature" />
        </div>
        <div class="field">
          <label for="f-wrapper">Wrapper <span class="hint-inline">(optional)</span></label>
          <select id="f-wrapper">
            <option value="">Not sure</option>
            <option value="Natural / Connecticut" ${guesses.wrapper_bucket === "Natural / Connecticut" ? "selected" : ""}>Natural / Connecticut</option>
            <option value="Habano" ${guesses.wrapper_bucket === "Habano" ? "selected" : ""}>Habano</option>
            <option value="Sun Grown" ${guesses.wrapper_bucket === "Sun Grown" ? "selected" : ""}>Sun Grown</option>
            <option value="Maduro" ${guesses.wrapper_bucket === "Maduro" ? "selected" : ""}>Maduro</option>
          </select>
        </div>
        <div class="field-row">
          <div class="field">
            <label for="f-box_qty">Box quantity</label>
            <input type="number" id="f-box_qty" value="${escapeAttr(guesses.box_qty || "")}" placeholder="25" min="1" max="100" />
          </div>
          <div class="field">
            <label for="f-price">Price (USD)</label>
            <input type="number" id="f-price" value="${escapeAttr(guesses.price || "")}" placeholder="340.00" step="0.01" min="0" />
          </div>
        </div>
      </div>
    </div>
    <div class="actions">
      <button class="approve" id="submit">Submit</button>
      <button id="close">Cancel</button>
    </div>
    <div class="footer">
      Operator reviews submissions before they go live.
      &nbsp;<a href="#" id="open-options">Settings</a>
    </div>
  `;
  document.getElementById("submit").addEventListener("click", () => submitProposal(tab, response, scraped));
  document.getElementById("close").addEventListener("click", () => window.close());
  wireFooter();
}

async function submitProposal(tab, response, scraped) {
  const btn = document.getElementById("submit");
  btn.disabled = true;
  btn.textContent = "Submitting…";

  const get = (id) => (document.getElementById(id).value || "").trim();
  const brand = get("f-brand");
  const line = get("f-line");
  const vitola = get("f-vitola");
  const wrapperBucket = get("f-wrapper");
  const boxQtyRaw = get("f-box_qty");
  const priceRaw = get("f-price");

  if (!brand || !line || !vitola || !boxQtyRaw) {
    btn.disabled = false;
    btn.textContent = "Submit";
    toast("Brand, line, vitola, and box quantity are required.");
    return;
  }

  const box_qty = parseInt(boxQtyRaw, 10);
  const confirmed_price = priceRaw ? parseFloat(priceRaw) : null;

  try {
    const observerId = await getObserverId();
    const proposeRes = await publicFetch("/api/community/propose-metadata", {
      method: "POST",
      body: {
        observer_id: observerId,
        observer_source: "consumer",
        url: tab.url,
        brand,
        line,
        vitola,
        // Friendly consumer-facing bucket name (e.g. "Maduro"). Empty
        // string means "Not sure" — operator handles wrapper-code lookup
        // during review by matching brand+line+vitola+box_qty in the
        // master catalog.
        wrapper: wrapperBucket || null,
        box_qty,
        confirmed_price,
        scraped_title: scraped?.title || scraped?.jsonldName || null,
      },
    });
    chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url });

    // Gap 2: hybrid instant feedback. If the server auto-matched the
    // submission to a CID with HIGH confidence AND a multi-retailer
    // comparison is available, re-render the popup with the comparison
    // immediately. The proposal is still 'pending' on the operator's
    // queue, but the consumer sees value right away. A subtle banner
    // makes the "provisional / awaiting operator confirmation" status
    // unambiguous so users don't treat an incorrect auto-match as final.
    if (proposeRes && proposeRes.comparison
        && proposeRes.comparison.results
        && proposeRes.comparison.results.length > 0) {
      renderProvisionalComparison(tab, response, scraped, proposeRes);
      return;
    }

    // No HIGH-confidence auto-match → render a thank-you screen with a
    // "Search prices on cigarpricescout.com" CTA using the user's own
    // form inputs. Previously this branch just toasted and closed,
    // which felt like a dead-end after the user spent 30 seconds
    // filling out the form.
    renderSubmittedWithSearch(tab, response, scraped, {
      brand,
      line,
      vitola,
      box_qty,
      wrapper: wrapperBucket || null,
    });
    return;
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Submit";
    toast(`Submit failed: ${e.message || e}`);
  }
}

// Post-submit thank-you with a homepage CTA. We deliberately don't deep-link
// to /compare — that endpoint returns JSON, not HTML, so any direct visit
// looks like a 404 to a real user. The homepage's search is the right
// surface for poking around while the operator reviews the submission.
function renderSubmittedWithSearch(tab, response, scraped, submittedMeta) {
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner matched">✓ Thanks for contributing!</div>
    <div class="section">
      <div class="cigar-meta" style="line-height:1.45">
        We're reviewing your submission and will map this URL to a
        comparison shortly. In the meantime, browse cigarpricescout.com
        — this cigar may already be in our catalog.
      </div>
    </div>
    <div class="actions">
      <button id="open-scout" class="primary">Visit cigarpricescout.com</button>
      <button id="close">Close</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
    </div>
  `;
  document.getElementById("open-scout").addEventListener("click", () => {
    chrome.tabs.create({ url: "https://cigarpricescout.com" });
    window.close();
  });
  document.getElementById("close").addEventListener("click", () => window.close());
  wireFooter();
}

// ── Gap 2: provisional comparison after a high-confidence submission ──

function renderProvisionalComparison(tab, response, scraped, proposeRes) {
  // The /api/community/propose-metadata response carries the same
  // comparison shape as /api/public/url-status's matched state, so the
  // comparison rendering below intentionally mirrors renderMatched —
  // identical sorting, identical row template, identical savings math.
  // The only differences are (a) the banner at the top, and (b) the
  // info note that the comparison is provisional.
  const comparison = proposeRes.comparison;
  const cheapest = comparison.results[0];
  const cheapestDeliv = cheapest.delivered_cents;
  const currentPageRetailer = response.retailer_key;
  const currentRow = comparison.results.find(r => r.retailer_key === currentPageRetailer);
  const savingsCents = (currentRow && currentRow.delivered_cents > cheapestDeliv)
    ? currentRow.delivered_cents - cheapestDeliv
    : 0;
  const conf = (proposeRes.match && proposeRes.match.confidence) || "HIGH";

  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner matched">✓ Cheapest: ${formatMoney(cheapestDeliv)} at ${escapeHtml(cheapest.retailer_name)}</div>
    <div class="provisional-note">
      <strong>Thanks for contributing.</strong> We matched your submission
      (${escapeHtml(conf)} confidence) so you can see the comparison now,
      but it's <em>provisional</em> until our reviewer confirms the cigar
      identity. Your contribution is queued.
    </div>
    <div class="section">
      <div class="cigar-name">${escapeHtml(comparison.cigar_name || "")}</div>
      <div class="cigar-meta">
        ${escapeHtml(comparison.wrapper || "")} · ${escapeHtml(comparison.vitola || "")} · ${escapeHtml(comparison.size || "")} · Box of ${comparison.box_qty || "?"}
      </div>
      <div class="results">
        ${comparison.results.map((r, i) => renderResultRow(r, i, cheapestDeliv)).join("")}
      </div>
      ${savingsCents > 0 ? `
        <div class="savings">
          You'd save ${formatMoney(savingsCents)} by buying from ${escapeHtml(cheapest.retailer_name)}.
        </div>
      ` : ""}
    </div>
    <div class="actions">
      <button id="view-all">See all ${comparison.total_retailers || comparison.results.length} retailers</button>
      <button id="close">Close</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
      <a href="https://cigarpricescout.com" target="_blank">cigarpricescout.com</a>
    </div>
  `;
  document.getElementById("view-all").addEventListener("click", () => {
    chrome.tabs.create({
      url: buildCigarLandingUrl(comparison.brand, comparison.line),
    });
    window.close();
  });
  document.getElementById("close").addEventListener("click", () => window.close());
  wireFooter();
}

// ── State: seen (someone already proposed or operator already touched) ─

function renderSeen(tab, response, scraped) {
  // Differentiate seen sub-states so the copy reflects what actually
  // happened. Pending proposals stay "Under review"; resolved ones
  // (operator already approved, awaiting publish) get a clearer
  // "Approved — prices coming soon" so the user understands their
  // contribution did land. Anything not approved-or-pending falls back
  // to the raw status label for transparency.
  const ss = (response.seen_status || "").toLowerCase();
  // "extension_*" rows live in extension_staged_approvals — the operator
  // already approved them and they're waiting on the publisher to drain
  // to CSV. Treat them as approved so the user gets honest feedback.
  // "community_pending" is the only true "consumer suggested, no review
  // yet" state.
  const isOperatorApproved =
    ss.startsWith("extension_") ||
    ss === "community_approved" ||
    ss.includes("published");
  const isRejected = ss.includes("rejected");
  const isCommunityPending = ss === "community_pending";
  let bannerText, bodyText;
  if (isOperatorApproved) {
    bannerText = "✓ Approved — prices coming soon";
    bodyText = "We've matched this cigar to our catalog. Prices will appear here within a few minutes once published.";
  } else if (isRejected) {
    bannerText = "Submission was rejected";
    bodyText = "We couldn't match this listing to our catalog.";
  } else if (isCommunityPending) {
    bannerText = "Under review";
    bodyText = "Someone already suggested info for this cigar.";
  } else {
    bannerText = `Under review · ${escapeHtml(ss.replace(/_/g, " "))}`;
    bodyText = "Someone already suggested info for this cigar.";
  }
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner seen">${bannerText}</div>
    <div class="empty-state" style="padding: 16px 14px 10px;">
      ${bodyText} In the meantime, browse cigarpricescout.com to search
      for similar cigars.
    </div>
    <div class="actions">
      <button id="open-scout" class="primary">Visit cigarpricescout.com</button>
      <button id="close">Close</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
    </div>
  `;
  document.getElementById("close").addEventListener("click", () => window.close());
  document.getElementById("open-scout").addEventListener("click", () => {
    chrome.tabs.create({ url: "https://cigarpricescout.com" });
    window.close();
  });
  wireFooter();
}

// ── State: no_scraper (unknown retailer) ──────────────────────────────

function renderNoScraper(tab, response) {
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner no_scraper">New retailer</div>
    <div class="empty-state" style="padding: 20px 14px;">
      We don't track <b>${escapeHtml(response.hostname || tab.hostname || "this site")}</b> yet.
      Request it and we'll notify you here when it goes live.
      No email needed — your extension does the notifying.
    </div>
    <div class="actions">
      <button class="approve" id="suggest">Request this retailer</button>
      <button id="close">Close</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
    </div>
  `;
  document.getElementById("suggest").addEventListener("click", async () => {
    const btn = document.getElementById("suggest");
    btn.disabled = true;
    btn.textContent = "Requesting…";
    try {
      await publicFetch("/api/community/request-retailer", {
        method: "POST",
        body: {
          observer_id: await getObserverId(),
          url: tab.url,
        },
      });
      toast("Thanks — we'll notify you when it goes live.");
      setTimeout(() => window.close(), 1200);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Request this retailer";
      toast(`Failed: ${e.message || e}`);
    }
  });
  document.getElementById("close").addEventListener("click", () => window.close());
  wireFooter();
}

// ── Form pre-fill heuristics ───────────────────────────────────────────

// Wrapper-bucket detection keywords. Order matters: more specific phrases
// must come BEFORE broader ones because the first match wins. Mirrors the
// server-side list in app/wrapper_buckets.py SCRAPE_KEYWORDS.
const WRAPPER_BUCKET_KEYWORDS = [
  ["sun grown",          "Sun Grown"],
  ["sungrown",           "Sun Grown"],
  ["ecuadorian sumatra", "Sun Grown"],
  ["maduro",             "Maduro"],
  ["oscuro",             "Maduro"],
  ["san andres",         "Maduro"],
  ["san andr",           "Maduro"],
  ["broadleaf",          "Maduro"],
  ["habano",             "Habano"],
  ["corojo",             "Habano"],
  ["connecticut",        "Natural / Connecticut"],
  ["cameroon",           "Natural / Connecticut"],
  ["claro",              "Natural / Connecticut"],
  ["natural",            "Natural / Connecticut"],
];

function detectWrapperBucket(...texts) {
  const haystack = texts.filter(Boolean).join(" ").toLowerCase();
  if (!haystack) return "";
  for (const [phrase, bucket] of WRAPPER_BUCKET_KEYWORDS) {
    if (haystack.includes(phrase)) return bucket;
  }
  return "";
}

function guessFromScrape(rawUrl, scraped) {
  const out = { brand: "", line: "", vitola: "", wrapper_bucket: "", box_qty: "", price: "" };
  if (!scraped) return out;

  // Brand from JSON-LD if it's not the storefront name (heuristic: JSON-LD
  // brand sometimes equals the retailer, e.g. Bayside puts "Coco Cigars").
  if (scraped.jsonldBrand && scraped.jsonldBrand.length <= 60) {
    out.brand = scraped.jsonldBrand;
  }

  // Parse title — "Brand Line Vitola" is the common Shopify shape.
  const title = (scraped.title || scraped.jsonldName || "").trim();
  if (title) {
    // Strip "Natural" / "Maduro" / wrapper-ish trailing tokens we don't
    // need for identification.
    const tokens = title.split(/\s+/);
    if (!out.brand && tokens.length >= 1) {
      // Try Brand = first 2 tokens if they're capitalized.
      out.brand = tokens.slice(0, 2).join(" ");
    }
    if (tokens.length >= 3) {
      out.line = tokens.slice(2, 4).join(" ");
    }
    if (tokens.length >= 5) {
      out.vitola = tokens.slice(4).join(" ");
    }
  }

  // Wrapper bucket from page text + JSON-LD description. Saves the user
  // a click in the common case where the page mentions the wrapper word
  // directly; they can still correct it with the dropdown.
  out.wrapper_bucket = detectWrapperBucket(
    title,
    scraped.ogDescription,
    (scraped.jsonldRaw && scraped.jsonldRaw.description) || "",
  );

  if (scraped.boxQty) out.box_qty = String(scraped.boxQty);
  if (scraped.price)  out.price = scraped.price.toFixed(2);

  return out;
}

// ── Utility ────────────────────────────────────────────────────────────

function wireFooter() {
  const opt = document.getElementById("open-options");
  if (opt) opt.addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
    window.close();
  });
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast show";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.classList.remove("show"); }, 2400);
  setTimeout(() => { t.remove(); }, 3000);
}

function quantityLabel(qtyType, boxQty) {
  if (qtyType === "box") return `box of ${boxQty || "?"}`;
  if (qtyType === "pack5") return "5-pack";
  if (qtyType === "pack10") return "10-pack";
  if (qtyType === "pack20") return "20-pack";
  if (qtyType === "single") return "single";
  if (boxQty) return `${boxQty}-count`;
  return "unknown";
}

function formatMoney(cents) {
  if (cents == null) return "—";
  return "$" + (cents / 100).toFixed(2);
}

function formatDateAbs(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    // YYYY-MM-DD in user's locale tz. Chosen over relative ("3 days ago")
    // because some anti-bot retailers rarely change prices; an absolute
    // date lets the user judge freshness for themselves.
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  } catch (_) {
    return "";
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function escapeAttr(s) { return escapeHtml(s); }
