#!/usr/bin/env python3
"""
Record daily price_history rows for blocked retailers using the same effective
prices shown on /compare (CSV shell + observed_prices + extension_staged_approvals).

Run after scraper track_changes in daily-pricing-update.yml. Requires
ANALYTICS_DB_URL (or DATABASE_URL) pointing at Railway Postgres.

Exit 0 when skipped (no DB URL) or on success; exit 1 on hard failures.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AUTOMATION_DIR = PROJECT_ROOT / "automation"
for p in (PROJECT_ROOT, AUTOMATION_DIR):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


def _pg_url() -> Optional[str]:
    return (os.getenv("ANALYTICS_DB_URL") or os.getenv("DATABASE_URL") or "").strip() or None


def _product_to_track_row(product: Any) -> Optional[Dict[str, Any]]:
    cid = (getattr(product, "cigar_id", None) or "").strip()
    price_cents = int(getattr(product, "price_cents", 0) or 0)
    if not cid or price_cents <= 0:
        return None
    in_stock = getattr(product, "in_stock", True)
    ps = getattr(product, "price_source", None) or "csv"
    updated = getattr(product, "observed_at", None)
    if not updated:
        updated = datetime.now().isoformat(timespec="seconds")
    return {
        "cigar_id": cid,
        "price": price_cents / 100.0,
        "in_stock": bool(in_stock),
        "url": getattr(product, "url", "") or "",
        "source": ps,
        "source_updated_at": updated,
    }


def _dedupe_by_cigar_id(products: List[Any]) -> List[Any]:
    """One row per (retailer_key, cigar_id); higher overlay priority wins."""
    priority = {"operator_approved": 3, "observed": 2, "csv": 1}
    best: Dict[tuple, Any] = {}
    for p in products:
        cid = (getattr(p, "cigar_id", None) or "").strip()
        rk = getattr(p, "retailer_key", None) or ""
        if not cid or not rk:
            continue
        key = (rk, cid)
        existing = best.get(key)
        ps = getattr(p, "price_source", "csv") or "csv"
        if not existing:
            best[key] = p
            continue
        es = getattr(existing, "price_source", "csv") or "csv"
        if priority.get(ps, 0) >= priority.get(es, 0):
            best[key] = p
    return list(best.values())


def build_effective_blocked_products() -> List[Any]:
    """Mirror load_all_products() merge order for blocked retailers only."""
    from app.cid_matcher import canonical_cigar_id_for_comparison  # type: ignore
    from app.main import (  # type: ignore
        RETAILERS,
        _load_observed_overlay,
        _load_staged_approval_overlay,
        _merge_blocked_overlay_onto_csv_products,
        get_blocked_retailer_keys,
        load_csv,
        load_master_index,
    )

    blocked = get_blocked_retailer_keys()
    if not blocked:
        return []

    master_index = load_master_index()
    all_products: List[Any] = []
    for retailer in RETAILERS:
        key = retailer["key"]
        if key not in blocked:
            continue
        all_products.extend(
            load_csv(
                retailer["csv"],
                key,
                retailer["name"],
                master_index=master_index,
            )
        )

    observed_products = _load_observed_overlay()
    if observed_products:
        merged_obs = _merge_blocked_overlay_onto_csv_products(
            all_products, observed_products, price_source="observed",
        )
        for op in observed_products:
            pair = (
                op.retailer_key,
                canonical_cigar_id_for_comparison(op.cigar_id or ""),
            )
            if pair not in merged_obs:
                all_products.append(op)

    staged_products = _load_staged_approval_overlay()
    if staged_products:
        merged_staged = _merge_blocked_overlay_onto_csv_products(
            all_products, staged_products, price_source="operator_approved",
        )
        for sp in staged_products:
            pair = (
                sp.retailer_key,
                canonical_cigar_id_for_comparison(sp.cigar_id or ""),
            )
            if pair not in merged_staged:
                all_products.append(sp)

    return _dedupe_by_cigar_id(all_products)


def load_previous_history_state(
    retailer_key: str,
    historical_db_path: Path,
    before_date: date,
) -> List[Dict[str, Any]]:
    """Rows from the most recent price_history date strictly before ``before_date``."""
    if not historical_db_path.exists():
        return []
    conn = sqlite3.connect(str(historical_db_path), detect_types=0)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cigar_id, price, in_stock, url
            FROM price_history
            WHERE retailer = ?
              AND date = (
                SELECT MAX(date) FROM price_history
                WHERE retailer = ? AND date < ?
              )
            """,
            (retailer_key, retailer_key, before_date.isoformat()),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {
            "cigar_id": r[0],
            "price": r[1],
            "in_stock": r[2],
            "url": r[3] or "",
        }
        for r in rows
        if r[0]
    ]


def main() -> int:
    db_url = _pg_url()
    if not db_url:
        print(
            "snapshot_blocked_effective_prices: ANALYTICS_DB_URL not set; skipping."
        )
        return 0

    os.environ["ANALYTICS_DB_URL"] = db_url

    try:
        products = build_effective_blocked_products()
    except Exception as e:
        print(f"snapshot_blocked_effective_prices: failed to build products: {e}")
        return 1

    from automation.automated_cigar_price_system import AutomatedCigarPriceSystem

    system = AutomatedCigarPriceSystem(project_root=str(PROJECT_ROOT))
    today = datetime.now().date()

    by_retailer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in products:
        row = _product_to_track_row(p)
        if row:
            by_retailer[p.retailer_key].append(row)

    if not by_retailer:
        print("snapshot_blocked_effective_prices: no priced blocked products to record.")
        return 0

    total_rows = 0
    for retailer_key in sorted(by_retailer.keys()):
        post_state = by_retailer[retailer_key]
        pre_state = load_previous_history_state(
            retailer_key, system.historical_db_path, today,
        )
        system.track_changes(retailer_key, pre_state, post_state)
        total_rows += len(post_state)
        system.logger.info(
            "Blocked snapshot: %s — %d row(s) (pre=%d)",
            retailer_key,
            len(post_state),
            len(pre_state),
        )

    print(
        f"snapshot_blocked_effective_prices: recorded {total_rows} row(s) "
        f"across {len(by_retailer)} blocked retailer(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
