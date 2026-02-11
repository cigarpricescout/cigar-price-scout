#!/usr/bin/env python3
"""
Migrate master_cigars.csv to SQLite database.

One-time migration script that:
1. Creates the SQLite schema with proper constraints
2. Imports all rows from master_cigars.csv
3. Validates data integrity (no duplicate CIDs, no missing required fields)
4. Reports any issues found

Usage:
    python tools/data_management/migrate_master_to_sqlite.py
"""

import csv
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Resolve paths relative to project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "master_cigars.csv"
DB_PATH = PROJECT_ROOT / "data" / "master_cigars.db"


def create_schema(conn):
    """Create the cigars table with proper constraints."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cigars (
            cigar_id TEXT PRIMARY KEY,
            brand TEXT NOT NULL,
            line TEXT NOT NULL,
            wrapper TEXT,
            wrapper_alias TEXT,
            vitola TEXT NOT NULL,
            length TEXT,
            ring_gauge TEXT,
            binder TEXT,
            filler TEXT,
            strength TEXT,
            box_quantity INTEGER NOT NULL,
            style TEXT,
            parent_brand TEXT,
            sub_brand TEXT,
            product_name TEXT,
            wrapper_code TEXT,
            packaging_type TEXT,
            country_of_origin TEXT,
            factory TEXT,
            release_type TEXT,
            sampler_flag TEXT DEFAULT 'N',
            msrp_stick_usd REAL,
            msrp_box_usd REAL,
            first_release_year TEXT,
            discontinued_flag TEXT DEFAULT 'N',
            retailer_sku TEXT,
            upc_ean TEXT,
            notes TEXT,
            source_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_cigars_brand ON cigars(brand);
        CREATE INDEX IF NOT EXISTS idx_cigars_brand_line ON cigars(brand, line);
        CREATE INDEX IF NOT EXISTS idx_cigars_wrapper_code ON cigars(wrapper_code);
    """)
    print("[OK] Schema created")


