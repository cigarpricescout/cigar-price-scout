"""
FastAPI routes powering the Chrome extension's per-URL CID-matching workflow.

Design contract (matches the user's manual workflow exactly):

  * Extension approvals are stored in a dedicated table, `extension_staged_approvals`.
    They DO NOT go through `url_staged_matches` (which is the weekly-discovery
    agent's path and prefills brand/line/etc. into the retailer CSV).
  * A local publisher (`tools/extension/publish_extension_approvals.py`) drains
    the table after a `git pull` and writes BARE rows into the retailer CSV:
        cigar_id,,URL,,,,,,,,
    i.e. only `cigar_id` and `url` are populated, every other column empty,
    so the retailer's existing extractor fills in title/price/in_stock on the
    next daily price-update run. This matches the format the user has used
    for manual additions.
  * For new CIDs (not yet in master_cigars), the same publisher also appends
    a row to `data/master_cigars.csv` and upserts into `data/master_cigars.db`
    BEFORE writing the retailer CSV row.
  * Two sibling tables exist for adjacent flows:
      - `pending_new_retailers`: URLs hitting unknown hostnames.
      - `url_skip_list`: URLs the user clicked "Skip" on.

Nothing in this module writes to CSVs or to the master SQLite DB; Railway only
writes to Postgres. Existing endpoints, tables, and the website's read paths
are completely untouched.

Mount in app/main.py with:

    from app.extension_endpoints import router as extension_router, init_extension_tables
    init_extension_tables()  # call inside startup_event()
    app.include_router(extension_router)
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.cid_matcher import (
    build_cid,
    build_retailer_registry,
    canonicalize_url,
    find_top_candidates,
    hostname_to_retailer_key,
    load_master_cigars,
    load_retailer_url_index,
    parse_cid,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["extension"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MASTER_CSV = PROJECT_ROOT / "data" / "master_cigars.csv"
STATIC_DATA = PROJECT_ROOT / "static" / "data"


# ── Cached snapshots of git-managed product data ──────────────────────
# These are reloaded periodically (cheap) so URLs published locally and pulled
# into the running Railway deployment via redeploy become visible without
# manual intervention. The cache TTL is long-ish because retailer CSVs only
# change on the daily automation cadence.

_CACHE_TTL_SECONDS = 600  # 10 minutes
_cache_state = {
    "loaded_at": 0.0,
    "master": [],          # list[dict] from load_master_cigars
    "master_by_cid": {},    # dict[str, dict]
    "retailers": {},       # hostname -> retailer_key
    "url_index": {},       # url -> (retailer_key, cigar_id)
}


def _refresh_cache(force: bool = False) -> None:
    """(Re)load master CSV + retailer registry + per-retailer URL index."""
    now = time.time()
    if not force and (now - _cache_state["loaded_at"]) < _CACHE_TTL_SECONDS:
        return
    try:
        master = load_master_cigars(MASTER_CSV)
        retailers = build_retailer_registry(STATIC_DATA)
        url_index = load_retailer_url_index(STATIC_DATA)
        master_by_cid = {row["cigar_id"]: row for row in master}
        _cache_state.update({
            "loaded_at": now,
            "master": master,
            "master_by_cid": master_by_cid,
            "retailers": retailers,
            "url_index": url_index,
        })
        logger.info(
            "Extension cache refreshed: %d master CIDs, %d retailer hosts, %d live URLs",
            len(master), len(retailers), len(url_index),
        )
    except Exception as e:
        logger.error("Extension cache refresh failed: %s", e)


# ── Schema (idempotent) ────────────────────────────────────────────────

def init_extension_tables() -> None:
    """Create the three additive tables the extension workflow needs.

    Safe to call repeatedly; uses IF NOT EXISTS for all DDL.
    """
    # Imported here to avoid a circular import with app.main.
    from app.main import get_analytics_conn  # type: ignore

    try:
        conn = get_analytics_conn()
        cur = conn.cursor()
        # Single table for all extension approvals (both existing-CID and
        # new-CID). The local publisher drains this and writes bare rows
        # (cigar_id + url only) to the retailer CSV. For new CIDs, it ALSO
        # appends to master_cigars.csv/.db first.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS extension_staged_approvals (
                id SERIAL PRIMARY KEY,
                cid TEXT NOT NULL,
                retailer_key TEXT NOT NULL,
                url TEXT NOT NULL,
                is_new_cid BOOLEAN DEFAULT FALSE,
                -- New-CID metadata (NULL when is_new_cid=FALSE). Captured so
                -- the local publisher can build the master_cigars row.
                brand TEXT,
                parent_brand TEXT,
                line TEXT,
                vitola TEXT,
                vitola2 TEXT,
                size TEXT,
                wrapper_code TEXT,
                wrapper TEXT,
                box_qty INTEGER,
                -- Scraped context (informational; not written to retailer CSV).
                title TEXT,
                price NUMERIC(10,2),
                in_stock BOOLEAN,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                published_at TIMESTAMPTZ,
                UNIQUE (retailer_key, url, cid)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_ext_staged_status
                ON extension_staged_approvals(status)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_ext_staged_url
                ON extension_staged_approvals(url)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_new_retailers (
                id SERIAL PRIMARY KEY,
                hostname TEXT NOT NULL,
                url TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                processed_at TIMESTAMPTZ,
                UNIQUE (hostname, url)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS url_skip_list (
                id SERIAL PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                retailer_key TEXT,
                reason TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Extension tables initialized")
    except Exception as e:
        logger.error("init_extension_tables failed: %s", e)


# ── Auth helper ────────────────────────────────────────────────────────

def _check_admin(request: Request) -> Optional[JSONResponse]:
    """Returns a 401 JSONResponse if the admin key is missing/wrong, else None."""
    admin_key = (
        request.headers.get("X-Admin-Key", "")
        or request.query_params.get("key", "")
    )
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


def _get_conn():
    from app.main import get_analytics_conn  # type: ignore
    return get_analytics_conn()


# ── Pydantic request bodies ────────────────────────────────────────────

class CIDParts(BaseModel):
    brand: str
    parent_brand: Optional[str] = None
    line: str
    vitola: str
    vitola2: Optional[str] = None
    size: str
    wrapper_code: str
    box_qty: int
    wrapper: Optional[str] = None  # human-readable wrapper name


class StageApprovalBody(BaseModel):
    url: str
    retailer_key: str
    cid: Optional[str] = None  # if provided, treat as existing-CID match
    cid_parts: Optional[CIDParts] = None  # if cid is missing, build from parts
    confidence: Optional[str] = "EXTENSION"
    reason: Optional[str] = None
    title: Optional[str] = None
    price: Optional[float] = None
    in_stock: Optional[bool] = None
    # When True and the resulting CID is not in master_cigars, the staged
    # row is flagged is_new_cid=TRUE so the local publisher creates the master
    # row before writing the retailer CSV row.
    create_if_missing: bool = True
    force: bool = False  # supersede an existing approved/published row
    # Optional review-decision context: what the matcher proposed vs what
    # the operator actually saved. Captured for review_decisions logging,
    # which becomes training data for the future ML reviewer.
    proposed_cid: Optional[str] = None
    proposed_score: Optional[float] = None
    proposed_confidence: Optional[str] = None


class ResolveProposalBody(BaseModel):
    proposal_id: int
    # 'approve_existing' — map to existing CID; cid required.
    # 'approve_new'      — operator creates a new CID via cid_parts.
    # 'reject'           — discard the proposal.
    # 'duplicate'        — already covered by another proposal/CID.
    action: str
    cid: Optional[str] = None
    cid_parts: Optional[CIDParts] = None
    notes: Optional[str] = None


class SkipUrlBody(BaseModel):
    url: str
    retailer_key: Optional[str] = None
    reason: Optional[str] = None


class QueueNewRetailerBody(BaseModel):
    url: str
    hostname: Optional[str] = None


class IdsBody(BaseModel):
    """Generic {ids: [int, ...]} body used by mark-* endpoints."""
    ids: List[int] = Field(default_factory=list)


# ── GET /api/admin/url-status ──────────────────────────────────────────

@router.get("/url-status")
async def url_status(
    request: Request,
    url: str = Query(..., min_length=1),
    title: Optional[str] = Query(None),
    refresh: bool = Query(False),
):
    """Verdict + candidates for a single URL.

    Response shape:
        {
          "state": "matched" | "seen" | "candidate" | "no_scraper" | "unknown",
          "retailer_key": str | null,
          "hostname": str,
          "url": str,
          "matched_cid": str | null,        # when state == "matched" or "seen"
          "seen_status": str | null,        # when state == "seen"
          "candidates": [ { cigar_id, score, confidence, details, brand, ... } ],
          "available_in_master": [ ... ],   # subset of candidates already in master
          "scraped_title": str | null
        }
    """
    auth = _check_admin(request)
    if auth:
        return auth

    _refresh_cache(force=refresh)

    # Normalize first so every downstream lookup (url_index, _lookup_seen,
    # candidates_for) sees the canonical form. Without this, a Shopify
    # ?variant=… URL fails to hit the CSV-backed url_index even though
    # the canonical URL is mapped.
    url = canonicalize_url(url)

    try:
        hostname = (urlparse(url).hostname or "").lower()
    except Exception:
        hostname = ""

    retailer_key = hostname_to_retailer_key(hostname, _cache_state["retailers"])

    # If we have no retailer key, decide between "no_scraper" (we have *some*
    # CSV that uses this domain but no extractor) and "unknown" (totally new
    # domain). For the extension's purpose these collapse to "no_scraper":
    # without a registered retailer_key we can't write a published row.
    if not retailer_key:
        return {
            "state": "no_scraper",
            "retailer_key": None,
            "hostname": hostname,
            "url": url,
            "matched_cid": None,
            "seen_status": None,
            "candidates": [],
            "available_in_master": [],
            "scraped_title": title,
        }

    # 1) Already in the live retailer CSV? `url` is already canonical here
    # (normalized at the endpoint boundary) and the url_index is keyed by
    # canonical URLs too, so this dict-get hits the right row even for
    # Shopify ?variant=… or utm_* URLs.
    live_hit = _cache_state["url_index"].get(url)
    if live_hit and live_hit[0] == retailer_key:
        return {
            "state": "matched",
            "retailer_key": retailer_key,
            "hostname": hostname,
            "url": url,
            "matched_cid": live_hit[1],
            "seen_status": "published",
            "candidates": _candidates_for(url, title),
            "available_in_master": [],
            "scraped_title": title,
        }

    # 2) Seen in staging? (approved / published / rejected / skipped)
    seen_status, seen_cid = _lookup_seen(url, retailer_key)
    if seen_status:
        return {
            "state": "seen",
            "retailer_key": retailer_key,
            "hostname": hostname,
            "url": url,
            "matched_cid": seen_cid,
            "seen_status": seen_status,
            "candidates": _candidates_for(url, title),
            "available_in_master": [],
            "scraped_title": title,
        }

    # 3) Fresh URL → propose CIDs from the master list
    cands = _candidates_for(url, title)
    available = [c for c in cands if c["cigar_id"] in _cache_state["master_by_cid"]]
    return {
        "state": "candidate",
        "retailer_key": retailer_key,
        "hostname": hostname,
        "url": url,
        "matched_cid": None,
        "seen_status": None,
        "candidates": cands,
        "available_in_master": [c["cigar_id"] for c in available],
        "scraped_title": title,
    }


def _candidates_for(url: str, title: Optional[str]) -> List[Dict]:
    """Run the matcher against the cached master list."""
    return find_top_candidates(url, title, _cache_state["master"], limit=5)


def _lookup_seen(url: str, retailer_key: str) -> Tuple[Optional[str], Optional[str]]:
    """Has the user already touched this URL via the extension or weekly agent?

    Returns (status, cid). status is one of:
      - "extension_pending" / "extension_published" — staged by this extension
      - "agent_approved" / "agent_published" / "agent_rejected" — from the
        weekly discovery agent (existing url_staged_matches)
      - "skipped" — clicked Skip in the popup
    None when the URL has never been seen.
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Extension's own staging table takes precedence.
        cur.execute(
            "SELECT status, cid FROM extension_staged_approvals "
            "WHERE url=%s AND retailer_key=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (url, retailer_key),
        )
        row = cur.fetchone()
        if row:
            conn.close()
            return f"extension_{row[0]}", row[1]

        # Weekly-discovery agent staging (read-only here; don't block the
        # extension from re-reviewing, but surface that the URL is known).
        cur.execute(
            "SELECT status, cid FROM url_staged_matches "
            "WHERE url=%s AND retailer_key=%s "
            "ORDER BY reviewed_at DESC NULLS LAST, created_at DESC LIMIT 1",
            (url, retailer_key),
        )
        row = cur.fetchone()
        if row and row[0] in ("approved", "published", "rejected"):
            conn.close()
            return f"agent_{row[0]}", row[1]

        cur.execute(
            "SELECT reason FROM url_skip_list WHERE url=%s LIMIT 1",
            (url,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return "skipped", None
    except Exception as e:
        logger.warning("lookup_seen error: %s", e)
    return None, None


# ── POST /api/admin/stage-approval ─────────────────────────────────────

@router.post("/stage-approval")
async def stage_approval(request: Request, body: StageApprovalBody):
    """Stage one extension approval. Writes Postgres only — no CSV/DB touch.

    The resolved CID is either:
      * provided directly via `body.cid` (existing-CID approval), or
      * built from `body.cid_parts` (form-edited CID; may or may not be in master).

    Whether the CID currently exists in master_cigars is recorded as
    `is_new_cid`. The local publisher reads this flag to decide whether to
    create a master row before writing the retailer CSV row.

    The retailer CSV row written downstream is BARE — only `cigar_id` and
    `url` are populated, every other column empty — matching the user's
    manual-add convention so the extractor fills in title/price/in_stock.

    Idempotent on (retailer_key, url, cid). When force=True, an existing
    same-(retailer_key, url) row with a DIFFERENT cid is marked 'superseded'
    so re-review with a corrected CID overrides the previous attempt.
    """
    auth = _check_admin(request)
    if auth:
        return auth

    _refresh_cache()

    # Normalize the URL once so the row we write to extension_staged_approvals
    # (and the bare row downstream in the retailer CSV) uses the canonical form.
    body.url = canonicalize_url(body.url)

    # Resolve the CID (either passed-in or built from form parts).
    cid: Optional[str] = (body.cid or "").strip() or None
    parts_dict: Optional[Dict[str, str]] = None
    if body.cid_parts:
        parts_dict = body.cid_parts.dict()
        parts_dict["box_qty_str"] = f"BOX{int(parts_dict['box_qty'])}"
        if not cid:
            cid = build_cid(parts_dict)
    if not cid:
        return JSONResponse(
            {"error": "either cid or cid_parts is required"},
            status_code=400,
        )

    parsed = parse_cid(cid)
    if not parsed:
        return JSONResponse(
            {"error": f"invalid CID format: '{cid}'"},
            status_code=400,
        )

    cid_in_master = cid in _cache_state["master_by_cid"]
    is_new_cid = not cid_in_master

    if is_new_cid and not body.create_if_missing:
        return JSONResponse(
            {"error": f"CID '{cid}' not in master and create_if_missing=False"},
            status_code=409,
        )

    # When the CID is in master, we still capture its descriptive parts so the
    # row is self-describing for debugging — but the publisher only uses them
    # for the master-create path.
    if not parts_dict:
        parts_dict = {
            "brand": parsed["brand"],
            "parent_brand": parsed["parent_brand"],
            "line": parsed["line"],
            "vitola": parsed["vitola"],
            "vitola2": parsed["vitola2"],
            "size": parsed["size"],
            "wrapper_code": parsed["wrapper_code"],
            "box_qty": _extract_box_qty(parsed["box_qty_str"]) or 0,
            "wrapper": None,
        }

    box_qty_int = int(parts_dict.get("box_qty") or 0)

    try:
        conn = _get_conn()
        cur = conn.cursor()

        if body.force:
            # Same URL, different CID being re-approved: mark prior attempts
            # as superseded so the publisher only acts on the latest decision.
            cur.execute(
                "UPDATE extension_staged_approvals "
                "SET status='superseded' "
                "WHERE retailer_key=%s AND url=%s AND cid<>%s "
                "AND status IN ('pending','published')",
                (body.retailer_key, body.url, cid),
            )

        cur.execute("""
            INSERT INTO extension_staged_approvals
            (cid, retailer_key, url, is_new_cid,
             brand, parent_brand, line, vitola, vitola2, size,
             wrapper_code, wrapper, box_qty,
             title, price, in_stock, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
            ON CONFLICT (retailer_key, url, cid) DO UPDATE
              SET is_new_cid=EXCLUDED.is_new_cid,
                  brand=EXCLUDED.brand,
                  parent_brand=EXCLUDED.parent_brand,
                  line=EXCLUDED.line,
                  vitola=EXCLUDED.vitola,
                  vitola2=EXCLUDED.vitola2,
                  size=EXCLUDED.size,
                  wrapper_code=EXCLUDED.wrapper_code,
                  wrapper=EXCLUDED.wrapper,
                  box_qty=EXCLUDED.box_qty,
                  title=EXCLUDED.title,
                  price=EXCLUDED.price,
                  in_stock=EXCLUDED.in_stock,
                  status=CASE
                    WHEN extension_staged_approvals.status='published' THEN 'published'
                    ELSE 'pending'
                  END
        """, (
            cid, body.retailer_key, body.url, is_new_cid,
            parts_dict["brand"], parts_dict.get("parent_brand") or parts_dict["brand"],
            parts_dict["line"], parts_dict["vitola"],
            parts_dict.get("vitola2") or parts_dict["vitola"],
            parts_dict["size"], parts_dict["wrapper_code"],
            parts_dict.get("wrapper"), box_qty_int,
            body.title, body.price, body.in_stock,
        ))
        conn.commit()
        conn.close()

        _log_review_decision(
            decision_type="extension_approval",
            url=body.url,
            retailer_key=body.retailer_key,
            proposed_cid=body.proposed_cid,
            final_cid=cid,
            final_metadata={
                **{k: parts_dict.get(k) for k in (
                    "brand", "parent_brand", "line", "vitola", "vitola2",
                    "size", "wrapper_code", "wrapper", "box_qty",
                )},
                "is_new_cid": is_new_cid,
                "title": body.title,
            },
            score=body.proposed_score,
            confidence_label=body.proposed_confidence or body.confidence,
            source_table="extension_staged_approvals",
            notes=body.reason,
        )

        return {
            "ok": True,
            "mode": "new_cid" if is_new_cid else "existing_cid",
            "cid": cid,
            "retailer_key": body.retailer_key,
            "url": body.url,
        }
    except Exception as e:
        logger.exception("stage_approval failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


def _extract_box_qty(box_qty_str: str) -> Optional[int]:
    import re
    m = re.search(r"\d+", box_qty_str or "")
    return int(m.group()) if m else None


# ── POST /api/admin/skip-url ───────────────────────────────────────────

@router.post("/skip-url")
async def skip_url(request: Request, body: SkipUrlBody):
    """Mark a URL as 'not a cigar page' so the extension hides it next time."""
    auth = _check_admin(request)
    if auth:
        return auth
    body.url = canonicalize_url(body.url)
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO url_skip_list (url, retailer_key, reason)
            VALUES (%s, %s, %s)
            ON CONFLICT (url) DO UPDATE
              SET reason=EXCLUDED.reason,
                  retailer_key=EXCLUDED.retailer_key
        """, (body.url, body.retailer_key, body.reason or "skipped"))
        conn.commit()
        conn.close()

        _log_review_decision(
            decision_type="skip",
            url=body.url,
            retailer_key=body.retailer_key,
            source_table="url_skip_list",
            notes=body.reason,
        )

        return {"ok": True}
    except Exception as e:
        logger.exception("skip_url failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── POST /api/admin/queue-new-retailer ────────────────────────────────

@router.post("/queue-new-retailer")
async def queue_new_retailer(request: Request, body: QueueNewRetailerBody):
    """Queue a URL/hostname for new-retailer onboarding.

    The local sync_new_retailer_queue.py drains this into
    tools/ai/new_retailer_queue.txt.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    host = body.hostname or (urlparse(body.url).hostname or "").lower()
    if not host:
        return JSONResponse({"error": "hostname could not be derived"}, status_code=400)
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pending_new_retailers (hostname, url)
            VALUES (%s, %s)
            ON CONFLICT (hostname, url) DO NOTHING
        """, (host, body.url))
        conn.commit()
        conn.close()
        return {"ok": True, "hostname": host}
    except Exception as e:
        logger.exception("queue_new_retailer failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── GET/POST: local-publisher endpoints ───────────────────────────────

@router.get("/pending-extension-approvals")
async def pending_extension_approvals(request: Request):
    """Local publisher fetches all pending extension approvals.

    Includes both new-CID rows (is_new_cid=TRUE — must be created in master
    first) and existing-CID rows (is_new_cid=FALSE — just append to retailer
    CSV). The publisher distinguishes by the `is_new_cid` flag.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, cid, retailer_key, url, is_new_cid,
                   brand, parent_brand, line, vitola, vitola2, size,
                   wrapper_code, wrapper, box_qty,
                   title, price, in_stock, created_at
            FROM extension_staged_approvals
            WHERE status='pending'
            ORDER BY is_new_cid DESC, created_at ASC
        """)
        rows = cur.fetchall()
        conn.close()
        return {"pending": [
            {
                "id": r[0], "cid": r[1], "retailer_key": r[2], "url": r[3],
                "is_new_cid": r[4],
                "brand": r[5], "parent_brand": r[6], "line": r[7],
                "vitola": r[8], "vitola2": r[9], "size": r[10],
                "wrapper_code": r[11], "wrapper": r[12], "box_qty": r[13],
                "title": r[14],
                "price": float(r[15]) if r[15] is not None else None,
                "in_stock": r[16],
                "created_at": str(r[17]) if r[17] else None,
            } for r in rows
        ]}
    except Exception as e:
        logger.exception("pending_extension_approvals failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/mark-extension-published")
async def mark_extension_published(request: Request, body: IdsBody):
    """Local publisher marks approvals as published after CSV/DB writes.

    Also retroactively attaches cigar_id (and infers quantity_type='box' +
    box_qty) on any observed_prices rows for the same (url, retailer_key)
    pair that landed BEFORE the URL was mapped to a CID. Without this,
    operator-side passive observations would stay orphaned (cigar_id=NULL)
    until the next time the URL is visited.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    if not body.ids:
        return {"published": 0, "observations_attached": 0}
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Capture (url, retailer_key, cid, box_qty) BEFORE we flip the status
        # so we can attach observations for the same URLs.
        cur.execute("""
            SELECT url, retailer_key, cid, box_qty
              FROM extension_staged_approvals
             WHERE id = ANY(%s)
        """, (list(body.ids),))
        triples = cur.fetchall()

        cur.execute(
            "UPDATE extension_staged_approvals "
            "SET status='published', published_at=NOW() "
            "WHERE id = ANY(%s)",
            (list(body.ids),),
        )
        updated = cur.rowcount

        observations_attached = 0
        for url, retailer_key, cid, box_qty in triples:
            if not (url and retailer_key and cid):
                continue
            # Only touch rows where cigar_id is still NULL — never overwrite
            # an existing mapping. Update quantity_type to 'box' only if it
            # was 'unknown', since the operator's CID approval implies box.
            cur.execute("""
                UPDATE observed_prices
                   SET cigar_id = %s,
                       box_qty = COALESCE(box_qty, %s),
                       quantity_type = CASE
                         WHEN quantity_type IN ('unknown', '') OR quantity_type IS NULL
                              THEN 'box'
                         ELSE quantity_type
                       END
                 WHERE url = %s
                   AND retailer_key = %s
                   AND cigar_id IS NULL
            """, (cid, box_qty, url, retailer_key))
            observations_attached += cur.rowcount

        conn.commit()
        conn.close()
        return {
            "published": updated,
            "observations_attached": observations_attached,
        }
    except Exception as e:
        logger.exception("mark_extension_published failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/pending-new-retailers")
async def pending_new_retailers(request: Request):
    """Local sync fetches new-retailer URLs awaiting drain into queue.txt."""
    auth = _check_admin(request)
    if auth:
        return auth
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, hostname, url, created_at
            FROM pending_new_retailers
            WHERE status='pending'
            ORDER BY hostname, created_at ASC
        """)
        rows = cur.fetchall()
        conn.close()
        return {"pending": [
            {"id": r[0], "hostname": r[1], "url": r[2],
             "created_at": str(r[3]) if r[3] else None}
            for r in rows
        ]}
    except Exception as e:
        logger.exception("pending_new_retailers failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/mark-retailer-queued")
async def mark_retailer_queued(request: Request, body: IdsBody):
    """Local sync marks new-retailer URLs as processed after writing to queue.txt."""
    auth = _check_admin(request)
    if auth:
        return auth
    if not body.ids:
        return {"processed": 0}
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE pending_new_retailers SET status='processed', processed_at=NOW() "
            "WHERE id = ANY(%s)",
            (list(body.ids),),
        )
        updated = cur.rowcount
        conn.commit()
        conn.close()
        return {"processed": updated}
    except Exception as e:
        logger.exception("mark_retailer_queued failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── GET /api/admin/cid-search (autocomplete for popup override) ───────

@router.get("/cid-search")
async def cid_search(
    request: Request,
    q: str = Query("", min_length=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Free-text search the master CID list for the popup's override picker."""
    auth = _check_admin(request)
    if auth:
        return auth
    _refresh_cache()
    ql = q.lower().strip()
    if not ql:
        # Return a small slice so the popup can render something on open
        rows = _cache_state["master"][:limit]
    else:
        rows = []
        for row in _cache_state["master"]:
            hay = " ".join(str(row.get(k, "") or "").lower()
                           for k in ("cigar_id", "brand", "line", "vitola", "wrapper"))
            if all(token in hay for token in ql.split()):
                rows.append(row)
                if len(rows) >= limit:
                    break
    return {"results": [
        {
            "cigar_id": r["cigar_id"],
            "brand": r.get("brand"),
            "line": r.get("line"),
            "vitola": r.get("vitola"),
            "wrapper": r.get("wrapper"),
            "wrapper_code": r.get("wrapper_code"),
            "size": r.get("size"),
            "box_qty": r.get("box_qty"),
        } for r in rows
    ]}


# ── GET /api/admin/master-vocab (autocomplete data for popup) ─────────

@router.get("/master-vocab")
async def master_vocab(request: Request, refresh: bool = Query(False)):
    """Compact vocabulary of every master_cigars row for client-side autocomplete.

    The popup uses this to render context-aware <datalist> dropdowns: picking
    Brand narrows Line options, picking Line narrows Vitola options, etc.

    Payload size ~150-200KB for ~2.3k rows; the background worker caches it
    for 1 hour so the popup gets it instantly on open.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    _refresh_cache(force=refresh)
    rows = [
        {
            "brand": r.get("brand") or "",
            "line": r.get("line") or "",
            "vitola": r.get("vitola") or "",
            "wrapper": r.get("wrapper") or "",
            "wrapper_code": r.get("wrapper_code") or "",
            "size": r.get("size") or "",
            "box_qty": r.get("box_qty"),
        }
        for r in _cache_state["master"]
    ]
    return {"rows": rows, "count": len(rows)}


# ── GET /api/admin/retailer-registry (used by extension at install) ───

@router.get("/observed-prices-recent")
async def observed_prices_recent(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    retailer_key: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="'operator' | 'consumer'"),
):
    """Debug peek at the newest observed_prices rows.

    Lets the operator verify the consumer-extension pipeline is alive
    without opening psql. Admin-gated; same auth as every other admin
    endpoint. Returns at most 500 rows.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    try:
        conn = _get_conn()
        cur = conn.cursor()
        where = []
        params: List = []
        if retailer_key:
            where.append("retailer_key = %s")
            params.append(retailer_key)
        if source:
            where.append("observer_source = %s")
            params.append(source)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        cur.execute(f"""
            SELECT id, observed_at, retailer_key, cigar_id,
                   quantity_type, box_qty,
                   price_cents, currency, in_stock,
                   scraped_title, url, observer_source
              FROM observed_prices
              {where_sql}
             ORDER BY observed_at DESC
             LIMIT %s
        """, params)
        cols = [c[0] for c in cur.description]
        rows = []
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            # Add a human-friendly price field so the response is glance-able.
            row["price"] = (row["price_cents"] / 100.0) if row.get("price_cents") else None
            rows.append(row)

        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE cigar_id IS NOT NULL) AS mapped,
                   COUNT(*) FILTER (WHERE quantity_type = 'box') AS boxes,
                   COUNT(*) FILTER (WHERE quantity_type = 'unknown') AS unknown_qty,
                   COUNT(*) FILTER (WHERE price_cents IS NULL) AS no_price,
                   COUNT(*) FILTER (WHERE observer_source = 'operator') AS from_operator,
                   COUNT(*) FILTER (WHERE observer_source = 'consumer') AS from_consumer
              FROM observed_prices
        """)
        totals = dict(zip([c[0] for c in cur.description], cur.fetchone()))
        conn.close()
        return {"results": rows, "totals": totals, "count": len(rows)}
    except Exception as e:
        logger.exception("observed_prices_recent failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/retailer-registry")
async def retailer_registry(request: Request, refresh: bool = Query(False)):
    """List known retailer hostnames + keys. Extension uses this to know which
    domains to enable on. No CIDs or pricing leaks here; just public host info.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    _refresh_cache(force=refresh)
    return {
        "retailers": [
            {"hostname": host, "retailer_key": key}
            for host, key in sorted(_cache_state["retailers"].items())
        ],
        "total": len(_cache_state["retailers"]),
    }


# ── Review-decision logging ───────────────────────────────────────────
# Every operator approve/edit/skip/reject is logged with both the proposed
# and the final state. This is the training-data spine for the future ML
# reviewer; it costs ~1 INSERT per operator action and adds no user-visible
# behavior. Best-effort: failures are logged but never bubble up.

def _log_review_decision(
    *,
    decision_type: str,
    url: Optional[str] = None,
    retailer_key: Optional[str] = None,
    proposed_cid: Optional[str] = None,
    final_cid: Optional[str] = None,
    proposed_metadata: Optional[Dict] = None,
    final_metadata: Optional[Dict] = None,
    score: Optional[float] = None,
    confidence_label: Optional[str] = None,
    source_table: Optional[str] = None,
    source_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> None:
    import json
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO review_decisions
              (decision_type, source_table, source_id, url, retailer_key,
               proposed_cid, final_cid, proposed_metadata, final_metadata,
               score, confidence_label, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
        """, (
            decision_type, source_table, source_id, url, retailer_key,
            proposed_cid, final_cid,
            json.dumps(proposed_metadata, default=str) if proposed_metadata else None,
            json.dumps(final_metadata, default=str) if final_metadata else None,
            score, confidence_label, notes,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("log_review_decision failed (non-fatal): %s", e)


# ── Community proposal review (admin) ─────────────────────────────────
# These admin endpoints power the operator's review of metadata proposals
# submitted by consumer extension users. Pending proposals show up
# alongside (and filterable from) the existing weekly-discovery staged
# matches in the admin UI.

@router.get("/community-proposals")
async def community_proposals(
    request: Request,
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=500),
):
    """Paginated list of consumer-submitted metadata proposals."""
    auth = _check_admin(request)
    if auth:
        return auth
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, url, retailer_key, proposed_brand, proposed_line,
                   proposed_vitola, proposed_size, proposed_wrapper,
                   proposed_box_qty, scraped_title, observer_id,
                   observer_source, status, operator_notes, resolved_cid,
                   created_at, reviewed_at
              FROM community_url_proposals
             WHERE status = %s
             ORDER BY created_at DESC
             LIMIT %s
        """, (status, limit))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return {"results": rows, "count": len(rows), "status": status}
    except Exception as e:
        logger.exception("community_proposals failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/resolve-community-proposal")
async def resolve_community_proposal(request: Request, body: ResolveProposalBody):
    """Operator action on a single community proposal.

    Actions:
      * approve_existing  — map URL to an existing CID (no master change).
                            Stages an extension_staged_approvals row so the
                            local publisher writes a bare retailer-CSV row.
      * approve_new       — operator promotes the proposal into a real CID.
                            Stages an extension_staged_approvals row with
                            is_new_cid=TRUE so the publisher creates the
                            master_cigars row first.
      * reject / duplicate — closes the proposal, no staging.
    Every action also writes a review_decisions row for ML training.
    """
    auth = _check_admin(request)
    if auth:
        return auth

    action = (body.action or "").lower().strip()
    if action not in {"approve_existing", "approve_new", "reject", "duplicate"}:
        return JSONResponse({"error": f"invalid action '{action}'"}, status_code=400)

    _refresh_cache()

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, url, retailer_key, proposed_brand, proposed_line,
                   proposed_vitola, proposed_size, proposed_wrapper,
                   proposed_box_qty, scraped_title
              FROM community_url_proposals
             WHERE id = %s AND status = 'pending'
             FOR UPDATE
        """, (body.proposal_id,))
        prop = cur.fetchone()
        if not prop:
            conn.close()
            return JSONResponse(
                {"error": f"proposal {body.proposal_id} not pending or not found"},
                status_code=404,
            )
        (pid, p_url, p_retailer, p_brand, p_line, p_vitola, p_size,
         p_wrapper, p_box_qty, p_title) = prop

        proposed_metadata = {
            "brand": p_brand, "line": p_line, "vitola": p_vitola,
            "size": p_size, "wrapper": p_wrapper, "box_qty": p_box_qty,
            "scraped_title": p_title,
        }

        resolved_cid: Optional[str] = None
        final_metadata: Optional[Dict] = None

        if action in ("approve_existing", "approve_new"):
            if not p_retailer:
                conn.rollback()
                conn.close()
                return JSONResponse(
                    {"error": "proposal has no retailer_key; can't stage approval"},
                    status_code=400,
                )

            if action == "approve_existing":
                if not body.cid:
                    conn.rollback()
                    conn.close()
                    return JSONResponse(
                        {"error": "approve_existing requires `cid`"},
                        status_code=400,
                    )
                resolved_cid = body.cid.strip()
                parsed = parse_cid(resolved_cid)
                if not parsed:
                    conn.rollback()
                    conn.close()
                    return JSONResponse(
                        {"error": f"invalid CID '{resolved_cid}'"},
                        status_code=400,
                    )
                is_new = resolved_cid not in _cache_state["master_by_cid"]
                parts_dict = {
                    "brand": parsed["brand"], "parent_brand": parsed["parent_brand"],
                    "line": parsed["line"], "vitola": parsed["vitola"],
                    "vitola2": parsed["vitola2"], "size": parsed["size"],
                    "wrapper_code": parsed["wrapper_code"],
                    "box_qty": _extract_box_qty(parsed["box_qty_str"]) or 0,
                    "wrapper": None,
                }
            else:  # approve_new
                if not body.cid_parts:
                    conn.rollback()
                    conn.close()
                    return JSONResponse(
                        {"error": "approve_new requires `cid_parts`"},
                        status_code=400,
                    )
                parts_dict = body.cid_parts.dict()
                parts_dict["box_qty_str"] = f"BOX{int(parts_dict['box_qty'])}"
                resolved_cid = build_cid(parts_dict)
                is_new = resolved_cid not in _cache_state["master_by_cid"]

            final_metadata = {k: parts_dict.get(k) for k in (
                "brand", "parent_brand", "line", "vitola", "vitola2",
                "size", "wrapper_code", "wrapper", "box_qty",
            )}

            # Stage into extension_staged_approvals so the existing
            # local publisher handles CSV writes uniformly.
            cur.execute("""
                INSERT INTO extension_staged_approvals
                  (cid, retailer_key, url, is_new_cid,
                   brand, parent_brand, line, vitola, vitola2, size,
                   wrapper_code, wrapper, box_qty,
                   title, price, in_stock, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
                ON CONFLICT (retailer_key, url, cid) DO UPDATE
                  SET is_new_cid=EXCLUDED.is_new_cid,
                      brand=EXCLUDED.brand,
                      parent_brand=EXCLUDED.parent_brand,
                      line=EXCLUDED.line,
                      vitola=EXCLUDED.vitola,
                      vitola2=EXCLUDED.vitola2,
                      size=EXCLUDED.size,
                      wrapper_code=EXCLUDED.wrapper_code,
                      wrapper=EXCLUDED.wrapper,
                      box_qty=EXCLUDED.box_qty,
                      title=EXCLUDED.title,
                      status=CASE
                        WHEN extension_staged_approvals.status='published' THEN 'published'
                        ELSE 'pending'
                      END
            """, (
                resolved_cid, p_retailer, p_url, is_new,
                parts_dict["brand"], parts_dict.get("parent_brand") or parts_dict["brand"],
                parts_dict["line"], parts_dict["vitola"],
                parts_dict.get("vitola2") or parts_dict["vitola"],
                parts_dict["size"], parts_dict["wrapper_code"],
                parts_dict.get("wrapper"), int(parts_dict.get("box_qty") or 0),
                p_title, None, None,
            ))

        # Close the proposal regardless of approve/reject path.
        new_status = "approved" if action in ("approve_existing", "approve_new") else action
        cur.execute("""
            UPDATE community_url_proposals
               SET status=%s, operator_notes=%s,
                   resolved_cid=%s, reviewed_at=NOW()
             WHERE id=%s
        """, (new_status, body.notes, resolved_cid, body.proposal_id))

        conn.commit()
        conn.close()

        _log_review_decision(
            decision_type="community_proposal_" + action,
            url=p_url,
            retailer_key=p_retailer,
            final_cid=resolved_cid,
            proposed_metadata=proposed_metadata,
            final_metadata=final_metadata,
            source_table="community_url_proposals",
            source_id=pid,
            notes=body.notes,
        )

        return {
            "ok": True,
            "proposal_id": body.proposal_id,
            "status": new_status,
            "resolved_cid": resolved_cid,
        }
    except Exception as e:
        logger.exception("resolve_community_proposal failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)
