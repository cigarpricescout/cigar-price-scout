import {
  publicFetch,
  hasConsented,
  getObserverId,
  getZip,
  setPreferredCidForUrl,
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

// Must match app/wrapper_buckets.NATURAL_LIGHT_WRAPPER_BUCKET
const NATURAL_LIGHT_WRAPPER_BUCKET = "Natural / Connecticut / Cameroon";

function normalizeLegacyWrapperBucket(w) {
  if (w == null || typeof w !== "string") return w;
  const t = w.trim();
  if (t === "Natural / Connecticut") return NATURAL_LIGHT_WRAPPER_BUCKET;
  return w;
}

const FALLBACK_WRAPPER_BUCKETS = [NATURAL_LIGHT_WRAPPER_BUCKET, "Habano", "Sun Grown", "Maduro"];

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function catalogBlKey(brand, line) {
  return `${String(brand || "").trim()}|${String(line || "").trim()}`;
}

function catalogBlvKey(brand, line, vitola) {
  return `${String(brand || "").trim()}|${String(line || "").trim()}|${String(vitola || "").trim()}`;
}

function defaultCatalogShape() {
  return {
    brands: [],
    lines_by_brand: {},
    vitolas_by_brand_line: {},
    vitolas_for_match: [],
    boxes_by_brand_line_vitola: {},
    buckets_by_brand_line_vitola: {},
    buckets_by_brand_line: {},
    vitolas_by_brand_line_bucket: {},
    wrapper_catalog_rows_by_blv: {},
    all_bucket_names: [...FALLBACK_WRAPPER_BUCKETS],
  };
}

function normalizeAllBucketNames(arr) {
  if (!arr || !Array.isArray(arr) || !arr.length) return null;
  const seen = new Set();
  const out = [];
  for (const raw of arr) {
    const label = normalizeLegacyWrapperBucket(String(raw).trim()) || String(raw).trim();
    if (label && !seen.has(label)) {
      seen.add(label);
      out.push(label);
    }
  }
  return out.length ? out : null;
}

function mergeCatalog(raw) {
  const d = defaultCatalogShape();
  if (!raw || typeof raw !== "object") return d;
  return {
    brands: raw.brands || d.brands,
    lines_by_brand: raw.lines_by_brand || d.lines_by_brand,
    vitolas_by_brand_line: raw.vitolas_by_brand_line || d.vitolas_by_brand_line,
    vitolas_for_match: raw.vitolas_for_match || d.vitolas_for_match,
    boxes_by_brand_line_vitola: raw.boxes_by_brand_line_vitola || d.boxes_by_brand_line_vitola,
    buckets_by_brand_line_vitola: raw.buckets_by_brand_line_vitola || d.buckets_by_brand_line_vitola,
    buckets_by_brand_line: raw.buckets_by_brand_line || d.buckets_by_brand_line,
    vitolas_by_brand_line_bucket: raw.vitolas_by_brand_line_bucket || d.vitolas_by_brand_line_bucket,
    wrapper_catalog_rows_by_blv: raw.wrapper_catalog_rows_by_blv || d.wrapper_catalog_rows_by_blv,
    all_bucket_names: normalizeAllBucketNames(raw.all_bucket_names) || d.all_bucket_names,
  };
}

function genericWrapperBucketsForSelect(catalog) {
  const raw = (catalog.all_bucket_names && catalog.all_bucket_names.length)
    ? catalog.all_bucket_names
    : FALLBACK_WRAPPER_BUCKETS;
  const seen = new Set();
  const out = [];
  for (const bkt of raw) {
    const label = normalizeLegacyWrapperBucket(String(bkt).trim()) || String(bkt).trim();
    if (label && !seen.has(label)) {
      seen.add(label);
      out.push(label);
    }
  }
  return out.length ? out : [...FALLBACK_WRAPPER_BUCKETS];
}

/** Encoded <option> values so catalog-specific labels stay unique per row. */
function wrapperSelectEncodeGeneric(bucket) {
  return `WG|${encodeURIComponent(normalizeLegacyWrapperBucket(bucket) || bucket)}`;
}

function wrapperSelectEncodeCatalog(bucket, label) {
  return `WC|${encodeURIComponent(normalizeLegacyWrapperBucket(bucket) || bucket)}|${encodeURIComponent(label)}`;
}

/** @returns {{ bucket: string, label?: string, kind: string }} */
function parseWrapperSelectValue(raw) {
  if (!raw || raw === "__manual__") return { bucket: "", kind: "empty" };
  if (raw.startsWith("WG|")) {
    const b = decodeURIComponent(raw.slice(3));
    return { bucket: normalizeLegacyWrapperBucket(b) || b, kind: "generic" };
  }
  if (raw.startsWith("WC|")) {
    const rest = raw.slice(3);
    const i = rest.indexOf("|");
    if (i === -1) {
      const b = decodeURIComponent(rest);
      return { bucket: normalizeLegacyWrapperBucket(b) || b, kind: "catalog", label: "" };
    }
    const b = decodeURIComponent(rest.slice(0, i));
    const lab = decodeURIComponent(rest.slice(i + 1));
    return {
      bucket: normalizeLegacyWrapperBucket(b) || b,
      label: lab,
      kind: "catalog",
    };
  }
  return { bucket: normalizeLegacyWrapperBucket(String(raw).trim()) || String(raw).trim(), kind: "legacy" };
}

function catalogWrapperRowsForBlv(catalog, brand, line, vitola) {
  const k = catalogBlvKey(brand, line, vitola);
  return (catalog.wrapper_catalog_rows_by_blv && catalog.wrapper_catalog_rows_by_blv[k]) || [];
}

/** Catalog rows to show as extra options (label distinct from bucket name). */
function catalogWrapperRowsDistinctFromBucket(catalog, brand, line, vitola) {
  return catalogWrapperRowsForBlv(catalog, brand, line, vitola).filter((r) => {
    const lab = (r.label || "").trim().toLowerCase();
    const bkt = (r.bucket || "").trim().toLowerCase();
    return lab && lab !== bkt;
  });
}

function labelFragsForScrapeMatch(label) {
  const t = String(label || "").trim().toLowerCase();
  if (!t) return [];
  const out = [t];
  const p = t.indexOf("(");
  if (p > 0) {
    const head = t.slice(0, p).trim();
    if (head) out.push(head);
  }
  const m = t.match(/\(([^)]+)\)/);
  if (m && m[1]) {
    const inner = m[1].trim().toLowerCase();
    if (inner) out.push(inner);
  }
  return [...new Set(out)];
}

function bestCatalogWrapperRowFromScrape(rows, haystack) {
  const h = String(haystack || "").toLowerCase();
  if (!h || !rows || !rows.length) return null;
  let bestRow = null;
  let bestScore = 0;
  for (const r of rows) {
    for (const frag of labelFragsForScrapeMatch(r.label)) {
      if (frag.length >= 3 && h.includes(frag)) {
        if (frag.length > bestScore) {
          bestScore = frag.length;
          bestRow = r;
        }
      }
    }
  }
  return bestRow;
}

function optionExists(selEl, value) {
  return !!(value && selEl && [...selEl.options].some((o) => o.value === value));
}

/**
 * Wrapper choices after brand+line+vitola: always the four generic buckets,
 * plus master-catalog display strings for this vitola when they differ from
 * the bucket name alone (e.g. Dominican Rosado → Maduro).
 */
