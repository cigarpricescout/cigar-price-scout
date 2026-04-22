"""
Backfill missing URLs in retailer CSVs using harvester output,
and remove entries that have no URL and no price (unscrape-able dead weight).
"""
import csv
import os
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "static" / "data"
HARVESTER_DIR = PROJECT_ROOT / "tools" / "catalog_harvester_output"


def load_harvester_urls() -> dict:
    """Aggregate (retailer_key, cid) -> url from all harvester output files."""
    urls = {}
    for f in sorted(HARVESTER_DIR.glob("*.csv")):
        with open(f, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (row.get("retailer_key", ""), row.get("cid", ""))
                url = (row.get("product_url") or "").strip()
                if url and key not in urls:
                    urls[key] = url
    return urls


def process_csvs():
    harvester_urls = load_harvester_urls()
    print(f"Loaded {len(harvester_urls)} URL mappings from harvester output\n")

    total_backfilled = 0
    total_removed = 0
    total_kept = 0

    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".csv") or "DORMANT" in fname or "backup" in fname or "BROKEN" in fname:
            continue

        csv_path = DATA_DIR / fname
        retailer_key = fname.replace(".csv", "")

        rows = []
        fieldnames = None
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                rows.append(row)

        new_rows = []
        backfilled = 0
        removed = 0

        for row in rows:
            cid = (row.get("cigar_id") or "").strip()
            url = (row.get("url") or "").strip()
            price = (row.get("price") or "").strip()

            if url:
                new_rows.append(row)
                continue

            # No URL — try to backfill from harvester
            harvester_url = harvester_urls.get((retailer_key, cid))
            if harvester_url:
                row["url"] = harvester_url
                new_rows.append(row)
                backfilled += 1
                continue

            # No URL and has a price — keep it (price was set some other way)
            if price:
                new_rows.append(row)
                continue

            # No URL, no price — remove
            removed += 1

        if backfilled or removed:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(new_rows)

            print(f"  {retailer_key}: backfilled {backfilled} URLs, removed {removed} dead entries")
            total_backfilled += backfilled
            total_removed += removed

    print(f"\nDone: {total_backfilled} URLs backfilled, {total_removed} dead entries removed")


if __name__ == "__main__":
    process_csvs()
