"""
One-time script to fetch all approved matches from the live API
and publish them into the retailer CSVs.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import csv
import requests
import pandas as pd

ADMIN_KEY = os.getenv("ADMIN_SECRET_KEY", "v1nO7JvjQFfQtl4BQ4mOLWx9VileAY2T")
API_BASE = "https://cigarpricescout.com"
DATA_DIR = PROJECT_ROOT / "static" / "data"


def fetch_approved():
    resp = requests.get(
        f"{API_BASE}/api/admin/approved-matches",
        headers={"X-Admin-Key": ADMIN_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("matches", [])


def publish(matches):
    by_retailer = {}
    for m in matches:
        by_retailer.setdefault(m["retailer_key"], []).append(m)

    total_added = 0
    total_updated = 0
    published_ids = []

    for retailer_key, rmatches in sorted(by_retailer.items()):
        csv_path = DATA_DIR / f"{retailer_key}.csv"
        if not csv_path.exists():
            print(f"  SKIP {retailer_key} — CSV not found")
            continue

        df = pd.read_csv(csv_path)
        if "cigar_id" in df.columns:
            df["cigar_id"] = df["cigar_id"].astype(str).str.strip()
        existing_cids = set(df["cigar_id"].dropna().unique())

        new_rows = []
        updated = 0

        for m in rmatches:
            cid = str(m.get("cid") or "").strip()
            url = str(m.get("url") or "").strip()

            if not cid or not url:
                print(f"  SKIP {retailer_key}: missing cid or url (id={m.get('id')})")
                continue

            if cid in existing_cids:
                mask = df["cigar_id"] == cid
                existing_url = df.loc[mask, "url"].iloc[0] if mask.any() else ""
                existing_s = (
                    "" if pd.isna(existing_url) else str(existing_url).strip()
                )
                if existing_s != url:
                    df.loc[mask, "url"] = url
                    updated += 1
                    print(f"  UPDATED {retailer_key}: {cid[:50]} -> {url[:70]}")
                else:
                    print(f"  EXISTS  {retailer_key}: {cid[:50]} (URL already matches)")
                published_ids.append(m["id"])
                continue

            new_row = {
                "cigar_id": cid,
                "title": "",
                "url": url,
                "brand": m.get("brand", ""),
                "line": m.get("line", ""),
                "wrapper": m.get("wrapper", ""),
                "vitola": m.get("vitola", ""),
                "size": m.get("size", ""),
                "box_qty": m.get("box_qty", ""),
                "price": "",
                "in_stock": "",
            }
            for col in df.columns:
                if col not in new_row:
                    new_row[col] = ""
            new_rows.append(new_row)
            published_ids.append(m["id"])
            print(f"  ADDED   {retailer_key}: {cid[:50]} -> {url[:70]}")

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            df = pd.concat([df, new_df], ignore_index=True)

        if new_rows or updated:
            df.to_csv(csv_path, index=False)
            total_added += len(new_rows)
            total_updated += updated

    print(f"\nTotals: {total_added} added, {total_updated} updated")

    if published_ids:
        try:
            resp = requests.post(
                f"{API_BASE}/api/admin/mark-published",
                json={"ids": published_ids},
                headers={"X-Admin-Key": ADMIN_KEY},
                timeout=15,
            )
            resp.raise_for_status()
            print(f"Marked {len(published_ids)} matches as published in DB")
        except Exception as e:
            print(f"WARNING: Failed to mark as published: {e}")

    return total_added + total_updated


if __name__ == "__main__":
    print("Fetching approved matches from API...")
    matches = fetch_approved()
    print(f"Found {len(matches)} approved matches\n")

    if matches:
        publish(matches)
    else:
        print("No approved matches to publish.")
