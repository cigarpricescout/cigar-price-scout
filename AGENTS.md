# Cigar Price Scout — System Reference

This file is the canonical hand-off doc for AI agents (or humans) joining the
project. It explains how the site works end-to-end so you can be productive
without spelunking through every file.

If you change anything architectural, **update this file in the same PR**.

---

## 1. What this product is

`cigarpricescout.com` is a price-comparison site for premium cigars. Visitors
search a brand/line/wrapper/vitola/size and get a sorted list of retailers
with delivered prices (base + shipping + tax). It runs as a FastAPI app on
Railway with PostgreSQL for analytics + staging tables, SQLite for the master
cigar catalog, and per-retailer CSVs for product data.

Two Chrome extensions live alongside the site:
- **`extension/`** — operator-only, admin-gated. Manually maps URLs to CIDs.
- **`consumer-extension/`** — public, Web Store-ready. Anonymous passive
  observation + CID proposals.

---

## 2. The three price-data input methods

This is the single most important thing to understand. There are **three**
parallel pipelines feeding `/compare`, each with different identifiers,
trust models, and quality controls:

| # | Source | Storage | Identifier | Trust model |
|---|---|---|---|---|
| 1 | **Automated scrapers** (extractors → CSV) | `static/data/{key}.csv` | n/a | Operator-curated; CSV is canonical |
| 2 | **Website form** `/submit-deal` / `/api/community-price` | `community_prices` PG table | `voter_hash` (SHA256 of IP) | 3-downvote auto-deactivation |
| 3 | **Chrome extension** (operator + consumer) | `observed_prices` + `community_url_proposals` PG tables | `observer_id` (random per-install hash) | Operator review queue + box-qty guard |

All three merge into `load_all_products()` in `app/main.py`. As of commit
`ff61839`, sources #2 and #3 are deduplicated against #1 by:
- **Canonical URL** match (strongest — strips `?variant=`, `utm_*`, etc.)
- **`(retailer_key, cigar_id)`** match (resolves source #2's freeform
  retailer name to a canonical key via URL hostname or fuzzy name match)

CSV/observed wins on collision. Drops are logged at INFO level.

---

## 3. Data flow at a glance

```
                          ┌──────────────────────────────┐
                          │ Visitor opens /compare        │
                          └──────────────┬───────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────┐
                          │ load_all_products()  (cached) │
                          └──────────────┬───────────────┘
            ┌────────────────┬───────────┴───────────┬────────────────┐
            │                │                       │                │
            ▼                ▼                       ▼                ▼
       CSV rows      observed_prices         community_url_      community_prices
       (RETAILERS)   (last-14d aggregate,    proposals          (legacy website form)
                     blocked retailers only) (operator-approved
                                              only — appears via
                                              future flow)

      dedup: canonical URL ∪ (retailer_key, cigar_id)
                          │
                          ▼
                /compare results
```

**Write paths:**

- Source 1: local extractors (in `tools/price_monitoring/retailers/`) write
  per-retailer CSVs; CI commits + pushes.
- Source 2: `POST /api/community-price` from `/submit-deal` page form.
- Source 3:
  - Passive: `POST /api/community/observe` from the consumer extension's
    background worker (gated by consent + product-page filter + dedup).
  - Active: `POST /api/community/propose-metadata` from the popup's
    candidate-state 5-field form.

---

## 4. Key tables (Postgres unless noted)

| Table | Owner | Purpose |
|---|---|---|
| `observed_prices` | community | Raw per-URL price readings from the consumer extension. Indexed on url, cigar_id, retailer_key (all + observed_at DESC). |
| `community_url_proposals` | community | Consumer-submitted metadata for URLs not yet mapped to a CID. Operator approves/edits/rejects via admin tooling. |
| `community_retailer_requests` | community | Per-observer requests to add a new retailer. Lazy-fulfilled when hostname enters the registry; powers `chrome.notifications` in the consumer extension. |
| `community_prices` | legacy website | Website-form-submitted prices. Older system; kept running but dedup'd in `/compare`. |
| `community_votes` | legacy website | Downvote ledger for `community_prices`. |
| `extension_staged_approvals` | operator extension | Operator-staged URL → CID approvals. Drained by `tools/extension/publish_extension_approvals.py` into local CSVs + master DB. |
| `pending_new_retailers` | operator extension | URLs the operator hit on unknown hostnames + consumer retailer requests. |
| `url_skip_list` | operator extension | URLs marked "skip" by the operator. |
| `review_decisions` | shared | Every operator approve/edit/reject decision. Future ML reviewer training data. |
| `search_events` | analytics | One row per `/compare` request. Used for popularity analytics. |
| `master_cigars` (SQLite) | local + Railway | The 2300+ CID master catalog. `data/master_cigars.db` (SQLite) is canonical; `data/master_cigars.csv` is the human-editable mirror. |

