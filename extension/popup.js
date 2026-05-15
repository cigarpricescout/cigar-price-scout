// Popup UI. Reads the cached url-status from the background worker, renders
// one of 5 states, and dispatches user actions (approve / skip / queue new
// retailer) to the backend.

import { apiFetch, getAdminKey } from "./config.js";

const root = document.getElementById("root");

const WRAPPER_CODES = [
  "MAD", "NAT", "CAM", "ECU", "HAB", "SUM", "BRZ", "MEX", "NIC", "HON",
  "DOM", "OSC", "CON", "CORO", "CRIO", "ROS", "SUN", "CAND", "OLOR",
];

// Friendly consumer-facing wrapper categories. Operator extension Gap 4
// uses the same 4 buckets the consumer extension uses, so when an
// operator approves a consumer-proposed URL the bucket round-trips
// cleanly without code translation. Must stay in sync with
// app/wrapper_buckets.py — the Python module is the source of truth.
const WRAPPER_BUCKETS = {
  "Natural / Connecticut": ["NAT", "CT", "CAM", "CL"],
  "Habano":                ["HAB", "CORO", "CON"],
  "Sun Grown":             ["SUN", "ECU", "NIC"],
  "Maduro":                ["MAD", "MEX", "MD", "DOM"],
};

// Default canonical code per bucket — used when the operator picks a
// bucket but neither candidate matching nor master lookup gives us a
// specific code (e.g. brand-new CID). The default is the most common
// code in each bucket, so a "best guess" is at least sensible.
const BUCKET_DEFAULT_CODE = {
  "Natural / Connecticut": "NAT",
  "Habano":                "HAB",
  "Sun Grown":             "SUN",
  "Maduro":                "MAD",
};

function bucketForCode(code) {
  if (!code) return "";
  const upper = code.toUpperCase();
  for (const [bucket, codes] of Object.entries(WRAPPER_BUCKETS)) {
    if (codes.includes(upper)) return bucket;
  }
  return "";  // outside the 4 buckets → "Specific code" override
}

// Master-vocabulary rows from the backend. Used to populate context-aware
// <datalist> dropdowns on the brand/line/vitola/size/box_qty fields.
let VOCAB_ROWS = [];

// When the operator picks a row from "Similar CIDs" or URL-based candidates,
// we lock approval to that exact `cigar_id` from master (POST `cid` only).
// Any edit to identity fields clears the lock so `cid_parts` + buildCidString
// apply again (new SKU path).
let lockedMasterCid = null;

// Latest `/cid-search` rows for the click handler on `#similar-cids`
// (replaced on each debounced refresh).
let lastSimilarResults = [];

// ── Bootstrapping ─────────────────────────────────────────────────────

(async function init() {
  try {
    const adminKey = await getAdminKey();
    if (!adminKey) {
      renderNoAdminKey();
      return;
    }

    let payload;
    try {
      // forceRefresh: the background-worker badge cache has a 5-min TTL,
      // so without this the popup can serve stale data — most painfully,
      // a community_proposal that landed in Postgres AFTER the badge
      // cache was populated (consumer submitted, then operator opens
      // popup within 5 min) would be invisible. Refresh on every popup
      // open trades ~300ms latency for always-fresh state.
      payload = await chrome.runtime.sendMessage({ type: "getStatusForTab", forceRefresh: true });
    } catch (e) {
      return renderError(`Background worker error: ${e.message || e}`);
    }
    if (!payload || payload.error) {
      return renderError(payload && payload.error || "No active tab.");
    }

    const { tab, response, vocab } = payload;
    if (!response) {
      return renderError("Could not reach the backend. Check your admin key / network.");
    }
    if (response.state === "error") {
      return renderError(response.error || "Unknown backend error.");
    }
    VOCAB_ROWS = (vocab && vocab.rows) || [];

    switch (response.state) {
      case "matched":    return renderMatched(tab, response);
      case "seen":       return renderSeen(tab, response);
      case "candidate":  return renderCandidate(tab, response);
      case "no_scraper": return renderNoScraper(tab, response);
      default:           return renderError(`Unexpected state: ${response.state}`);
    }
  } catch (e) {
    renderError(String((e && e.message) || e));
  }
})();

// ── Renderers ────────────────────────────────────────────────────────

function renderHeader(tab, response) {
  return `
    <div class="header">
      <div class="title">${escapeHtml(response.retailer_key || response.hostname || "—")}</div>
      <div class="meta">${escapeHtml(tab.url)}</div>
    </div>
  `;
}

function renderMatched(tab, response) {
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner matched">✓ Already published to ${escapeHtml(response.retailer_key)}</div>
    ${matchedCommunityBanner(response)}
    <div class="section">
      <div class="section-label">Matched CID</div>
      <div class="cid-display">${escapeHtml(response.matched_cid || "—")}</div>
    </div>
    ${renderScraped(response)}
    <div class="actions">
      ${response.community_proposal
        ? `<button class="approve" id="resolve-cp">Approve consumer submission</button>`
        : ""}
      <button class="secondary" id="re-review">Re-review</button>
      <button class="skip" id="close">Close</button>
    </div>
    <div class="footer"><a href="#" id="open-options">Settings</a></div>
  `;
  wireMatchedActions(tab, response);
  wireResolveCommunityProposal(tab, response);
}

function renderSeen(tab, response) {
  const label = (response.seen_status || "").replace("_", " ");
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner seen">Status: ${escapeHtml(label)}</div>
    ${matchedCommunityBanner(response)}
    <div class="section">
      <div class="section-label">Previously matched to</div>
      <div class="cid-display">${escapeHtml(response.matched_cid || "—")}</div>
    </div>
    ${renderScraped(response)}
    <div class="actions">
      ${response.community_proposal
        ? `<button class="approve" id="resolve-cp">Approve consumer submission</button>`
        : ""}
      <button class="secondary" id="re-review">Re-review</button>
      <button class="skip" id="close">Close</button>
    </div>
    <div class="footer"><a href="#" id="open-options">Settings</a></div>
  `;
  wireMatchedActions(tab, response);
  wireResolveCommunityProposal(tab, response);
}

