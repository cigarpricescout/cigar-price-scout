# Cigar Price Scout — Consumer Chrome Extension

The public-facing Chrome extension. Anonymous, opt-in, box-only.

## What it does

When the user lands on a known cigar retailer's product page:

* **State `matched`** — the URL is in a retailer CSV. The popup shows the
  top-3 cheapest retailers carrying the same CID (delivered prices,
  shipping/tax estimated by user's ZIP) and a savings callout.
* **State `candidate`** — known retailer, unknown URL. The popup shows
  a 5-field "help us identify this cigar" form: brand, line, vitola,
  box quantity, price. All fields are pre-filled from the scraper and
  editable. Submission posts to `/api/community/propose-metadata`.
* **State `seen`** — someone already proposed this URL or the operator
  already touched it. Popup shows "under review."
* **State `no_scraper`** — known cigar-adjacent domain but no extractor
  built. Popup offers "Suggest this retailer."
* **State `non_product`** — homepage, cart, etc. Popup is empty.
* Pack-of-5 or single variants on any box-CID URL show "We track box
  prices only — switch to the box variant." (Sprint 2 scoping decision.)

## Backend dependencies

| Endpoint | Why |
|---|---|
| `GET /api/public/retailer-registry` | Bootstrap: which hostnames to activate on. |
| `GET /api/public/url-status` | Single-call popup state + inline comparison data. |
| `POST /api/community/observe` | Passive price observation (consent-gated). |
| `POST /api/community/propose-metadata` | "Help us identify this cigar" form submit. |
| `POST /api/community/delete-my-observations` | Options page "Forget me" button. |

All endpoints are no-auth; observer identity is a per-install random hex
ID stored in `chrome.storage.local`. The same ID acts as bearer for the
delete-me request.

## Privacy guarantees baked into the code

* Observation **never** fires before `consent.html` has been accepted.
  See `hasConsented()` gate in `config.js`.
* Observation **only** fires on hostnames present in the public
  retailer registry. See `resolveRetailerKey()` gate in
  `background.js#refreshForTab`.
* Observation **never** fires on non-product paths (homepage,
  `/collections`, `/cart`, `/checkout`, etc.). See
  `looksLikeProductPage()` in `background.js`.
* Per-canonical-URL dedupe (1 hour, persisted in
  `chrome.storage.session`) prevents accidental flooding.
* Observer ID is rotatable from the options page; rotation does NOT
  delete past observations (the user can use the explicit "Delete my
  data" button for that).

## Local install (dev)

1. Open `chrome://extensions`.
2. Enable "Developer mode" (top right).
3. Click **Load unpacked**.
4. Select this directory (`consumer-extension/`).
5. The consent screen opens in a new tab.
6. Pin the extension to the toolbar for easy access.

The extension is independent from `extension/` (the operator extension).
Both can be installed side-by-side; they use different storage keys and
different observer IDs.

## Pre-Web-Store TODO

* Narrow `host_permissions` from `<all_urls>` to a static list of
  registered retailer hostnames (generate via a small Python script
  reading `/api/public/retailer-registry` into `manifest.json`).
* Add real `icons/` (16, 32, 48, 128 px).
* Privacy policy URL in the Web Store listing.
* Screenshot set + promotional images.
* Toggle "consent default" question — currently opt-in; some app stores
  may require an explicit unchecked default.
