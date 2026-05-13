"""
Drain extension_staged_approvals from the live API and materialize them into:

  1. data/master_cigars.csv         (new CIDs only)
  2. data/master_cigars.db          (new CIDs only)
  3. static/data/{retailer_key}.csv (every approval — BARE row: cigar_id + url
                                    only; all other columns empty so the
                                    retailer's extractor fills in title/
                                    price/in_stock on the next price run)

This script must run AFTER `git pull --rebase` and BEFORE `git push`, so that
the master CSV and per-retailer CSVs reflect the latest state from any other
writers (the daily automation, manual edits) without clobbering them.

Use the companion `publish_extension_batch.ps1` to do pull + run + commit + push
in one shot. Or fold the `main()` call into your existing daily automation.

Idempotency:
  - For NEW CIDs, we INSERT OR IGNORE into master_cigars.db and skip the CSV
    append if the CID already exists in master_cigars.csv. Safe to re-run.
  - For retailer CSV writes, we skip rows where the (cigar_id, url) pair is
    already present.

Exit codes:
  0 = success (including "nothing to publish")
  1 = network / API error
  2 = data integrity error (e.g. missing required master field)
"""
from __future__ import annotations

import csv
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' is required. pip install requests")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("[ERROR] 'pandas' is required. pip install pandas")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_CSV = PROJECT_ROOT / "data" / "master_cigars.csv"
MASTER_DB = PROJECT_ROOT / "data" / "master_cigars.db"
STATIC_DATA = PROJECT_ROOT / "static" / "data"

DEFAULT_API_BASE = "https://cigarpricescout.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("publish_extension_approvals")


def _api_base() -> str:
    return os.getenv("EXTENSION_API_BASE", DEFAULT_API_BASE).rstrip("/")


def _admin_key() -> str:
    key = os.getenv("ADMIN_SECRET_KEY", "")
    if not key:
        log.error("ADMIN_SECRET_KEY is not set in the environment")
        sys.exit(1)
    return key