// Variant of communityProposalBanner for the matched/seen states.
// Same visual look, but the copy + behavior differ: the URL is already
// mapped, so the operator's job here is just to acknowledge the
// consumer's submission and flip community_url_proposals.status to
// 'approved' (or 'rejected'). No form to fill in — they can do it
// in one click via the "Approve consumer submission" action button.
function matchedCommunityBanner(response) {
  const cp = response.community_proposal;
  if (!cp) return "";
  const age = humanizeAge(cp.created_at);
  const others = cp.total_pending > 1
    ? ` <span class="cp-more">+${cp.total_pending - 1} more</span>`
    : "";
  const productLine = [cp.proposed_brand, cp.proposed_line, cp.proposed_vitola]
    .filter(Boolean).join(" ").trim() || "(no product info)";
  const meta = [
    cp.proposed_size,
    cp.proposed_box_qty ? `Box ${cp.proposed_box_qty}` : "",
    cp.proposed_wrapper,
    typeof cp.confirmed_price === "number" ? `$${cp.confirmed_price.toFixed(2)}` : "",
  ].filter(Boolean).join(" • ");
  // Correction-flow variant: the consumer is reporting that the
  // existing CID/price is wrong. Surface what we were showing them
  // (current_cid, current_price) so the operator can make an
  // informed decision rather than just rubber-stamping.
  if (cp.is_correction) {
    const currentLine = cp.current_cid ? `<code>${escapeHtml(cp.current_cid)}</code>` : "(no CID on record)";
    const currentPrice = typeof cp.current_price === "number" ? `$${cp.current_price.toFixed(2)}` : "—";
    const proposedPrice = typeof cp.confirmed_price === "number" ? `$${cp.confirmed_price.toFixed(2)}` : "—";
    return `
      <div class="community-proposal correction">
        <div class="cp-header">
          <span class="cp-badge cp-correction-badge">Consumer disagrees${others}</span>
          ${age ? `<span class="cp-age">${escapeHtml(age)}</span>` : ""}
        </div>
        <div class="cp-diff">
          <div class="cp-diff-row">
            <div class="cp-diff-label">Currently showing</div>
            <div class="cp-diff-current">${currentLine}<br><span class="cp-price">${currentPrice}</span></div>
          </div>
          <div class="cp-diff-row">
            <div class="cp-diff-label">Consumer says</div>
            <div class="cp-diff-proposed">${escapeHtml(productLine)}<br><span class="cp-price">${proposedPrice}</span>${meta ? ` <span class="cp-meta-inline">${escapeHtml(meta)}</span>` : ""}</div>
          </div>
        </div>
        <div class="cp-hint">
          Sale prices are reported WITHOUT coupon codes. If the new
          price is far below current, double-check the box quantity
          before approving.
        </div>
      </div>
    `;
  }
  return `
    <div class="community-proposal">
      <div class="cp-header">
        <span class="cp-badge">Consumer also submitted${others}</span>
        ${age ? `<span class="cp-age">${escapeHtml(age)}</span>` : ""}
      </div>
      <div class="cp-product">${escapeHtml(productLine)}</div>
      ${meta ? `<div class="cp-meta">${escapeHtml(meta)}</div>` : ""}
      <div class="cp-hint">
        URL is already mapped — just acknowledge their submission to
        close the loop. They'll see the comparison card on next visit.
      </div>
    </div>
  `;
}

function wireResolveCommunityProposal(tab, response) {
  const btn = document.getElementById("resolve-cp");
  if (!btn) return;
  const cp = response.community_proposal;
  if (!cp || !cp.proposal_id) return;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Approving…";
    try {
      await apiFetch("/api/admin/resolve-community-proposal", {
        method: "POST",
        body: {
          proposal_id: cp.proposal_id,
          action: "approve_existing",
          cid: response.matched_cid,
        },
      });
      // Bust the cached url-status so a re-open of this URL doesn't
      // still show the banner. The next /api/admin/url-status call
      // will see status='approved' and omit community_proposal from
      // the response.
      chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url }).catch(() => {});
      toast("Consumer submission approved");
      setTimeout(() => window.close(), 600);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Approve consumer submission";
      toast(`Failed: ${e.message || e}`, "error");
    }
  });
}