function mountWrapperSelectForBrandLineVitola(catalog, selEl, brand, line, vitola, prefs) {
  if (!selEl) return;
  const prevRaw = (prefs && prefs.prevRaw) ? String(prefs.prevRaw).trim() : "";
  const preferredPlain = (prefs && prefs.preferredPlainBucket) ? String(prefs.preferredPlainBucket).trim() : "";
  const scrapeHaystack = (prefs && prefs.scrapeHaystack) ? String(prefs.scrapeHaystack) : "";

  const generics = genericWrapperBucketsForSelect(catalog);
  const extras = catalogWrapperRowsDistinctFromBucket(catalog, brand, line, vitola);
  const allRows = catalogWrapperRowsForBlv(catalog, brand, line, vitola);

  let html = '<option value="">Not sure</option>';
  html += `<option value="__manual__">${escapeHtml("Other / not in catalog")}</option>`;

  html += `<optgroup label="${escapeAttr("Wrapper category")}">`;
  for (const bkt of generics) {
    const enc = wrapperSelectEncodeGeneric(bkt);
    html += `<option value="${escapeAttr(enc)}">${escapeHtml(bkt)}</option>`;
  }
  html += "</optgroup>";

  if (extras.length) {
    html += `<optgroup label="${escapeAttr("Our catalog (this vitola)")}">`;
    for (const r of extras) {
      const enc = wrapperSelectEncodeCatalog(r.bucket, r.label);
      const lineLabel = `${r.label} — ${r.bucket}`;
      html += `<option value="${escapeAttr(enc)}">${escapeHtml(lineLabel)}</option>`;
    }
    html += "</optgroup>";
  }

  selEl.innerHTML = html;

  if (optionExists(selEl, prevRaw)) {
    selEl.value = prevRaw;
    return;
  }
  const scrapeHit = bestCatalogWrapperRowFromScrape(allRows, scrapeHaystack);
  if (scrapeHit) {
    const lab = (scrapeHit.label || "").trim().toLowerCase();
    const bkt = (scrapeHit.bucket || "").trim().toLowerCase();
    let want;
    if (lab && lab !== bkt) {
      want = wrapperSelectEncodeCatalog(scrapeHit.bucket, scrapeHit.label);
    } else {
      want = wrapperSelectEncodeGeneric(scrapeHit.bucket);
    }
    if (optionExists(selEl, want)) {
      selEl.value = want;
      return;
    }
  }
  const prefNorm = normalizeLegacyWrapperBucket(preferredPlain) || preferredPlain;
  if (prefNorm) {
    const wg = wrapperSelectEncodeGeneric(prefNorm);
    if (optionExists(selEl, wg)) {
      selEl.value = wg;
      return;
    }
  }
  selEl.value = "";
}

function vitolaOptionsFor(catalog, brand, line, wrapperBucket) {
  const bl = catalogBlKey(brand, line);
  const allSorted = ((catalog.vitolas_by_brand_line && catalog.vitolas_by_brand_line[bl]) || []).slice().sort();
  let wb = (wrapperBucket || "").trim();
  wb = normalizeLegacyWrapperBucket(wb) || wb;
  if (!wb || wb === "__manual__") return allSorted;
  const k = `${bl}|${wb}`;
  let sub = (catalog.vitolas_by_brand_line_bucket && catalog.vitolas_by_brand_line_bucket[k]) || [];
  if (!sub.length && wb === NATURAL_LIGHT_WRAPPER_BUCKET) {
    const legacyKey = `${bl}|Natural / Connecticut`;
    sub = (catalog.vitolas_by_brand_line_bucket && catalog.vitolas_by_brand_line_bucket[legacyKey]) || [];
  }
  if (sub.length) return [...sub].sort();
  return allSorted;
}

/** Vitola choices after brand+line (all vitolas for that line; wrapper is chosen next). */
function mountVitolaSelect(catalog, selEl, brand, line, preferredVitola) {
  if (!selEl) return;
  const manualEl = document.getElementById("f-vitola-manual");
  const prevSel = (selEl.value || "").trim();
  const prevManual = manualEl ? (manualEl.value || "").trim() : "";
  const opts = vitolaOptionsFor(catalog, brand, line, "");
  let html = '<option value="">Choose vitola…</option>';
  for (const v of opts) {
    html += `<option value="${escapeAttr(v)}">${escapeHtml(v)}</option>`;
  }
  html += `<option value="__manual__">${escapeHtml("Other / type vitola…")}</option>`;
  selEl.innerHTML = html;
  const pick = (x) => x && [...selEl.options].some((o) => o.value === x);
  const pref = (preferredVitola || "").trim();
  const prefInList = pref && opts.includes(pref);
  if (pick(prevSel) && prevSel !== "__manual__") {
    selEl.value = prevSel;
    if (manualEl) {
      manualEl.style.display = "none";
      manualEl.value = "";
    }
  } else if (prevSel === "__manual__") {
    selEl.value = "__manual__";
    if (manualEl) {
      manualEl.value = prevManual || pref;
      manualEl.style.display = "block";
    }
  } else if (prefInList) {
    selEl.value = pref;
    if (manualEl) {
      manualEl.style.display = "none";
      manualEl.value = "";
    }
  } else if (pref) {
    selEl.value = "__manual__";
    if (manualEl) {
      manualEl.value = pref;
      manualEl.style.display = "block";
    }
  } else if (manualEl) {
    manualEl.style.display = "none";
    manualEl.value = "";
  }
}

/** Box control: always editable; catalog counts are datalist suggestions only. */
function mountBoxQtyForCatalog(mountEl, catalog, brand, line, vitola, preferredVal) {
  if (!mountEl) return;
  const k = catalogBlvKey(brand, line, vitola);
  const boxList = ((catalog.boxes_by_brand_line_vitola && catalog.boxes_by_brand_line_vitola[k]) || [])
    .slice()
    .sort((a, b) => a - b);
  const pv = preferredVal != null && String(preferredVal).trim() !== "" ? String(preferredVal).trim() : "";
  const dl = boxList.length
    ? `<datalist id="box-qty-suggestions">${boxList.map((n) => `<option value="${escapeAttr(String(n))}"></option>`).join("")}</datalist>`
    : "";
  const listAttr = boxList.length ? ' list="box-qty-suggestions"' : "";
  mountEl.innerHTML = `
    <label for="f-box_qty">Box quantity</label>
    <input type="number" id="f-box_qty"${listAttr} value="${escapeAttr(pv)}"
           placeholder="e.g. 20 or 25" min="1" max="100" step="1" autocomplete="off" />
    ${dl}
    <div class="hint-inline">Suggestions from our catalog — type any count if the page differs.</div>
  `;
}

/** Brand: native select of all catalog brands, plus Other + text field. */
function mountBrandSelect(mountEl, catalog, initialBrand) {
  if (!mountEl) return;
  const brands = [...(catalog.brands || [])].sort((a, b) => a.localeCompare(b));
  const tri = (initialBrand || "").trim();
  const inList = tri && brands.includes(tri);
  let html = `<label for="f-brand-sel">Brand</label>`;
  html += `<select id="f-brand-sel">`;
  html += `<option value="">Choose brand…</option>`;
  for (const b of brands) {
    html += `<option value="${escapeAttr(b)}">${escapeHtml(b)}</option>`;
  }
  html += `<option value="__manual__">${escapeHtml("Other / not in catalog…")}</option></select>`;
  html += `<input type="text" id="f-brand-txt" maxlength="80" placeholder="Type brand name…" autocomplete="off" style="display:none;margin-top:6px" />`;
  mountEl.innerHTML = html;
  const sel = document.getElementById("f-brand-sel");
  const txt = document.getElementById("f-brand-txt");
  if (!sel || !txt) return;
  if (!tri) {
    sel.value = "";
    txt.value = "";
    txt.style.display = "none";
  } else if (inList) {
    sel.value = tri;
    txt.value = "";
    txt.style.display = "none";
  } else {
    sel.value = "__manual__";
    txt.value = tri;
    txt.style.display = "block";
  }
}