Master CSV → DB sync is handled by `tools/master/` scripts.

---

## 5. Endpoints

### Public (no auth)

| Method | Path | Use |
|---|---|---|
| GET | `/` | Homepage |
| GET | `/compare?brand=&line=&...` | The core comparison results |
| GET | `/options` | Brand → line → wrapper → vitola dropdown tree |
| GET | `/cigars/{brand-slug}/{line-slug}` | SEO landing page |
| GET | `/submit-deal` | Promotional deal submission form (legacy) |
| POST | `/api/submit-deal` | Promotional deal submission backend |
| POST | `/api/community-price` | Legacy community-price form submission |
| POST | `/api/report-row` | Downvote a `community_prices` row |

### Public consumer-extension API (`/api/public/*` and `/api/community/*`)

| Method | Path | Use |
|---|---|---|
| GET  | `/api/public/retailer-registry` | Hostnames the extension activates on |
| GET  | `/api/public/url-status?url=&zip=` | Single-call popup state (matched / candidate / seen / no_scraper) + inline top-3 comparison |
| POST | `/api/community/observe` | Anonymous passive price observation |
| POST | `/api/community/propose-metadata` | Consumer-suggested brand/line/vitola/box_qty/price for an unmapped URL |
| POST | `/api/community/request-retailer` | "Please add this retailer" — observer-linked |
| GET  | `/api/community/my-requests?observer_id=` | Polled by extension every 6h for chrome.notifications |
| POST | `/api/community/delete-my-observations` | GDPR-friendly forget-me. `observer_id` acts as the bearer. |

### Operator-only admin API (`/api/admin/*`, requires `X-Admin-Key` or `?key=`)

| Method | Path | Use |
|---|---|---|
| GET  | `/api/admin/retailer-registry` | Full registry view |
| GET  | `/api/admin/url-status?url=` | Per-URL state for the operator extension |
| GET  | `/api/admin/master-vocab` | Brand/line/vitola/wrapper vocab for the popup datalist |
| POST | `/api/admin/stage-approval` | Stage an extension approval |
| POST | `/api/admin/skip-url` | Add a URL to `url_skip_list` |
| GET  | `/api/admin/pending-new-retailers` | Operator queue of unknown-retailer URLs |
| GET  | `/api/admin/retailer-requests` | Aggregated by hostname — prioritize anti-bot retailers to onboard |
| GET  | `/api/admin/observed-prices-recent` | Debug: most recent observations |
| POST | `/api/admin/cleanup-orphan-observations` | Delete non-product / tracking-param / empty observation rows |
| POST | `/api/admin/mark-extension-published` | Local publisher confirms a row landed in the CSV |
| POST | `/api/admin/resolve-proposal` | Operator approves/edits/rejects a `community_url_proposals` row |

Note: `/api/admin/url-status` also returns a `community_proposal` object
on every response (null when none exists) so the operator extension
popup can pre-fill the candidate form from a consumer's submission. When
the operator approves a URL with a pending proposal, the
`/api/admin/stage-approval` body accepts `community_proposal_id` — the
backend then flips `community_url_proposals.status='approved'` and
stamps `resolved_cid` in the same transaction, closing the consumer
contribution loop end-to-end.

`POST /api/community/propose-metadata` runs a server-side CID match
against `master_cigars` after insert. When the submission resolves to a
single CID at HIGH confidence (with exact `box_qty` match and a
wrapper-bucket-compatible `wrapper_code`), the response includes a
`comparison` object the consumer popup renders immediately as a
provisional price-comparison card. The proposal still queues for
operator review; the consumer just sees value right away. Lower-
confidence matches return `comparison: null` and the consumer sees the
standard "submitted for review" toast.

---

## 6. Retailer config (`RETAILERS` list in `app/main.py`)

Every retailer is a row in `RETAILERS`. Fields:

