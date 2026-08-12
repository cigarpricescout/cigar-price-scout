"""Prune data/historical_prices.db so it stays under GitHub's 100 MB push limit.

Daily pricing automation appends to this SQLite file and commits it. Once the
file exceeds 100 MB, ``git push`` is rejected (GH001) and the whole daily job
fails — even though CSV scrapes succeeded. This script keeps a rolling window
of price_history (and related change tables) and VACUUMs the file.

Usage:
  python scripts/prune_historical_prices_db.py              # dry-run stats
  python scripts/prune_historical_prices_db.py --apply      # prune + vacuum
  python scripts/prune_historical_prices_db.py --apply --keep-days 120
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "historical_prices.db"
# Leave headroom under GitHub's hard 100 MB limit for a few days of growth.
TARGET_BYTES = 70 * 1024 * 1024
DEFAULT_KEEP_DAYS = 150


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.2f} MB"


def _stats(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    out = {}
    for table in (
        "price_history",
        "price_changes",
        "stock_changes",
        "automation_runs",
        "retailer_runs",
    ):
        try:
            out[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            out[table] = None
    try:
        out["ph_range"] = cur.execute(
            "SELECT MIN(date), MAX(date) FROM price_history"
        ).fetchone()
    except sqlite3.Error:
        out["ph_range"] = (None, None)
    return out


def prune(db_path: Path, keep_days: int, apply: bool) -> int:
    if not db_path.exists():
        print(f"[ERROR] missing {db_path}")
        return 2

    before = db_path.stat().st_size
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    print(f"DB: {db_path}")
    print(f"Size before: {_mb(before)}")
    print(f"Keep last {keep_days} days (cutoff date < {cutoff})")

    conn = sqlite3.connect(str(db_path))
    stats_before = _stats(conn)
    print(f"Rows before: {stats_before}")

    if not apply:
        print("\nDRY RUN — re-run with --apply to prune + VACUUM.")
        conn.close()
        return 0

    cur = conn.cursor()
    deletes = [
        ("price_history", "DELETE FROM price_history WHERE date < ?", (cutoff,)),
        ("price_changes", "DELETE FROM price_changes WHERE date < ?", (cutoff,)),
        ("stock_changes", "DELETE FROM stock_changes WHERE date < ?", (cutoff,)),
        (
            "automation_runs",
            "DELETE FROM automation_runs WHERE date < ?",
            (cutoff,),
        ),
        (
            "retailer_runs",
            "DELETE FROM retailer_runs WHERE date < ?",
            (cutoff,),
        ),
    ]
    for name, sql, params in deletes:
        try:
            cur.execute(sql, params)
            print(f"  deleted from {name}: {cur.rowcount}")
        except sqlite3.Error as e:
            print(f"  skip {name}: {e}")
    conn.commit()

    # Free pages on disk (this rewrites the file).
    print("VACUUM...")
    conn.execute("VACUUM")
    conn.close()

    after = db_path.stat().st_size
    print(f"Size after: {_mb(after)} (was {_mb(before)})")

    # If still too large, tighten the window further.
    if after > TARGET_BYTES:
        tighter = max(60, keep_days // 2)
        tighter_cutoff = (date.today() - timedelta(days=tighter)).isoformat()
        print(
            f"Still above target {_mb(TARGET_BYTES)}; "
            f"tightening to {tighter} days (cutoff {tighter_cutoff})"
        )
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        for name, sql, _ in deletes:
            try:
                cur.execute(sql, (tighter_cutoff,))
                print(f"  deleted from {name}: {cur.rowcount}")
            except sqlite3.Error as e:
                print(f"  skip {name}: {e}")
        conn.commit()
        print("VACUUM...")
        conn.execute("VACUUM")
        conn.close()
        after = db_path.stat().st_size
        print(f"Size after tighten: {_mb(after)}")

    if after >= 100 * 1024 * 1024:
        print(
            "[ERROR] DB is still >= 100 MB — do not commit it. "
            "Exclude data/historical_prices.db from the push."
        )
        return 1

    print("[OK] DB is under GitHub's 100 MB limit.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    return prune(Path(args.db), args.keep_days, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