function renderNoScraper(tab, response) {
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner no_scraper">
      No scraper for <strong>${escapeHtml(response.hostname || "this host")}</strong>.
      Add it to the queue so it can be onboarded before approvals.
    </div>
    <div class="section">
      <div class="section-label">URL</div>
      <div class="cid-display">${escapeHtml(tab.url)}</div>
    </div>
    <div class="actions">
      <button class="approve" id="queue-retailer">Add to new-retailer queue</button>
      <button class="skip" id="skip">Skip this URL</button>
    </div>
    <div class="footer"><a href="#" id="open-options">Settings</a></div>
  `;
  document.getElementById("queue-retailer").addEventListener("click", async () => {
    await safe(async () => {
      await apiFetch("/api/admin/queue-new-retailer", {
        method: "POST",
        body: { url: tab.url, hostname: response.hostname },
      });
      toast("Queued for onboarding");
      window.close();
    }, "queue");
  });
  document.getElementById("skip").addEventListener("click", () => skipUrl(tab.url));
  document.getElementById("open-options").addEventListener("click", openOptions);
}

function renderCandidate(tab, response) {
  const top = (response.candidates && response.candidates[0]) || null;
  const alts = (response.candidates || []).slice(1, 5);
  const proposalParts = partsFromCommunityProposal(response.community_proposal);
  // Pre-fill priority: consumer proposal > matcher top candidate > URL
  // guess. Consumer proposals are higher signal than URL-pattern guesses
  // because a real human saw the page and typed the values; we trust
  // their input more than the matcher's heuristics on the URL alone.
  const parts = proposalParts
    || (top ? partsFromCandidate(top) : suggestPartsFromUrl(tab.url, response.scraped_title));

  // Consumer proposals omit parent_brand. When the matcher already has a
  // high-signal cigar_id for the same brand+line, inherit its encoded parent
  // slot so we don't mint COHIBA|COHIBA when master is COHIBA|| — while still
  // preserving ARTUROFUENTE|ARTUROFUENTE|HEMINGWAY|… when that is canonical.
  if (proposalParts && top && top.cigar_id) {
    const canon = splitCid(top.cigar_id);
    if (
      cidPart(proposalParts.brand) === cidPart(canon.brand)
      && cidPart(proposalParts.line) === cidPart(canon.line)
    ) {
      parts.parent_brand = canon.parent_brand != null ? canon.parent_brand : "";
    }
  }

  // Gap 4 + Gap 1 bridge: when a consumer proposal pre-filled the form
  // it stored the wrapper as a friendly BUCKET name (e.g. "Maduro"),
  // not a canonical code. Resolve bucket → wrapper_code using the
  // matcher's top candidates so the form lands with a populated CID
  // preview that the operator can approve in one click.
  if (proposalParts
      && !parts.wrapper_code
      && response.community_proposal
      && response.community_proposal.proposed_wrapper) {
    parts.wrapper_code = resolveBucketToCode(
      response.community_proposal.proposed_wrapper,
      response,
    );
  }

  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="section">
      ${communityProposalBanner(response)}
      <div class="section-label">
        Catalog draft
        ${top ? `<span class="confidence ${top.confidence}">${top.confidence} ${(top.score*100|0)}%</span>` : ""}
      </div>
      <div id="catalog-draft-summary" class="catalog-draft-summary">
        ${escapeHtml(humanDraftSummaryFromParts(parts) || "Add brand, line, vitola…")}
      </div>
      <details class="cand-tech" style="margin-bottom:8px">
        <summary>Pipe CID (advanced)</summary>
        <div class="cid-display" id="cid-preview">${escapeHtml(buildCidString(parts))}</div>
      </details>
      <div id="master-lock-hint" class="banner seen" style="display:none;font-size:11px;margin-top:8px;line-height:1.4"></div>
      ${top ? renderMatchChips(top.details) : ""}
      ${renderScraped(response)}

      <div class="fields" id="cid-fields">
        <input type="hidden" id="f-parent_brand" name="parent_brand"
               value="${escapeAttr(parts.parent_brand ?? "")}" />
        ${field("brand",         "Brand",         parts.brand,         "text")}
        ${field("line",          "Line",          parts.line,          "text")}
        ${field("vitola",        "Vitola",        parts.vitola,        "text")}
        ${field("vitola2",       "Vitola2",       parts.vitola2,       "text")}
        ${field("size",          "Size (LxR)",    parts.size,          "text")}
        ${wrapperField(parts.wrapper_code)}
        ${field("box_qty",       "Box Qty",       parts.box_qty,       "number")}
      </div>

      ${manualPricingBlock(response)}

      <div id="dup-warning" style="display:none"></div>

      <div class="section-label" style="margin-top:10px">
        Similar catalog rows
        <span style="font-weight:normal;color:#888;text-transform:none;letter-spacing:0">
          — updates as you type
        </span>
      </div>
      <div class="candidates" id="similar-cids">
        <div class="empty-similar" style="font-size:11px;color:#888;padding:6px 0">
          Fill Brand and Line to search the master catalog.
        </div>
      </div>

      ${alts.length ? `
        <div class="section-label" style="margin-top:10px">URL-based catalog candidates</div>
        <div class="candidates" id="alt-candidates">
          ${alts.map((c, i) => {
            const primary = escapeHtml(masterCatalogSummaryRow(c) || "Catalog row");
            const cid = escapeHtml(c.cigar_id || "");
            return `
            <div class="cand" data-idx="${i + 1}">
              <div class="col-left">
                <div class="cand-primary">${primary}</div>
                <details class="cand-tech">
                  <summary>Pipe CID</summary>
                  <span class="cand-cid">${cid}</span>
                </details>
              </div>
              <span class="confidence ${c.confidence}">${c.confidence} ${(c.score*100|0)}%</span>
            </div>`;
          }).join("")}
        </div>
      ` : ""}
    </div>

    <div class="actions">
      <button class="approve" id="approve">Approve</button>
      <button class="skip" id="skip">Skip</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a> ·
      Map this URL to an existing master cigar_id only (see banner above)
    </div>
  `;

  wireCandidateActions(tab, response);
}

function renderNoAdminKey() {
  root.innerHTML = `
    <div class="header"><div class="title">Cigar Price Scout</div></div>
    <div class="banner error">Admin key not configured.</div>
    <div class="section" style="font-size:13px; color:#555; line-height:1.5">
      Click <strong>Settings</strong> below and paste your ADMIN_SECRET_KEY.
      The extension stores it in <code>chrome.storage.local</code> on this device only.
    </div>
    <div class="actions">
      <button class="approve" id="open-options">Open settings</button>
    </div>
  `;
  document.getElementById("open-options").addEventListener("click", openOptions);
}

function renderError(msg) {
  root.innerHTML = `
    <div class="header"><div class="title">Cigar Price Scout</div></div>
    <div class="banner error">${escapeHtml(msg)}</div>
    <div class="actions">
      <button class="secondary" id="retry">Retry</button>
      <button class="skip" id="open-options">Settings</button>
    </div>
  `;
  document.getElementById("retry").addEventListener("click", () => location.reload());
  document.getElementById("open-options").addEventListener("click", openOptions);
}

// ── Helpers (rendering) ───────────────────────────────────────────────

function field(name, label, value, type, full = false) {
  // Combobox: native <input list=...> + <datalist>. User can pick a known
  // master value (which avoids "1964 Anniversary" vs "1964 Anniversary Serie"
  // dupes) or type anything new. Datalist <option>s are populated by
  // rebuildDatalists() after render, scoped by the other field values.
  return `
    <div class="field ${full ? "full" : ""}">
      <label for="f-${name}">${label}</label>
      <input id="f-${name}" name="${name}" type="${type}"
             value="${escapeAttr(value ?? "")}"
             list="dl-${name}" autocomplete="off" />
      <datalist id="dl-${name}"></datalist>
    </div>
  `;
}

// Returns true when the retailer has no working scraper (`blocked` because
// of anti-bot protection, or `dormant` because we paused a broken one). In
// both cases nothing downstream will ever fill price/in_stock for the
// approved URL, so the operator MUST enter those values manually now.
function needsManualPricing(response) {
  const s = response && response.extractor_status;
  return s === "blocked" || s === "dormant";
}

// Conditional price + in-stock block. Pre-fills from the page scrape so
// most of the time the operator just confirms the values. Rendered inline
// in the candidate form when needsManualPricing(response) is true; empty
// string otherwise (the active-retailer path is unchanged — the daily
// scraper fills these columns).
function manualPricingBlock(response) {
  if (!needsManualPricing(response)) return "";
  const s = response._scraped || {};
  const priceVal = (typeof s.price === "number" && !Number.isNaN(s.price))
    ? s.price.toFixed(2)
    : "";
  // Default to "in stock" unless the scraper EXPLICITLY captured the
  // page as out-of-stock. Operators are usually browsing live inventory,
  // so missing-data → true is the safer default than missing-data → null.
  const inStockVal = s.inStock === false ? "false" : "true";
  return `
    <div class="manual-pricing">
      <div class="manual-pricing-banner">
        <strong>No scraper for this retailer.</strong>
        Your price + stock entry below is saved directly to the CSV.
      </div>
      <div class="field-row">
        <div class="field">
          <label for="f-price">Price (USD)</label>
          <input id="f-price" name="price" type="number" step="0.01" min="0"
                 value="${escapeAttr(priceVal)}" placeholder="0.00" />
        </div>
        <div class="field">
          <label for="f-in_stock">In stock</label>
          <select id="f-in_stock" name="in_stock">
            <option value="true"  ${inStockVal === "true"  ? "selected" : ""}>Yes</option>
            <option value="false" ${inStockVal === "false" ? "selected" : ""}>No</option>
          </select>
        </div>
      </div>
    </div>
  `;
}