| Field | Required | Meaning |
|---|---|---|
| `key` | yes | Internal id; must equal `static/data/{key}.csv`'s stem. |
| `name` | yes | Display name. |
| `csv` | yes | Path to the per-retailer CSV. Empty file (header-only) is legal. |
| `authorized` | yes | Affiliate / authorized-dealer flag. Affects UI badge. |
| `extractor_status` | no, default `"active"` | `"active"` (daily scraper fills price/title/in_stock) / `"blocked"` (anti-bot — no scraper; operator-entered price is the data source) / `"dormant"` (scraper broken/paused; treated like blocked). |
| `hostname` | no | Explicit primary hostname. **Required** for `blocked` retailers (their CSVs are empty so the registry can't infer one). |

`extractor_status` drives two consumer-of-the-data UIs:

- **Operator extension popup** (`extension/popup.js`): when `blocked` or
  `dormant`, the candidate form renders editable **Price (USD)** and
  **In stock** fields (pre-filled from the page scrape). For `active`
  retailers the fields are hidden because the daily extractor will
  overwrite anything entered there.
- **Local publisher** (`tools/extension/publish_extension_approvals.py`):
  for `active` writes a *bare row* (only `cigar_id` + `url`, scraper
  fills the rest later); for `blocked`/`dormant` writes a *full row*
  with title/brand/line/wrapper/vitola/size/box_qty/price/in_stock so
  the data appears immediately in `/compare`. Re-approving the same
  (cid, url) on a blocked retailer **refreshes** the row's price/stock
  so operators can update stale prices by re-visiting the page.

**Onboarding a new retailer:**

1. Add a row to `RETAILERS`. For an anti-bot retailer, set
   `extractor_status="blocked"` and `hostname="..."`.
2. Create an empty `static/data/{key}.csv` with the standard header.
3. Deploy. The registry picks up the hostname automatically.
4. Anyone who previously called `/api/community/request-retailer` for that
   hostname gets a `chrome.notification` on their next poll.

For an `active` (scrapable) retailer, also build the extractor under
`tools/price_monitoring/retailers/` and wire it into the daily automation.

---

## 7. CID format

All cigars are uniquely identified by an 8-part pipe-delimited canonical
ID built by `app.cid_matcher.build_cid()`:

```
BRAND|PARENTBRAND|LINE|VITOLA|VITOLA2|SIZE|WRAPPERCODE|BOXQTY
```

Examples:
- `ARTUROFUENTE|ARTUROFUENTE|HEMINGWAY|SIGNATURE|SIGNATURE|6x46|SUN|BOX25`
- `MYFATHER|MYFATHER|LEBIJOU1922|TORO|TORO|6x52|HAB|BOX23`

Rules:
- All segments uppercase, whitespace-stripped.
- `SIZE` is `LENGTH×RING` (e.g., `6x46`).
- `WRAPPERCODE` is a short code (SUN, HAB, MAD, CON, etc.). Human-readable
  wrapper name lives in the master catalog, not the CID. Consumers never
  see the codes — they pick from 4 friendly buckets defined in
  `app/wrapper_buckets.py` (Natural/Connecticut, Habano, Sun Grown,
  Maduro) which map to canonical codes. The bucket name is stored as
  `community_url_proposals.proposed_wrapper`; the operator picks the
  canonical code during review.
- `BOXQTY` is `BOX25` / `PACK5` / `SINGLE`. The box quantity is part of the
  identity — a Box-of-25 and a Pack-of-5 of the "same" cigar are different
  CIDs because they have different prices and trust signals.

The `_resolve_cigar_id_from_url()` guard in `app/community_endpoints.py`
**refuses** to attach a CID to an observation when the observation's
detected `box_qty` contradicts the CID's encoded `BOXQTY`. This prevents
"$70 for cigar_id=...BOX25" nonsense when a Shopify page hosts both
variants under one URL.

---

## 8. URL canonicalization

`app.cid_matcher.canonicalize_url()` is applied at **every API boundary**
(observe, propose-metadata, request-retailer, url-status, stage-approval,
skip-url). It strips:

- Tracking query params: `variant`, `gclid`, `fbclid`, `utm_*`, `ref`,
  `aff*`, `_pos`, `_sid`, `mc_cid`, `yclid`, etc.
- Tracking prefixes: `utm_`, `matomo_`, `mtm_`, `pk_`, `piwik_`
- Trailing slash from path; lowercases scheme + host.

This is why a user clicking a `?variant=46267620622467` URL still hits the
url_index entry that was published with the clean canonical URL.

---

## 9. Deployment model

```
                ┌─────────────────────┐
                │   GitHub (main)     │
                └──────────┬──────────┘
                           │   git push
        ┌──────────────────┴──────────────────┐
        ▼                                     ▼
  Railway deploy                       Local publisher
  (FastAPI app)                        (PowerShell scheduled task)
        │                                     │
        │  reads                              │  drains Postgres staging
        │  CSVs from git                      │  → writes CSVs locally
        │  writes ONLY to                     │  → git pull --rebase
        │  Postgres                           │  → git commit + push
        ▼                                     ▼
   cigarpricescout.com                   master_cigars.db (SQLite)
                                         data/master_cigars.csv
```

**Critical rule:** Railway never writes to CSVs or to the master SQLite DB.
Only the local publisher does. Railway-side writes go to Postgres only
(observed_prices, community_url_proposals, extension_staged_approvals,
pending_new_retailers, community_prices, etc.).

This means: the operator's "approve a CID" decision happens on Railway
(POST `/api/admin/stage-approval`), but the actual write to
`static/data/{key}.csv` happens on the local Windows machine when the
publisher next runs, which then pushes to GitHub, which redeploys Railway.

---

## 10. Operator-facing workflows

### Daily

The local publisher (PowerShell scheduled task) drains:
- `extension_staged_approvals` → per-retailer CSVs (+ master row for new CIDs).
- `pending_new_retailers` → `tools/ai/new_retailer_queue.txt`.

Then `git pull --rebase` + commit + push, which triggers a Railway redeploy.

### Weekly

Monday 7am: `automation/run_weekly_discovery.py` runs (see
`AI_WORKFLOW_INSTRUCTIONS.md`). It identifies new URLs found by the
extractors that don't yet have CIDs, runs the AI matcher, and stages
high-confidence matches into `extension_staged_approvals` for operator
review via `tools/ai/review_matches.py`.

### Ad-hoc: onboarding an anti-bot retailer

1. Check `/api/admin/retailer-requests` for the highest-demand hostname.
2. Edit `app/main.py` — add a `RETAILERS` row with
   `extractor_status="blocked"` + `hostname`.
3. Add an empty `static/data/{key}.csv` (header only).
4. Commit + push. Railway redeploys.
5. On next poll (within 6 hours), every consumer who requested that
   hostname gets a `chrome.notification`.

### Ad-hoc: approving a community CID proposal

(Operator-side UI not built yet as of 2026-05-13. Workflow:)
1. `GET /api/admin/observed-prices-recent` to see context.
2. `POST /api/admin/resolve-proposal` with the proposal_id and either:
   - `action="approve_existing"` + `cid="..."`, OR
   - `action="approve_new"` + `cid_parts={...}` (creates a new master CID).
3. The local publisher next picks up the resulting `extension_staged_approvals` row.

---

## 11. Manual smoke test playbook

Run this whenever the three input methods have changed and you want to
verify they still cooperate cleanly. Estimated time: ~15 minutes.

> **Easy mode:** Open `https://cigarpricescout.com/admin/smoke-tests?key=YOUR_ADMIN_SECRET_KEY`
> for a click-driven version of every test below. Each card has an "Open
> test URL" button and a "Refresh" button that pulls live state from the
> admin API and shows pass/fail badges. The dashboard is the canonical UI
> for this section; the manual SQL below is the fallback.

### Prereqs

- Operator extension loaded at `chrome://extensions` (sideloaded from
  `extension/`).
- Consumer extension loaded at `chrome://extensions` (sideloaded from
  `consumer-extension/`).
- Admin key set in the operator extension's options page.
- A Postgres client (psql, TablePlus, Railway data tab — anything).

### Test 1: extractor → CSV → /compare

**Goal:** Confirm the canonical path still works.

1. Pick any cigar in the master catalog that's on multiple retailers, e.g.
   `Arturo Fuente / Hemingway / Signature`.
2. Visit `https://cigarpricescout.com/compare?brand=Arturo%20Fuente&line=Hemingway&vitola=Signature&size=6x46`.
3. **Expect:** ≥2 retailer rows, prices > $0, in-stock dots correct,
   `price_source: "csv"` for each row in the JSON response (open DevTools
   network tab or hit the URL directly).

### Test 2: Chrome extension observation (matched URL)

**Goal:** Confirm passive observation + retro-CID attachment works.

1. With both extensions loaded and the consumer extension consented in,
   open a known retailer + cigar URL, e.g.
   `https://baysidecigars.com/products/arturo-fuente-hemingway-signature`.
2. Wait ~3 seconds for the badge to turn green (`$`).
3. Click the consumer extension popup. **Expect:** "Cheapest: $X at Y"
   banner with top-3 rows. At least one row should carry a
   📊 "Last seen YYYY-MM-DD" badge (the bayside row, since it's `blocked`).
4. In Postgres:
   ```sql
   SELECT url, retailer_key, cigar_id, price_cents, quantity_type, observed_at
   FROM observed_prices ORDER BY id DESC LIMIT 3;
   ```
   **Expect:** Newest row has `retailer_key='baysidecigars'`, `cigar_id`
   set to the Hemingway Signature BOX25 CID, `quantity_type='box'`.

### Test 3: Chrome extension proposal (unmapped URL)

**Goal:** Confirm candidate-state form posts cleanly.

1. Pick a URL the system DOESN'T know yet on a blocked retailer, e.g. an
   unfamiliar JR Cigars product page.
2. Click the consumer extension popup. **Expect:** Amber "? Help us
   identify this cigar" banner with a 5-field form (Brand, Line, Vitola,
   Box Qty, Price) pre-filled from the page scrape.
3. Fix any wrong fields, hit Submit.
4. In Postgres:
   ```sql
   SELECT id, url, retailer_key, proposed_brand, proposed_line,
          proposed_vitola, proposed_box_qty, confirmed_price_cents, status
   FROM community_url_proposals ORDER BY id DESC LIMIT 1;
   ```
   **Expect:** New row with `status='pending'`, `confirmed_price_cents`
   matches what you submitted (×100).

### Test 4: New retailer request flow

**Goal:** Confirm the `chrome.notifications` plumbing.

1. Open the consumer extension on a retailer that's NOT in the registry,
   e.g. `https://www.cigarsdaily.com` (or any non-cigar retailer site).
2. Popup **Expect:** "We don't track ... yet" with "Request this retailer".
3. Click Request this retailer. **Expect:** Toast "we'll notify you when
   it goes live".
4. In Postgres:
   ```sql
   SELECT observer_id, hostname, requested_at, fulfilled_at
   FROM community_retailer_requests ORDER BY id DESC LIMIT 1;
   ```
   **Expect:** New row with `fulfilled_at IS NULL`.
5. **Operator side:** add the retailer to `RETAILERS` + create an empty
   CSV, deploy.
6. Wait up to 6 hours (or reload the extension to force the poll). When
   the consumer's `my-requests` endpoint runs, the row's `fulfilled_at`
   gets set and (if the OS allows it) a `chrome.notification` fires.

### Test 5: Website community-price form

**Goal:** Confirm the legacy path still writes.

1. Visit `/submit-deal` and submit a price for a real cigar URL on a
   retailer that doesn't appear in `RETAILERS`, e.g. a small boutique.
2. In Postgres:
   ```sql
   SELECT id, retailer_name, brand, line, price_cents, url, submitted_at
   FROM community_prices ORDER BY id DESC LIMIT 1;
   ```
   **Expect:** Your submission landed.
3. Visit `/compare?brand=...&line=...` for that cigar. **Expect:** The
   community submission appears as a row labeled with `community: true`.

### Test 6: Dedup (the new piece)

**Goal:** Confirm the website form doesn't duplicate extension data.

1. Find a (URL, retailer, cigar) tuple where:
   - The extension has produced an `observed_prices` row, AND
   - You can submit the same product via `/submit-deal`.
2. Submit the same URL via `/submit-deal`.
3. Visit `/compare` for that cigar. **Expect:** ONE row for that retailer,
   not two.
4. Railway logs should contain a line like
   `load_all_products: dropped 1 community submission(s) ...`.

### Test 7: "Forget me"

**Goal:** GDPR-style deletion works.

1. In the consumer extension, open Options → "Delete my data". Confirm.
2. In Postgres:
   ```sql
   SELECT COUNT(*) FROM observed_prices WHERE observer_id='<your_id>';
   SELECT COUNT(*) FROM community_url_proposals WHERE observer_id='<your_id>';
   SELECT COUNT(*) FROM community_retailer_requests WHERE observer_id='<your_id>';
   ```
   **Expect:** All three return 0.

If any test fails, **stop and investigate before shipping changes** —
this playbook is the contract between the three pipelines.

---

## 12. Codebase map

Files you'll touch most often, grouped by concern:

### Backend (FastAPI on Railway)

- `app/main.py` — App entry, `RETAILERS` list, `Product` class,
  `load_all_products()`, all the website-facing routes (`/`, `/compare`,
  `/options`, `/submit-deal`, `/api/community-price`, etc.).
- `app/cid_matcher.py` — CID parsing/building, retailer registry,
  URL canonicalization, master catalog loader, programmatic URL→CID matcher.
- `app/extension_endpoints.py` — Operator admin API (`/api/admin/*`),
  cache state, table init for staging tables.
- `app/community_endpoints.py` — Public consumer-extension API
  (`/api/community/*` and `/api/public/*`), table init for community tables.

### Extensions

- `extension/` — Operator extension. Sideloaded only. Admin-keyed.
- `consumer-extension/` — Consumer extension. Web-Store-shape, anonymous.
  See `consumer-extension/README.md` for the user-facing privacy promises.

### Local publisher + automation (run on Windows, never on Railway)

- `tools/extension/publish_extension_approvals.py` — drains
  `extension_staged_approvals` → CSVs + master DB.
- `tools/extension/sync_new_retailer_queue.py` — drains
  `pending_new_retailers` → `tools/ai/new_retailer_queue.txt`.
- `automation/run_weekly_discovery.py` — Monday 7am scheduled task.
- `automation/automated_cigar_price_system.py` — daily extractor +
  publisher orchestrator.
- `tools/price_monitoring/retailers/{retailer}_extractor.py` — one per
  active retailer.
- `tools/ai/review_matches.py` — operator review CLI for staged matches.

### Data + static

- `static/data/{key}.csv` — one per retailer. Header:
  `cigar_id,title,url,brand,line,wrapper,vitola,size,box_qty,price,in_stock,current_promotions_applied`.
- `data/master_cigars.db` (SQLite) + `data/master_cigars.csv` — master
  catalog. SQLite is canonical.
- `data/historical_prices.db` (SQLite) — local price history archive.

---

## 13. Conventions and gotchas

- **PowerShell, not bash.** This is a Windows dev machine. Use `;` to
  chain commands; `&&` is invalid PowerShell syntax. Use `working_directory`
  in Shell tool calls instead of `cd path && cmd`.
- **Never write CSVs from Railway.** All CSV writes happen on the local
  publisher. Anything else creates merge conflicts and lost data.
- **Always canonicalize URLs at the boundary.** Every endpoint that
  accepts a URL must call `canonicalize_url()` before lookups or
  storage. The url_index is keyed by canonical URLs.
- **Box-only comparison.** `/compare` only shows `quantity_type='box'`
  rows. Pack/single rows are captured (in `observed_prices`) but never
  surface in the comparison. If we ever add singles support, audit
  `_load_observed_overlay` and the popup's matched-state copy.
- **CID box-qty is identity, not metadata.** Never attach a CID to an
  observation whose box_qty contradicts the CID's encoded BOXQTY.
- **The operator extension is `extension/`. The consumer extension is
  `consumer-extension/`.** They share scraping logic but talk to
  different API surfaces — operator hits `/api/admin/*` with an admin
  key, consumer hits `/api/public/*` and `/api/community/*` anonymously.
- **`observer_id` is the foundation for future badges/dashboards/watchlists.**
  Don't break its meaning. Every contribution table already carries it.
- **Dormant retailers** (those with `DORMANT` in the CSV filename, or
  `extractor_status="dormant"`) are skipped entirely by
  `build_retailer_registry()` and `load_csv()`. Use this when sunsetting
  a retailer without deleting historical data.

---

## 14. When in doubt

- For "how do these three input methods interact?" → read section 2 + 3.
- For "what tables exist?" → section 4.
- For "what endpoints exist?" → section 5.
- For "how do I add a new retailer?" → section 6 + 10.
- For "is this change safe to ship?" → run section 11.
- For "what file owns X?" → section 12.

Last updated: 2026-05-13, commit `ff61839`.