/** Line: native select of lines for the chosen brand, or free text if brand is Other. */
function mountLineFieldFromBrand(mountEl, catalog, lineInitial) {
  if (!mountEl) return;
  const readBrandState = () => {
    const sel = document.getElementById("f-brand-sel");
    if (!sel) return { kind: "empty" };
    if (!sel.value) return { kind: "empty" };
    if (sel.value === "__manual__") {
      return { kind: "manual", text: (document.getElementById("f-brand-txt")?.value || "").trim() };
    }
    return { kind: "catalog", brand: sel.value.trim() };
  };
  const preserve = (lineInitial != null ? String(lineInitial) : "").trim();
  const st = readBrandState();
  if (st.kind === "empty") {
    mountEl.innerHTML = `<label>Line</label><select id="f-line-sel" disabled><option value="">Select brand first…</option></select>`;
    return;
  }
  if (st.kind === "manual") {
    mountEl.innerHTML = `<label for="f-line-free">Line</label><input type="text" id="f-line-free" maxlength="80" value="${escapeAttr(preserve)}" placeholder="e.g. Hemingway" autocomplete="off" />`;
    return;
  }
  const lines = (catalog.lines_by_brand && catalog.lines_by_brand[st.brand]) || [];
  const sorted = [...lines].sort((a, b) => a.localeCompare(b));
  const inList = preserve && sorted.includes(preserve);
  let html = `<label for="f-line-sel">Line</label>`;
  html += `<select id="f-line-sel">`;
  html += `<option value="">Choose line…</option>`;
  for (const l of sorted) {
    html += `<option value="${escapeAttr(l)}"${l === preserve && inList ? " selected" : ""}>${escapeHtml(l)}</option>`;
  }
  html += `<option value="__manual__"${!inList && preserve ? " selected" : ""}>Other / not in catalog…</option></select>`;
  html += `<input type="text" id="f-line-txt" maxlength="80" placeholder="Type line name…" autocomplete="off" style="display:${!inList && preserve ? "block" : "none"};margin-top:6px" value="${escapeAttr(!inList ? preserve : "")}" />`;
  mountEl.innerHTML = html;
}

function readCandidateBrand() {
  const sel = document.getElementById("f-brand-sel");
  if (!sel) return "";
  if (sel.value === "__manual__") return (document.getElementById("f-brand-txt")?.value || "").trim();
  return (sel.value || "").trim();
}

function readCandidateLine() {
  const free = document.getElementById("f-line-free");
  if (free) return (free.value || "").trim();
  const sel = document.getElementById("f-line-sel");
  const txt = document.getElementById("f-line-txt");
  if (!sel || sel.disabled) return "";
  if (sel.value === "__manual__") return (txt?.value || "").trim();
  return (sel.value || "").trim();
}

function readCandidateVitola() {
  const sel = document.getElementById("f-vitola");
  if (!sel) return "";
  if (sel.value === "__manual__") return (document.getElementById("f-vitola-manual")?.value || "").trim();
  return (sel.value || "").trim();
}

// ── Bootstrap ──────────────────────────────────────────────────────────

(async () => {
  try {
    // Hard gate: if the user hasn't consented yet, send them to the
    // consent screen instead of showing the comparison UI.
    if (!(await hasConsented())) {
      return renderNeedConsent();
    }

    let payload;
    try {
      payload = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ type: "getStatusForTab" }, (resp) => {
          const err = chrome.runtime.lastError;
          if (err) {
            resolve({
              tab: null,
              response: { state: "error", error: err.message },
              scraped: null,
            });
            return;
          }
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
      case "candidate":   return renderCandidate(tab, response, scraped, null);
      case "seen":        return renderSeen(tab, response, scraped);
      case "no_scraper":  return renderNoScraper(tab, response);
      case "non_product": return renderEmpty("Browse a cigar product page to see comparisons.");
      case "error":       return renderError(response.error || "Unknown error");
      default:            return renderError(`Unexpected state: ${response.state}`);
    }
  } catch (e) {
    renderError(String((e && e.message) || e));
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
    const pickRowEmpty = (response.cigar_options && response.cigar_options.length > 1)
      ? `
      <div class="field cigar-picker" style="margin-bottom:12px">
        <label for="cigar-pick" style="font-size:12px;font-weight:600">Which cigar on this page?</label>
        <select id="cigar-pick" style="width:100%;margin-top:4px;padding:6px 8px;font-size:13px;border-radius:6px;border:1px solid #d1d5db">
          ${response.cigar_options.map((o) => `
            <option value="${escapeAttr(o.cigar_id)}" ${o.cigar_id === response.matched_cid ? "selected" : ""}>${escapeHtml(o.label)}</option>
          `).join("")}
        </select>
      </div>`
      : "";
    const displayName = (comparison && comparison.cigar_name)
      || [comparison && comparison.brand, comparison && comparison.line].filter(Boolean).join(" ")
      || "This listing";
    const metaBits = [
      comparison && comparison.wrapper,
      comparison && comparison.vitola,
      comparison && comparison.size,
      (comparison && comparison.box_qty) ? `Box of ${comparison.box_qty}` : "",
    ].filter(Boolean);
    const metaLine = metaBits.length ? metaBits.join(" · ") : "";
    const cidHint = response.matched_cid
      ? `<div class="cigar-cid" style="font-size:11px;color:#6b7280;word-break:break-all;margin-top:6px">CID: ${escapeHtml(response.matched_cid)}</div>`
      : "";

    root.innerHTML = `
      ${renderHeader(tab, response)}
      <div class="banner matched">✓ We track: ${escapeHtml(displayName)}</div>
      <div class="section">
        ${metaLine ? `<div class="cigar-meta" style="font-size:13px;line-height:1.45;margin-bottom:8px">${escapeHtml(metaLine)}</div>` : ""}
        ${cidHint}
        ${pickRowEmpty}
        <div class="empty-state" style="padding: 16px 0;">
          ${escapeHtml(comparison?.reason || "Not enough retailers yet to compare.")}
        </div>
        <div class="actions" style="padding-top:8px">
          <button type="button" id="add-cigar-empty" class="footer-action-btn" style="width:100%">Add cigar</button>
        </div>
      </div>
      <div class="footer">
        <a href="#" id="open-options">Settings</a>
        <a href="https://cigarpricescout.com" target="_blank">cigarpricescout.com</a>
      </div>
    `;
    const addBtn = document.getElementById("add-cigar-empty");
    if (addBtn) {
      addBtn.addEventListener("click", () => {
        renderCandidate(tab, response, scraped, {
          mode: "add_another",
          previousMatched: { tab, response, scraped },
        });
      });
    }
    if (response.cigar_options && response.cigar_options.length > 1) {
      const sel = document.getElementById("cigar-pick");
      if (sel) {
        sel.addEventListener("change", async () => {
          await setPreferredCidForUrl(tab.url, sel.value);
          chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url });
          chrome.runtime.sendMessage({ type: "getStatusForTab" }, (resp) => {
            if (chrome.runtime.lastError) return;
            if (resp && resp.response && resp.tab) {
              renderMatched(resp.tab, resp.response, resp.scraped);
            }
          });
        });
      }
    }
    wireFooter();
    return;
  }

  const cheapest = comparison.results[0];
  const cheapestDeliv = cheapest.delivered_cents;
  const currentPageRetailer = response.retailer_key;
  const currentRow = comparison.this_listing
    || comparison.results.find((r) => r.retailer_key === currentPageRetailer);
  const savingsCents = (currentRow && currentRow.delivered_cents > cheapestDeliv)
    ? currentRow.delivered_cents - cheapestDeliv
    : 0;
  const pageIsCheapestDeal = !!(currentRow && currentRow.delivered_cents === cheapestDeliv);
  const bannerMatched = pageIsCheapestDeal
    ? "✓ You've found the cheapest!"
    : `✓ Cheapest: ${formatMoney(cheapestDeliv)} at ${escapeHtml(cheapest.retailer_name)}`;

  const displayRows = compareRowsForPopup(comparison, tab.url, currentPageRetailer);
  const pickRow = (response.cigar_options && response.cigar_options.length > 1)
    ? `
      <div class="field cigar-picker" style="margin-bottom:12px">
        <label for="cigar-pick" style="font-size:12px;font-weight:600">Which cigar on this page?</label>
        <select id="cigar-pick" style="width:100%;margin-top:4px;padding:6px 8px;font-size:13px;border-radius:6px;border:1px solid #d1d5db">
          ${response.cigar_options.map((o) => `
            <option value="${escapeAttr(o.cigar_id)}" ${o.cigar_id === response.matched_cid ? "selected" : ""}>${escapeHtml(o.label)}</option>
          `).join("")}
        </select>
      </div>`
    : "";

  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner matched">${escapeHtml(bannerMatched)}</div>
    <div class="section">
      <div class="cigar-name">${escapeHtml(comparison.cigar_name || "")}</div>
      <div class="cigar-meta">
        ${escapeHtml(comparison.wrapper || "")} · ${escapeHtml(comparison.vitola || "")} · ${escapeHtml(comparison.size || "")} · Box of ${comparison.box_qty || "?"}
      </div>
      ${pickRow}
      <div class="results">
        ${displayRows.map(({ row, index, thisPage }) =>
          renderResultRow(row, index, cheapestDeliv, { thisPage }),
        ).join("")}
      </div>
      <button type="button" id="view-all" class="view-all-btn">See all ${comparison.total_retailers || comparison.results.length} retailers</button>
      ${savingsCents > 0 ? `
        <div class="savings">
          You'd save ${formatMoney(savingsCents)} by buying from ${escapeHtml(cheapest.retailer_name)}.
        </div>
      ` : ""}
    </div>
    <div class="actions actions-footer-row">
      <div class="actions-three">
        <button type="button" id="report-incorrect" class="footer-action-btn" title="Report incorrect data for this listing">Report incorrect</button>
        <button type="button" id="add-cigar" class="footer-action-btn">Add cigar</button>
        <button type="button" id="close" class="footer-action-btn">Close</button>
      </div>
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
  document.getElementById("report-incorrect").addEventListener("click", () => {
    renderCorrection(tab, response, scraped);
  });
  document.getElementById("add-cigar").addEventListener("click", () => {
    renderCandidate(tab, response, scraped, {
      mode: "add_another",
      previousMatched: { tab, response, scraped },
    });
  });
  document.getElementById("close").addEventListener("click", () => window.close());
  if (response.cigar_options && response.cigar_options.length > 1) {
    const sel = document.getElementById("cigar-pick");
    if (sel) {
      sel.addEventListener("change", async () => {
        await setPreferredCidForUrl(tab.url, sel.value);
        chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url });
        chrome.runtime.sendMessage({ type: "getStatusForTab" }, (resp) => {
          if (resp && resp.response && resp.tab) {
            renderMatched(resp.tab, resp.response, resp.scraped);
          }
        });
      });
    }
  }
  wireFooter();
}