def parse_float(val):
    """Safely parse a float value, returning None for empty/invalid."""
    if not val or val.strip() == '':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_int(val):
    """Safely parse an integer value, returning 0 for empty/invalid."""
    if not val or val.strip() == '':
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def import_csv(conn):
    """Import all rows from master_cigars.csv into SQLite."""
    if not CSV_PATH.exists():
        print(f"[ERROR] CSV not found: {CSV_PATH}")
        sys.exit(1)

    with open(CSV_PATH, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"[INFO] Read {len(rows)} rows from {CSV_PATH.name}")

    # Validate before inserting
    issues = []
    cid_counts = {}
    for i, row in enumerate(rows, start=2):  # start=2 because row 1 is header
        cid = row.get('cigar_id', '').strip()
        brand = row.get('Brand', '').strip()
        line = row.get('Line', '').strip()
        vitola = row.get('Vitola', '').strip()
        box_qty = row.get('Box Quantity', '').strip()

        if not cid:
            issues.append(f"  Row {i}: Empty cigar_id (Brand={brand}, Line={line})")
        if not brand:
            issues.append(f"  Row {i}: Empty Brand (CID={cid})")
        if not line:
            issues.append(f"  Row {i}: Empty Line (CID={cid})")
        if not vitola:
            issues.append(f"  Row {i}: Empty Vitola (CID={cid})")

        if cid:
            cid_counts[cid] = cid_counts.get(cid, 0) + 1

    # Check for duplicate CIDs
    duplicates = {cid: count for cid, count in cid_counts.items() if count > 1}
    if duplicates:
        issues.append(f"\n  DUPLICATE CIDs found ({len(duplicates)}):")
        for cid, count in sorted(duplicates.items()):
            issues.append(f"    {cid} appears {count} times")

    if issues:
        print(f"\n[WARNING] Found {len(issues)} data issues:")
        for issue in issues:
            print(issue)
        print()

    # Handle duplicates: keep first occurrence, skip exact duplicates, warn on conflicts
    if duplicates:
        print("[INFO] Handling duplicates: keeping first occurrence of each CID...")
        seen_cids = set()
        deduped_rows = []
        for row in rows:
            cid = row.get('cigar_id', '').strip()
            if cid in seen_cids:
                continue
            seen_cids.add(cid)
            deduped_rows.append(row)
        skipped_dupes = len(rows) - len(deduped_rows)
        print(f"  Removed {skipped_dupes} duplicate rows")
        rows = deduped_rows

    # Insert rows
    now = datetime.now().isoformat()
    inserted = 0
    skipped = 0

    for row in rows:
        cid = row.get('cigar_id', '').strip()
        if not cid:
            skipped += 1
            continue

        try:
            conn.execute("""
                INSERT INTO cigars (
                    cigar_id, brand, line, wrapper, wrapper_alias, vitola,
                    length, ring_gauge, binder, filler, strength, box_quantity,
                    style, parent_brand, sub_brand, product_name, wrapper_code,
                    packaging_type, country_of_origin, factory, release_type,
                    sampler_flag, msrp_stick_usd, msrp_box_usd, first_release_year,
                    discontinued_flag, retailer_sku, upc_ean, notes, source_url,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                cid,
                row.get('Brand', '').strip(),
                row.get('Line', '').strip(),
                row.get('Wrapper', '').strip() or None,
                row.get('Wrapper_Alias', '').strip() or None,
                row.get('Vitola', '').strip(),
                row.get('Length', '').strip() or None,
                row.get('Ring Gauge', '').strip() or None,
                row.get('Binder', '').strip() or None,
                row.get('Filler', '').strip() or None,
                row.get('Strength', '').strip() or None,
                parse_int(row.get('Box Quantity', '0')),
                row.get('Style', '').strip() or None,
                row.get('parent_brand', '').strip() or None,
                row.get('sub_brand', '').strip() or None,
                row.get('product_name', '').strip() or None,
                row.get('wrapper_code', '').strip() or None,
                row.get('packaging_type', '').strip() or None,
                row.get('country_of_origin', '').strip() or None,
                row.get('factory', '').strip() or None,
                row.get('release_type', '').strip() or None,
                row.get('sampler_flag', 'N').strip() or 'N',
                parse_float(row.get('msrp_stick_usd', '')),
                parse_float(row.get('msrp_box_usd', '')),
                row.get('first_release_year', '').strip() or None,
                row.get('discontinued_flag', 'N').strip() or 'N',
                row.get('retailer_sku', '').strip() or None,
                row.get('upc_ean', '').strip() or None,
                row.get('notes', '').strip() or None,
                row.get('source_url', '').strip() or None,
                now,
                now,
            ))
            inserted += 1
        except sqlite3.IntegrityError as e:
            print(f"  [SKIP] Duplicate CID: {cid}")
            skipped += 1

    conn.commit()
    print(f"[OK] Imported {inserted} cigars ({skipped} skipped)")
    return inserted


def verify(conn):
    """Run verification queries on the imported data."""
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM cigars")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT brand) FROM cigars")
    brands = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT brand || '|' || line) FROM cigars")
    lines = cursor.fetchone()[0]

    cursor.execute("SELECT brand, COUNT(*) as cnt FROM cigars GROUP BY brand ORDER BY cnt DESC LIMIT 5")
    top_brands = cursor.fetchall()

    print(f"\n{'='*50}")
    print(f"  DATABASE VERIFICATION")
    print(f"{'='*50}")
    print(f"  Total cigars:      {total}")
    print(f"  Unique brands:     {brands}")
    print(f"  Unique lines:      {lines}")
    print(f"  Top brands:")
    for brand, count in top_brands:
        print(f"    {brand}: {count} SKUs")
    print(f"  Database file:     {DB_PATH}")
    print(f"  Database size:     {DB_PATH.stat().st_size / 1024:.1f} KB")
    print(f"{'='*50}")


def main():
    print(f"\n{'='*50}")
    print(f"  MASTER CIGARS CSV -> SQLITE MIGRATION")
    print(f"{'='*50}")
    print(f"  Source: {CSV_PATH}")
    print(f"  Target: {DB_PATH}\n")

    if DB_PATH.exists():
        print(f"[WARNING] Database already exists at {DB_PATH}")
        response = input("  Overwrite? (y/N): ").strip().lower()
        if response != 'y':
            print("  Aborted.")
            sys.exit(0)
        DB_PATH.unlink()
        print("  Removed existing database.\n")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        create_schema(conn)
        imported = import_csv(conn)
        if imported > 0:
            verify(conn)
            print(f"\n[SUCCESS] Migration complete. master_cigars.db is ready.")
            print(f"  You can now use cigar_manager.py to add/edit cigars.")
        else:
            print("\n[ERROR] No rows imported.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