function wrapperField(value) {
  // Gap 4: operator extension uses the same 4 friendly buckets the
  // consumer extension does. The hidden f-wrapper_code input remains
  // the truth source readFields() consumes — wireWrapperBucket() keeps
  // it synced with the bucket selection. A "Specific code" toggle
  // reveals the legacy 14-code dropdown for power-user overrides
  // (e.g. picking BRZ or OSC that no bucket includes).
  const currentBucket = bucketForCode(value);
  const bucketOptions = Object.keys(WRAPPER_BUCKETS).map(b =>
    `<option value="${escapeAttr(b)}" ${b === currentBucket ? "selected" : ""}>${escapeHtml(b)}</option>`
  ).join("");
  const codeOptions = WRAPPER_CODES.map(c =>
    `<option value="${c}" ${c === value ? "selected" : ""}>${c}</option>`
  ).join("");
  const custom = value && !WRAPPER_CODES.includes(value)
    ? `<option value="${escapeAttr(value)}" selected>${escapeHtml(value)} (custom)</option>`
    : "";
  const showSpecific = !!value && !currentBucket;  // off-bucket → reveal override
  return `
    <div class="field wrapper-field">
      <label for="f-wrapper_bucket">Wrapper</label>
      <select id="f-wrapper_bucket" name="wrapper_bucket"${showSpecific ? ' style="display:none"' : ""}>
        <option value="">— pick one —</option>
        ${bucketOptions}
      </select>
      <span class="wrapper-resolved" id="wrapper-resolved"${value ? "" : ' style="display:none"'}>
        → <code>${escapeHtml(value || "")}</code>
      </span>
      <a href="#" class="wrapper-toggle" id="wrapper-specific-toggle">
        ${showSpecific ? "Use friendly bucket" : "Use specific code"}
      </a>
      <select id="f-wrapper_code" name="wrapper_code"${showSpecific ? "" : ' style="display:none"'}>
        <option value=""></option>
        ${custom}${codeOptions}
      </select>
    </div>
  `;
}

// Resolves a bucket pick to the canonical wrapper_code, preferring
// codes that already appear in the response's top candidates (so we
// reuse master's existing CID when the operator's bucket lines up
// with one of them). Falls back to the bucket's default code for
// brand-new CIDs.
function resolveBucketToCode(bucket, response) {
  if (!bucket) return "";
  const allowed = WRAPPER_BUCKETS[bucket] || [];
  if (!allowed.length) return "";
  const cands = (response && response.candidates) || [];
  for (const c of cands) {
    const code = (c.wrapper_code || "").toUpperCase();
    if (code && allowed.includes(code)) return code;
  }
  return BUCKET_DEFAULT_CODE[bucket] || allowed[0] || "";
}

// Called once after renderCandidate paints the form. Wires bucket
// changes → hidden wrapper_code updates → CID-preview refresh.
// `onUserOverride` runs when the operator changes wrapper UI — clears a
// locked master CID so approval is not sent against a stale selection.
function wireWrapperBucket(response, onUserOverride) {
  const bucketEl  = document.getElementById("f-wrapper_bucket");
  const codeEl    = document.getElementById("f-wrapper_code");
  const resolved  = document.getElementById("wrapper-resolved");
  const toggle    = document.getElementById("wrapper-specific-toggle");
  const preview   = document.getElementById("cid-preview");
  if (!bucketEl || !codeEl) return;

  const refreshResolved = () => {
    const v = codeEl.value || "";
    if (resolved) {
      resolved.style.display = v ? "" : "none";
      const codeNode = resolved.querySelector("code");
      if (codeNode) codeNode.textContent = v;
    }
    if (preview) {
      refreshCidPreviewBlock();
      refreshCatalogDraftSummary();
    }
  };

  bucketEl.addEventListener("change", () => {
    const code = resolveBucketToCode(bucketEl.value, response);
    codeEl.value = code;
    if (onUserOverride) onUserOverride();
    else refreshResolved();
  });

  codeEl.addEventListener("change", () => {
    if (onUserOverride) onUserOverride();
    else refreshResolved();
  });

  if (toggle) {
    toggle.addEventListener("click", (e) => {
      e.preventDefault();
      if (onUserOverride) onUserOverride();
      const showingSpecific = codeEl.style.display !== "none";
      if (showingSpecific) {
        codeEl.style.display = "none";
        bucketEl.style.display = "";
        toggle.textContent = "Use specific code";
        // Keep the current wrapper_code; just hide the picker.
      } else {
        codeEl.style.display = "";
        bucketEl.style.display = "none";
        toggle.textContent = "Use friendly bucket";
      }
      refreshResolved();
    });
  }
}

function renderMatchChips(details) {
  if (!details) return "";
  const flags = ["brand", "line", "vitola", "wrapper", "size", "box_qty"];
  return `
    <div class="match-details">
      ${flags.map(k => `
        <span class="chip ${details[`${k}_match`] ? "on" : "off"}">${k}</span>
      `).join("")}
    </div>
  `;
}

function renderScraped(response) {
  const s = response._scraped || {};
  const t = response.scraped_title || s.title || "";
  if (!t) return "";
  return `
    <div class="scraped">
      <strong>On page:</strong> ${escapeHtml(t.slice(0, 140))}
    </div>
  `;
}

// ── Wiring ───────────────────────────────────────────────────────────

function wireMatchedActions(tab, response) {
  document.getElementById("close").addEventListener("click", () => window.close());
  document.getElementById("open-options").addEventListener("click", openOptions);
  document.getElementById("re-review").addEventListener("click", () => {
    // Convert this URL to the candidate view, forcing supersession on approve.
    const synthetic = {
      ...response,
      state: "candidate",
      candidates: response.candidates && response.candidates.length
        ? response.candidates
        : (response.matched_cid ? [{
            cigar_id: response.matched_cid,
            confidence: "HIGH",
            score: 1.0,
            details: {},
          }] : []),
      _force: true,
    };
    renderCandidate(tab, synthetic);
  });
}

