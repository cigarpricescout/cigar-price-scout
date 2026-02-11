#!/usr/bin/env python3
"""
Cigar Master Database Manager (cigar_db.py)

CLI tool for managing the master cigar SQLite database.
CIDs are frozen at creation time -- metadata edits do NOT change the CID.

Commands:
    add         Add a new cigar (auto-generates CID)
    edit        Edit metadata for an existing CID
    rename-cid  Change a CID across master DB and all retailer CSVs
    list        Search/filter cigars
    validate    Check retailer CSVs for orphaned CIDs
    export      Export database to CSV
    stats       Show database statistics

Usage:
    python tools/data_management/cigar_db.py add
    python tools/data_management/cigar_db.py list --brand "Padron"
    python tools/data_management/cigar_db.py edit PADRON|PADRON|1964ANNIVERSARY|DIPLOMATICO|...
    python tools/data_management/cigar_db.py validate
    python tools/data_management/cigar_db.py export
    python tools/data_management/cigar_db.py stats
"""

import argparse
import csv
import glob
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Resolve paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "master_cigars.db"
RETAILER_CSV_DIR = PROJECT_ROOT / "static" / "data"

# Wrapper code mapping (replicates your Google Sheets formula logic)
WRAPPER_CODE_MAP = {
    "natural": "CAM",
    "connecticut broadleaf": "CT",
    "connecticut broadleaf oscuro": "CT",
    "ecuadorian sungrown": "SUN",
    "candela": "NAT",
    "connecticut shade": "CT",
    "rosado sungrown": "SUN",
    "ecuadorian rosado": "SUN",
    "maduro": "MAD",
    "claro": "CLA",
}


def get_db():
    """Get a database connection."""
    if not DB_PATH.exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        print("  Run migrate_master_to_sqlite.py first.")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def generate_cid(brand, parent_brand, line, vitola, length, ring_gauge, wrapper, box_quantity):
    """Generate a CID from cigar metadata. Replicates the Google Sheets formula."""
    b = brand.upper().replace(" ", "")
    pb = (parent_brand or brand).upper().replace(" ", "")
    ln = line.upper().replace(" ", "")
    v = vitola.upper().replace(" ", "")
    size = f"{length}x{ring_gauge}"

    wrapper_lower = wrapper.lower().strip()
    wc = WRAPPER_CODE_MAP.get(wrapper_lower, wrapper.upper().replace(" ", "")[:3])

    return f"{b}|{pb}|{ln}|{v}|{v}|{size}|{wc}|BOX{box_quantity}"


# ─── ADD ──────────────────────────────────────────────────────────────────────