// ── Report-incorrect: edit form pre-filled from current comparison ────

function renderCorrection(tab, response, scraped) {
  const comparison = response.comparison || {};
  const currentRetailerKey = response.retailer_key;
  const currentRow = comparison.this_listing
    || (comparison.results || []).find((r) => r.retailer_key === currentRetailerKey);
  const currentInStock = currentRow && typeof currentRow.in_stock === "boolean"
    ? currentRow.in_stock
    : true;
  // Sale price = delivered minus shipping/tax. This matches what the
  // user sees on the retailer's page, which is what we want them to
  // verify/correct (NOT the delivered total, which would confuse the
  // "no coupons applied" rule).
  const currentSaleCents = currentRow
    ? Math.max(0, (currentRow.delivered_cents || 0) - (currentRow.shipping_cents || 0) - (currentRow.tax_cents || 0))
    : null;
  const currentSaleDollars = currentSaleCents != null ? (currentSaleCents / 100).toFixed(2) : "";

  // Pick the wrapper bucket that best matches the comparison's wrapper.
  // Falls back to "Not sure" so the user can pick something explicit.
  const wrapperGuess = normalizeLegacyWrapperBucket(
    comparison.wrapper ? bucketFromWrapperString(comparison.wrapper) : "",
  );

  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner candidate">Report incorrect data</div>
    <div class="section">
      <div class="cigar-meta" style="line-height:1.45;color:#374151;margin-bottom:10px">
        Edit any field that's wrong and submit. We'll review your correction
        before it goes live. <strong>Don't apply coupon codes</strong> —
        enter the price the page shows BEFORE any code is applied.
      </div>
      <div class="fields" id="correction-form">
        <div class="field">
          <label for="c-brand">Brand</label>
          <input type="text" id="c-brand" value="${escapeAttr(comparison.brand || "")}" maxlength="80" />
        </div>
        <div class="field">
          <label for="c-line">Line</label>
          <input type="text" id="c-line" value="${escapeAttr(comparison.line || "")}" maxlength="80" />
        </div>
        <div class="field">
          <label for="c-vitola">Vitola</label>
          <input type="text" id="c-vitola" value="${escapeAttr(comparison.vitola || "")}" maxlength="80" />
        </div>
        <div class="field">
          <label for="c-wrapper">Wrapper</label>
          <select id="c-wrapper">
            <option value="">Not sure</option>
            <option value="${escapeAttr(NATURAL_LIGHT_WRAPPER_BUCKET)}" ${wrapperGuess === NATURAL_LIGHT_WRAPPER_BUCKET ? "selected" : ""}>${escapeHtml(NATURAL_LIGHT_WRAPPER_BUCKET)}</option>
            <option value="Habano" ${wrapperGuess === "Habano" ? "selected" : ""}>Habano</option>
            <option value="Sun Grown" ${wrapperGuess === "Sun Grown" ? "selected" : ""}>Sun Grown</option>
            <option value="Maduro" ${wrapperGuess === "Maduro" ? "selected" : ""}>Maduro</option>
          </select>
        </div>
        <div class="field-row">
          <div class="field">
            <label for="c-box_qty">Box quantity</label>
            <input type="number" id="c-box_qty" value="${escapeAttr(comparison.box_qty || "")}" min="1" max="100" step="1" />
          </div>
          <div class="field">
            <label for="c-price">Sale price (USD) <span class="hint-inline">no coupons</span></label>
            <input type="number" id="c-price" value="${escapeAttr(currentSaleDollars)}" placeholder="${escapeAttr(currentSaleDollars)}" step="0.01" min="0" />
            <div class="hint-below">Enter the price shown on the page before any coupon code. Coupons are tracked separately.</div>
          </div>
        </div>
        <div class="field field-checkbox-row">
          <label class="checkbox-label" for="c-in-stock">
            <input type="checkbox" id="c-in-stock" ${currentInStock ? "checked" : ""} />
            <span>In stock on this page (uncheck if out of stock)</span>
          </label>
        </div>
      </div>
    </div>
    <div class="actions">
      <button class="approve" id="submit-correction">Submit correction</button>
      <button id="cancel-correction">Cancel</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
    </div>
  `;
  document.getElementById("submit-correction").addEventListener("click", () => {
    submitCorrection(tab, response, scraped, {
      currentSaleCents,
      currentInStock,
      currentBrand: comparison.brand || "",
      currentLine: comparison.line || "",
      currentVitola: comparison.vitola || "",
      currentBoxQty: comparison.box_qty || null,
    });
  });
  document.getElementById("cancel-correction").addEventListener("click", () => {
    renderMatched(tab, response, scraped);
  });
  wireFooter();
}

// Loose mirror of detectWrapperBucket() — but operates on a string that
// already names the wrapper (e.g. "Maduro" or "Connecticut"), not free
// text. Used to pre-select the dropdown when the comparison carries a
// known wrapper.
function bucketFromWrapperString(s) {
  const w = String(s || "").toLowerCase();
  if (!w) return "";
  if (w.includes("sun grown") || w.includes("sungrown")) return "Sun Grown";
  if (w.includes("maduro") || w.includes("oscuro") || w.includes("san andr") || w.includes("broadleaf")) return "Maduro";
  if (w.includes("habano") || w.includes("corojo")) return "Habano";
  if (w.includes("connecticut") || w.includes("cameroon") || w.includes("natural") || w.includes("claro")) return NATURAL_LIGHT_WRAPPER_BUCKET;
  return "";
}

async function submitCorrection(tab, response, scraped, ctx) {
  const btn = document.getElementById("submit-correction");
  btn.disabled = true;
  btn.textContent = "Submitting…";

  const get = (id) => (document.getElementById(id).value || "").trim();
  const brand = get("c-brand");
  const line = get("c-line");
  const vitola = get("c-vitola");
  const wrapper = get("c-wrapper");
  const boxQtyRaw = get("c-box_qty");
  const priceRaw = get("c-price");

  if (!brand || !line || !vitola) {
    btn.disabled = false;
    btn.textContent = "Submit correction";
    toast("Brand, line, and vitola are required.");
    return;
  }

  const proposedBoxQty = boxQtyRaw ? parseInt(boxQtyRaw, 10) : null;
  const proposedPrice = priceRaw ? parseFloat(priceRaw) : null;
  const inStockEl = document.getElementById("c-in-stock");
  const proposed_in_stock = inStockEl ? !!inStockEl.checked : true;
  const current_in_stock = ctx.currentInStock !== undefined ? !!ctx.currentInStock : true;

  // Client-side guards mirror the server-side ones (loose band) so the
  // user gets immediate feedback without a round-trip. Server still
  // validates — these are UX, not security.
  if (proposedPrice != null) {
    if (proposedPrice < 5) {
      btn.disabled = false;
      btn.textContent = "Submit correction";
      toast("Sale price must be at least $5. Don't subtract coupon codes — coupons are tracked separately.");
      return;
    }
    if (proposedPrice > 5000) {
      btn.disabled = false;
      btn.textContent = "Submit correction";
      toast("Sale price must be at most $5,000.");
      return;
    }
    if (ctx.currentSaleCents && ctx.currentSaleCents > 0) {
      const proposedCents = Math.round(proposedPrice * 100);
      const dev = Math.abs(proposedCents - ctx.currentSaleCents) / ctx.currentSaleCents;
      if (dev > 0.75) {
        btn.disabled = false;
        btn.textContent = "Submit correction";
        toast(`That's ${Math.round(dev * 100)}% off the listed price. If a coupon is applied, enter the price BEFORE the coupon.`);
        return;
      }
    }
  }

  try {
    const observerId = await getObserverId();
    const result = await publicFetch("/api/community/report-correction", {
      method: "POST",
      body: {
        observer_id: observerId,
        observer_source: "consumer",
        url: tab.url,
        current_cid: response.matched_cid || null,
        current_price: ctx.currentSaleCents != null ? ctx.currentSaleCents / 100 : null,
        current_in_stock,
        proposed_in_stock,
        proposed_brand: brand,
        proposed_line: line,
        proposed_vitola: vitola,
        proposed_wrapper: wrapper || null,
        proposed_box_qty: proposedBoxQty,
        proposed_price: proposedPrice,
        scraped_title: scraped?.title || scraped?.jsonldName || null,
      },
    });
    chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url });

    if (result && result.status === "no_changes_detected") {
      // Per design: this is a silent thank-you, NOT a queued review.
      renderCorrectionThanks(tab, response, "No changes detected — nothing was sent for review.");
      return;
    }
    if (result && result.status === "applied_immediately") {
      renderCorrectionThanks(
        tab,
        response,
        "Thanks — we applied your price and stock update. Comparisons should reflect it on the next refresh.",
      );
      return;
    }
    renderCorrectionThanks(tab, response, "Thanks — your correction is in our review queue.");
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Submit correction";
    // publicFetch error message is shaped like
    //   "400 Bad Request: {\"error\":\"price_too_low\",\"reason\":\"...\"}"
    // — try to parse the JSON tail and surface the server's `reason`
    // (which is human-readable). Fall back to the raw message if the
    // body wasn't JSON for some reason.
    const raw = (e && e.message) ? e.message : String(e);
    let userMsg = raw;
    const jsonStart = raw.indexOf("{");
    if (jsonStart >= 0) {
      try {
        const body = JSON.parse(raw.slice(jsonStart));
        if (body && body.reason) userMsg = body.reason;
        else if (body && body.error) userMsg = body.error;
      } catch (_) { /* keep raw */ }
    }
    toast(userMsg.length > 220 ? userMsg.slice(0, 220) + "…" : userMsg);
  }
}