function updateMasterLockUi() {
  const hint = document.getElementById("master-lock-hint");
  if (hint) {
    hint.style.display = "block";
    if (lockedMasterCid) {
      hint.className = "banner seen";
      hint.textContent =
        "This URL will be saved against the selected master row. " +
        "Expand \"Pipe CID (advanced)\" to verify the full key. " +
        "Edit a field above only if you need to search again — that clears this selection.";
    } else {
      hint.className = "banner no_scraper";
      hint.textContent =
        "Pick a master row from Similar catalog rows or URL-based candidates (or use the top match). " +
        "Approve is disabled until a master key is selected — new CIDs cannot be created from this popup.";
    }
  }
  refreshCidPreviewBlock();
  refreshCatalogDraftSummary();
  syncApproveEnabled();
}

function syncApproveEnabled() {
  const btn = document.getElementById("approve");
  if (btn) btn.disabled = !lockedMasterCid;
}

function setLockedMasterCid(cid) {
  lockedMasterCid = (cid || "").trim() || null;
  updateMasterLockUi();
}

function clearLockedMasterCid() {
  lockedMasterCid = null;
  updateMasterLockUi();
}

function wireCandidateActions(tab, response) {
  lockedMasterCid = null;
  updateMasterLockUi();

  const refreshSimilar = debounce(() => {
    updateSimilarCids(readFields());
  }, 300);

  const onFormEdit = () => {
    clearLockedMasterCid();
    refreshCidPreviewBlock();
    refreshCatalogDraftSummary();
    rebuildDatalists(readFields());
    refreshSimilar();
  };

  wireWrapperBucket(response, onFormEdit);

  const fields = document.querySelectorAll("#cid-fields input, #cid-fields select");
  fields.forEach(f => {
    f.addEventListener("input", onFormEdit);
    f.addEventListener("change", onFormEdit);
  });

  const similarHost = document.getElementById("similar-cids");
  if (similarHost) {
    similarHost.addEventListener("click", (e) => {
      if (e.target.closest("details")) return;
      const el = e.target.closest(".cand.similar");
      if (!el) return;
      const idx = parseInt(el.getAttribute("data-idx"), 10);
      const cand = lastSimilarResults[idx];
      if (!cand || !cand.cigar_id) return;
      applyFields(partsFromCandidate(cand));
      setLockedMasterCid(cand.cigar_id);
      rebuildDatalists(readFields());
      refreshSimilar();
    });
  }

  // Click alt candidate (URL-based) → populate the form + lock exact master CID.
  const alts = document.getElementById("alt-candidates");
  if (alts) {
    alts.addEventListener("click", (e) => {
      if (e.target.closest("details")) return;
      const el = e.target.closest(".cand");
      if (!el) return;
      const idx = parseInt(el.getAttribute("data-idx"), 10);
      const cand = (response.candidates || [])[idx];
      if (!cand || !cand.cigar_id) return;
      applyFields(partsFromCandidate(cand));
      setLockedMasterCid(cand.cigar_id);
      rebuildDatalists(readFields());
      refreshSimilar();
    });
  }

  document.getElementById("approve").addEventListener("click", () => approve(tab, response));
  document.getElementById("skip").addEventListener("click", () => skipUrl(tab.url));
  document.getElementById("open-options").addEventListener("click", openOptions);

  rebuildDatalists(readFields());
  refreshSimilar();

  const top = (response.candidates && response.candidates[0]) || null;
  if (top && top.cigar_id) {
    setLockedMasterCid(top.cigar_id);
  } else {
    updateMasterLockUi();
  }
}

// ── Context-aware datalists (master-driven dropdowns) ─────────────────

// Given the current form state, rebuild every <datalist> so its options are
// scoped by the values the user has already typed. E.g. once Brand="Padron",
// the Line dropdown only shows Padron lines.
function rebuildDatalists(parts) {
  if (!VOCAB_ROWS.length) return;
  const eq = (a, b) => norm(a) === norm(b);
  const has = v => v != null && String(v).trim() !== "";

  // Cascade: each subsequent dropdown is filtered by all earlier fields.
  const byBrand = parts.brand ? VOCAB_ROWS.filter(r => eq(r.brand, parts.brand)) : VOCAB_ROWS;
  const byLine  = has(parts.line)   ? byBrand.filter(r => eq(r.line, parts.line)) : byBrand;
  const byVit   = has(parts.vitola) ? byLine.filter(r => eq(r.vitola, parts.vitola)) : byLine;
  const bySize  = has(parts.size)   ? byVit.filter(r => eq(r.size, parts.size))   : byVit;

  setDatalistFromRows("dl-brand",        VOCAB_ROWS, "brand");
  setDatalistFromRows("dl-line",         byBrand,    "line");
  setDatalistFromRows("dl-vitola",       byLine,     "vitola");
  setDatalistFromRows("dl-vitola2",      byLine,     "vitola");
  setDatalistFromRows("dl-size",         byVit,      "size");
  setDatalistFromRows("dl-box_qty",      bySize,     "box_qty");
}

function norm(v) { return String(v || "").trim().toLowerCase(); }

