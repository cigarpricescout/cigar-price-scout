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

// ── Bootstrapping ─────────────────────────────────────────────────────

(async function init() {
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
        Proposed CID
        ${top ? `<span class="confidence ${top.confidence}">${top.confidence} ${(top.score*100|0)}%</span>` : ""}
      </div>
      <div class="cid-display" id="cid-preview">${escapeHtml(buildCidString(parts))}</div>
      ${top ? renderMatchChips(top.details) : ""}
      ${renderScraped(response)}

      <div class="fields" id="cid-fields">
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
        Similar CIDs in master
        <span style="font-weight:normal;color:#888;text-transform:none;letter-spacing:0">
          — updates as you type
        </span>
      </div>
      <div class="candidates" id="similar-cids">
        <div class="empty-similar" style="font-size:11px;color:#888;padding:6px 0">
          Fill Brand and Line to see existing CIDs in this family.
        </div>
      </div>

      ${alts.length ? `
        <div class="section-label" style="margin-top:10px">URL-based candidates</div>
        <div class="candidates" id="alt-candidates">
          ${alts.map((c, i) => `
            <div class="cand" data-idx="${i + 1}">
              <div class="cand-cid">${escapeHtml(c.cigar_id)}</div>
              <span class="confidence ${c.confidence}">${c.confidence} ${(c.score*100|0)}%</span>
            </div>
          `).join("")}
        </div>
      ` : ""}
    </div>

    <div class="actions">
      <button class="approve" id="approve">Approve</button>
      <button class="skip" id="skip">Skip</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a> ·
      Edit any field to override the proposed CID
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
function wireWrapperBucket(response) {
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
    if (preview) preview.textContent = buildCidString(readFields());
  };

  bucketEl.addEventListener("change", () => {
    const code = resolveBucketToCode(bucketEl.value, response);
    codeEl.value = code;
    refreshResolved();
  });

  codeEl.addEventListener("change", refreshResolved);

  if (toggle) {
    toggle.addEventListener("click", (e) => {
      e.preventDefault();
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

function wireCandidateActions(tab, response) {
  // Gap 4: wire the friendly bucket picker → wrapper_code resolution.
  wireWrapperBucket(response);

  // Live-update the CID preview, the datalist dropdowns (context-aware
  // suggestions from master), AND the similar-CIDs panel as the user edits.
  const fields = document.querySelectorAll("#cid-fields input, #cid-fields select");
  const preview = document.getElementById("cid-preview");
  const refreshSimilar = debounce(() => {
    updateSimilarCids(readFields());
  }, 300);
  fields.forEach(f => f.addEventListener("input", () => {
    const parts = readFields();
    preview.textContent = buildCidString(parts);
    rebuildDatalists(parts);
    refreshSimilar();
  }));

  // Click alt candidate (URL-based) → populate the form with its parts.
  const alts = document.getElementById("alt-candidates");
  if (alts) {
    alts.querySelectorAll(".cand").forEach(el => {
      el.addEventListener("click", () => {
        const idx = parseInt(el.getAttribute("data-idx"), 10);
        const cand = (response.candidates || [])[idx];
        if (!cand) return;
        applyFields(partsFromCandidate(cand));
        const parts = readFields();
        preview.textContent = buildCidString(parts);
        rebuildDatalists(parts);
        refreshSimilar();
      });
    });
  }

  document.getElementById("approve").addEventListener("click", () => approve(tab, response));
  document.getElementById("skip").addEventListener("click", () => skipUrl(tab.url));
  document.getElementById("open-options").addEventListener("click", openOptions);

  // Populate dropdowns + run an initial similar-CIDs search.
  rebuildDatalists(readFields());
  refreshSimilar();
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
        Fill Brand and Line to see existing CIDs in this family.
      </div>`;
    if (warning) { warning.style.display = "none"; warning.innerHTML = ""; }
    return;
  }

  let results = [];
  try {
    const data = await apiFetch("/api/admin/cid-search", { query: { q, limit: 6 } });
    results = data.results || [];
  } catch (e) {
    container.innerHTML = `<div style="font-size:11px;color:#c62828;padding:6px 0">Search failed: ${escapeHtml(e.message || String(e))}</div>`;
    return;
  }

  const currentCid = buildCidString(parts);
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
        No existing CIDs matched "${escapeHtml(q)}". This will be a new CID.
      </div>`;
    return;
  }

  container.innerHTML = results.map((r, i) => {
    const isDup = r.cigar_id === currentCid;
    const meta = [
      r.brand, r.line, r.vitola,
      r.size ? `${r.size}` : "",
      r.wrapper ? `${r.wrapper}` : "",
      r.box_qty ? `box ${r.box_qty}` : "",
    ].filter(Boolean).join(" · ");
    return `
      <div class="cand similar" data-idx="${i}" ${isDup ? 'style="outline:2px solid #c62828"' : ""}>
        <div style="flex:1;min-width:0">
          <div class="cand-cid">${escapeHtml(r.cigar_id)}</div>
          <div style="font-size:10px;color:#666;margin-top:2px">${escapeHtml(meta)}</div>
        </div>
        ${isDup ? '<span class="confidence" style="background:#ffebee;color:#c62828">EXISTS</span>' : ""}
      </div>
    `;
  }).join("");

  container.querySelectorAll(".cand").forEach(el => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.getAttribute("data-idx"), 10);
      const cand = results[idx];
      if (!cand) return;
      applyFields(partsFromCandidate(cand));
      document.getElementById("cid-preview").textContent = buildCidString(readFields());
      // After populating, re-check duplicates against the new state.
      updateSimilarCids(readFields());
    });
  });
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
    parent_brand: trim(get("parent_brand")) || trim(get("brand")),
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
  const parts = readFields();
  const errors = validateParts(parts);
  if (errors.length) return toast(errors[0], "error");

  // Capture what the matcher initially proposed (top candidate) so the
  // review_decisions log can compare it to what the operator ended up
  // approving. This is training-data spine for the future AI reviewer.
  const top = (response.candidates && response.candidates[0]) || null;

  // Price + in-stock: prefer the operator's manual entry when the retailer
  // is blocked/dormant (the fields are rendered by manualPricingBlock).
  // For active retailers the fields aren't shown, so fall back to the
  // silent scrape capture — the daily extractor will overwrite anyway.
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

  const body = {
    url: tab.url,
    retailer_key: response.retailer_key,
    cid_parts: parts,
    title: response.scraped_title || (response._scraped && response._scraped.title) || "",
    price: priceValue,
    in_stock: inStockValue,
    create_if_missing: true,
    force: !!response._force,
    confidence: "EXTENSION",
    reason: "Approved via Chrome extension",
    proposed_cid: top ? top.cigar_id : null,
    proposed_score: top ? top.score : null,
    proposed_confidence: top ? top.confidence : null,
    // When a consumer proposal triggered this approval, pass its id so the
    // backend can flip community_url_proposals.status='approved' in the
    // same transaction — closing the contribution loop end-to-end.
    community_proposal_id:
      (response.community_proposal && response.community_proposal.proposal_id) || null,
  };
  const btn = document.getElementById("approve");
  btn.disabled = true;
  btn.textContent = "Approving…";
  try {
    const res = await apiFetch("/api/admin/stage-approval", { method: "POST", body });
    chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url }).catch(() => {});
    // Surface the proposal-resolution count when present so the operator
    // confirms the consumer's submission actually got closed out.
    let msg = res.mode === "new_cid" ? "Approved (new CID staged)" : "Approved";
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
  return [
    cidPart(p.brand),
    cidPart(p.parent_brand) || cidPart(p.brand),
    cidPart(p.line),
    cidPart(p.vitola),
    cidPart(p.vitola2) || cidPart(p.vitola),
    cidSize(p.size),
    cidPart(p.wrapper_code),
    box,
  ].join("|");
}

function splitCid(cid) {
  const parts = (cid || "").split("|");
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
  return {
    brand:        cand.brand        || canonical.brand,
    parent_brand: cand.parent_brand || canonical.parent_brand || cand.brand || canonical.brand,
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
    parent_brand: cp.proposed_brand  || "",
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
      <div class="cp-product">${escapeHtml(productLine)}</div>
      ${meta ? `<div class="cp-meta">${escapeHtml(meta)}</div>` : ""}
      <div class="cp-hint">
        Form pre-filled below. Edit any field, then Approve — the proposal
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
