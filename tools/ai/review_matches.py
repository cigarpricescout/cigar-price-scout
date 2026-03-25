#!/usr/bin/env python3
"""
Review Tool - Validate staged URL matches before publishing.

Displays each staged match with:
  - The CID and its master metadata (what shows on your website)
  - The matched URL
  - Live extracted data from the retailer (price, box qty, stock)
  - Confidence level and AI's reasoning

You review the output, then mark approvals/rejections in staged_matches.csv,
or use the interactive mode to approve/reject inline.

Usage:
    # Show all staged matches with live price data
    python tools/ai/review_matches.py

    # Interactive mode - approve/reject one by one
    python tools/ai/review_matches.py --interactive

    # Show only matches for a specific retailer
    python tools/ai/review_matches.py --retailer cigarking

    # Skip live extraction (just show CID metadata + URLs)
    python tools/ai/review_matches.py --skip-extraction
"""

import os
import sys
import json
import time
import argparse
import importlib.util
from pathlib import Path
from datetime import datetime

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RETAILERS_DIR = PROJECT_ROOT / "tools" / "price_monitoring" / "retailers"
AI_DIR = Path(__file__).resolve().parent
STAGED_FILE = AI_DIR / "staged_matches.csv"
FEEDBACK_FILE = AI_DIR / "feedback_history.json"

sys.path.insert(0, str(RETAILERS_DIR))

EXTRACTOR_MAP = {
    "absolutecigars": ("absolute_cigars_extractor", "extract_absolute_cigars_data"),
    "atlantic": ("atlantic_cigar_extractor", "extract_atlantic_cigar_data"),
    "bighumidor": ("big_humidor_extractor", "extract_big_humidor_data"),
    "bnbtobacco": ("bnb_tobacco_extractor", "extract_bnb_tobacco_data"),
    "cigarboxpa": ("cigarboxpa_extractor", "extract_cigarboxpa_data"),
    "cigardepot": ("cigardepot_extractor", "extract_cigardepot_data"),
    "cigarhustler": ("cigarhustler_extractor", "extract_cigarhustler_data"),
    "cigarking": ("cigar_king_extractor", "extract_cigar_king_data"),
    "cigarsdirect": ("cigarsdirect_extractor", "extract_cigarsdirect_data"),
    "coronacigar": ("coronacigar_extractor", "extract_coronacigar_data"),
    "foxcigar": ("fox_cigar", "extract_fox_cigar_data"),
    "holts": ("holts_cigars_extractor", "extract_holts_cigars_data"),
    "iheartcigars": ("iheartcigars_production_final", "extract_iheartcigars_data"),
    "nickscigarworld": ("nicks_cigars", "extract_nicks_cigars_data"),
    "planetcigars": ("planet_cigars_extractor", "extract_planet_cigars_data"),
    "pyramidcigars": ("pyramid_cigars_extractor", "extract_pyramid_cigars_data"),
    "smallbatchcigar": ("smallbatch_cigar_extractor", "extract_smallbatch_cigar_data"),
    "smokeinn": ("smokeinn_extractor", "extract_smokeinn_data"),
    "stogies": ("stogies_extractor", "extract_stogies_data"),
    "tampasweethearts": ("tampa_sweethearts_extractor", "extract_tampa_sweethearts_data"),
    "thecigarshop": ("thecigarshop_extractor", "extract_thecigarshop_data"),
    "tobaccolocker": ("tobacco_locker_extractor", "extract_tobacco_locker_data"),
    "tobaccostock": ("tobaccostock_extractor", "extract_tobaccostock_data"),
    "twoguys": ("two_guys_extractor", "extract_two_guys_data"),
    "watchcity": ("watch_city_extractor", "extract_watch_city_data"),
}