function renderCorrectionThanks(tab, response, message) {
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner matched">✓ Got it</div>
    <div class="section">
      <div class="cigar-meta" style="line-height:1.45">${escapeHtml(message)}</div>
    </div>
    <div class="actions">
      <button id="back-to-matched" class="primary">Back to comparison</button>
      <button id="close-thanks">Close</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
    </div>
  `;
  document.getElementById("back-to-matched").addEventListener("click", () => {
    // Re-render from the original response — we don't refetch because
    // the operator hasn't reviewed yet.
    renderMatched(tab, response, null);
  });
  document.getElementById("close-thanks").addEventListener("click", () => window.close());
  wireFooter();
}

/** Build popup rows: top-N comparison plus CPS row for this URL when missing. */
function compareRowsForPopup(comparison, tabUrl, retailerKey) {
  const top = (comparison.results || []).slice();
  const focus = comparison.this_listing;
  const norm = (u) => String(u || "").split("?")[0].trim().toLowerCase();
  const tabU = norm(tabUrl);
  const rowKey = (r) => `${r.retailer_key}|${norm(r.url)}`;

  const out = [];
  const seenRetailers = new Set();

  for (const r of top) {
    const rk = r.retailer_key || "";
    // One row per retailer in the popup — duplicate CSV rows caused twin listings.
    if (rk && seenRetailers.has(rk)) continue;
    if (rk) seenRetailers.add(rk);

    const thisPage = !!(
      retailerKey && rk === retailerKey
      && (!tabU || !norm(r.url) || norm(r.url) === tabU)
    );
    out.push({ row: r, index: out.length, thisPage });
  }

  if (focus) {
    const fk = focus.retailer_key || "";
    const existingIdx = out.findIndex((e) => e.row.retailer_key === fk);
    if (existingIdx >= 0) {
      // Prefer this_listing for the tab retailer (authoritative URL/price).
      out[existingIdx] = { row: focus, index: existingIdx, thisPage: true };
    } else if (!top.some((r) => rowKey(r) === rowKey(focus))) {
      out.push({ row: focus, index: out.length, thisPage: true });
    }
  }
  return out;
}

function thisPagePriceHighlight(row, cheapestDeliv) {
  if (row.in_stock && row.delivered_cents <= cheapestDeliv) return "good";
  return "bad";
}

function renderResultRow(r, idx, cheapestDeliv, opts = {}) {
  const { thisPage = false } = opts;
  const cheapestClass = (r.delivered_cents === cheapestDeliv) ? "cheapest" : "";
  const oosClass = r.in_stock ? "" : "out-of-stock";
  const thisPageClass = thisPage
    ? `this-page this-page-${thisPagePriceHighlight(r, cheapestDeliv)}`
    : "";
  const thisPageLabel = thisPage
    ? `<span class="this-page-badge" title="Cigar Price Scout data for the page you are on">This page</span>`
    : "";
  const authBadge = r.authorized ? `<span class="auth-badge">authorized</span>` : "";
  // Always show a stock badge so users can spot at a glance which
  // retailers actually have the cigar buyable right now — the common
  // case is "looking at an out-of-stock listing, want to find an
  // in-stock one elsewhere." When the user explicitly sees "in stock"
  // on the alternatives, the OOS label on the page they came from
  // becomes much more actionable.
  const stockBadge = r.in_stock
    ? `<span class="stock-badge in-stock">in stock</span>`
    : `<span class="stock-badge out">out of stock</span>`;
  const shipTax = (r.shipping_cents + r.tax_cents) > 0
    ? `<span class="ship-tax">+${formatMoney(r.shipping_cents + r.tax_cents)} ship/tax</span>`
    : "";
  return `
    <a href="${escapeAttr(r.url || '#')}" target="_blank" rel="noopener" class="result-row ${cheapestClass} ${oosClass} ${thisPageClass}">
      <div class="result-rank">${idx + 1}</div>
      <div class="result-name">
        ${escapeHtml(r.retailer_name)}
        ${thisPageLabel}
        ${authBadge}${stockBadge}
      </div>
      <div class="result-price">
        <span class="price-line">${formatMoney(r.delivered_cents)}</span>
        ${shipTax}
      </div>
    </a>
  `;
}

// ── State: candidate (URL unknown — propose metadata) ─────────────────

async function renderCandidate(tab, response, scraped, opts = null) {
  // opts: null | { formStateOverride } | { mode: "add_another", previousMatched: { tab, response, scraped } }
  const mode = opts && opts.mode === "add_another" ? "add_another" : "default";
  const formStateOverride = opts && opts.formStateOverride != null ? opts.formStateOverride : null;
  const previousMatched = opts && opts.previousMatched ? opts.previousMatched : null;
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

  // Volatile fields (wrapper bucket guess, box quantity, price) are
  // page-DOM-driven and don't benefit from catalog snapping — keep
  // the local scrape for those.
  const localGuess = guessFromScrape(tab.url, scraped);

  // Snap brand / line / vitola to our master catalog. The old
  // client-side prefill split the title into token slices, which on
  // real pages produced garbage like brand="Arturo Fuente Cigars" or
  // line="Hemingway Best" — the user had to delete chunks before the
  // form was submittable. The server-side matcher (a) only suggests
  // canonical catalog brands/lines/vitolas, (b) returns empty when no
  // match exists (better an empty field than a wrong one), and (c)
  // returns the catalog whitelists so the form can offer full <select>
  // lists (Chrome popup datalists are flaky). Vitola is chosen before
  // wrapper so the wrapper step can list catalog-specific labels for
  // that vitola (e.g. Dominican Rosado) alongside the four buckets.
  let prefill = { brand: "", line: "", vitola: "" };
  let catalog = defaultCatalogShape();
  try {
    const guessRes = await publicFetch("/api/public/guess-metadata", {
      method: "POST",
      body: {
        url: tab.url || "",
        title: scraped?.title || "",
        jsonld_name: scraped?.jsonldName || "",
        jsonld_brand: scraped?.jsonldBrand || "",
        og_description: scraped?.ogDescription || "",
      },
    });
    if (guessRes?.prefill) prefill = guessRes.prefill;
    if (guessRes?.catalog) catalog = mergeCatalog(guessRes.catalog);
  } catch (_) {
    // Endpoint unreachable or 500 — fall through with blanks. The user
    // can still type freely; the only thing we lose is autocomplete.
  }

  // Apply form-state override (from "Edit my answers"). Lets the user
  // refine their inputs without losing the catalog-snapped prefill +
  // datalists.
  const initialValues = {
    brand:   formStateOverride?.brand   ?? prefill.brand,
    line:    formStateOverride?.line    ?? prefill.line,
    vitola:  formStateOverride?.vitola  ?? prefill.vitola,
    wrapper: formStateOverride?.wrapper ?? localGuess.wrapper_bucket,
    box_qty: (formStateOverride && formStateOverride.box_qty != null)
               ? formStateOverride.box_qty
               : localGuess.box_qty,
    price:   (formStateOverride && formStateOverride.confirmed_price != null)
               ? formStateOverride.confirmed_price
               : localGuess.price,
  };


  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner candidate">${mode === "add_another" ? "+ Add another cigar" : "? Help us identify this cigar"}</div>
    <div class="section">
      <div class="scraper-chip">
        Detected on page: <b>${escapeHtml(scraped?.title || scraped?.jsonldName || tab.title || "(no title)")}</b>
      </div>
      <div class="fields" id="cid-form">
        <div class="field" id="f-brand-mount"></div>
        <div class="field" id="f-line-mount"></div>
        <div class="field">
          <label for="f-vitola">Vitola</label>
          <select id="f-vitola"></select>
          <input type="text" id="f-vitola-manual" maxlength="80" placeholder="Type vitola if not in list…" autocomplete="off" style="display:none;margin-top:6px" />
        </div>
        <div class="field">
          <label for="f-wrapper">Wrapper <span class="hint-inline">(category + catalog names)</span></label>
          <select id="f-wrapper"></select>
        </div>
        <div class="field-row">
          <div class="field" id="box-qty-field"></div>
          <div class="field">
            <label for="f-price">Price (USD)</label>
            <input type="number" id="f-price" value="${escapeAttr(initialValues.price || "")}" placeholder="340.00" step="0.01" min="0" />
          </div>
        </div>
      </div>
    </div>
    <div class="actions">
      <button class="approve" id="submit">Submit</button>
      ${mode === "add_another"
        ? `<button type="button" id="cancel-add-another">Back to comparison</button>`
        : `<button type="button" id="close">Cancel</button>`}
    </div>
    <div class="footer">
      Operator reviews submissions before they go live.
      &nbsp;<a href="#" id="open-options">Settings</a>
    </div>
  `;

  // Master-driven cascade: brand → line → vitola → wrapper → box.
  const brandMount = document.getElementById("f-brand-mount");
  const lineMount = document.getElementById("f-line-mount");
  const wrapperSelect = document.getElementById("f-wrapper");
  const vitolaSelect = document.getElementById("f-vitola");
  const boxQtyMount = document.getElementById("box-qty-field");

  mountBrandSelect(brandMount, catalog, initialValues.brand);
  mountLineFieldFromBrand(lineMount, catalog, initialValues.line);

  let lastBrandSelValue = (document.getElementById("f-brand-sel") || {}).value || "";

  function readBoxPreference() {
    const el = document.getElementById("f-box_qty");
    if (!el) return initialValues.box_qty;
    return (el.value || "").trim() || initialValues.box_qty;
  }

  function runCatalogCascade() {
    const b = readCandidateBrand();
    const l = readCandidateLine();
    const wrapperPrev = (wrapperSelect.value || "").trim();
    const parsedWrapperPrev = parseWrapperSelectValue(wrapperPrev);
    const vitPref =
      readCandidateVitola() ||
      (initialValues.vitola || "").trim();
    mountVitolaSelect(catalog, vitolaSelect, b, l, vitPref);
    const v = readCandidateVitola();
    const scrapeHaystack = [
      scraped?.title,
      scraped?.jsonldName,
      scraped?.ogDescription,
      (scraped?.jsonldRaw && scraped.jsonldRaw.description) || "",
    ].filter(Boolean).join(" ").trim();
    mountWrapperSelectForBrandLineVitola(catalog, wrapperSelect, b, l, v, {
      prevRaw: wrapperPrev,
      preferredPlainBucket:
        parsedWrapperPrev.bucket ||
        (initialValues.wrapper || "").trim() ||
        localGuess.wrapper_bucket,
      scrapeHaystack,
    });
    mountBoxQtyForCatalog(boxQtyMount, catalog, b, l, v, readBoxPreference());
  }

  function wireLineFieldHandlers() {
    const lineSel = document.getElementById("f-line-sel");
    if (lineSel && !lineSel.disabled) {
      lineSel.addEventListener("change", () => {
        const lineTxt = document.getElementById("f-line-txt");
        if (lineTxt) {
          lineTxt.style.display = lineSel.value === "__manual__" ? "block" : "none";
          if (lineSel.value !== "__manual__") lineTxt.value = "";
        }
        runCatalogCascade();
      });
    }
    const lineFree = document.getElementById("f-line-free");
    if (lineFree) {
      lineFree.addEventListener("input", debounce(runCatalogCascade, 250));
      lineFree.addEventListener("blur", runCatalogCascade);
    }
    const lineTxt = document.getElementById("f-line-txt");
    if (lineTxt) {
      lineTxt.addEventListener("input", debounce(runCatalogCascade, 200));
      lineTxt.addEventListener("blur", runCatalogCascade);
    }
  }

  function wireBrandHandlers() {
    const sel = document.getElementById("f-brand-sel");
    const txt = document.getElementById("f-brand-txt");
    if (sel) {
      sel.addEventListener("change", () => {
        if (txt) {
          txt.style.display = sel.value === "__manual__" ? "block" : "none";
          if (sel.value !== "__manual__") txt.value = "";
        }
        const sv = sel.value;
        if (sv !== lastBrandSelValue) {
          lastBrandSelValue = sv;
          mountLineFieldFromBrand(lineMount, catalog, "");
          wireLineFieldHandlers();
        }
        runCatalogCascade();
      });
    }
    if (txt) {
      txt.addEventListener("input", debounce(runCatalogCascade, 300));
      txt.addEventListener("blur", runCatalogCascade);
    }
  }

  wireBrandHandlers();
  wireLineFieldHandlers();
  runCatalogCascade();

  if (vitolaSelect) {
    vitolaSelect.addEventListener("change", runCatalogCascade);
    vitolaSelect.addEventListener("blur", runCatalogCascade);
  }
  const vitolaManual = document.getElementById("f-vitola-manual");
  if (vitolaManual) {
    vitolaManual.addEventListener("input", debounce(runCatalogCascade, 200));
    vitolaManual.addEventListener("blur", runCatalogCascade);
  }
  if (wrapperSelect) {
    wrapperSelect.addEventListener("change", runCatalogCascade);
  }

  if (boxQtyMount) {
    boxQtyMount.addEventListener("input", debounce((ev) => {
      if (ev.target && ev.target.id === "f-box_qty") runCatalogCascade();
    }, 200));
  }

  document.getElementById("submit").addEventListener("click", () => submitProposal(tab, response, scraped));
  const closeBtn = document.getElementById("close");
  if (closeBtn) closeBtn.addEventListener("click", () => window.close());
  const cancelAdd = document.getElementById("cancel-add-another");
  if (cancelAdd && previousMatched) {
    cancelAdd.addEventListener("click", () => {
      renderMatched(previousMatched.tab, previousMatched.response, previousMatched.scraped);
    });
  }
  wireFooter();
}

