// Popup UI. Reads the cached url-status from the background worker, renders
// one of 5 states, and dispatches user actions (approve / skip / queue new
// retailer) to the backend.

import { apiFetch, getAdminKey } from "./config.js";

const root = document.getElementById("root");

const WRAPPER_CODES = [
  "MAD", "NAT", "CAM", "ECU", "HAB", "SUM", "BRZ", "MEX", "NIC", "HON",
  "DOM", "OSC", "CON", "CORO", "CRIO", "ROS", "SUN", "CAND", "OLOR",
];

// ── Bootstrapping ─────────────────────────────────────────────────────

(async function init() {
  const adminKey = await getAdminKey();
  if (!adminKey) {
    renderNoAdminKey();
    return;
  }

  let payload;
  try {
    payload = await chrome.runtime.sendMessage({ type: "getStatusForTab" });
  } catch (e) {
    return renderError(`Background worker error: ${e.message || e}`);
  }
  if (!payload || payload.error) {
    return renderError(payload && payload.error || "No active tab.");
  }

  const { tab, response } = payload;
  if (!response) {
    return renderError("Could not reach the backend. Check your admin key / network.");
  }
  if (response.state === "error") {
    return renderError(response.error || "Unknown backend error.");
  }

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
    <div class="section">
      <div class="section-label">Matched CID</div>
      <div class="cid-display">${escapeHtml(response.matched_cid || "—")}</div>
    </div>
    ${renderScraped(response)}
    <div class="actions">
      <button class="secondary" id="re-review">Re-review</button>
      <button class="skip" id="close">Close</button>
    </div>
    <div class="footer"><a href="#" id="open-options">Settings</a></div>
  `;
  wireMatchedActions(tab, response);
}

function renderSeen(tab, response) {
  const label = (response.seen_status || "").replace("_", " ");
  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="banner seen">Status: ${escapeHtml(label)}</div>
    <div class="section">
      <div class="section-label">Previously matched to</div>
      <div class="cid-display">${escapeHtml(response.matched_cid || "—")}</div>
    </div>
    ${renderScraped(response)}
    <div class="actions">
      <button class="secondary" id="re-review">Re-review</button>
      <button class="skip" id="close">Close</button>
    </div>
    <div class="footer"><a href="#" id="open-options">Settings</a></div>
  `;
  wireMatchedActions(tab, response);
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
  const parts = top
    ? splitCid(top.cigar_id)
    : suggestPartsFromUrl(tab.url, response.scraped_title);

  root.innerHTML = `
    ${renderHeader(tab, response)}
    <div class="section">
      <div class="section-label">
        Proposed CID
        ${top ? `<span class="confidence ${top.confidence}">${top.confidence} ${(top.score*100|0)}%</span>` : ""}
      </div>
      <div class="cid-display" id="cid-preview">${escapeHtml(buildCidString(parts))}</div>
      ${top ? renderMatchChips(top.details) : ""}
      ${renderScraped(response)}

      <div class="fields" id="cid-fields">
        ${field("brand",         "Brand",         parts.brand,         "text")}
        ${field("parent_brand",  "Parent Brand",  parts.parent_brand,  "text")}
        ${field("line",          "Line",          parts.line,          "text")}
        ${field("vitola",        "Vitola",        parts.vitola,        "text")}
        ${field("vitola2",       "Vitola2",       parts.vitola2,       "text")}
        ${field("size",          "Size (LxR)",    parts.size,          "text")}
        ${wrapperField(parts.wrapper_code)}
        ${field("box_qty",       "Box Qty",       parts.box_qty,       "number")}
      </div>

      ${alts.length ? `
        <div class="section-label" style="margin-top:10px">Other candidates</div>
        <div class="candidates" id="alt-candidates">
          ${alts.map(c => `
            <div class="cand" data-cid="${escapeAttr(c.cigar_id)}">
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
  return `
    <div class="field ${full ? "full" : ""}">
      <label for="f-${name}">${label}</label>
      <input id="f-${name}" name="${name}" type="${type}" value="${escapeAttr(value ?? "")}" />
    </div>
  `;
}

function wrapperField(value) {
  const options = WRAPPER_CODES.map(c =>
    `<option value="${c}" ${c === value ? "selected" : ""}>${c}</option>`
  ).join("");
  const custom = value && !WRAPPER_CODES.includes(value)
    ? `<option value="${escapeAttr(value)}" selected>${escapeHtml(value)} (custom)</option>`
    : "";
  return `
    <div class="field">
      <label for="f-wrapper_code">Wrapper Code</label>
      <select id="f-wrapper_code" name="wrapper_code">
        <option value=""></option>
        ${custom}${options}
      </select>
    </div>
  `;
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
  // Live-update the CID preview as the user edits.
  const fields = document.querySelectorAll("#cid-fields input, #cid-fields select");
  const preview = document.getElementById("cid-preview");
  fields.forEach(f => f.addEventListener("input", () => {
    preview.textContent = buildCidString(readFields());
  }));

  // Click alt candidate → populate the form with its parts.
  const alts = document.getElementById("alt-candidates");
  if (alts) {
    alts.querySelectorAll(".cand").forEach(el => {
      el.addEventListener("click", () => {
        const cid = el.getAttribute("data-cid");
        const parts = splitCid(cid);
        applyFields(parts);
        preview.textContent = cid;
      });
    });
  }

  document.getElementById("approve").addEventListener("click", () => approve(tab, response));
  document.getElementById("skip").addEventListener("click", () => skipUrl(tab.url));
  document.getElementById("open-options").addEventListener("click", openOptions);
}

function readFields() {
  const get = id => (document.getElementById(`f-${id}`) || {}).value || "";
  return {
    brand: (get("brand") || "").trim().toUpperCase(),
    parent_brand: (get("parent_brand") || get("brand") || "").trim().toUpperCase(),
    line: (get("line") || "").trim().toUpperCase(),
    vitola: (get("vitola") || "").trim().toUpperCase(),
    vitola2: (get("vitola2") || get("vitola") || "").trim().toUpperCase(),
    size: (get("size") || "").trim().toLowerCase(),
    wrapper_code: (get("wrapper_code") || "").trim().toUpperCase(),
    box_qty: parseInt(get("box_qty"), 10) || 0,
  };
}

function applyFields(parts) {
  for (const [k, v] of Object.entries(parts)) {
    const el = document.getElementById(`f-${k}`);
    if (!el) continue;
    el.value = v ?? "";
  }
}

async function approve(tab, response) {
  const parts = readFields();
  const errors = validateParts(parts);
  if (errors.length) return toast(errors[0], "error");

  const body = {
    url: tab.url,
    retailer_key: response.retailer_key,
    cid_parts: parts,
    title: response.scraped_title || (response._scraped && response._scraped.title) || "",
    create_if_missing: true,
    force: !!response._force,
    confidence: "EXTENSION",
    reason: "Approved via Chrome extension",
  };
  const btn = document.getElementById("approve");
  btn.disabled = true;
  btn.textContent = "Approving…";
  try {
    const res = await apiFetch("/api/admin/stage-approval", { method: "POST", body });
    chrome.runtime.sendMessage({ type: "invalidateCache", url: tab.url }).catch(() => {});
    toast(res.mode === "new_cid" ? "Approved (new CID staged)" : "Approved");
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

function buildCidString(p) {
  const box = p.box_qty ? `BOX${p.box_qty}` : "";
  return [
    p.brand || "",
    p.parent_brand || p.brand || "",
    p.line || "",
    p.vitola || "",
    p.vitola2 || p.vitola || "",
    p.size || "",
    p.wrapper_code || "",
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

function suggestPartsFromUrl(url, scrapedTitle) {
  // Very minimal fallback when there are zero candidates: leave fields blank,
  // user fills in from the page.
  return {
    brand: "", parent_brand: "", line: "", vitola: "", vitola2: "",
    size: "", wrapper_code: "", box_qty: "",
  };
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