def cmd_add(args):
    """Add a new cigar to the database."""
    conn = get_db()

    print("\n  ADD NEW CIGAR")
    print("  " + "=" * 40)

    # Required fields
    brand = input("  Brand: ").strip()
    if not brand:
        print("  [ERROR] Brand is required."); return

    parent_brand = input(f"  Parent brand [{brand}]: ").strip() or brand
    line = input("  Line: ").strip()
    if not line:
        print("  [ERROR] Line is required."); return

    wrapper = input("  Wrapper: ").strip()
    vitola = input("  Vitola: ").strip()
    if not vitola:
        print("  [ERROR] Vitola is required."); return

    length = input("  Length (e.g. 6.5): ").strip()
    ring_gauge = input("  Ring Gauge (e.g. 52): ").strip()
    box_quantity = input("  Box Quantity: ").strip()
    if not box_quantity:
        print("  [ERROR] Box Quantity is required."); return

    # Generate CID
    cid = generate_cid(brand, parent_brand, line, vitola, length, ring_gauge, wrapper, int(box_quantity))
    print(f"\n  Generated CID: {cid}")

    # Check if CID already exists
    existing = conn.execute("SELECT cigar_id FROM cigars WHERE cigar_id = ?", (cid,)).fetchone()
    if existing:
        print(f"  [ERROR] CID already exists in database. Use 'edit' to modify it.")
        conn.close()
        return

    # Optional fields
    print("\n  Optional fields (press Enter to skip):")
    wrapper_alias = input("  Wrapper Alias: ").strip() or None
    wrapper_lower = wrapper.lower().strip()
    wrapper_code = WRAPPER_CODE_MAP.get(wrapper_lower, wrapper.upper().replace(" ", "")[:3])
    binder = input("  Binder: ").strip() or None
    filler = input("  Filler: ").strip() or None
    strength = input("  Strength (Mild/Medium/Medium-Full/Full): ").strip() or None
    style = input("  Style (Parejo/Box Press/Torpedo/etc): ").strip() or None
    country = input("  Country of Origin: ").strip() or None
    factory = input("  Factory: ").strip() or None

    # Confirm
    print(f"\n  Summary:")
    print(f"    CID:     {cid}")
    print(f"    Brand:   {brand} (Line: {line})")
    print(f"    Wrapper: {wrapper} ({wrapper_code})")
    print(f"    Vitola:  {vitola} ({length}x{ring_gauge})")
    print(f"    Box:     {box_quantity}")

    confirm = input("\n  Save? (Y/n): ").strip().lower()
    if confirm == 'n':
        print("  Cancelled.")
        conn.close()
        return

    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO cigars (
            cigar_id, brand, line, wrapper, wrapper_alias, vitola,
            length, ring_gauge, binder, filler, strength, box_quantity,
            style, parent_brand, wrapper_code, packaging_type,
            country_of_origin, factory, release_type, sampler_flag,
            discontinued_flag, product_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Box', ?, ?, 'Regular Production', 'N', 'N', ?, ?, ?)
    """, (
        cid, brand, line, wrapper, wrapper_alias, vitola,
        length, ring_gauge, binder, filler, strength, int(box_quantity),
        style, parent_brand, wrapper_code,
        country, factory, vitola, now, now,
    ))
    conn.commit()
    conn.close()
    print(f"\n  [OK] Added: {cid}")


# ─── EDIT ─────────────────────────────────────────────────────────────────────

def cmd_edit(args):
    """Edit metadata for an existing CID. CID itself does NOT change."""
    conn = get_db()

    cid = args.cigar_id
    row = conn.execute("SELECT * FROM cigars WHERE cigar_id = ?", (cid,)).fetchone()

    if not row:
        # Try partial match
        rows = conn.execute("SELECT cigar_id FROM cigars WHERE cigar_id LIKE ?", (f"%{cid}%",)).fetchall()
        if rows:
            print(f"  CID not found. Did you mean one of these?")
            for r in rows[:10]:
                print(f"    {r['cigar_id']}")
        else:
            print(f"  [ERROR] CID not found: {cid}")
        conn.close()
        return

    print(f"\n  EDIT CIGAR (CID stays frozen)")
    print(f"  CID: {cid}")
    print(f"  " + "=" * 40)
    print(f"  Press Enter to keep current value.\n")

    # Editable fields
    editable = [
        ('brand', 'Brand'), ('line', 'Line'), ('wrapper', 'Wrapper'),
        ('wrapper_alias', 'Wrapper Alias'), ('vitola', 'Vitola'),
        ('length', 'Length'), ('ring_gauge', 'Ring Gauge'),
        ('binder', 'Binder'), ('filler', 'Filler'), ('strength', 'Strength'),
        ('box_quantity', 'Box Quantity'), ('style', 'Style'),
        ('parent_brand', 'Parent Brand'), ('wrapper_code', 'Wrapper Code'),
        ('country_of_origin', 'Country'), ('factory', 'Factory'),
        ('notes', 'Notes'),
    ]

    updates = {}
    for field, label in editable:
        current = row[field] if row[field] is not None else ''
        new_val = input(f"  {label} [{current}]: ").strip()
        if new_val and new_val != str(current):
            updates[field] = new_val

    if not updates:
        print("\n  No changes made.")
        conn.close()
        return

    # Apply updates
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    set_clause += ", updated_at = ?"
    values = list(updates.values()) + [datetime.now().isoformat(), cid]

    conn.execute(f"UPDATE cigars SET {set_clause} WHERE cigar_id = ?", values)
    conn.commit()
    conn.close()

    print(f"\n  [OK] Updated {len(updates)} field(s). CID unchanged: {cid}")


# ─── RENAME-CID ──────────────────────────────────────────────────────────────

def cmd_rename_cid(args):
    """Rename a CID across the master DB and ALL retailer CSVs."""
    conn = get_db()

    old_cid = args.old_cid
    new_cid = args.new_cid

    # Verify old CID exists
    row = conn.execute("SELECT * FROM cigars WHERE cigar_id = ?", (old_cid,)).fetchone()
    if not row:
        print(f"  [ERROR] Old CID not found: {old_cid}")
        conn.close()
        return

    # Verify new CID doesn't exist
    existing = conn.execute("SELECT cigar_id FROM cigars WHERE cigar_id = ?", (new_cid,)).fetchone()
    if existing:
        print(f"  [ERROR] New CID already exists: {new_cid}")
        conn.close()
        return

    # Scan retailer CSVs for references
    csv_files = list(RETAILER_CSV_DIR.glob("*.csv"))
    affected_files = []
    total_refs = 0

    for csv_file in csv_files:
        if 'backup' in csv_file.name:
            continue
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                content = f.read()
            if old_cid in content:
                count = content.count(old_cid)
                affected_files.append((csv_file, count))
                total_refs += count
        except Exception:
            pass

    print(f"\n  RENAME CID")
    print(f"  " + "=" * 50)
    print(f"  Old: {old_cid}")
    print(f"  New: {new_cid}")
    print(f"  Retailer CSVs affected: {len(affected_files)} files, {total_refs} references")
    for csv_file, count in affected_files:
        print(f"    {csv_file.name}: {count} reference(s)")

    confirm = input(f"\n  This will update the master DB and {len(affected_files)} retailer CSV(s). Proceed? (y/N): ").strip().lower()
    if confirm != 'y':
        print("  Cancelled.")
        conn.close()
        return

    # Update master DB
    conn.execute("UPDATE cigars SET cigar_id = ?, updated_at = ? WHERE cigar_id = ?",
                 (new_cid, datetime.now().isoformat(), old_cid))
    conn.commit()
    print(f"  [OK] Master DB updated")

    # Update retailer CSVs
    for csv_file, _ in affected_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace(old_cid, new_cid)
            with open(csv_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  [OK] Updated: {csv_file.name}")
        except Exception as e:
            print(f"  [ERROR] Failed to update {csv_file.name}: {e}")

    # Also update historical DB if it exists
    hist_db = PROJECT_ROOT / "data" / "historical_prices.db"
    if hist_db.exists():
        try:
            hconn = sqlite3.connect(hist_db)
            hconn.execute("UPDATE price_history SET cigar_id = ? WHERE cigar_id = ?", (new_cid, old_cid))
            hconn.execute("UPDATE price_changes SET cigar_id = ? WHERE cigar_id = ?", (new_cid, old_cid))
            hconn.commit()
            hconn.close()
            print(f"  [OK] Updated historical_prices.db")
        except Exception as e:
            print(f"  [WARNING] Could not update historical DB: {e}")

    conn.close()
    print(f"\n  [DONE] CID renamed successfully.")


# ─── LIST ─────────────────────────────────────────────────────────────────────

def cmd_list(args):
    """Search and filter cigars."""
    conn = get_db()

    query = "SELECT cigar_id, brand, line, wrapper, vitola, length, ring_gauge, box_quantity FROM cigars WHERE 1=1"
    params = []

    if args.brand:
        query += " AND brand LIKE ?"
        params.append(f"%{args.brand}%")
    if args.line:
        query += " AND line LIKE ?"
        params.append(f"%{args.line}%")
    if args.wrapper:
        query += " AND wrapper LIKE ?"
        params.append(f"%{args.wrapper}%")
    if args.cid:
        query += " AND cigar_id LIKE ?"
        params.append(f"%{args.cid}%")

    query += " ORDER BY brand, line, vitola"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        print("  No cigars found matching your criteria.")
        return

    print(f"\n  Found {len(rows)} cigar(s):\n")
    print(f"  {'Brand':<20} {'Line':<25} {'Vitola':<18} {'Size':<8} {'Wrapper':<25} {'Box':<4}")
    print(f"  {'-'*20} {'-'*25} {'-'*18} {'-'*8} {'-'*25} {'-'*4}")

    for row in rows:
        size = f"{row['length'] or ''}x{row['ring_gauge'] or ''}"
        print(f"  {row['brand']:<20} {row['line']:<25} {row['vitola']:<18} {size:<8} {(row['wrapper'] or 'N/A'):<25} {row['box_quantity']:<4}")

    if len(rows) > 20:
        print(f"\n  ... showing all {len(rows)} results")


# ─── VALIDATE ─────────────────────────────────────────────────────────────────

def cmd_validate(args):
    """Check all retailer CSVs for CIDs that don't exist in the master DB."""
    conn = get_db()

    # Load all valid CIDs
    valid_cids = set(row[0] for row in conn.execute("SELECT cigar_id FROM cigars").fetchall())
    conn.close()

    csv_files = sorted(RETAILER_CSV_DIR.glob("*.csv"))
    total_orphans = 0
    total_checked = 0
    files_with_issues = 0

    print(f"\n  VALIDATING RETAILER CSVs")
    print(f"  Master DB: {len(valid_cids)} valid CIDs")
    print(f"  Scanning: {RETAILER_CSV_DIR}\n")

    for csv_file in csv_files:
        if 'backup' in csv_file.name:
            continue

        try:
            with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                orphans = []
                row_count = 0
                for row in reader:
                    row_count += 1
                    cid = row.get('cigar_id', '').strip()
                    if cid and cid not in valid_cids:
                        orphans.append(cid)

                total_checked += row_count
                if orphans:
                    files_with_issues += 1
                    total_orphans += len(orphans)
                    print(f"  [WARN] {csv_file.name}: {len(orphans)} orphaned CID(s) out of {row_count}")
                    for o in orphans[:5]:
                        print(f"         {o}")
                    if len(orphans) > 5:
                        print(f"         ... and {len(orphans) - 5} more")
        except Exception as e:
            print(f"  [ERROR] Could not read {csv_file.name}: {e}")

    print(f"\n  {'='*50}")
    print(f"  Files scanned:    {len(csv_files)}")
    print(f"  Total rows:       {total_checked}")
    print(f"  Orphaned CIDs:    {total_orphans}")
    print(f"  Files with issues: {files_with_issues}")

    if total_orphans == 0:
        print(f"  Status: ALL CLEAR")
    else:
        print(f"  Status: {total_orphans} orphans need attention")
    print(f"  {'='*50}")


# ─── EXPORT ───────────────────────────────────────────────────────────────────

def cmd_export(args):
    """Export the database back to CSV."""
    conn = get_db()
    output = args.output or (PROJECT_ROOT / "data" / "master_cigars_export.csv")

    rows = conn.execute("SELECT * FROM cigars ORDER BY brand, line, vitola").fetchall()
    columns = [desc[0] for desc in conn.execute("SELECT * FROM cigars LIMIT 1").description]
    conn.close()

    # Map SQLite column names back to original CSV column names
    col_map = {
        'cigar_id': 'cigar_id', 'brand': 'Brand', 'line': 'Line',
        'wrapper': 'Wrapper', 'wrapper_alias': 'Wrapper_Alias', 'vitola': 'Vitola',
        'length': 'Length', 'ring_gauge': 'Ring Gauge', 'binder': 'Binder',
        'filler': 'Filler', 'strength': 'Strength', 'box_quantity': 'Box Quantity',
        'style': 'Style', 'parent_brand': 'parent_brand', 'sub_brand': 'sub_brand',
        'product_name': 'product_name', 'wrapper_code': 'wrapper_code',
        'packaging_type': 'packaging_type', 'country_of_origin': 'country_of_origin',
        'factory': 'factory', 'release_type': 'release_type',
        'sampler_flag': 'sampler_flag', 'msrp_stick_usd': 'msrp_stick_usd',
        'msrp_box_usd': 'msrp_box_usd', 'first_release_year': 'first_release_year',
        'discontinued_flag': 'discontinued_flag', 'retailer_sku': 'retailer_sku',
        'upc_ean': 'upc_ean', 'notes': 'notes', 'source_url': 'source_url',
    }

    # Exclude internal timestamp columns from export
    export_cols = [c for c in columns if c not in ('created_at', 'updated_at')]
    csv_headers = [col_map.get(c, c) for c in export_cols]

    with open(output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)
        for row in rows:
            writer.writerow([row[c] if row[c] is not None else '' for c in export_cols])

    print(f"  [OK] Exported {len(rows)} cigars to {output}")


# ─── STATS ────────────────────────────────────────────────────────────────────

def cmd_stats(args):
    """Show database statistics."""
    conn = get_db()
    c = conn.cursor()

    total = c.execute("SELECT COUNT(*) FROM cigars").fetchone()[0]
    brands = c.execute("SELECT COUNT(DISTINCT brand) FROM cigars").fetchone()[0]
    lines = c.execute("SELECT COUNT(DISTINCT brand || '|' || line) FROM cigars").fetchone()[0]

    print(f"\n  MASTER CIGAR DATABASE")
    print(f"  {'='*40}")
    print(f"  Total SKUs:    {total}")
    print(f"  Brands:        {brands}")
    print(f"  Lines:         {lines}")
    print(f"  Database:      {DB_PATH}")
    print(f"  Size:          {DB_PATH.stat().st_size / 1024:.1f} KB")

    print(f"\n  Top 10 Brands:")
    for row in c.execute("SELECT brand, COUNT(*) as cnt FROM cigars GROUP BY brand ORDER BY cnt DESC LIMIT 10"):
        print(f"    {row[0]:<25} {row[1]} SKUs")

    print(f"\n  Wrapper codes:")
    for row in c.execute("SELECT wrapper_code, COUNT(*) as cnt FROM cigars WHERE wrapper_code IS NOT NULL GROUP BY wrapper_code ORDER BY cnt DESC LIMIT 10"):
        print(f"    {row[0]:<6} {row[1]} SKUs")

    conn.close()
    print(f"  {'='*40}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Cigar Master Database Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add
    subparsers.add_parser("add", help="Add a new cigar (interactive)")

    # edit
    edit_p = subparsers.add_parser("edit", help="Edit metadata for an existing CID")
    edit_p.add_argument("cigar_id", help="The CID to edit (partial match supported)")

    # rename-cid
    rename_p = subparsers.add_parser("rename-cid", help="Rename a CID across DB and all retailer CSVs")
    rename_p.add_argument("old_cid", help="Current CID")
    rename_p.add_argument("new_cid", help="New CID")

    # list
    list_p = subparsers.add_parser("list", help="Search/filter cigars")
    list_p.add_argument("--brand", help="Filter by brand name")
    list_p.add_argument("--line", help="Filter by line name")
    list_p.add_argument("--wrapper", help="Filter by wrapper")
    list_p.add_argument("--cid", help="Filter by CID fragment")

    # validate
    subparsers.add_parser("validate", help="Check retailer CSVs for orphaned CIDs")

    # export
    export_p = subparsers.add_parser("export", help="Export database to CSV")
    export_p.add_argument("--output", help="Output file path", default=None)

    # stats
    subparsers.add_parser("stats", help="Show database statistics")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "add": cmd_add,
        "edit": cmd_edit,
        "rename-cid": cmd_rename_cid,
        "list": cmd_list,
        "validate": cmd_validate,
        "export": cmd_export,
        "stats": cmd_stats,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