async function submitProposal(tab, response, scraped) {
  const btn = document.getElementById("submit");
  btn.disabled = true;
  btn.textContent = "Checking…";

  const get = (id) => (document.getElementById(id).value || "").trim();
  const brand = readCandidateBrand();
  const line = readCandidateLine();
  let vitola = readCandidateVitola();
  const wrapperRaw = get("f-wrapper");
  let wrapperBucket = parseWrapperSelectValue(wrapperRaw).bucket;
  if (wrapperRaw === "__manual__") wrapperBucket = "";
  const boxQtyRaw = get("f-box_qty");
  const priceRaw = get("f-price");

  if (!brand || !line || !vitola || !boxQtyRaw) {
    btn.disabled = false;
    btn.textContent = "Submit";
    toast("Brand, line, vitola, and box quantity are required.");
    return;
  }

  const box_qty = parseInt(boxQtyRaw, 10);
  if (!Number.isFinite(box_qty) || box_qty < 1 || box_qty > 100) {
    btn.disabled = false;
    btn.textContent = "Submit";
    toast("Enter a valid box quantity between 1 and 100.");
    return;
  }
  const confirmed_price = priceRaw ? parseFloat(priceRaw) : null;
  const formMeta = {
    brand, line, vitola,
    wrapper: wrapperBucket || null,
    box_qty,
    confirmed_price,
    scraped_title: scraped?.title || scraped?.jsonldName || null,
  };

  try {
    const observerId = await getObserverId();

    // Step 1: "Is this the cigar?" preview. Server runs the HIGH-
    // confidence matcher and (a) returns a human-readable candidate
    // when it finds one, or (b) returns null so we fall through to the
    // operator-review queue. Doing this BEFORE writing anything means
    // a user who picks "No, not quite" doesn't accidentally publish a
    // wrong CID — they get the standard review-queue flow.
    let preview = null;
    try {
      preview = await publicFetch("/api/community/preview-candidate", {
        method: "POST",
        body: {
          observer_id: observerId,
          observer_source: "consumer",
          url: tab.url,
          ...formMeta,
        },
      });
    } catch (_) {
      // Preview is best-effort. If it fails (network blip, server
      // hiccup), fall through to the legacy review-queue path so the
      // user doesn't lose their submission.
      preview = null;
    }

    if (preview && preview.candidate && preview.candidate.cigar_id) {
      const conf = (preview.candidate.confidence || "").toUpperCase();
      if (conf === "HIGH") {
        btn.textContent = "Publishing…";
        try {
          await executeConfirmCandidate(tab, response, scraped, formMeta, preview.candidate);
          return;
        } catch (e) {
          toast(`Could not auto-publish (${e.message || e}). Please confirm manually.`);
          renderCigarConfirm(tab, response, scraped, formMeta, preview.candidate);
          return;
        }
      }
      renderCigarConfirm(tab, response, scraped, formMeta, preview.candidate);
      return;
    }

    // No candidate available → submit straight to the operator review
    // queue with the form state.
    await submitToReviewQueue(tab, response, scraped, formMeta, observerId);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Submit";
    toast(`Submit failed: ${e.message || e}`);
  }
}


