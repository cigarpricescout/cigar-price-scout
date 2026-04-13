"""
Catalog Harvester — Shopify-first, zero-AI-cost CID matching.

Detects Shopify retailers, scrapes their full product catalogs via the
public /products.json API, and fuzzy-matches products against unmonitored
CIDs from master_cigars.csv.

Usage:
    python tools/catalog_harvester.py                   # detect + harvest + match, write CSV
    python tools/catalog_harvester.py --detect-only      # just print which retailers are Shopify
    python tools/catalog_harvester.py --upload            # also upload matches to staging API
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from rapidfuzz import fuzz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MASTER_CSV = PROJECT_ROOT / "data" / "master_cigars.csv"
DATA_DIR = PROJECT_ROOT / "static" / "data"
OUTPUT_DIR = PROJECT_ROOT / "tools" / "catalog_harvester_output"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

RETAILER_DOMAINS = {
    "absolutecigars":   "absolutecigars.com",
    "atlantic":         "atlanticcigar.com",
    "bighumidor":       "www.bighumidor.com",
    "bnbtobacco":       "www.bnbtobacco.com",
    "cigarboxpa":       "www.cigarboxpa.com",
    "cigardepot":       "cigardepot.us",
    "cigarhustler":     "cigarhustler.com",
    "cigarking":        "www.cigarking.com",
    "cigarsdirect":     "www.cigarsdirect.com",
    "coronacigar":      "www.coronacigar.com",
    "foxcigar":         "foxcigar.com",
    "hilands":          "www.hilandscigars.com",
    "holts":            "www.holts.com",
    "iheartcigars":     "iheartcigars.com",
    "nickscigarworld":  "nickscigarworld.com",
    "planetcigars":     "www.planetcigars.com",
    "pyramidcigars":    "pyramidcigars.com",
    "smallbatchcigar":  "www.smallbatchcigar.com",
    "smokeinn":         "www.smokeinn.com",
    "stogies":          "stogiesworldclasscigars.com",
    "tampasweethearts": "www.tampasweethearts.com",
    "thecigarshop":     "www.thecigarshop.com",
    "tobaccolocker":    "tobaccolocker.com",
    "tobaccostock":     "www.tobaccostock.com",
    "twoguys":          "www.2guyscigars.com",
    "watchcity":        "watchcitycigar.com",
}

# ---------------------------------------------------------------------------
# CID Parsing
# ---------------------------------------------------------------------------

def parse_cid(cid: str) -> dict:
    """Parse a pipe-delimited CID into its components."""
    parts = cid.split("|")
    if len(parts) < 8:
        return {}
    box_match = re.match(r"BOX(\d+)", parts[7])
    return {
        "cid": cid,
        "brand": parts[0].replace("|", " "),
        "parent_brand": parts[1],
        "line": parts[2],
        "vitola": parts[3],
        "size": parts[5],
        "wrapper_code": parts[6],
        "box_qty": int(box_match.group(1)) if box_match else None,
    }


def load_master_cids() -> list[dict]:
    """Load all CIDs from master_cigars.csv with human-readable metadata."""
    cids = []
    with open(MASTER_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid_str = row.get("cigar_id", "").strip()
            if not cid_str:
                continue
            parsed = parse_cid(cid_str)
            if parsed:
                parsed["brand_display"] = row.get("Brand", "").strip()
                parsed["line_display"] = row.get("Line", "").strip()
                parsed["vitola_display"] = row.get("Vitola", "").strip()
                parsed["wrapper_display"] = row.get("Wrapper", "").strip()
                parsed["box_qty_master"] = row.get("Box Quantity", "").strip()
                cids.append(parsed)
    return cids


def load_monitored_cids() -> dict[str, set]:
    """Return {retailer_key: set(cid)} for all active retailer CSVs."""
    monitored = defaultdict(set)
    for f in DATA_DIR.glob("*.csv"):
        if any(x in f.name for x in ["DORMANT", "BROKEN", "backup"]):
            continue
        key = f.stem
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                for row in csv.DictReader(fh):
                    cid = row.get("cigar_id", "").strip()
                    if cid:
                        monitored[key].add(cid)
        except Exception:
            pass
    return dict(monitored)


# ---------------------------------------------------------------------------
# Shopify Detection & Catalog Harvesting
# ---------------------------------------------------------------------------

def detect_shopify(domain: str) -> bool:
    """Check if a domain is a Shopify store by probing /products.json."""
    url = f"https://{domain}/products.json?limit=1"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "products" in data:
                return True
    except Exception:
        pass
    return False


def harvest_shopify_catalog(domain: str, retailer_key: str) -> list[dict]:
    """Fetch the full Shopify product catalog via /products.json pagination."""
    products = []
    page = 1
    base_url = f"https://{domain}/products.json?limit=250&page="

    while True:
        url = f"{base_url}{page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("products", [])
        except Exception as e:
            print(f"    [WARN] Page {page} failed for {domain}: {e}")
            break

        if not batch:
            break

        for p in batch:
            handle = p.get("handle", "")
            title = p.get("title", "")
            vendor = p.get("vendor", "")
            product_type = p.get("product_type", "")
            tags = p.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]

            variants = []
            for v in p.get("variants", []):
                variants.append({
                    "title": v.get("title", ""),
                    "price": v.get("price", "0"),
                    "compare_at_price": v.get("compare_at_price"),
                    "available": v.get("available"),
                })

            products.append({
                "retailer_key": retailer_key,
                "domain": domain,
                "handle": handle,
                "url": f"https://{domain}/products/{handle}",
                "title": title,
                "vendor": vendor,
                "product_type": product_type,
                "tags": tags,
                "variants": variants,
            })

        print(f"    Page {page}: {len(batch)} products")
        page += 1
        time.sleep(1.0)

    return products


# ---------------------------------------------------------------------------
# Box Variant Extraction
# ---------------------------------------------------------------------------

def find_box_variant(variants: list[dict]) -> dict | None:
    """Find the box variant from a list of Shopify variants.
    Returns the variant dict with parsed box_qty, or None."""
    for v in variants:
        title = (v.get("title") or "").lower()
        if "box" in title:
            qty_match = re.search(r"(\d+)", title)
            if qty_match:
                return {**v, "box_qty": int(qty_match.group(1))}
            return {**v, "box_qty": None}

    if len(variants) == 1:
        title = (variants[0].get("title") or "").lower()
        if "pack" not in title and "single" not in title:
            return {**variants[0], "box_qty": None}

    return None


# ---------------------------------------------------------------------------
# Fuzzy CID Matching
# ---------------------------------------------------------------------------

BRAND_ALIASES = {
    "liga": "drew estate",
    "liga privada": "drew estate",
    "fuente": "arturo fuente",
    "opusx": "arturo fuente",
    "opus x": "arturo fuente",
    "padron": "padron",
    "padrón": "padron",
    "my father": "my father",
    "oliva": "oliva",
    "ashton": "ashton",
    "cohiba": "cohiba",
    "rocky patel": "rocky patel",
    "rp": "rocky patel",
    "perdomo": "perdomo",
    "macanudo": "macanudo",
    "crowned heads": "crowned heads",
    "cao": "cao",
    "lfd": "la flor dominicana",
    "la flor": "la flor dominicana",
    "foundation": "foundation",
    "montecristo": "montecristo",
    "hoyo": "hoyo de monterrey",
    "romeo": "romeo y julieta",
    "diamond crown": "diamond crown",
    "aging room": "aging room",
}


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[''`\-]", " ", text)
    text = re.sub(r"[^a-z0-9\s.]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _resolve_brand(vendor: str, title: str) -> str:
    """Try to resolve a canonical brand name from vendor or title."""
    combined = _normalize(f"{vendor} {title}")
    for alias, canonical in BRAND_ALIASES.items():
        if alias in combined:
            return canonical
    return _normalize(vendor)


def score_match(product: dict, box_variant: dict, cid: dict) -> dict:
    """Score how well a Shopify product matches a CID. Returns a dict with
    score (0-100), confidence level, and reason."""

    product_title = _normalize(product.get("title", ""))
    product_vendor = _normalize(product.get("vendor", ""))
    product_brand = _resolve_brand(product.get("vendor", ""), product.get("title", ""))
    product_tags = " ".join(_normalize(t) for t in product.get("tags", []))
    product_text = f"{product_title} {product_vendor} {product_tags}"

    cid_brand = _normalize(cid["brand_display"])
    cid_line = _normalize(cid["line_display"])
    cid_vitola = _normalize(cid["vitola_display"])
    cid_box_qty = cid.get("box_qty")

    score = 0
    reasons = []

    brand_score = fuzz.token_set_ratio(cid_brand, product_brand)
    if brand_score < 60:
        brand_score = fuzz.partial_ratio(cid_brand, product_text)
    if brand_score >= 75:
        score += 30
        reasons.append(f"brand={brand_score}")
    elif brand_score >= 50:
        score += 15
        reasons.append(f"brand~={brand_score}")
    else:
        return {"score": 0, "confidence": "NONE", "reason": "brand mismatch"}

    line_score = fuzz.token_set_ratio(cid_line, product_title)
    if line_score < 60:
        line_score = max(line_score, fuzz.partial_ratio(cid_line, product_title))
    if line_score >= 80:
        score += 30
        reasons.append(f"line={line_score}")
    elif line_score >= 60:
        score += 15
        reasons.append(f"line~={line_score}")
    else:
        return {"score": 0, "confidence": "NONE", "reason": f"line mismatch ({line_score})"}

    vitola_score = fuzz.token_set_ratio(cid_vitola, product_title)
    if vitola_score >= 80:
        score += 25
        reasons.append(f"vitola={vitola_score}")
    elif vitola_score >= 55:
        score += 10
        reasons.append(f"vitola~={vitola_score}")
    else:
        vitola_in_tags = fuzz.partial_ratio(cid_vitola, product_tags)
        if vitola_in_tags >= 80:
            score += 15
            reasons.append(f"vitola_tag={vitola_in_tags}")

    variant_box_qty = box_variant.get("box_qty")
    if cid_box_qty and variant_box_qty:
        if cid_box_qty == variant_box_qty:
            score += 15
            reasons.append("box_qty=exact")
        elif abs(cid_box_qty - variant_box_qty) <= 2:
            score += 8
            reasons.append(f"box_qty~={variant_box_qty}")

    if score >= 80:
        confidence = "HIGH"
    elif score >= 55:
        confidence = "MEDIUM"
    elif score >= 35:
        confidence = "LOW"
    else:
        confidence = "NONE"

    return {
        "score": score,
        "confidence": confidence,
        "reason": ", ".join(reasons),
    }


def match_catalog_to_cids(
    products: list[dict],
    unmonitored_cids: list[dict],
    retailer_key: str,
    monitored_for_retailer: set,
) -> list[dict]:
    """Match harvested products against unmonitored CIDs for a retailer."""
    matches = []
    already_matched_cids = set()

    for product in products:
        box_variant = find_box_variant(product.get("variants", []))
        if not box_variant:
            continue

        price = box_variant.get("price", "0")
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            price_float = 0
        if price_float < 30:
            continue

        best_match = None
        best_score = 0

        for cid in unmonitored_cids:
            if cid["cid"] in monitored_for_retailer:
                continue
            if cid["cid"] in already_matched_cids:
                continue

            result = score_match(product, box_variant, cid)
            if result["score"] > best_score and result["confidence"] != "NONE":
                best_score = result["score"]
                best_match = {
                    "cid": cid["cid"],
                    "brand": cid["brand_display"],
                    "line": cid["line_display"],
                    "vitola": cid["vitola_display"],
                    "wrapper": cid["wrapper_display"],
                    "cid_box_qty": cid.get("box_qty"),
                    "retailer_key": retailer_key,
                    "product_title": product["title"],
                    "product_url": product["url"],
                    "product_vendor": product.get("vendor", ""),
                    "variant_title": box_variant.get("title", ""),
                    "variant_price": price,
                    "variant_box_qty": box_variant.get("box_qty"),
                    "available": box_variant.get("available"),
                    "score": result["score"],
                    "confidence": result["confidence"],
                    "reason": result["reason"],
                }

        if best_match and best_match["confidence"] in ("HIGH", "MEDIUM"):
            matches.append(best_match)
            already_matched_cids.add(best_match["cid"])

    return matches


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

OUTPUT_FIELDS = [
    "confidence", "score", "cid", "brand", "line", "vitola", "wrapper",
    "cid_box_qty", "retailer_key", "product_title", "product_url",
    "product_vendor", "variant_title", "variant_price", "variant_box_qty",
    "available", "reason",
]


def write_matches_csv(matches: list[dict], path: Path):
    """Write matches to a CSV sorted by confidence then score."""
    conf_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    matches.sort(key=lambda m: (conf_order.get(m["confidence"], 9), -m["score"]))

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(matches)


def upload_to_staging_api(matches: list[dict]):
    """Upload matches to the existing url_staged_matches API."""
    base_url = os.environ.get("APP_BASE_URL", "").rstrip("/")
    secret = os.environ.get("ADMIN_SECRET_KEY", "")
    if not base_url or not secret:
        print("[SKIP] APP_BASE_URL or ADMIN_SECRET_KEY not set, skipping upload")
        return

    upload_url = f"{base_url}/api/admin/upload-matches"
    headers = {"X-Admin-Key": secret, "Content-Type": "application/json"}
    payload = []
    for m in matches:
        payload.append({
            "cid": m["cid"],
            "retailer_key": m["retailer_key"],
            "url": m["product_url"],
            "confidence": m["confidence"],
            "reason": f"Catalog harvester: {m['reason']} | "
                      f"product='{m['product_title']}' variant='{m['variant_title']}' "
                      f"price=${m['variant_price']}",
            "brand": m["brand"],
            "line": m["line"],
            "vitola": m["vitola"],
            "wrapper": m["wrapper"],
            "size": "",
            "box_qty": m.get("variant_box_qty") or m.get("cid_box_qty") or "",
            "price": m.get("variant_price"),
            "in_stock": m.get("available"),
        })

    BATCH = 200
    total_uploaded = 0
    for i in range(0, len(payload), BATCH):
        batch = payload[i:i + BATCH]
        try:
            resp = requests.post(
                upload_url,
                json={"matches": batch},
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            total_uploaded += data.get("uploaded", 0)
            print(f"  Batch {i // BATCH + 1}: uploaded {data.get('uploaded', 0)} new matches")
        except Exception as e:
            print(f"  Batch {i // BATCH + 1}: FAILED - {e}")

    print(f"[OK] Uploaded {total_uploaded} / {len(payload)} matches to staging API")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def upload_csv_to_staging(csv_path: str, confidence_filter: str = ""):
    """Read matches from a previously generated CSV and upload them to the staging API."""
    import csv as csv_mod
    path = Path(csv_path)
    if not path.exists():
        print(f"[ERROR] File not found: {csv_path}")
        return

    matches = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv_mod.DictReader(f)
        for row in reader:
            if confidence_filter and row.get("confidence", "") != confidence_filter:
                continue
            matches.append(row)

    print(f"Loaded {len(matches)} matches from {path.name}")
    if confidence_filter:
        print(f"  (filtered to {confidence_filter} only)")

    if not matches:
        print("Nothing to upload.")
        return

    upload_to_staging_api(matches)


def main():
    parser = argparse.ArgumentParser(description="Catalog Harvester")
    parser.add_argument("--detect-only", action="store_true",
                        help="Only detect Shopify retailers, don't harvest")
    parser.add_argument("--upload", action="store_true",
                        help="Upload matches to the staging API after harvesting")
    parser.add_argument("--upload-csv", type=str, default=None,
                        help="Upload matches directly from an existing CSV file (skips harvest)")
    parser.add_argument("--confidence", type=str, default="",
                        help="Filter to a confidence level when using --upload-csv (e.g. HIGH)")
    parser.add_argument("--retailer", type=str, default=None,
                        help="Only process a specific retailer key")
    args = parser.parse_args()

    if args.upload_csv:
        upload_csv_to_staging(args.upload_csv, args.confidence)
        return

    print("=" * 70)
    print("CATALOG HARVESTER — Shopify Detection + Fuzzy CID Matching")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Phase 1: Detect Shopify
    print("\n[Phase 1] Detecting Shopify retailers...")
    shopify_retailers = {}
    retailers_to_check = RETAILER_DOMAINS.items()
    if args.retailer:
        retailers_to_check = [(k, v) for k, v in retailers_to_check if k == args.retailer]

    for key, domain in retailers_to_check:
        is_shopify = detect_shopify(domain)
        status = "SHOPIFY" if is_shopify else "other"
        print(f"  {key:25s} {domain:40s} {status}")
        if is_shopify:
            shopify_retailers[key] = domain
        time.sleep(0.5)

    print(f"\nShopify retailers found: {len(shopify_retailers)} / {len(dict(retailers_to_check))}")

    if args.detect_only:
        return

    if not shopify_retailers:
        print("No Shopify retailers detected. Nothing to harvest.")
        return

    # Load CID data
    print("\n[Phase 2] Loading master CIDs and monitored data...")
    all_cids = load_master_cids()
    monitored = load_monitored_cids()
    all_monitored_union = set()
    for cid_set in monitored.values():
        all_monitored_union |= cid_set
    unmonitored = [c for c in all_cids if c["cid"] not in all_monitored_union]
    print(f"  Master CIDs: {len(all_cids)}")
    print(f"  Monitored (union): {len(all_monitored_union)}")
    print(f"  Unmonitored: {len(unmonitored)}")

    # Phase 2+3: Harvest and match per retailer
    all_matches = []

    for key, domain in sorted(shopify_retailers.items()):
        print(f"\n[Harvest] {key} ({domain})...")
        catalog = harvest_shopify_catalog(domain, key)
        print(f"  Total products: {len(catalog)}")

        if not catalog:
            continue

        retailer_monitored = monitored.get(key, set())
        cigar_products = [
            p for p in catalog
            if any(kw in (p.get("product_type") or "").lower()
                   for kw in ["cigar", ""])
        ]

        print(f"  Matching against {len(unmonitored)} unmonitored CIDs...")
        matches = match_catalog_to_cids(cigar_products, unmonitored, key, retailer_monitored)
        high = sum(1 for m in matches if m["confidence"] == "HIGH")
        med = sum(1 for m in matches if m["confidence"] == "MEDIUM")
        print(f"  Matches: {len(matches)} ({high} HIGH, {med} MEDIUM)")
        all_matches.extend(matches)

    # Output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"matches_{timestamp}.csv"
    write_matches_csv(all_matches, output_path)

    high_total = sum(1 for m in all_matches if m["confidence"] == "HIGH")
    med_total = sum(1 for m in all_matches if m["confidence"] == "MEDIUM")

    print("\n" + "=" * 70)
    print("RESULTS")
    print(f"  Total matches: {len(all_matches)} ({high_total} HIGH, {med_total} MEDIUM)")
    print(f"  Output: {output_path}")
    print("=" * 70)

    if args.upload and all_matches:
        print("\n[Upload] Sending matches to staging API...")
        upload_to_staging_api(all_matches)


if __name__ == "__main__":
    main()
