"""Rewrite Commission-Junction (and similar) affiliate-redirect URLs in a
retailer CSV back to the clean storefront product URL they wrap.

Affiliate redirects (anrdoezrs.net/click-...?url=<encoded real url>&...) break
two things:
  1. The daily scraper follows the redirect — any wrong embedded slug prices the
     wrong product.
  2. The site stores the *redirect* as the canonical URL, so the real product
     page can never match in the operator/consumer extension for corrections.

This decodes the embedded ``url=`` target, strips its query string, and writes
that clean URL back. UTM/affiliate params (when configured) are added at
click-time by app.main.add_tracking_params, so the CSV should hold clean URLs.

Usage (PowerShell):
  # Preview the rewrites (no file changes):
  python scripts/clean_affiliate_urls.py static/data/gothamcigars.csv

  # Apply them:
  python scripts/clean_affiliate_urls.py static/data/gothamcigars.csv --apply
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

# Commission Junction (and friends) rotating click-tracking hosts.
AFFILIATE_HOSTS = {
    "anrdoezrs.net", "dpbolvw.net", "kqzyfj.com", "jdoqocy.com",
    "tkqlhce.com", "lduhtrp.net", "ftjcfx.com", "www.anrdoezrs.net",
    "www.dpbolvw.net", "www.kqzyfj.com", "www.jdoqocy.com",
    "www.tkqlhce.com", "www.lduhtrp.net", "www.ftjcfx.com",
}


def clean_url(url: str) -> str | None:
    """Return the decoded clean target if ``url`` is an affiliate redirect, else None."""
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.hostname not in AFFILIATE_HOSTS:
        return None
    target = parse_qs(parts.query).get("url", [None])[0]
    if not target:
        return None
    t = urlsplit(target)
    if not t.scheme or not t.netloc:
        return None
    # Drop the query string (sku/variant params) for a clean canonical PDP URL,
    # matching the clean gothamcigars.com rows already in the file.
    return urlunsplit((t.scheme, t.netloc, t.path, "", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="Path to the retailer CSV to clean.")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry run).")
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.exists():
        print(f"[ERROR] not found: {path}")
        return 2

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    changes = 0
    for row in rows:
        new = clean_url(row.get("url", ""))
        if new and new != row.get("url"):
            print(f"  {row.get('cigar_id','?')}")
            print(f"    - {row['url']}")
            print(f"    + {new}")
            row["url"] = new
            changes += 1

    print(f"\n{changes} affiliate redirect(s) {'rewritten' if args.apply else 'would be rewritten'}.")
    if not changes:
        return 0
    if not args.apply:
        print("Dry run — re-run with --apply to write.")
        return 0

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