// ── "Is this the cigar?" confirmation screen ──────────────────────────
//
// Renders a card with the candidate CID parsed into readable form and
// three actions: YES (auto-publish), NO (operator review), Edit. YES
// is the primary because most candidates the matcher offers will be
// correct — this is HIGH-confidence only on the server side.

// Shared body for "Yes, that's it" and for HIGH-confidence auto-confirm
// after preview-candidate.
async function executeConfirmCandidate(tab, response, scraped, formMeta, candidate) {
  const observerId = await getObserverId();
  const confirmRes = await publicFetch("/api/community/confirm-candidate", {
    method: "POST",
    body: {
      observer_id: observerId,
      observer_source: "consumer",
      url: tab.url,
      cigar_id: candidate.cigar_id,
      scraped_title: formMeta.scraped_title,
      confirmed_price: formMeta.confirmed_price,
      in_stock: null,
    },
  });
  chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url });

  if (confirmRes && confirmRes.comparison
      && confirmRes.comparison.results
      && confirmRes.comparison.results.length > 0) {
    renderProvisionalComparison(tab, response, scraped, confirmRes);
    return;
  }
  renderSubmittedWithSearch(tab, response, scraped, formMeta);
}

function renderCigarConfirm(tab, response, scraped, formMeta, candidate) {
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner candidate">? Is this the cigar?</div>
    <div class="section">
      <div class="cigar-meta" style="font-size:14px; line-height:1.5">
        We found a likely match in our catalog:
      </div>
      <div class="candidate-card">
        <div class="candidate-label">${escapeHtml(candidate.label || "")}</div>
      </div>
      <div class="hint-below">
        Confirming maps this page to that cigar so you (and everyone else)
        can compare prices across retailers right away.
      </div>
    </div>
    <div class="actions">
      <button class="approve" id="confirm-yes">Yes, that's it</button>
      <button id="confirm-no">No, not quite</button>
    </div>
    <div class="actions" style="padding-top:0">
      <button class="link-btn" id="confirm-edit">Edit my answers</button>
    </div>
    <div class="footer">
      <a href="#" id="open-options">Settings</a>
    </div>
  `;

  document.getElementById("confirm-yes").addEventListener("click", async () => {
    const yesBtn = document.getElementById("confirm-yes");
    const noBtn = document.getElementById("confirm-no");
    yesBtn.disabled = true;
    if (noBtn) noBtn.disabled = true;
    yesBtn.textContent = "Publishing…";
    try {
      await executeConfirmCandidate(tab, response, scraped, formMeta, candidate);
    } catch (e) {
      yesBtn.disabled = false;
      if (noBtn) noBtn.disabled = false;
      yesBtn.textContent = "Yes, that's it";
      toast(`Couldn't publish: ${e.message || e}`);
    }
  });

  document.getElementById("confirm-no").addEventListener("click", async () => {
    // User rejected the candidate. Route to operator review (likely a
    // new CID is needed). Same payload as before — just no auto-publish.
    const noBtn = document.getElementById("confirm-no");
    const yesBtn = document.getElementById("confirm-yes");
    noBtn.disabled = true;
    if (yesBtn) yesBtn.disabled = true;
    noBtn.textContent = "Sending…";
    try {
      const observerId = await getObserverId();
      await submitToReviewQueue(tab, response, scraped, formMeta, observerId);
    } catch (e) {
      noBtn.disabled = false;
      if (yesBtn) yesBtn.disabled = false;
      noBtn.textContent = "No, not quite";
      toast(`Submit failed: ${e.message || e}`);
    }
  });

  document.getElementById("confirm-edit").addEventListener("click", () => {
    // Go back to the form with the user's last inputs preserved so they
    // don't have to retype everything.
    renderCandidate(tab, response, scraped, { formStateOverride: formMeta });
  });

  wireFooter();
}


