"""Shared helpers for data/historical_prices.db schema and daily snapshots."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any, Dict, List, Optional


def migrate_price_history_schema(conn: sqlite3.Connection) -> None:
    """Add source provenance columns to existing databases."""
    cur = conn.cursor()
    cols = {row[1] for row in cur.execute("PRAGMA table_info(price_history)")}
    if "source" not in cols:
        cur.execute("ALTER TABLE price_history ADD COLUMN source TEXT")
    if "source_updated_at" not in cols:
        cur.execute("ALTER TABLE price_history ADD COLUMN source_updated_at TEXT")


def _normalize_source(raw: Optional[str]) -> str:
    s = (raw or "csv").strip().lower()
    if s in ("operator_approved", "observed", "csv", "community"):
        return s
    return "csv"


def _source_updated_at(row: Dict[str, Any]) -> str:
    ts = row.get("source_updated_at")
    if ts:
        return str(ts)
    return datetime.now().isoformat(timespec="seconds")


def record_daily_price_history(
    conn: sqlite3.Connection,
    retailer_key: str,
    pre_state: List[Dict[str, Any]],
    post_state: List[Dict[str, Any]],
    *,
    snapshot_date: Optional[date] = None,
    track_price_changes: bool = True,
    track_stock_changes: bool = True,
) -> None:
    """Insert today's price_history rows and optional change tables."""
    migrate_price_history_schema(conn)
    cursor = conn.cursor()
    today = snapshot_date or datetime.now().date()

    pre_lookup = {row.get("cigar_id", ""): row for row in pre_state if row.get("cigar_id")}
    post_lookup = {row.get("cigar_id", ""): row for row in post_state if row.get("cigar_id")}

    for row in post_state:
        cigar_id = row.get("cigar_id", "")
        price = row.get("price")
        in_stock = row.get("in_stock", True)
        url = row.get("url", "")
        if cigar_id and price is not None:
            cursor.execute(
                """
                INSERT OR IGNORE INTO price_history
                (retailer, cigar_id, date, price, in_stock, url, source, source_updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    retailer_key,
                    cigar_id,
                    today,
                    float(price),
                    bool(in_stock),
                    url,
                    _normalize_source(row.get("source")),
                    _source_updated_at(row),
                ),
            )

    if track_price_changes:
        for cigar_id, post_row in post_lookup.items():
            if cigar_id in pre_lookup:
                pre_price = pre_lookup[cigar_id].get("price")
                post_price = post_row.get("price")
                if pre_price is not None and post_price is not None:
                    pre_price = float(pre_price)
                    post_price = float(post_price)
                    if abs(pre_price - post_price) > 0.01:
                        price_change = post_price - pre_price
                        change_type = "increase" if price_change > 0 else "decrease"
                        cursor.execute(
                            """
                            INSERT INTO price_changes
                            (retailer, cigar_id, date, old_price, new_price, price_change, change_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                retailer_key,
                                cigar_id,
                                today,
                                pre_price,
                                post_price,
                                price_change,
                                change_type,
                            ),
                        )
            else:
                post_price = post_row.get("price")
                if post_price is not None:
                    cursor.execute(
                        """
                        INSERT INTO price_changes
                        (retailer, cigar_id, date, old_price, new_price, price_change, change_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            retailer_key,
                            cigar_id,
                            today,
                            None,
                            float(post_price),
                            float(post_price),
                            "new",
                        ),
                    )

    if track_stock_changes:
        for cigar_id, post_row in post_lookup.items():
            if cigar_id in pre_lookup:
                pre_stock = pre_lookup[cigar_id].get("in_stock", True)
                post_stock = post_row.get("in_stock", True)
                pre_stock = str(pre_stock).lower() not in ("false", "0", "no", "")
                post_stock = str(post_stock).lower() not in ("false", "0", "no", "")
                if pre_stock != post_stock:
                    change_type = "in_stock" if post_stock else "out_of_stock"
                    cursor.execute(
                        """
                        INSERT INTO stock_changes
                        (retailer, cigar_id, date, old_stock, new_stock, change_type)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            retailer_key,
                            cigar_id,
                            today,
                            pre_stock,
                            post_stock,
                            change_type,
                        ),
                    )

    conn.commit()