WRAPPER_NAMES = {
    "MAD": "Maduro", "NAT": "Natural", "CAM": "Cameroon",
    "ECU": "Ecuadorian", "HAB": "Habano", "SUM": "Sumatra",
    "BRD": "Broadleaf", "OSC": "Oscuro", "NIC": "Nicaraguan",
    "MEX": "Mexican San Andres", "CLA": "Claro", "HON": "Honduran",
}


def load_master():
    """Load master cigars data."""
    master_csv = PROJECT_ROOT / "data" / "master_cigars.csv"
    if master_csv.exists():
        return pd.read_csv(master_csv)
    return pd.DataFrame()


def get_master_metadata(master_df, cid):
    """Get display metadata from master for a CID."""
    row = master_df[master_df["cigar_id"] == cid]
    if len(row) == 0:
        return None
    r = row.iloc[0]
    return {
        "brand": r.get("Brand", ""),
        "line": r.get("Line", ""),
        "vitola": r.get("Vitola", ""),
        "size": f"{r.get('Length', '')}x{r.get('Ring Gauge', '')}",
        "wrapper": r.get("Wrapper", ""),
        "box_qty": int(r.get("Box Quantity", 0)) if pd.notna(r.get("Box Quantity")) else 0,
    }


def extract_live_data(retailer_key, url):
    """Run the retailer's extractor against a URL."""
    if retailer_key not in EXTRACTOR_MAP:
        return {"error": f"No extractor mapped for {retailer_key}"}

    mod_name, fn_name = EXTRACTOR_MAP[retailer_key]
    try:
        mod = __import__(mod_name)
        fn = getattr(mod, fn_name)
        result = fn(url)
        return {
            "price": result.get("price"),
            "box_quantity": result.get("box_quantity"),
            "in_stock": result.get("in_stock"),
            "error": result.get("error"),
        }
    except Exception as e:
        return {"error": str(e)}


def display_match(idx, total, row, master_meta, live_data=None):
    """Display a single match for review."""
    print(f"\n{'='*60}")
    print(f"  MATCH #{idx} of {total}  |  {row['retailer_key']}  |  {row['confidence']} confidence")
    print(f"{'='*60}")
    print(f"  URL: {row['url']}")
    print(f"  AI reason: {row.get('reason', 'N/A')}")

    print(f"\n  CID: {row['cid']}")
    if master_meta:
        print(f"  --- Master Metadata (what shows on your website) ---")
        print(f"  Brand:    {master_meta['brand']}")
        print(f"  Line:     {master_meta['line']}")
        print(f"  Vitola:   {master_meta['vitola']}")
        print(f"  Size:     {master_meta['size']}")
        print(f"  Wrapper:  {master_meta['wrapper']}")
        print(f"  Box Qty:  {master_meta['box_qty']}")
    else:
        print(f"  (CID not found in master)")

    if live_data:
        print(f"\n  --- Live Extraction from URL ---")
        if live_data.get("error"):
            print(f"  Error: {live_data['error']}")
        else:
            price = live_data.get("price")
            print(f"  Price:    ${price}" if price else "  Price:    N/A")
            print(f"  Box Qty:  {live_data.get('box_quantity', 'N/A')}")
            stock = "In Stock" if live_data.get("in_stock") else "Out of Stock"
            print(f"  Stock:    {stock}")

            # Flag mismatches
            if master_meta:
                if live_data.get("box_quantity") and master_meta["box_qty"]:
                    if int(live_data["box_quantity"]) != int(master_meta["box_qty"]):
                        print(f"  *** BOX QTY MISMATCH: extracted {live_data['box_quantity']}, master says {master_meta['box_qty']}")
    print()


