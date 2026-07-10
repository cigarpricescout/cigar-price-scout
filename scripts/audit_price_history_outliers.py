"""Find and remove price_history rows that are extreme outliers vs peers.

Targets bogus homepage scrapes ($59–$70 on $300+ boxes) and obvious typos
($8499, $1300 on $110 boxes), not legitimate premium retailers.

Usage:
  python scripts/audit_price_history_outliers.py              # dry-run summary
  python scripts/audit_price_history_outliers.py --verbose    # list every row
  python scripts/audit_price_history_outliers.py --apply      # delete flagged rows
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "historical_prices.db"

MIN_PEER_COUNT = 2
MIN_PEER_MEDIAN = 100.0


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def is_outlier(price: float, peer_median: float) -> bool:
    """True when price is almost certainly bad data, not a real deal."""
    if peer_median < MIN_PEER_MEDIAN:
        return False
    # Classic bogus homepage scrape: $59.95 / $69.95 on premium boxes.
    if price <= 75 and peer_median >= 150:
        return True
    # Deep low outlier vs same-day peers.
    if price < peer_median * 0.25:
        return True
    # Obvious high scraper typos.
    if price > 2000:
        return True
    if price > peer_median * 5 and price > 500:
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Delete flagged rows")
    ap.add_argument("--verbose", action="store_true", help="Print every flagged row")
    ap.add_argument("--db", default=str(DB))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT rowid, retailer, cigar_id, date, price
        FROM price_history
        WHERE price > 0
        ORDER BY cigar_id, date, retailer
        """
    )
    rows = cur.fetchall()
    print(f"Scanned {len(rows)} price_history rows in {args.db}")

    by_cigar_date: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for row in rows:
        rowid, retailer, cigar_id, dt, price = row
        by_cigar_date[(cigar_id, dt)].append((rowid, retailer, price))

    flagged: list[tuple] = []
    for (cigar_id, dt), peers in by_cigar_date.items():
        if len(peers) < MIN_PEER_COUNT + 1:
            continue
        peer_median = _median([p[2] for p in peers])
        for rowid, retailer, price in peers:
            if is_outlier(price, peer_median):
                flagged.append((rowid, retailer, cigar_id, dt, price, peer_median))

    flagged.sort(key=lambda r: (r[2], r[3], r[1]))
    print(f"\nFlagged {len(flagged)} outlier row(s) across "
          f"{len({(r[1], r[2]) for r in flagged})} retailer+cigar pair(s).\n")

    by_pair: dict[tuple[str, str], list] = defaultdict(list)
    for row in flagged:
        by_pair[(row[1], row[2])].append(row)

    print(f"{'retailer':20} {'rows':>5}  price range        cigar_id")
    print("-" * 95)
    for (retailer, cigar_id), items in sorted(by_pair.items(), key=lambda x: (-len(x[1]), x[0][0])):
        prices = [i[4] for i in items]
        short = cigar_id[:55] + ("..." if len(cigar_id) > 55 else "")
        print(f"{retailer:20} {len(items):>5}  ${min(prices):.0f}-${max(prices):.0f}   {short}")

    if args.verbose and flagged:
        print("\nDetailed rows:")
        for rowid, retailer, cigar_id, dt, price, median in flagged:
            print(f"  {retailer:18} {dt}  ${price:>8.2f}  (peer med ${median:.2f})  {cigar_id[:70]}")

    if not flagged:
        conn.close()
        return 0

    if not args.apply:
        print(f"\nDRY RUN — re-run with --apply to delete {len(flagged)} row(s).")
        conn.close()
        return 0

    cur.executemany("DELETE FROM price_history WHERE rowid = ?", [(r[0],) for r in flagged])
    conn.commit()
    print(f"\nDeleted {len(flagged)} outlier row(s) from price_history.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