function setDatalistFromRows(id, rows, key) {
  const dl = document.getElementById(id);
  if (!dl) return;
  const seen = new Map(); // lowercased -> display value (keep first/canonical casing)
  for (const r of rows) {
    const raw = r[key];
    if (raw == null || raw === "") continue;
    const display = String(raw);
    const k = display.toLowerCase();
    if (!seen.has(k)) seen.set(k, display);
  }
  const values = Array.from(seen.values()).sort((a, b) => {
    // Numeric sort for box_qty, alphabetical otherwise.
    const na = Number(a), nb = Number(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a.localeCompare(b);
  });
  dl.innerHTML = values
    .map(v => `<option value="${escapeAttr(v)}"></option>`)
    .join("");
}

// ── Similar-CIDs panel (debounced live search) ────────────────────────

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// Find existing CIDs that share brand+line+vitola+wrapper+box with the
// current draft but have a different size. Used to warn the operator before
// they create a near-duplicate CID (e.g. PADRON|...|5x52|... when
// PADRON|...|5.5x52|... already exists).
function findSizeVariants(parts, results) {
  const sameKey = (a, b) => norm(a) === norm(b);
  const targetSize = norm(parts.size);
  if (!targetSize) return [];
  return results.filter(r => {
    if (!r.cigar_id) return false;
    const rs = norm(r.size);
    if (!rs || rs === targetSize) return false;
    if (!sameKey(r.brand,        parts.brand))        return false;
    if (!sameKey(r.line,         parts.line))         return false;
    if (!sameKey(r.vitola,       parts.vitola))       return false;
    // wrapper_code/box_qty may not always be returned; if absent, skip the
    // check so we still surface obvious near-dups on the main fields.
    if (r.wrapper_code != null && !sameKey(r.wrapper_code, parts.wrapper_code)) return false;
    if (r.box_qty != null && parts.box_qty &&
        String(r.box_qty) !== String(parts.box_qty)) return false;
    return true;
  }).slice(0, 3);
}

function buildSimilarQuery(parts) {
  // Combine brand + line + vitola (whichever are populated with >=2 chars).
  // The backend's /cid-search does AND-of-tokens substring matching, so the
  // more the user has typed, the narrower the result set.
  return [parts.brand, parts.line, parts.vitola]
    .map(s => (s || "").trim())
    .filter(s => s.length >= 2)
    .join(" ")
    .trim();
}

async function updateSimilarCids(parts) {
  const container = document.getElementById("similar-cids");
  const warning   = document.getElementById("dup-warning");
  if (!container) return;

  const q = buildSimilarQuery(parts);
  if (!q) {
    container.innerHTML = `
      <div class="empty-similar" style="font-size:11px;color:#888;padding:6px 0">
        Fill Brand and Line to search the master catalog.
      </div>`;
    if (warning) { warning.style.display = "none"; warning.innerHTML = ""; }
    lastSimilarResults = [];
    return;
  }

  let results = [];
  try {
    const data = await apiFetch("/api/admin/cid-search", { query: { q, limit: 6 } });
    results = data.results || [];
  } catch (e) {
    container.innerHTML = `<div style="font-size:11px;color:#c62828;padding:6px 0">Search failed: ${escapeHtml(e.message || String(e))}</div>`;
    lastSimilarResults = [];
    return;
  }

  const currentCid = lockedMasterCid || buildCidString(parts);
  const dup = results.find(r => r.cigar_id === currentCid);

  // Size-variant near-dup: same brand|line|vitola|wrapper|box, only size
  // differs. This catches "5x52 vs 5.5x52" where the operator might be
  // about to create a duplicate CID for a SKU that already exists under a
  // rounded size.
  const sizeVariants = !dup ? findSizeVariants(parts, results) : [];

  if (warning) {
    if (dup) {
      warning.style.display = "block";
      warning.className = "banner error";
      warning.style.padding = "8px 10px";
      warning.style.marginTop = "8px";
      warning.style.borderRadius = "4px";
      warning.style.fontSize = "12px";
      warning.innerHTML =
        `⚠ This CID already exists in master. Approving will re-use it (no duplicate created), ` +
        `but double-check the fields are right.`;
    } else if (sizeVariants.length) {
      warning.style.display = "block";
      warning.className = "banner seen";
      warning.style.padding = "8px 10px";
      warning.style.marginTop = "8px";
      warning.style.borderRadius = "4px";
      warning.style.fontSize = "12px";
      const list = sizeVariants
        .map(v => `<code style="font-size:11px">${escapeHtml(v.cigar_id)}</code>`)
        .join(", ");
      warning.innerHTML =
        `⚠ Same brand/line/vitola already exists with a different size: ${list}. ` +
        `Consider using the existing CID's size (retailers often round 5.5 to 5) ` +
        `instead of creating a near-duplicate.`;
    } else {
      warning.style.display = "none";
      warning.innerHTML = "";
    }
  }

  if (!results.length) {
    container.innerHTML = `
      <div class="empty-similar" style="font-size:11px;color:#888;padding:6px 0">
        No catalog rows matched "${escapeHtml(q)}". Try different tokens or adjust fields.
      </div>`;
    lastSimilarResults = [];
    return;
  }

  lastSimilarResults = results;

  container.innerHTML = results.map((r, i) => {
    const isDup = r.cigar_id === currentCid;
    const primary = escapeHtml(masterCatalogSummaryRow(r) || "Catalog row");
    const cid = escapeHtml(r.cigar_id || "");
    return `
      <div class="cand similar" data-idx="${i}" ${isDup ? 'style="outline:2px solid #c62828"' : ""}>
        <div class="col-left">
          <div class="cand-primary">${primary}</div>
          <details class="cand-tech">
            <summary>Pipe CID</summary>
            <span class="cand-cid">${cid}</span>
          </details>
        </div>
        ${isDup ? '<span class="confidence" style="background:#ffebee;color:#c62828">EXISTS</span>' : ""}
      </div>
    `;
  }).join("");
}

function readFields() {
  // IMPORTANT: We preserve the natural form (Title Case, spaces intact) so
  // the master_cigars.csv human-readable columns display correctly on the
  // website (e.g. "Corona Gorda" — not "CORONAGORDA"). The CID is built
  // from these via cidPart()/cidSize() which strip spaces and uppercase.
  const get = id => (document.getElementById(`f-${id}`) || {}).value || "";
  const trim = v => (v || "").trim();
  return {
    brand:        trim(get("brand")),
    parent_brand: trim(get("parent_brand")),
    line:         trim(get("line")),
    vitola:       trim(get("vitola")),
    vitola2:      trim(get("vitola2")) || trim(get("vitola")),
    size:         trim(get("size")).toLowerCase(),
    wrapper_code: trim(get("wrapper_code")).toUpperCase(), // always all-caps codes
    box_qty:      parseInt(get("box_qty"), 10) || 0,
  };
}

function applyFields(parts) {
  for (const [k, v] of Object.entries(parts)) {
    const el = document.getElementById(`f-${k}`);
    if (!el) continue;
    el.value = v ?? "";
  }
  // Gap 4: keep the friendly bucket dropdown in sync with wrapper_code.
  // When the operator clicks an alt candidate, this ensures the bucket
  // visibly reflects the candidate's canonical wrapper without forcing
  // them into the "Specific code" override.
  const code = (parts.wrapper_code || "").toUpperCase();
  const bucket = bucketForCode(code);
  const bucketEl  = document.getElementById("f-wrapper_bucket");
  const codeEl    = document.getElementById("f-wrapper_code");
  const resolved  = document.getElementById("wrapper-resolved");
  const toggle    = document.getElementById("wrapper-specific-toggle");
  if (bucketEl && bucket) {
    bucketEl.value = bucket;
    bucketEl.style.display = "";
    if (codeEl) codeEl.style.display = "none";
    if (toggle) toggle.textContent = "Use specific code";
  } else if (codeEl && code && !bucket) {
    // Off-bucket code (BRZ, OSC, etc.) — reveal the specific-code UI.
    codeEl.style.display = "";
    if (bucketEl) bucketEl.style.display = "none";
    if (toggle) toggle.textContent = "Use friendly bucket";
  }
  if (resolved) {
    const codeNode = resolved.querySelector("code");
    if (codeNode) codeNode.textContent = code;
    resolved.style.display = code ? "" : "none";
  }
}

async function approve(tab, response) {
  const top = (response.candidates && response.candidates[0]) || null;

  let priceValue, inStockValue;
  const priceEl = document.getElementById("f-price");
  const stockEl = document.getElementById("f-in_stock");
  if (needsManualPricing(response) && priceEl) {
    const raw = (priceEl.value || "").trim();
    if (raw === "") {
      priceValue = null;
    } else {
      const parsed = parseFloat(raw);
      if (Number.isNaN(parsed) || parsed < 0) {
        return toast("Enter a valid price (e.g. 12.99) or leave blank.", "error");
      }
      priceValue = parsed;
    }
    inStockValue = stockEl ? (stockEl.value === "true") : null;
  } else {
    priceValue = (response._scraped && response._scraped.price) || null;
    inStockValue = (response._scraped && response._scraped.inStock) ?? null;
  }

  if (lockedMasterCid) {
    const body = {
      url: tab.url,
      retailer_key: response.retailer_key,
      cid: lockedMasterCid,
      title: response.scraped_title || (response._scraped && response._scraped.title) || "",
      price: priceValue,
      in_stock: inStockValue,
      create_if_missing: false,
      force: !!response._force,
      confidence: "EXTENSION",
      reason: "Approved via Chrome extension (exact master CID)",
      proposed_cid: top ? top.cigar_id : null,
      proposed_score: top ? top.score : null,
      proposed_confidence: top ? top.confidence : null,
      community_proposal_id:
        (response.community_proposal && response.community_proposal.proposal_id) || null,
    };
    const btn = document.getElementById("approve");
    btn.disabled = true;
    btn.textContent = "Approving…";
    try {
      const res = await apiFetch("/api/admin/stage-approval", { method: "POST", body });
      chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url }).catch(() => {});
      let msg = "Approved";
      const resolved = res.resolved_consumer_proposals || 0;
      if (resolved > 0) {
        msg += resolved === 1
          ? " · 1 consumer proposal resolved"
          : ` · ${resolved} consumer proposals resolved`;
      }
      toast(msg);
      setTimeout(() => window.close(), 600);
    } catch (e) {
      toast(`Approve failed: ${e.message || e}`, "error");
      btn.disabled = false;
      btn.textContent = "Approve";
    }
    return;
  }

  toast(
    "Select a master cigar from Similar CIDs or URL candidates first. "
    + "New CIDs are not created from this popup — add the SKU to master_cigars via your catalog workflow, then map this URL.",
    "error",
  );
}

