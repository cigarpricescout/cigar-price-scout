"""
Fix box quantities and dimensions for Padron CIDs that have incorrect metadata.
Only modifies CIDs that are NOT referenced in any retailer CSV or historical DB.

22 corrections total:
- 14 box quantity fixes (both Natural + Maduro variants = 28 CID changes)
- 8 dimension fixes (various wrappers)
"""

import sqlite3
import os
import csv
import glob

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..')
MASTER_DB = os.path.join(DATA_DIR, 'data', 'master_cigars.db')
HISTORICAL_DB = os.path.join(DATA_DIR, 'data', 'historical_prices.db')
CSV_DIR = os.path.join(DATA_DIR, 'static', 'data')


def get_referenced_padron_cids():
    """Get all Padron CIDs that exist in retailer CSVs or historical DB."""
    referenced = set()

    # Retailer CSVs
    for fpath in glob.glob(os.path.join(CSV_DIR, '*.csv')):
        if '_backup_' in os.path.basename(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cid = row.get('cigar_id', '').strip()
                    if cid and 'PADRON' in cid.upper():
                        referenced.add(cid)
        except Exception:
            pass

    # Historical DB
    if os.path.exists(HISTORICAL_DB):
        hconn = sqlite3.connect(HISTORICAL_DB)
        for row in hconn.execute(
            "SELECT DISTINCT cigar_id FROM price_history WHERE cigar_id LIKE '%PADRON%'"
        ).fetchall():
            referenced.add(row[0])
        hconn.close()

    return referenced


# Box quantity corrections: (line, vitola, wrong_qty, correct_qty)
BOX_QTY_FIXES = [
    ('1926 Serie', 'No. 90 (Tubo)', 15, 10),
    ('1926 Serie 40 Years', '40 Years Torpedo', 10, 20),
    ('1926 Serie 80 Years', '80 Years Perfecto', 10, 8),
    ('1926 Serie TAA', 'No. 47 TAA', 20, 24),
    ('1926 Serie TAA', 'No. 48 TAA', 20, 24),
    ('1964 Anniversary', 'A', 15, 10),
    ('1964 Anniversary', 'Imperial', 26, 25),
    ('1964 Anniversary', 'Monarca', 26, 25),
    ('1964 Anniversary', 'Piramide', 20, 25),
    ('1964 Anniversary', 'Superior', 26, 25),
    ('1964 Anniversary TAA', 'Belicoso TAA', 20, 25),
    ('Padron Series', 'Cortico', 5, 30),
    ('Padron Series', 'Delicias', 25, 26),
    ('Padron Series', 'Magnum', 10, 26),
]

# Dimension corrections: (line, vitola, wrong_len, wrong_rg, correct_len, correct_rg)
DIMENSION_FIXES = [
    ('Damaso', 'No. 8', '4', '50', '5.5', '46'),
    ('Damaso', 'No. 15', '5.5', '50', '6', '52'),
    ('Damaso', 'No. 17', '6', '50', '7', '54'),
    ('Damaso', 'No. 32', '4.5', '52', '5.25', '52'),
    ('Family Reserve', 'No. 45', '5.125', '52', '6', '52'),
    ('Family Reserve', 'No. 50', '6.5', '50', '5', '54'),
    ('Family Reserve', 'No. 85', '6.5', '54', '5.25', '50'),
    ('Family Reserve', 'No. 95', '8', '52', '4.75', '60'),
]


def rebuild_cid(old_cid, old_size, new_size, old_box, new_box):
    """Rebuild a CID by replacing the size and/or box portions."""
    new_cid = old_cid
    if old_size and new_size and old_size != new_size:
        new_cid = new_cid.replace(f'|{old_size}|', f'|{new_size}|')
    if old_box and new_box and old_box != new_box:
        new_cid = new_cid.replace(old_box, new_box)
    return new_cid


def main():
    referenced = get_referenced_padron_cids()
    print(f"Padron CIDs referenced in retailer CSVs / historical DB: {len(referenced)}")
    print()

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    total_updated = 0
    blocked = 0

    # --- BOX QUANTITY FIXES ---
    print("=== Box Quantity Fixes ===\n")
    for line, vitola, wrong_qty, correct_qty in BOX_QTY_FIXES:
        rows = cursor.execute(
            "SELECT cigar_id, wrapper, box_quantity, length, ring_gauge FROM cigars "
            "WHERE brand = 'Padron' AND line = ? AND vitola = ?",
            (line, vitola)
        ).fetchall()

        for old_cid, wrapper, current_qty, length, rg in rows:
            if old_cid in referenced:
                print(f"  BLOCKED (in use): {old_cid}")
                blocked += 1
                continue

            old_box = f"|BOX{wrong_qty}"
            new_box = f"|BOX{correct_qty}"
            new_cid = old_cid.replace(old_box, new_box)

            # Check for conflicts
            conflict = cursor.execute(
                "SELECT 1 FROM cigars WHERE cigar_id = ?", (new_cid,)
            ).fetchone()
            if conflict:
                print(f"  CONFLICT: {new_cid} already exists -- skipping")
                continue

            cursor.execute(
                "UPDATE cigars SET cigar_id = ?, box_quantity = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE cigar_id = ?",
                (new_cid, correct_qty, old_cid)
            )
            print(f"  OK [{wrapper}] box {current_qty} -> {correct_qty}")
            print(f"    OLD: {old_cid}")
            print(f"    NEW: {new_cid}")
            total_updated += 1

    # --- DIMENSION FIXES ---
    print("\n=== Dimension Fixes ===\n")
    for line, vitola, wrong_len, wrong_rg, correct_len, correct_rg in DIMENSION_FIXES:
        rows = cursor.execute(
            "SELECT cigar_id, wrapper, length, ring_gauge, box_quantity FROM cigars "
            "WHERE brand = 'Padron' AND line = ? AND vitola = ?",
            (line, vitola)
        ).fetchall()

        for old_cid, wrapper, cur_len, cur_rg, bq in rows:
            if old_cid in referenced:
                print(f"  BLOCKED (in use): {old_cid}")
                blocked += 1
                continue

            old_size = f"{wrong_len}x{wrong_rg}"
            new_size = f"{correct_len}x{correct_rg}"
            new_cid = old_cid.replace(f"|{old_size}|", f"|{new_size}|")

            if new_cid == old_cid:
                # Size string might not match exactly, try current values
                cur_size = f"{cur_len}x{cur_rg}"
                new_cid = old_cid.replace(f"|{cur_size}|", f"|{new_size}|")

            if new_cid == old_cid:
                print(f"  SKIP (size not found in CID): {old_cid}")
                continue

            conflict = cursor.execute(
                "SELECT 1 FROM cigars WHERE cigar_id = ?", (new_cid,)
            ).fetchone()
            if conflict:
                print(f"  CONFLICT: {new_cid} already exists -- skipping")
                continue

            cursor.execute(
                "UPDATE cigars SET cigar_id = ?, length = ?, ring_gauge = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE cigar_id = ?",
                (new_cid, correct_len, correct_rg, old_cid)
            )
            print(f"  OK [{wrapper}] {cur_len}x{cur_rg} -> {correct_len}x{correct_rg}")
            print(f"    OLD: {old_cid}")
            print(f"    NEW: {new_cid}")
            total_updated += 1

    conn.commit()

    # --- VERIFICATION ---
    print(f"\n=== Summary ===")
    print(f"  Total CIDs updated: {total_updated}")
    print(f"  Blocked (in use): {blocked}")

    # Verify box quantities
    print(f"\n=== Verification: spot-check corrected values ===")
    checks = [
        ('1926 Serie', 'No. 90 (Tubo)', 10),
        ('1926 Serie 40 Years', '40 Years Torpedo', 20),
        ('1926 Serie 80 Years', '80 Years Perfecto', 8),
        ('1964 Anniversary', 'A', 10),
        ('1964 Anniversary', 'Imperial', 25),
        ('Padron Series', 'Magnum', 26),
        ('Padron Series', 'Delicias', 26),
    ]
    for line, vitola, expected_bq in checks:
        rows = cursor.execute(
            "SELECT wrapper, box_quantity FROM cigars WHERE brand='Padron' AND line=? AND vitola=?",
            (line, vitola)
        ).fetchall()
        for wrapper, bq in rows:
            status = "OK" if bq == expected_bq else f"WRONG (got {bq})"
            print(f"  {line} / {vitola} / {wrapper}: box={bq} [{status}]")

    dim_checks = [
        ('Damaso', 'No. 8', '5.5', '46'),
        ('Family Reserve', 'No. 95', '4.75', '60'),
        ('Family Reserve', 'No. 50', '5', '54'),
    ]
    for line, vitola, exp_len, exp_rg in dim_checks:
        rows = cursor.execute(
            "SELECT wrapper, length, ring_gauge FROM cigars WHERE brand='Padron' AND line=? AND vitola=?",
            (line, vitola)
        ).fetchall()
        for wrapper, l, rg in rows:
            ok = l == exp_len and rg == exp_rg
            status = "OK" if ok else f"WRONG (got {l}x{rg})"
            print(f"  {line} / {vitola} / {wrapper}: {l}x{rg} [{status}]")

    conn.close()


if __name__ == '__main__':
    main()
