"""
Shared daily CSV price updater for Shopify-backed retailers.

Reads static/data/<retailer_key>.csv, syncs metadata from data/master_cigars.csv,
fetches price/stock via the retailer extractor (Shopify JSON path), writes CSV back.
"""

from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DATA = PROJECT_ROOT / "static" / "data"
MASTER_CSV = PROJECT_ROOT / "data" / "master_cigars.csv"


def _load_master_by_cid() -> Dict[str, Dict[str, Any]]:
    if not MASTER_CSV.exists():
        print(f"[WARN] Master file not found: {MASTER_CSV}")
        return {}
    df = pd.read_csv(MASTER_CSV, dtype=str, keep_default_na=False)
    out: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        cid = str(row.get("cigar_id", "")).strip()
        if cid:
            out[cid] = row.to_dict()
    print(f"[INFO] Loaded {len(out)} CIDs from master_cigars.csv")
    return out


def _sync_metadata(row: Dict[str, Any], master: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    cid = str(row.get("cigar_id", "")).strip()
    if not cid or cid not in master:
        return row
    m = master[cid]
    length = m.get("Length", "").strip()
    rg = m.get("Ring Gauge", "").strip()
    size = f"{length}x{rg}" if length and rg else row.get("size", "")
    bq = m.get("Box Quantity", "").strip()
    try:
        box_qty_meta = int(float(bq)) if bq else row.get("box_qty", "")
    except (ValueError, TypeError):
        box_qty_meta = row.get("box_qty", "")

    row["title"] = m.get("product_name", row.get("title", ""))
    row["brand"] = m.get("Brand", row.get("brand", ""))
    row["line"] = m.get("Line", row.get("line", ""))
    row["wrapper"] = m.get("Wrapper", row.get("wrapper", ""))
    row["vitola"] = m.get("Vitola", row.get("vitola", ""))
    row["size"] = size or row.get("size", "")
    if box_qty_meta != "" and box_qty_meta is not None:
        row["box_qty"] = box_qty_meta
    return row


def _normalize_extract(
    raw: Optional[Dict[str, Any]],
) -> tuple[Optional[float], Optional[bool], Any]:
    if not raw:
        return None, None, None
    if raw.get("success") is False:
        return None, False, None
    price = raw.get("price")
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None
    instock = raw.get("in_stock")
    if instock is None:
        instock = True
    box_qty = raw.get("box_quantity")
    if box_qty is None:
        box_qty = raw.get("box_qty")
    return price, instock, box_qty


def run_shopify_retailer_update(
    retailer_key: str,
    extract_fn: Callable[[str], Dict[str, Any]],
    delay_s: float = 1.0,
) -> int:
    """
    Run price update for one retailer. Returns process exit code (0 = ok).
    """
    csv_path = STATIC_DATA / f"{retailer_key}.csv"
    if not csv_path.exists():
        print(f"[ERROR] CSV not found: {csv_path}")
        return 1

    master = _load_master_by_cid()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if not fieldnames:
            print("[ERROR] CSV has no header")
            return 1
        rows: List[Dict[str, Any]] = list(reader)

    if not rows:
        print(f"[INFO] {retailer_key}.csv has no product rows yet — nothing to update.")
        print("Successful updates: 0")
        print("Failed updates: 0")
        return 0

    ok = 0
    fail = 0

    print("=" * 70)
    print(f"{retailer_key.upper()} PRICE UPDATE — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 70)

    updated: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        row = dict(row)
        url = (row.get("url") or "").strip()
        cid = (row.get("cigar_id") or "").strip()
        label = (cid[:48] + "...") if len(cid) > 48 else (cid or "(no cid)")
        print(f"\n[{i + 1}/{len(rows)}] {label}")

        row = _sync_metadata(row, master)

        if not url:
            print("  [SKIP] No URL")
            fail += 1
            updated.append(row)
            continue

        try:
            time.sleep(delay_s)
            raw = extract_fn(url)
            price, instock, box_from_ex = _normalize_extract(raw)
            if price is not None:
                row["price"] = price
                row["in_stock"] = instock
                if box_from_ex is not None and str(box_from_ex).strip() != "":
                    row["box_qty"] = box_from_ex
                ok += 1
                print(f"  [OK] ${price} in_stock={instock}")
            else:
                fail += 1
                err = (raw or {}).get("error", "no price")
                print(f"  [FAIL] {err}")
        except Exception as e:
            fail += 1
            print(f"  [FAIL] {e}")

        updated.append(row)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in updated:
            w.writerow(row)

    print("\n" + "=" * 70)
    print(f"Successful updates: {ok}")
    print(f"Failed updates: {fail}")
    print("=" * 70)
    return 0 if ok > 0 or fail == 0 else 0


if __name__ == "__main__":
    print("Use update_<retailer>_prices_final.py for each shop.", file=sys.stderr)
    sys.exit(1)
