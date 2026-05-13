# Cigar Price Scout — CID Match Chrome Extension

A Manifest V3 Chrome extension that proposes a CID for the retailer product
page you're currently viewing, lets you approve or edit the proposed CID, and
stages the result for the daily automation to publish.

## How it fits with the rest of the project

1. **You browse to any retailer product page** (any host with an extractor in
   `tools/price_monitoring/retailers/` and a CSV in `static/data/`).
2. Background worker auto-fetches `GET /api/admin/url-status?url=…` and sets a
   badge:
   - `?` — fresh URL, a CID candidate is proposed.
   - `OK` — already published in the live retailer CSV.
   - `...` — already staged via this extension or the weekly agent.
   - `+` — no scraper for this host; offer to queue for onboarding.
3. **Click the extension icon** → popup opens with the proposed CID prefilled
   into 8 editable fields. Approve = stage; Skip = remember and ignore.
4. Approvals land in Postgres (`extension_staged_approvals`). They are NEVER
   written to CSVs by Railway.
5. On your next daily automation run (or manual
   `tools/extension/publish_extension_batch.ps1`) the local publisher:
   - Pulls the latest CSVs (`git pull --rebase`).
   - For new CIDs, appends to `data/master_cigars.csv` and upserts into
     `data/master_cigars.db`.
   - For every approval, appends a **bare** row to
     `static/data/{retailer_key}.csv` (just `cigar_id` + `url`, every other
     column empty — exactly your manual-add convention).
   - Marks rows as `published`.
   - Commits + pushes.
6. The retailer's existing extractor fills in `title` / `price` / `in_stock`
   on the next price-update step.

## Loading the extension

1. Open `chrome://extensions`.
2. Toggle **Developer mode** on (top-right).
3. Click **Load unpacked** and select this `extension/` folder.
4. Click the puzzle-piece icon in the Chrome toolbar and pin "Cigar Price
   Scout — CID Match".
5. Click the extension icon, then **Settings** (or right-click the icon →
   Options). Paste your `ADMIN_SECRET_KEY` and click **Test connection**.
   You should see `OK — N retailers known…`.

## Day-to-day usage

- Browse to a retailer product page.
- Wait a beat (badge will update).
- Click the icon.
- For a **candidate**: tweak any of the 8 CID fields if needed (the CID
  preview updates live), then click **Approve**. Or click **Skip** if it's
  not a product page.
- For an **already-matched** URL: the popup just confirms what CID it points
  to. Click **Re-review** if you want to change it (use this carefully — it
  supersedes the previous approval).
- For a **no-scraper** host: click **Add to new-retailer queue** to drop the
  URL into `tools/ai/new_retailer_queue.txt` on the next local publish.

## Materializing approvals

Either:

- **Automatic**: do nothing — your daily automation
  (`automation/automated_cigar_price_system.py` step 2.4) now drains
  extension approvals before retailer scrapers run.
- **Manual** (anytime): from a PowerShell prompt with `ADMIN_SECRET_KEY` set:
  ```powershell
  pwsh tools/extension/publish_extension_batch.ps1
  ```
  This pulls, drains, commits, and pushes. Add `-DryRun` to see what would
  happen without writing.

## What this extension WILL NOT do

- Write to any CSV, the master SQLite DB, or `tools/ai/new_retailer_queue.txt`
  directly. All writes go through the admin-gated API into Postgres, and a
  local script run by you (or your daily automation) does the file writes
  after `git pull`. This is the same architecture as your existing weekly-
  discovery approval flow — extended, not replaced.
- Change any existing endpoint, table, or website read path. Everything
  added is purely additive and admin-gated.
- Work without `ADMIN_SECRET_KEY` — you can install it but the popup will
  prompt you to set it.

## Files

| File | Purpose |
|------|---------|
| `manifest.json`   | MV3 manifest |
| `background.js`   | Service worker — tab listener + URL-status cache + badge |
| `popup.html/.js/.css` | 5-state popup UI |
| `options.html/.js`    | One-field admin-key settings page |
| `config.js`       | Shared API + storage helpers |
