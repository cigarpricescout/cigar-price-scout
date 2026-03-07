# DORMANT RETAILERS - REQUIRES INVESTIGATION

## CC Crafter (cccrafter-DORMANT.csv)
**Issue:** JavaScript-dependent Box/Single variation pricing
- Site uses dynamic JS to load box-specific stock when option is selected
- Static HTML scraping cannot determine Box vs Single stock accurately
- Per-stick vs box price detection works, but stock requires headless browser
- **Priority:** Low (would need Selenium/Playwright implementation)

## Gotham Cigars (gothamcigars-DORMANT.csv)
**Issue:** Unreliable price extraction - multiple pricing options on page
- Site shows Single, 5-Pack, and Box prices
- Using min() captures single prices, using max() captures inflated prices
- Padron 1964 Imperial: Shows $489.99 on site, extractor pulls $389.26
- Attempting to fix Imperial broke 3 other products (+35% to +176% price increases)
- **Root Cause:** Need context-aware extraction that identifies "Box of 25" specifically
- **Priority:** HIGH - investigate site structure and implement targeted box price extraction
- **Next Steps:**
  1. Manually inspect HTML of problem products
  2. Identify consistent pattern for box pricing context
  3. Implement regex/selector that finds price adjacent to "Box of X" text
  4. Test on 10+ products before re-enabling

## Neptune Cigar (neptune-BROKEN.csv)
**Issue:** Empty CSV (0 products)
- CSV exists but has no product data
- Automation script fails when processing empty CSV
- **Priority:** Medium - may have been intentionally removed
- **Next Steps:** Determine if Neptune should be populated or permanently removed

---

**Automation Behavior:** Script automatically skips retailers when CSV file doesn't exist (line 305 check).
Dormant CSVs are renamed to prevent processing.

**Date:** 2026-03-05
**Last Updated By:** AI Assistant