def fetch_pending() -> List[Dict]:
    """GET /api/admin/pending-extension-approvals."""
    r = requests.get(
        f"{_api_base()}/api/admin/pending-extension-approvals",
        headers={"X-Admin-Key": _admin_key()},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("pending", [])


def mark_published(ids: List[int]) -> Tuple[int, int]:
    """Returns (rows marked published, observed_prices rows retro-attached)."""
    if not ids:
        return 0, 0
    r = requests.post(
        f"{_api_base()}/api/admin/mark-extension-published",
        headers={"X-Admin-Key": _admin_key()},
        json={"ids": ids},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("published", 0), data.get("observations_attached", 0)


# ── Master CSV/DB writes (new CIDs only) ──────────────────────────────

MASTER_REQUIRED_FIELDS = ("brand", "line", "vitola", "size", "wrapper_code", "box_qty")


def _length_ring_from_size(size: str) -> Tuple[str, str]:
    """Best-effort split of '6x50' / '5.5x52' into ('6','50') or ('5.5','52')."""
    if not size or "x" not in size.lower():
        return "", ""
    try:
        left, right = size.lower().split("x", 1)
        return left.strip(), right.strip()
    except Exception:
        return "", ""


def _read_master_existing_cids() -> set:
    if not MASTER_CSV.exists():
        return set()
    df = pd.read_csv(MASTER_CSV, dtype=str, keep_default_na=False)
    if "cigar_id" not in df.columns:
        return set()
    return set(df["cigar_id"].astype(str).str.strip().unique())


def _append_master_csv(rows: List[Dict]) -> int:
    """Append new rows to data/master_cigars.csv, preserving its column order.

    Returns the number of rows actually written (0 if all already exist).
    """
    if not rows:
        return 0
    if not MASTER_CSV.exists():
        log.error("master_cigars.csv not found at %s", MASTER_CSV)
        return 0

    df_existing = pd.read_csv(MASTER_CSV, dtype=str, keep_default_na=False)
    columns = list(df_existing.columns)
    existing_cids = set(df_existing["cigar_id"].astype(str).str.strip().unique())

    new_rows = []
    for r in rows:
        cid = (r.get("cid") or "").strip()
        if not cid or cid in existing_cids:
            continue
        length, ring = _length_ring_from_size(r.get("size") or "")
        # Build the row using master_cigars column order; fill what we know
        # from the staged approval, leave optional metadata blank (the user
        # batch-fills Strength/Binder/Filler/Country/etc. later).
        row = {col: "" for col in columns}
        row["Brand"] = r.get("brand") or ""
        row["Line"] = r.get("line") or ""
        row["Wrapper"] = r.get("wrapper") or ""
        row["Wrapper_Alias"] = ""
        row["Vitola"] = r.get("vitola") or ""
        row["Length"] = length
        row["Ring Gauge"] = ring
        row["Binder"] = ""
        row["Filler"] = ""
        row["Strength"] = ""
        row["Box Quantity"] = str(r.get("box_qty") or "")
        row["Style"] = ""
        row["cigar_id"] = cid
        row["parent_brand"] = r.get("parent_brand") or r.get("brand") or ""
        row["sub_brand"] = ""
        row["product_name"] = r.get("vitola") or ""
        row["wrapper_code"] = r.get("wrapper_code") or ""
        row["packaging_type"] = "Box"
        row["country_of_origin"] = ""
        row["factory"] = ""
        row["release_type"] = "Regular Production"
        row["sampler_flag"] = "N"
        row["discontinued_flag"] = "N"
        row["notes"] = "Created via Chrome extension"
        row["source_url"] = r.get("url") or ""
        new_rows.append(row)
        existing_cids.add(cid)

    if not new_rows:
        return 0

    # Append in-place to preserve the file (no re-write of existing rows).
    with MASTER_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        for r in new_rows:
            writer.writerow(r)

    return len(new_rows)


def _upsert_master_db(rows: List[Dict]) -> int:
    """Upsert new CIDs into data/master_cigars.db (SQLite). Returns count written."""
    if not rows or not MASTER_DB.exists():
        if rows and not MASTER_DB.exists():
            log.warning("master_cigars.db missing — skipping DB upsert (CSV-only)")
        return 0

    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()
    written = 0
    try:
        for r in rows:
            cid = (r.get("cid") or "").strip()
            if not cid:
                continue
            length, ring = _length_ring_from_size(r.get("size") or "")
            cur.execute("""
                INSERT OR IGNORE INTO cigars (
                    cigar_id, brand, line, wrapper, wrapper_alias, vitola,
                    length, ring_gauge, binder, filler, strength,
                    box_quantity, style, parent_brand, sub_brand,
                    product_name, wrapper_code, packaging_type,
                    country_of_origin, factory, release_type,
                    sampler_flag, discontinued_flag, notes, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid,
                r.get("brand") or "",
                r.get("line") or "",
                r.get("wrapper") or "",
                "",
                r.get("vitola") or "",
                length, ring,
                "", "", "",
                int(r.get("box_qty") or 0),
                "",
                r.get("parent_brand") or r.get("brand") or "",
                "",
                r.get("vitola") or "",
                r.get("wrapper_code") or "",
                "Box",
                "", "",
                "Regular Production",
                "N", "N",
                "Created via Chrome extension",
                r.get("url") or "",
            ))
            if cur.rowcount > 0:
                written += 1
        conn.commit()
    finally:
        conn.close()
    return written


# ── Retailer CSV writes (bare row: cigar_id + url only) ───────────────

def _preview_retailer_outcome(retailer_key: str, cid: str, url: str) -> str:
    """Same logic as _append_bare_retailer_row but read-only. For --dry-run."""
    csv_path = STATIC_DATA / f"{retailer_key}.csv"
    if not csv_path.exists():
        return "skip (missing CSV)"
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if "cigar_id" not in df.columns or "url" not in df.columns:
        return "skip (missing cigar_id/url columns)"
    df["cigar_id"] = df["cigar_id"].astype(str).str.strip()
    df["url"] = df["url"].astype(str).str.strip()
    if ((df["cigar_id"] == cid) & (df["url"] == url)).any():
        return "no-op (row already present)"
    if (df["cigar_id"] == cid).any():
        return "update existing row's URL"
    return "append BARE row (cigar_id,,url)"


def _format_full_row_extras(r: Dict) -> Dict[str, str]:
    """Convert a staged-approval row into CSV column→value dict for the
    blocked/dormant 'full row' write path.

    Column names mirror the existing schema in static/data/*.csv (title,
    brand, line, wrapper, vitola, size, box_qty, price, in_stock). The
    `wrapper` column uses the human-readable form ("Maduro", "Connecticut
    Shade") not the canonical CID code, matching what scrapers populate
    for active retailers.
    """
    def _s(v) -> str:
        return "" if v is None else str(v).strip()

    def _price(v) -> str:
        if v is None:
            return ""
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return ""

    def _stock(v) -> str:
        # CSV convention used by every extractor: capitalized Python repr.
        # Empty string for "unknown" so it sorts/filters distinctly from
        # an explicit False.
        if v is True:
            return "True"
        if v is False:
            return "False"
        return ""

    return {
        "title":    _s(r.get("title")),
        "brand":    _s(r.get("brand")),
        "line":     _s(r.get("line")),
        # Operator may not have a wrapper alias yet, fall back to the
        # canonical code so the column is never empty for a full row.
        "wrapper":  _s(r.get("wrapper")) or _s(r.get("wrapper_code")),
        "vitola":   _s(r.get("vitola")),
        "size":     _s(r.get("size")),
        "box_qty":  _s(r.get("box_qty")),
        "price":    _price(r.get("price")),
        "in_stock": _stock(r.get("in_stock")),
    }


def _append_retailer_row(
    retailer_key: str,
    cid: str,
    url: str,
    extra_cols: Optional[Dict[str, str]] = None,
) -> str:
    """Append or update a row in static/data/{retailer_key}.csv.

    Two modes:

    - **Bare row** (extra_cols=None) for `active` retailers. Writes only
      `cigar_id` and `url`; the daily extractor fills the rest on its next
      run. This is the legacy behavior every retailer extractor expects.

    - **Full row** (extra_cols={title,brand,line,wrapper,vitola,size,
      box_qty,price,in_stock}) for `blocked`/`dormant` retailers, where no
      extractor will ever fill the row. The operator's manual entry IS the
      data source, so we persist it directly.

    For both modes:
    - Same (cid, url) pair already present → no-op for bare, **overwrite
      extras** for full (so re-approval refreshes stale prices).
    - Same cid, different url → update url on that row; in full mode also
      refresh the extras.
    - New row → append.

    Returns one of: 'added', 'exists', 'updated_url', 'updated_full',
    'missing_csv'.
    """
    csv_path = STATIC_DATA / f"{retailer_key}.csv"
    if not csv_path.exists():
        log.warning("CSV not found for retailer '%s'; skipping %s", retailer_key, cid[:40])
        return "missing_csv"

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if "cigar_id" not in df.columns or "url" not in df.columns:
        log.warning("CSV %s has no cigar_id/url columns; skipping", csv_path.name)
        return "missing_csv"

    df["cigar_id"] = df["cigar_id"].astype(str).str.strip()
    df["url"] = df["url"].astype(str).str.strip()

    def _apply_extras(idx: int) -> None:
        if not extra_cols:
            return
        for col, val in extra_cols.items():
            if col in df.columns:
                df.at[idx, col] = val

    # Same (cid, url) already there. For bare-row mode this is idempotent
    # (no-op). For full-row mode we treat re-approval as a refresh — the
    # operator just confirmed the price on the page, so trust the new value
    # over whatever's in the CSV.
    same_pair = (df["cigar_id"] == cid) & (df["url"] == url)
    if same_pair.any():
        if extra_cols:
            idx = df.index[same_pair][0]
            _apply_extras(idx)
            df.to_csv(csv_path, index=False)
            return "updated_full"
        return "exists"

    # Same cid but different url: update the URL on that row (treat as
    # URL fix). Also refresh extras when in full-row mode.
    same_cid = df["cigar_id"] == cid
    if same_cid.any():
        idx = df.index[same_cid][0]
        df.at[idx, "url"] = url
        _apply_extras(idx)
        df.to_csv(csv_path, index=False)
        return "updated_url"

    # Otherwise: append a new row. Bare for active retailers, full for
    # blocked/dormant (extra_cols provided).
    new_row = {col: "" for col in df.columns}
    new_row["cigar_id"] = cid
    new_row["url"] = url
    if extra_cols:
        for col, val in extra_cols.items():
            if col in df.columns:
                new_row[col] = val
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(csv_path, index=False)
    return "added"


# Back-compat alias for any external callers. Internal call sites now use
# _append_retailer_row directly.
def _append_bare_retailer_row(retailer_key: str, cid: str, url: str) -> str:
    return _append_retailer_row(retailer_key, cid, url)


# ── Orchestrator ──────────────────────────────────────────────────────

def publish_all(dry_run: bool = False) -> Dict[str, int]:
    """Drain all pending extension approvals. Returns stats dict.

    Order of operations matters:
      1. Append every new CID to master_cigars.csv + master_cigars.db.
      2. For EVERY approval (new and existing CID), append bare retailer row.
      3. Mark all processed approvals as published in Postgres.

    Step 1 must run before step 2 so that by the time the retailer CSV row is
    written, master already knows the CID (any tool that joins on cigar_id
    will resolve it correctly).
    """
    stats = {
        "fetched": 0,
        "new_cids_to_master": 0,
        "master_csv_added": 0,
        "master_db_added": 0,
        "retailer_added": 0,
        "retailer_exists": 0,
        "retailer_url_updated": 0,
        # Re-approval on a blocked/dormant retailer that overwrote the
        # existing row's title/price/in_stock with operator-supplied
        # values. Separate from `retailer_added` so dashboards can show
        # "fresh contributions" vs. "price refreshes".
        "retailer_full_updated": 0,
        "retailer_missing_csv": 0,
        # Number of full rows written (added OR updated) for blocked/
        # dormant retailers. Useful for understanding how much of the
        # CSV is sourced from operator entry vs. extractors.
        "retailer_full_rows_written": 0,
        "marked_published": 0,
    }

    pending = fetch_pending()
    stats["fetched"] = len(pending)
    if not pending:
        log.info("No pending extension approvals.")
        return stats

    log.info("Fetched %d pending extension approval(s)", len(pending))

    # Validate each row up front; reject malformed ones loudly (don't mark
    # them published, so they re-surface for inspection).
    valid: List[Dict] = []
    for r in pending:
        cid = (r.get("cid") or "").strip()
        url = (r.get("url") or "").strip()
        retailer_key = (r.get("retailer_key") or "").strip()
        if not (cid and url and retailer_key):
            log.warning("Skipping malformed approval id=%s: missing required field", r.get("id"))
            continue
        if r.get("is_new_cid"):
            missing = [k for k in MASTER_REQUIRED_FIELDS if not str(r.get(k) or "").strip()]
            if missing:
                log.warning(
                    "Skipping new-CID approval id=%s (%s): missing %s",
                    r.get("id"), cid[:40], ",".join(missing),
                )
                continue
        valid.append(r)

    if not valid:
        log.info("No valid approvals to publish after validation.")
        return stats

    new_cids = [r for r in valid if r.get("is_new_cid")]
    stats["new_cids_to_master"] = len(new_cids)

    if dry_run:
        log.info("[dry-run] would publish %d approvals (%d new CIDs)",
                 len(valid), len(new_cids))
        existing_master = _read_master_existing_cids()
        for r in valid:
            cid = (r.get("cid") or "").strip()
            url = (r.get("url") or "").strip()
            retailer_key = (r.get("retailer_key") or "").strip()
            is_new = bool(r.get("is_new_cid"))
            # If the row says it's new but the CID already exists in master,
            # surface that — it'll be re-used (no dupe created), but worth
            # knowing so you can verify the chosen CID was intended.
            already_in_master = cid in existing_master
            tag = (
                "NEW_CID    " if is_new and not already_in_master
                else "EXISTING   " if not is_new
                else "NEW→EXISTS "  # user marked new, but CID matches master
            )
            log.info(
                "  %s id=%s  %s  %s",
                tag, r.get("id"), retailer_key.ljust(20), cid,
            )
            log.info("      url   : %s", url)
            if is_new:
                log.info(
                    "      meta  : brand=%s | parent=%s | line=%s | vitola=%s | size=%s | wrapper=%s/%s | box=%s",
                    r.get("brand") or "", r.get("parent_brand") or "",
                    r.get("line") or "", r.get("vitola") or "",
                    r.get("size") or "",
                    r.get("wrapper") or "", r.get("wrapper_code") or "",
                    r.get("box_qty") or "",
                )
            outcome = _preview_retailer_outcome(retailer_key, cid, url)
            status = (r.get("extractor_status") or "active").strip().lower()
            row_kind = "FULL row" if status in ("blocked", "dormant") else "BARE row"
            log.info("      retailer csv: would %s (%s) in static/data/%s.csv",
                     outcome, row_kind, retailer_key)
            if status in ("blocked", "dormant"):
                log.info("      price : %s  in_stock: %s",
                         r.get("price"), r.get("in_stock"))
        return stats

    # Step 1: master writes
    if new_cids:
        stats["master_csv_added"] = _append_master_csv(new_cids)
        stats["master_db_added"] = _upsert_master_db(new_cids)
        log.info(
            "Master: +%d CSV row(s), +%d DB row(s) for %d new CID(s)",
            stats["master_csv_added"], stats["master_db_added"], len(new_cids),
        )

    # Step 2: per-retailer row writes. Active retailers get bare rows (the
    # daily extractor will fill price/title/in_stock on its next run);
    # blocked/dormant retailers get full rows because no extractor will
    # ever populate them. The extractor_status field is set per-row by the
    # /api/admin/pending-extension-approvals response.
    published_ids: List[int] = []
    for r in valid:
        status = (r.get("extractor_status") or "active").strip().lower()
        is_full_row = status in ("blocked", "dormant")
        extras = _format_full_row_extras(r) if is_full_row else None

        outcome = _append_retailer_row(
            r["retailer_key"], r["cid"], r["url"], extra_cols=extras,
        )
        if outcome == "added":
            stats["retailer_added"] += 1
            if is_full_row:
                stats["retailer_full_rows_written"] += 1
        elif outcome == "exists":
            stats["retailer_exists"] += 1
        elif outcome == "updated_url":
            stats["retailer_url_updated"] += 1
            if is_full_row:
                stats["retailer_full_rows_written"] += 1
        elif outcome == "updated_full":
            stats["retailer_full_updated"] += 1
            stats["retailer_full_rows_written"] += 1
        elif outcome == "missing_csv":
            stats["retailer_missing_csv"] += 1
            # Don't mark this one as published — the user needs to know the
            # retailer CSV is missing.
            continue
        published_ids.append(r["id"])
        # Tag the log line so operators can see at a glance whether each
        # row was a manual-entry write (FULL) or a scraper-placeholder
        # (BARE). Helpful when triaging "why didn't this price appear?"
        tag = "FULL" if is_full_row else "BARE"
        log.info(
            "  %s %s  %s  %s  %s",
            outcome.ljust(12), tag,
            r["retailer_key"].ljust(20),
            r["cid"][:60], r["url"][:80],
        )

    # Step 3: mark as published in Postgres. The API also retroactively
    # attaches cigar_id to any observed_prices rows for the same URLs that
    # were captured before the operator approved a CID.
    if published_ids:
        marked, attached = mark_published(published_ids)
        stats["marked_published"] = marked
        stats["observations_attached"] = attached
        log.info("Marked %d approval(s) as published in Postgres", marked)
        if attached:
            log.info("Retro-attached cigar_id on %d existing observed_prices row(s)", attached)

    return stats


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and validate without writing anything")
    args = parser.parse_args(argv)

    try:
        stats = publish_all(dry_run=args.dry_run)
    except requests.RequestException as e:
        log.error("API error: %s", e)
        return 1
    except Exception as e:
        log.exception("Unexpected error: %s", e)
        return 2

    log.info("=" * 60)
    for k, v in stats.items():
        log.info("  %-26s %d", k, v)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
