"""
One-shot cleanup after the cigarhustler box-price extractor fix.

Why this exists:
  The previous _extract_price returned the lowest $-value found on the
  page, which silently wrote per-stick / 5-pack prices into the box-qty
  CSV column (e.g. Padron 1964 Diplomatico Maduro box-of-25 showed
  $18.70 instead of $442.50). That bad data also seeded
  historical_prices.db.price_history / price_changes / stock_changes.
  Once the fix is in place we need to:
    1. Blank price + in_stock in static/data/cigarhustler.csv so the
       next daily pricing run repopulates them with correct values.
       Metadata columns (cigar_id, url, brand, line, wrapper, vitola,
       size, box_qty) stay — they're driven by master_cigars anyway
       and re-running the updater would re-fetch the same data.
    2. Delete every cigarhustler-tagged row from
       data/historical_prices.db so charts / change feeds don't keep
       surfacing the bogus numbers.

The retailer_runs table is intentionally left alone: those rows are
run-level metadata (timing, success counts) and aren't shown to users.

Run with:  python scripts/cleanup_cigarhustler.py
Add --dry-run to preview without writing.
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / 'static' / 'data' / 'cigarhustler.csv'
DB_PATH = REPO_ROOT / 'data' / 'historical_prices.db'
RETAILER_KEY = 'cigarhustler'

# Tables in historical_prices.db that have a `retailer` column AND hold
# user-facing price/stock data (not just run metadata). Wipe these.
PRICE_TABLES = ('price_history', 'price_changes', 'stock_changes')


def blank_csv(path: Path, dry_run: bool) -> tuple[int, int]:
    """Replace price + in_stock columns with empty strings.

    Returns (rows_touched, rows_total).
    """
    if not path.exists():
        print(f'[skip] CSV not found: {path}')
        return 0, 0

    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    touched = 0
    for row in rows:
        # Only count it as "touched" if the row actually had a value to clear,
        # so the summary is honest when re-run.
        if row.get('price') or row.get('in_stock'):
            touched += 1
        row['price'] = ''
        row['in_stock'] = ''

    if dry_run:
        print(f'[dry-run] would blank price+in_stock on {touched}/{len(rows)} rows in {path.name}')
        return touched, len(rows)

    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f'[ok] blanked price+in_stock on {touched}/{len(rows)} rows in {path.name}')
    return touched, len(rows)


def wipe_historical(db_path: Path, retailer_key: str, dry_run: bool) -> dict[str, int]:
    """Delete every row tagged with retailer_key in each PRICE_TABLE.

    Returns {table_name: rows_deleted}.
    """
    if not db_path.exists():
        print(f'[skip] historical DB not found: {db_path}')
        return {}

    deleted: dict[str, int] = {}
    conn = sqlite3.connect(db_path)
    try:
        for table in PRICE_TABLES:
            # Confirm the table exists and has a retailer column before touching it.
            cur = conn.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in cur.fetchall()]
            if not cols:
                print(f'[skip] table {table} not found')
                continue
            if 'retailer' not in cols:
                print(f'[skip] table {table} has no retailer column (cols={cols})')
                continue

            cur = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE retailer = ?", (retailer_key,))
            n = cur.fetchone()[0]
            if dry_run:
                print(f'[dry-run] would delete {n} rows from {table}')
                deleted[table] = n
                continue
            conn.execute(f"DELETE FROM {table} WHERE retailer = ?", (retailer_key,))
            deleted[table] = n
            print(f'[ok] deleted {n} rows from {table}')
        if not dry_run:
            conn.commit()
            # Reclaim space — these can be sizeable on the daily-run DB.
            conn.execute('VACUUM')
            print('[ok] VACUUMed historical_prices.db')
    finally:
        conn.close()
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    args = parser.parse_args()

    print('=' * 70)
    print(f'CIGAR HUSTLER CLEANUP  (dry-run={args.dry_run})')
    print('=' * 70)

    csv_touched, csv_total = blank_csv(CSV_PATH, args.dry_run)
    hist = wipe_historical(DB_PATH, RETAILER_KEY, args.dry_run)

    print('-' * 70)
    print(f'CSV:         blanked {csv_touched}/{csv_total} rows')
    for table in PRICE_TABLES:
        print(f'  {table:18s} {hist.get(table, 0):>8} rows')
    print('=' * 70)
    if args.dry_run:
        print('Re-run without --dry-run to apply.')
    else:
        print('Done. Next daily pricing run will repopulate price + in_stock.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