async function skipUrl(url) {
  try {
    await apiFetch("/api/admin/skip-url", {
      method: "POST",
      body: { url, reason: "skipped via extension" },
    });
    chrome.runtime.sendMessage({ type: "invalidateCache", url }).catch(() => {});
    toast("Skipped");
    setTimeout(() => window.close(), 400);
  } catch (e) {
    toast(`Skip failed: ${e.message || e}`, "error");
  }
}

function validateParts(p) {
  const errs = [];
  if (!p.brand)        errs.push("Brand is required");
  if (!p.line)         errs.push("Line is required");
  if (!p.vitola)       errs.push("Vitola is required");
  if (!p.size || !/^\d+(\.\d+)?x\d+$/.test(p.size))
                       errs.push("Size must be like '6x50' or '5.5x52'");
  if (!p.wrapper_code) errs.push("Wrapper code is required");
  if (!p.box_qty || p.box_qty < 1) errs.push("Box quantity is required");
  return errs;
}

// Normalize a natural-form value ("Corona Gorda") into its CID component
// ("CORONAGORDA"): strip internal whitespace + uppercase. Must match the
// backend's build_cid() so the preview matches what gets stored.
function cidPart(s) {
  return String(s || "").trim().replace(/\s+/g, "").toUpperCase();
}
function cidSize(s) {
  return String(s || "").trim().replace(/\s+/g, "").toLowerCase();
}

function buildCidString(p) {
  const box = p.box_qty ? `BOX${parseInt(p.box_qty, 10)}` : "";
  const pb = p.parent_brand;
  const parentSeg =
    pb != null && String(pb).trim() !== "" ? cidPart(pb) : "";
  return [
    cidPart(p.brand),
    parentSeg,
    cidPart(p.line),
    cidPart(p.vitola),
    cidPart(p.vitola2) || cidPart(p.vitola),
    cidSize(p.size),
    cidPart(p.wrapper_code),
    box,
  ].join("|");
}

function splitCid(cid) {
  let parts = (cid || "").split("|");
  // Tolerate legacy / hand-edited CIDs where BOX qty was split: ...|CAM|BOX|25
  if (
    parts.length >= 9
    && String(parts[parts.length - 2] || "").toUpperCase() === "BOX"
    && /^\d+$/.test(String(parts[parts.length - 1] || "").trim())
  ) {
    parts = parts.slice(0, parts.length - 2).concat(
      "BOX" + String(parts[parts.length - 1]).trim(),
    );
  }
  while (parts.length < 8) parts.push("");
  const boxNum = (parts[7].match(/\d+/) || [""])[0];
  return {
    brand: parts[0],
    parent_brand: parts[1],
    line: parts[2],
    vitola: parts[3],
    vitola2: parts[4],
    size: parts[5],
    wrapper_code: parts[6],
    box_qty: boxNum ? parseInt(boxNum, 10) : "",
  };
}

// Build form-ready parts dict from a candidate. Prefers the master CSV's
// natural-form values (Title Case, spaces) so the user sees and edits the
// same shape the website displays. Falls back to the canonical CID parts
// for fields the master doesn't expose directly.
function partsFromCandidate(cand) {
  const canonical = splitCid(cand.cigar_id);
  // Preserve empty parent (`BRAND||LINE` in master). `||` in JS would skip
  // a legitimate empty canonical.parent_brand — only fall back to brand
  // when the candidate omits parent entirely (undefined/null).
  let parent = cand.parent_brand;
  if (parent === undefined || parent === null) {
    parent = canonical.parent_brand;
  }
  if (parent === undefined || parent === null) {
    parent = "";
  }
  return {
    brand:        cand.brand        || canonical.brand,
    parent_brand: parent,
    line:         cand.line         || canonical.line,
    vitola:       cand.vitola       || canonical.vitola,
    vitola2:      cand.vitola2      || cand.vitola || canonical.vitola2,
    size:         cand.size         || canonical.size,
    wrapper_code: cand.wrapper_code || canonical.wrapper_code,
    box_qty:      cand.box_qty      || canonical.box_qty,
  };
}

function suggestPartsFromUrl(url, scrapedTitle) {
  // Very minimal fallback when there are zero candidates: leave fields blank,
  // user fills in from the page.
  return {
    brand: "", parent_brand: "", line: "", vitola: "", vitola2: "",
    size: "", wrapper_code: "", box_qty: "",
  };
}

