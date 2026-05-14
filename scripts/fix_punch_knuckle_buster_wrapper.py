"""Surface "Habano" as the wrapper alias on Punch Knuckle Buster's NIC row.

The cigar band literally says "Habano" — but the master catalog had
Wrapper='Nicaraguan Habano' / Wrapper_Alias='Natural' for the NIC variant.
Combined with a (now-removed) global wrapper-alias fallback, the dropdown
was rendering "Sun Grown (Natural)" — Padron's mapping leaking into Punch.

This one-shot script normalizes the master row in both data sources so the
dropdown reads "Habano (Nicaraguan)" — Habano prominent, origin in parens.

Idempotent: safe to re-run; only writes when the canonical/alias fields
do not already match the target.
"""
from __future__ import annotations

import csv
import shutil
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

CSV_PATH = Path("data/master_cigars.csv")
DB_PATH = Path("data/master_cigars.db")

# Match exactly the NIC variant — narrow enough that we won't accidentally
# touch the MAD/ECU sibling rows.
CID_TARGET = "PUNCH|PUNCH|KNUCKLEBUSTER|GORDO|GORDO|6x60|NIC|BOX20"
NEW_WRAPPER = "Habano"          # Wrapper / wrapper
NEW_WRAPPER_ALIAS = "Nicaraguan"  # Wrapper_Alias / wrapper_alias


def update_csv() -> None:
    if not CSV_PATH.exists():
        print(f"[skip] {CSV_PATH} not found")
        return

    rows: list[dict] = []
    fieldnames: list[str] = []
    touched = 0
    with CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            if row.get("cigar_id") == CID_TARGET:
                if (row.get("Wrapper") != NEW_WRAPPER
                        or row.get("Wrapper_Alias") != NEW_WRAPPER_ALIAS):
                    row["Wrapper"] = NEW_WRAPPER
                    row["Wrapper_Alias"] = NEW_WRAPPER_ALIAS
                    touched += 1
            rows.append(row)

    if touched == 0:
        print(f"[csv] no change needed (already Wrapper={NEW_WRAPPER!r}, "
              f"Wrapper_Alias={NEW_WRAPPER_ALIAS!r})")
        return

    backup = CSV_PATH.with_suffix(
        f".csv.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    shutil.copy2(CSV_PATH, backup)
    print(f"[csv] backed up to {backup}")

    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"[csv] updated {touched} row(s)")


def update_db() -> None:
    if not DB_PATH.exists():
        print(f"[skip] {DB_PATH} not found")
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "SELECT wrapper, wrapper_alias FROM cigars WHERE cigar_id = ?",
            (CID_TARGET,),
        )
        row = cur.fetchone()
        if not row:
            print(f"[db] no row found for cigar_id={CID_TARGET}")
            return
        current_wrapper, current_alias = row
        if current_wrapper == NEW_WRAPPER and current_alias == NEW_WRAPPER_ALIAS:
            print("[db] no change needed (already correct)")
            return
        conn.execute(
            "UPDATE cigars SET wrapper = ?, wrapper_alias = ? WHERE cigar_id = ?",
            (NEW_WRAPPER, NEW_WRAPPER_ALIAS, CID_TARGET),
        )
        conn.commit()
        print(f"[db] updated {CID_TARGET}: "
              f"wrapper {current_wrapper!r} -> {NEW_WRAPPER!r}, "
              f"wrapper_alias {current_alias!r} -> {NEW_WRAPPER_ALIAS!r}")
    finally:
        conn.close()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    update_csv()
    update_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
