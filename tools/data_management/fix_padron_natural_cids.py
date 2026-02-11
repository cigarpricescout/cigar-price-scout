"""
Fix 44 truncated Padron Natural CIDs in master_cigars.db.

Problem: All Padron Natural CIDs were imported without the |BOX## suffix and
with wrapper code CAM instead of NAT. This makes them unmatchable to retailer
CSVs, which use NAT|BOX## format.

Solution: For each truncated Natural CID, mirror the Maduro counterpart CID
and swap |MAD| -> |NAT|. This matches the pattern already used in retailer CSVs.

Also checks and updates historical_prices.db if any old CIDs exist there.
"""

import sqlite3
import os

MASTER_DB = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'master_cigars.db')
HISTORICAL_DB = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'historical_prices.db')


def build_rename_map(conn):
    """Build old_cid -> new_cid mapping for all truncated Padron Natural CIDs."""
    naturals = conn.execute("""
        SELECT cigar_id, line, vitola
        FROM cigars
        WHERE brand = 'Padron' AND cigar_id NOT LIKE '%|BOX%'
        ORDER BY line, vitola
    """).fetchall()

    rename_map = {}
    for old_cid, line, vitola in naturals:
        # Find the Maduro counterpart
        mad = conn.execute("""
            SELECT cigar_id FROM cigars
            WHERE brand = 'Padron' AND line = ? AND vitola = ? AND wrapper = 'Maduro'
        """, (line, vitola)).fetchone()

        if mad:
            new_cid = mad[0].replace('|MAD|', '|NAT|')
            rename_map[old_cid] = new_cid
        else:
            print(f"  WARNING: No Maduro counterpart for {old_cid} -- skipping")

    return rename_map


def fix_master_db(rename_map):
    """Update CIDs in master_cigars.db."""
    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    print(f"\n=== Fixing {len(rename_map)} CIDs in master_cigars.db ===\n")

    success = 0
    for old_cid, new_cid in sorted(rename_map.items()):
        # Check for conflict (new CID already exists)
        existing = cursor.execute(
            "SELECT cigar_id FROM cigars WHERE cigar_id = ?", (new_cid,)
        ).fetchone()

        if existing:
            print(f"  CONFLICT: {new_cid} already exists -- skipping {old_cid}")
            continue

        cursor.execute(
            "UPDATE cigars SET cigar_id = ?, updated_at = CURRENT_TIMESTAMP WHERE cigar_id = ?",
            (new_cid, old_cid)
        )
        if cursor.rowcount == 1:
            print(f"  OK: {old_cid}")
            print(f"   -> {new_cid}")
            success += 1
        else:
            print(f"  MISS: {old_cid} not found in database")

    conn.commit()
    conn.close()
    print(f"\nMaster DB: {success} CIDs updated successfully")
    return success


def fix_historical_db(rename_map):
    """Update any matching CIDs in historical_prices.db."""
    if not os.path.exists(HISTORICAL_DB):
        print("\nhistorical_prices.db not found -- skipping")
        return 0

    conn = sqlite3.connect(HISTORICAL_DB)
    cursor = conn.cursor()

    # Check which old CIDs exist in historical data
    found = 0
    updated = 0
    for old_cid, new_cid in sorted(rename_map.items()):
        count = cursor.execute(
            "SELECT COUNT(*) FROM price_history WHERE cigar_id = ?", (old_cid,)
        ).fetchone()[0]

        if count > 0:
            found += 1
            cursor.execute(
                "UPDATE price_history SET cigar_id = ? WHERE cigar_id = ?",
                (new_cid, old_cid)
            )
            updated += cursor.rowcount
            print(f"  Historical: {old_cid} -> {new_cid} ({count} rows)")

    conn.commit()
    conn.close()

    if found == 0:
        print("\nHistorical DB: No truncated CIDs found (nothing to fix)")
    else:
        print(f"\nHistorical DB: {updated} rows updated across {found} CIDs")

    return updated


def verify(rename_map):
    """Verify the fixes worked."""
    conn = sqlite3.connect(MASTER_DB)

    # Check no more truncated CIDs
    remaining = conn.execute("""
        SELECT COUNT(*) FROM cigars
        WHERE brand = 'Padron' AND cigar_id NOT LIKE '%|BOX%'
    """).fetchone()[0]

    # Check all new CIDs exist
    missing = 0
    for new_cid in rename_map.values():
        exists = conn.execute(
            "SELECT 1 FROM cigars WHERE cigar_id = ?", (new_cid,)
        ).fetchone()
        if not exists:
            missing += 1
            print(f"  VERIFY FAIL: {new_cid} not found")

    # Verify the 5 retailer orphan CIDs now exist in master
    retailer_cids = [
        'PADRON|PADRON|1926SERIE|NO.9|NO.9|5.25x56|NAT|BOX24',
        'PADRON|PADRON|1964ANNIVERSARY|CORONA|CORONA|6x42|NAT|BOX25',
        'PADRON|PADRON|1964ANNIVERSARY|DIPLOMATICO|DIPLOMATICO|7x50|NAT|BOX25',
        'PADRON|PADRON|1964ANNIVERSARY|EXCLUSIVO|EXCLUSIVO|5.5x50|NAT|BOX25',
        'PADRON|PADRON|1964ANNIVERSARY|PRINCIPE|PRINCIPE|4.5x46|NAT|BOX25',
    ]
    orphan_fixed = 0
    for cid in retailer_cids:
        exists = conn.execute(
            "SELECT 1 FROM cigars WHERE cigar_id = ?", (cid,)
        ).fetchone()
        if exists:
            orphan_fixed += 1
        else:
            print(f"  ORPHAN STILL MISSING: {cid}")

    conn.close()

    print(f"\n=== Verification ===")
    print(f"  Remaining truncated CIDs: {remaining}")
    print(f"  New CIDs missing from DB: {missing}")
    print(f"  Retailer orphan CIDs now in master: {orphan_fixed}/5")

    if remaining == 0 and missing == 0 and orphan_fixed == 5:
        print("  ALL CHECKS PASSED")
    else:
        print("  SOME CHECKS FAILED - review above")


if __name__ == '__main__':
    conn = sqlite3.connect(MASTER_DB)
    rename_map = build_rename_map(conn)
    conn.close()

    print(f"Found {len(rename_map)} truncated CIDs to fix")

    fix_master_db(rename_map)
    fix_historical_db(rename_map)
    verify(rename_map)