// Build form-ready parts from a pending consumer proposal. The consumer
// submitted brand/line/vitola/box_qty plus a friendly wrapper BUCKET name
// (e.g. "Maduro"), NOT a canonical wrapper code. The operator still picks
// the code from the 14-option dropdown — Gap 4 will resolve bucket→code
// automatically. wrapper_code is left blank here so the operator sees the
// pending choice clearly and doesn't accidentally promote a wrong code.
function partsFromCommunityProposal(cp) {
  if (!cp) return null;
  return {
    brand:        cp.proposed_brand  || "",
    // Consumers do not propose a distinct parent company; the CID slot is
    // filled from the matcher's top cigar_id when brand+line align (see
    // renderCandidate), otherwise left blank (master uses `BRAND||LINE` often).
    parent_brand: "",
    line:         cp.proposed_line   || "",
    vitola:       cp.proposed_vitola || "",
    vitola2:      cp.proposed_vitola || "",
    size:         cp.proposed_size   || "",
    wrapper_code: "",
    box_qty:      cp.proposed_box_qty != null ? String(cp.proposed_box_qty) : "",
  };
}

// Best-effort "12 minutes ago" / "3 hours ago" / "2 days ago" for the
// proposal banner. ISO 8601 timestamps from Postgres come through as
// strings; missing or unparseable input collapses to empty (the banner
// just omits the age line). Intentionally tiny — Intl.RelativeTimeFormat
// is overkill for this surface.
function humanizeAge(iso) {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 90)             return `${sec}s ago`;
  if (sec < 90 * 60)        return `${Math.round(sec / 60)}m ago`;
  if (sec < 36 * 3600)      return `${Math.round(sec / 3600)}h ago`;
  return `${Math.round(sec / 86400)}d ago`;
}

// Renders an info banner at the top of the candidate form when a consumer
// has already proposed metadata for this URL. Tells the operator what was
// submitted so they understand why the form is pre-filled. The banner is
// purely informational — the form itself is the action surface.
function communityProposalBanner(response) {
  const cp = response.community_proposal;
  if (!cp) return "";
  const age = humanizeAge(cp.created_at);
  const others = cp.total_pending > 1
    ? ` <span class="cp-more">+${cp.total_pending - 1} more</span>`
    : "";
  const novel = cp.needs_new_catalog_cid
    ? `<div class="cp-novel">This submission uses a <strong>brand or line we do not have in master yet</strong>. Add the full <code>master_cigars.csv</code> row and new pipe CID first, refresh the catalog cache, then lock that CID below and approve — the consumer’s box qty / price will publish on the staged retailer row.</div>`
    : "";
  const productLine = [cp.proposed_brand, cp.proposed_line, cp.proposed_vitola]
    .filter(Boolean).join(" ").trim() || "(no product info)";
  const meta = [
    cp.proposed_size,
    cp.proposed_box_qty ? `Box ${cp.proposed_box_qty}` : "",
    cp.proposed_wrapper,
    typeof cp.confirmed_price === "number" ? `$${cp.confirmed_price.toFixed(2)}` : "",
  ].filter(Boolean).join(" • ");
  return `
    <div class="community-proposal">
      <div class="cp-header">
        <span class="cp-badge">Consumer proposal${others}</span>
        ${age ? `<span class="cp-age">${escapeHtml(age)}</span>` : ""}
      </div>
      ${novel}
      <div class="cp-product">${escapeHtml(productLine)}</div>
      ${meta ? `<div class="cp-meta">${escapeHtml(meta)}</div>` : ""}
      <div class="cp-hint">
        Form pre-filled below. Pick an existing master CID (or add one to master first if the note above applies), then Approve — the proposal
        will be marked resolved and the consumer will see the comparison
        card on their next visit.
      </div>
    </div>
  `;
}

// ── Misc ─────────────────────────────────────────────────────────────

function openOptions(e) {
  if (e && e.preventDefault) e.preventDefault();
  chrome.runtime.openOptionsPage();
}

let toastTimeout = null;
function toast(msg, kind = "ok") {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const el = document.createElement("div");
  el.className = `toast ${kind === "error" ? "error" : ""}`;
  el.textContent = msg;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 250);
  }, 1800);
}

async function safe(fn, kind) {
  try { await fn(); }
  catch (e) { toast(`${kind} failed: ${e.message || e}`, "error"); }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
function escapeAttr(s) { return escapeHtml(s); }

function joinDisplayParts(parts) {
  return parts.filter(Boolean).join(" · ");
}

function humanDraftSummaryFromParts(parts) {
  if (!parts || typeof parts !== "object") return "";
  const brand = String(parts.brand || "").trim();
  const line = String(parts.line || "").trim();
  const vitola = String(parts.vitola || "").trim();
  const size = String(parts.size || "").trim();
  const wcode = String(parts.wrapper_code || "").trim();
  const bw =
    parts.box_qty != null && String(parts.box_qty).trim() !== ""
      ? `Box ${String(parts.box_qty).trim()}`
      : "";
  const brandLine = [brand, line].filter(Boolean).join(" ");
  return joinDisplayParts([brandLine || brand || line, vitola, size, wcode, bw]);
}

function masterCatalogSummaryRow(row) {
  if (!row || typeof row !== "object") return "";
  const brand = String(row.brand || "").trim();
  const line = String(row.line || "").trim();
  const vitola = String(row.vitola || "").trim();
  const size = String(row.size || "").trim();
  const wrapper = String(row.wrapper || "").trim();
  const wcode = String(row.wrapper_code || "").trim();
  const wrapperSeg = wrapper || wcode;
  const bw = row.box_qty != null && row.box_qty !== ""
    ? `Box ${row.box_qty}`
    : "";
  const brandLine = [brand, line].filter(Boolean).join(" ");
  const fromCols = joinDisplayParts([
    brandLine || brand || line, vitola, size, wrapperSeg, bw,
  ]);
  if (fromCols) return fromCols;
  if (row.cigar_id) return humanDraftSummaryFromParts(partsFromCandidate(row));
  return "";
}

function refreshCatalogDraftSummary() {
  const el = document.getElementById("catalog-draft-summary");
  if (!el) return;
  const text = humanDraftSummaryFromParts(readFields());
  el.textContent = text || "Add brand, line, vitola…";
}

function refreshCidPreviewBlock() {
  const preview = document.getElementById("cid-preview");
  if (!preview) return;
  preview.textContent = lockedMasterCid || buildCidString(readFields());
}