def interactive_review(matches_df, master_df, skip_extraction=False):
    """Interactive review mode - approve/reject one by one."""
    staged = matches_df[matches_df["status"] == "staged"].copy()
    if staged.empty:
        print("No staged matches to review.")
        return

    approvals = []
    rejections = []

    for i, (idx, row) in enumerate(staged.iterrows(), 1):
        meta = get_master_metadata(master_df, row["cid"])

        live = None
        if not skip_extraction:
            print(f"\n  Extracting live data from {row['retailer_key']}...", flush=True)
            live = extract_live_data(row["retailer_key"], row["url"])
            time.sleep(1)

        display_match(i, len(staged), row, meta, live)

        while True:
            choice = input("  [a]pprove / [r]eject / [s]kip / [q]uit: ").strip().lower()
            if choice in ("a", "r", "s", "q"):
                break
            print("  Please enter a, r, s, or q")

        if choice == "q":
            break
        elif choice == "a":
            matches_df.loc[idx, "status"] = "approved"
            approvals.append(idx)
            print("  -> Approved")
        elif choice == "r":
            feedback = input("  Reason for rejection: ").strip()
            matches_df.loc[idx, "status"] = "rejected"
            matches_df.loc[idx, "feedback"] = feedback
            rejections.append({"idx": idx, "cid": row["cid"], "url": row["url"],
                              "retailer": row["retailer_key"], "feedback": feedback})
            print("  -> Rejected")
        else:
            print("  -> Skipped")

    # Save
    matches_df.to_csv(STAGED_FILE, index=False)

    # Save feedback
    if rejections:
        history = {"rejections": [], "corrections": []}
        if FEEDBACK_FILE.exists():
            with open(FEEDBACK_FILE) as f:
                history = json.load(f)
        for r in rejections:
            history["rejections"].append({
                "cid": r["cid"], "url": r["url"],
                "retailer_key": r["retailer"],
                "feedback": r["feedback"],
                "timestamp": datetime.now().isoformat(),
            })
        with open(FEEDBACK_FILE, "w") as f:
            json.dump(history, f, indent=2)

    print(f"\nDone. Approved: {len(approvals)}, Rejected: {len(rejections)}")
    if approvals:
        print("Run: python tools/ai/url_discoverer.py --publish-approved")


def batch_review(matches_df, master_df, skip_extraction=False, retailer_filter=None):
    """Display all staged matches for review (non-interactive)."""
    staged = matches_df[matches_df["status"] == "staged"].copy()
    if retailer_filter:
        staged = staged[staged["retailer_key"] == retailer_filter]

    if staged.empty:
        print("No staged matches to review.")
        return

    print(f"\n{len(staged)} matches to review\n")

    for i, (idx, row) in enumerate(staged.iterrows(), 1):
        meta = get_master_metadata(master_df, row["cid"])

        live = None
        if not skip_extraction:
            live = extract_live_data(row["retailer_key"], row["url"])
            time.sleep(1)

        display_match(i, len(staged), row, meta, live)

    print(f"{'='*60}")
    print(f"To approve/reject, either:")
    print(f"  1. Run: python tools/ai/review_matches.py --interactive")
    print(f"  2. Edit tools/ai/staged_matches.csv directly:")
    print(f"     - Set 'status' to 'approved' or 'rejected'")
    print(f"     - Add reason in 'feedback' column for rejections")
    print(f"     Then run: python tools/ai/url_discoverer.py --publish-approved")


def main():
    parser = argparse.ArgumentParser(description="Review staged URL matches")
    parser.add_argument("--interactive", action="store_true",
                       help="Approve/reject matches one by one")
    parser.add_argument("--retailer", type=str,
                       help="Only show matches for a specific retailer")
    parser.add_argument("--skip-extraction", action="store_true",
                       help="Skip live price extraction (faster, shows CID + URL only)")
    args = parser.parse_args()

    if not STAGED_FILE.exists():
        print("No staged matches file found. Run URL discovery first.")
        return

    matches_df = pd.read_csv(STAGED_FILE)
    master_df = load_master()

    if args.interactive:
        interactive_review(matches_df, master_df, args.skip_extraction)
    else:
        batch_review(matches_df, master_df, args.skip_extraction, args.retailer)


if __name__ == "__main__":
    main()
