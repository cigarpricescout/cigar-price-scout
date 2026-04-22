"""Sync data/master_cigars.db from data/master_cigars.csv.

The CSV is the source of truth for cigar metadata. The SQLite database is a
derivative the daily pricing updaters read from to backfill metadata into
retailer CSVs (see app/update_*_prices_final.py). When the CSV drifts from the
DB, new cigar entries silently lose their title/brand/line/etc. on the first
price run (see the Opus X Oro Oscuro incident, 2026-04-21).

This script upserts every row from the CSV into the DB. Existing rows keep their
`created_at`; `updated_at` is bumped. Rows in the DB that no longer appear in
the CSV are left untouched unless `--prune` is passed.

Run locally before a daily pricing push, and as a step in the GitHub Actions
daily pricing workflow.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "data" / "master_cigars.csv"
DEFAULT_DB = REPO_ROOT / "data" / "master_cigars.db"

# CSV column -> DB column. Every DB column that the daily pipeline cares about
# has a source column on the CSV side.
COLUMN_MAP: dict[str, str] = {
    "Brand": "brand",
    "Line": "line",
    "Wrapper": "wrapper",
    "Wrapper_Alias": "wrapper_alias",
    "Vitola": "vitola",
    "Length": "length",
    "Ring Gauge": "ring_gauge",
    "Binder": "binder",
    "Filler": "filler",
    "Strength": "strength",
    "Box Quantity": "box_quantity",
    "Style": "style",
    "cigar_id": "cigar_id",
    "parent_brand": "parent_brand",
    "sub_brand": "sub_brand",
    "product_name": "product_name",
    "wrapper_code": "wrapper_code",
    "packaging_type": "packaging_type",
    "country_of_origin": "country_of_origin",
    "factory": "factory",
    "release_type": "release_type",
    "sampler_flag": "sampler_flag",
    "msrp_stick_usd": "msrp_stick_usd",
    "msrp_box_usd": "msrp_box_usd",
    "first_release_year": "first_release_year",
    "discontinued_flag": "discontinued_flag",
    "retailer_sku": "retailer_sku",
    "upc_ean": "upc_ean",
    "notes": "notes",
    "source_url": "source_url",
}

# Required non-null columns per the current schema.
REQUIRED_DB_COLS = {"cigar_id", "brand", "line", "vitola", "box_quantity"}


def _clean(value: Any) -> Optional[Any]:
    """Turn pandas NaN / empty string into SQL NULL; strip str values."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return value


def _coerce_int(value: Any) -> Optional[int]:
    v = _clean(value)
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    v = _clean(value)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_row(rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Translate one CSV record into a dict keyed by DB columns."""
    out: dict[str, Any] = {}
    for csv_col, db_col in COLUMN_MAP.items():
        raw = rec.get(csv_col)
        if db_col == "box_quantity":
            out[db_col] = _coerce_int(raw)
        elif db_col in ("msrp_stick_usd", "msrp_box_usd"):
            out[db_col] = _coerce_float(raw)
        else:
            out[db_col] = _clean(raw)

    missing = [c for c in REQUIRED_DB_COLS if out.get(c) in (None, "")]
    if missing:
        return None
    return out


def sync(csv_path: Path, db_path: Path, prune: bool = False) -> dict[str, int]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    df = pd.read_csv(csv_path, dtype=str)
    csv_ids: set[str] = set()
    prepared: list[dict[str, Any]] = []
    skipped = 0

    for rec in df.to_dict("records"):
        row = build_row(rec)
        if row is None:
            skipped += 1
            continue
        csv_ids.add(row["cigar_id"])
        prepared.append(row)

    db_cols = list(COLUMN_MAP.values())
    placeholders = ", ".join(f":{c}" for c in db_cols)
    columns_sql = ", ".join(db_cols)
    update_sql = ", ".join(
        f"{c} = excluded.{c}" for c in db_cols if c != "cigar_id"
    )
    upsert = (
        f"INSERT INTO cigars ({columns_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT(cigar_id) DO UPDATE SET {update_sql}, "
        f"updated_at = CURRENT_TIMESTAMP"
    )

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        before = cur.execute("SELECT COUNT(*) FROM cigars").fetchone()[0]
        cur.executemany(upsert, prepared)

        pruned = 0
        if prune:
            db_ids = {r[0] for r in cur.execute("SELECT cigar_id FROM cigars")}
            orphans = db_ids - csv_ids
            if orphans:
                cur.executemany(
                    "DELETE FROM cigars WHERE cigar_id = ?",
                    [(i,) for i in orphans],
                )
                pruned = len(orphans)

        con.commit()
        after = cur.execute("SELECT COUNT(*) FROM cigars").fetchone()[0]
    finally:
        con.close()

    return {
        "csv_rows": len(df),
        "upserted": len(prepared),
        "skipped": skipped,
        "db_before": before,
        "db_after": after,
        "pruned": pruned,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete rows from the DB whose cigar_id is not in the CSV.",
    )
    args = parser.parse_args(argv)

    stats = sync(args.csv, args.db, prune=args.prune)
    print(
        "master_cigars sync complete: "
        f"csv_rows={stats['csv_rows']} "
        f"upserted={stats['upserted']} "
        f"skipped={stats['skipped']} "
        f"db_before={stats['db_before']} "
        f"db_after={stats['db_after']} "
        f"pruned={stats['pruned']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