// Submit the user's metadata to the operator review queue (legacy path).
// Extracted from the old submitProposal so both "No, not quite" and the
// no-candidate fallback can call the same code without duplication.
async function submitToReviewQueue(tab, response, scraped, formMeta, observerId) {
  const proposeRes = await publicFetch("/api/community/propose-metadata", {
    method: "POST",
    body: {
      observer_id: observerId,
      observer_source: "consumer",
      url: tab.url,
      brand: formMeta.brand,
      line: formMeta.line,
      vitola: formMeta.vitola,
      wrapper: formMeta.wrapper,
      box_qty: formMeta.box_qty,
      confirmed_price: formMeta.confirmed_price,
      scraped_title: formMeta.scraped_title,
    },
  });
  chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url });

  // Same instant-feedback shortcut as before: propose-metadata's own
  // server-side auto-matcher may still return a comparison when the
  // preview path didn't (e.g. cache was cold at preview time). Honor it.
  if (proposeRes && proposeRes.comparison
      && proposeRes.comparison.results
      && proposeRes.comparison.results.length > 0) {
    renderProvisionalComparison(tab, response, scraped, proposeRes);
    return;
  }
  renderSubmittedWithSearch(tab, response, scraped, formMeta);
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
  const currentRow = comparison.this_listing
    || comparison.results.find((r) => r.retailer_key === currentPageRetailer);
  const savingsCents = (currentRow && currentRow.delivered_cents > cheapestDeliv)
    ? currentRow.delivered_cents - cheapestDeliv
    : 0;
  const pageIsCheapestDeal = !!(currentRow && currentRow.delivered_cents === cheapestDeliv);
  const bannerProvisional = pageIsCheapestDeal
    ? "✓ You've found the cheapest!"
    : `✓ Cheapest: ${formatMoney(cheapestDeliv)} at ${escapeHtml(cheapest.retailer_name)}`;
  const conf = (proposeRes.match && proposeRes.match.confidence) || "HIGH";
  const displayRows = compareRowsForPopup(comparison, tab.url, currentPageRetailer);

  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner matched">${escapeHtml(bannerProvisional)}</div>
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
        ${displayRows.map(({ row, index, thisPage }) =>
          renderResultRow(row, index, cheapestDeliv, { thisPage }),
        ).join("")}
      </div>
      <button type="button" id="view-all" class="view-all-btn">See all ${comparison.total_retailers || comparison.results.length} retailers</button>
      ${savingsCents > 0 ? `
        <div class="savings">
          You'd save ${formatMoney(savingsCents)} by buying from ${escapeHtml(cheapest.retailer_name)}.
        </div>
      ` : ""}
    </div>
    <div class="actions actions-footer-row">
      <button type="button" id="close" class="footer-action-btn footer-action-btn-wide">Close</button>
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
  ["connecticut",        NATURAL_LIGHT_WRAPPER_BUCKET],
  ["cameroon",           NATURAL_LIGHT_WRAPPER_BUCKET],
  ["claro",              NATURAL_LIGHT_WRAPPER_BUCKET],
  ["natural",            NATURAL_LIGHT_WRAPPER_BUCKET],
];

function detectWrapperBucket(...texts) {
  const haystack = texts.filter(Boolean).join(" ").toLowerCase();
  if (!haystack) return "";
  for (const [phrase, bucket] of WRAPPER_BUCKET_KEYWORDS) {
    if (haystack.includes(phrase)) return bucket;
  }
  return "";
}

// NOTE: As of the catalog-snap rollout, only the non-text fields here
// (wrapper_bucket, box_qty, price) are actually surfaced to the user
// before /guess-metadata; renderCandidate then snaps brand/line/vitola
// and orders vitola before wrapper so wrapper can list catalog labels.
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

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function escapeAttr(s) { return escapeHtml(s); }
