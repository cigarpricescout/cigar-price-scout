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
import re
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
    merge_cid_into_url_index,
    parse_cid,
    url_index_entry_cids,
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
    "url_index": {},       # url -> (retailer_key, List[cigar_id])
}


def _load_staged_approval_url_overlay() -> List[Tuple[str, str, str]]:
    """Pending extension approvals as (canonical_url, retailer_key, cid).

    Multiple pending rows may reference the same URL with different CIDs
    (multi-SKU PDP). Every row is returned so ``_refresh_cache`` can merge
    each into the live index.
    """
    rows: List[Tuple[str, str, str]] = []
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT url, retailer_key, cid FROM extension_staged_approvals "
            "WHERE status='pending' AND url IS NOT NULL AND cid IS NOT NULL"
        )
        for url, retailer_key, cid in cur.fetchall():
            if not url or not retailer_key or not cid:
                continue
            rows.append((canonicalize_url(url), retailer_key, cid))
        conn.close()
    except Exception as e:
        logger.warning("staged-approval URL overlay load failed: %s", e)
    return rows


def _refresh_cache(force: bool = False) -> None:
    """(Re)load master CSV + retailer registry + per-retailer URL index."""
    now = time.time()
    if not force and (now - _cache_state["loaded_at"]) < _CACHE_TTL_SECONDS:
        return
    try:
        master = load_master_cigars(MASTER_CSV)
        # Blocked retailers (anti-bot, no extractor) won't have any sample
        # URL in their CSV to derive a hostname from. Pull explicit hostnames
        # from RETAILERS so the consumer extension still recognizes the
        # site and can collect observations.
        try:
            from app.main import get_blocked_retailer_hosts  # type: ignore
            extra_hosts = get_blocked_retailer_hosts()
        except Exception:
            extra_hosts = {}
        retailers = build_retailer_registry(STATIC_DATA, extra_hosts=extra_hosts)
        url_index = load_retailer_url_index(STATIC_DATA)
        # Layer pending operator approvals on top so just-approved URLs
        # are immediately matchable, without waiting for the publisher
        # to drain to CSV. CSV wins on collision (already-published
        # rows shouldn't be overwritten by stale staging data).
        overlay_rows = _load_staged_approval_url_overlay()
        overlay_added = 0
        for o_url, retailer_key, cid in overlay_rows:
            before = url_index.get(o_url)
            merge_cid_into_url_index(url_index, o_url, retailer_key, cid)
            if url_index.get(o_url) != before:
                overlay_added += 1
        master_by_cid = {row["cigar_id"]: row for row in master}
        _cache_state.update({
            "loaded_at": now,
            "master": master,
            "master_by_cid": master_by_cid,
            "retailers": retailers,
            "url_index": url_index,
        })
        logger.info(
            "Extension cache refreshed: %d master CIDs, %d retailer hosts, "
            "%d live URLs (+%d pending-approval overlay)",
            len(master), len(retailers), len(url_index), overlay_added,
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
                -- 'operator'        — staged by the operator extension (default)
                -- 'consumer_auto'   — auto-published from the consumer extension
                --                    after a "Yes, this is the cigar?" confirmation
                --                    against a HIGH-confidence master-catalog
                --                    candidate. Surfaced in a daily spot-check
                --                    report so the operator can verify the
                --                    auto-match was correct.
                source TEXT DEFAULT 'operator',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                published_at TIMESTAMPTZ,
                UNIQUE (retailer_key, url, cid)
            )
        """)
        # Backfill source column for older DBs that pre-date this addition.
        # ADD COLUMN IF NOT EXISTS is idempotent and a no-op when present.
        cur.execute("""
            ALTER TABLE extension_staged_approvals
            ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'operator'
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
            CREATE INDEX IF NOT EXISTS idx_ext_staged_source_created
                ON extension_staged_approvals(source, created_at DESC)
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
    # When the operator approves a URL the consumer extension previously
    # proposed metadata for, the popup passes the proposal's id so we can
    # close the loop: mark community_url_proposals.status='approved' and
    # stamp resolved_cid. This is how "consumer submits → operator
    # confirms → consumer sees comparison" actually works end-to-end.
    community_proposal_id: Optional[int] = None


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


def _pick_matched_cid(cids: List[str], cid_query: Optional[str]) -> Optional[str]:
    if not cids:
        return None
    if cid_query and cid_query in cids:
        return cid_query
    return cids[0]


def _cigar_pick_options(cids: List[str]) -> List[Dict[str, str]]:
    """Human labels for a multi-CID URL picker (operator + consumer UIs)."""
    master = _cache_state.get("master_by_cid") or {}
    out: List[Dict[str, str]] = []
    for cid in sorted(cids):
        row = master.get(cid)
        if row:
            head = " ".join(
                p for p in (row.get("brand"), row.get("line"), row.get("vitola")) if p
            )
            bits: List[str] = []
            if head:
                bits.append(head)
            if row.get("size"):
                bits.append(str(row["size"]))
            if row.get("wrapper"):
                bits.append(str(row["wrapper"]))
            bq = row.get("box_qty")
            if bq is not None:
                bits.append(f"Box of {bq}")
            label = " • ".join(bits) if bits else cid
        else:
            label = cid
        out.append({"cigar_id": cid, "label": label})
    return out


# ── GET /api/admin/url-status ──────────────────────────────────────────

@router.get("/url-status")
async def url_status(
    request: Request,
    url: str = Query(..., min_length=1),
    title: Optional[str] = Query(None),
    refresh: bool = Query(False),
    cid: Optional[str] = Query(
        None,
        description="When multiple CIDs share this URL, which one to treat as active.",
    ),
):
    """Verdict + candidates for a single URL.

    Response shape:
        {
          "state": "matched" | "seen" | "candidate" | "no_scraper" | "unknown",
          "retailer_key": str | null,
          "hostname": str,
          "url": str,
          "matched_cid": str | null,        # when state == "matched" or "seen"
          "cigar_options": [ { cigar_id, label } ] | null,  # when URL has 2+ CIDs
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

    # extractor_status drives the operator extension's UI: when 'blocked' or
    # 'dormant' there is no scraper to fill the row, so the popup must
    # surface editable price + in-stock fields and the publisher must write
    # a full row instead of a bare one. Imported lazily to keep the
    # extension_endpoints module decoupled from app.main import order.
    try:
        from app.main import get_extractor_status  # type: ignore
        extractor_status = get_extractor_status(retailer_key) if retailer_key else None
    except Exception:
        extractor_status = None

    # Pending consumer proposal for this URL? When present, the operator
    # popup pre-fills the candidate form with the consumer's submission so
    # the operator's review = one-click approve instead of re-typing the
    # same brand/line/vitola/box_qty/price. Exposed across all states so
    # even a 'matched' URL surfaces a pending re-classification proposal.
    community_proposal = _lookup_community_proposal(url)

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
            "cigar_options": None,
            "seen_status": None,
            "extractor_status": None,
            "candidates": [],
            "available_in_master": [],
            "scraped_title": title,
            "community_proposal": community_proposal,
        }

    # 1) Already in the live retailer CSV? `url` is already canonical here
    # (normalized at the endpoint boundary) and the url_index is keyed by
    # canonical URLs too, so this dict-get hits the right row even for
    # Shopify ?variant=… or utm_* URLs.
    live_hit = _cache_state["url_index"].get(url)
    rk_live, cids_live = url_index_entry_cids(live_hit)
    if rk_live == retailer_key and cids_live:
        matched_cid = _pick_matched_cid(cids_live, cid)
        cigar_options = _cigar_pick_options(cids_live) if len(cids_live) > 1 else None
        return {
            "state": "matched",
            "retailer_key": retailer_key,
            "hostname": hostname,
            "url": url,
            "matched_cid": matched_cid,
            "cigar_options": cigar_options,
            "seen_status": "published",
            "extractor_status": extractor_status,
            "candidates": _candidates_for(url, title),
            "available_in_master": [],
            "scraped_title": title,
            "community_proposal": community_proposal,
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
            "cigar_options": None,
            "seen_status": seen_status,
            "extractor_status": extractor_status,
            "candidates": _candidates_for(url, title),
            "available_in_master": [],
            "scraped_title": title,
            "community_proposal": community_proposal,
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
        "cigar_options": None,
        "seen_status": None,
        "extractor_status": extractor_status,
        "candidates": cands,
        "available_in_master": [c["cigar_id"] for c in available],
        "scraped_title": title,
        "community_proposal": community_proposal,
    }


def _candidates_for(url: str, title: Optional[str]) -> List[Dict]:
    """Run the matcher against the cached master list."""
    return find_top_candidates(url, title, _cache_state["master"], limit=5)


def _lookup_community_proposal(url: str) -> Optional[Dict]:
    """Return the most-recent PENDING community_url_proposal for a URL.

    Surfaces consumer-submitted metadata to the operator extension so
    when the operator visits a URL a user has already proposed for, the
    popup can pre-fill the form with the consumer's brand/line/vitola/
    wrapper-bucket/price entry instead of making the operator re-do the
    work. Returns None if no pending proposal exists.

    Returns a dict with the proposed fields and a `total_pending` count
    of how many consumers have proposed this URL (de-emphasized in the UI
    when 1, surfaced as social proof when >1).
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, proposed_brand, proposed_line, proposed_vitola,
                   proposed_size, proposed_wrapper, proposed_box_qty,
                   confirmed_price_cents, scraped_title, observer_source,
                   created_at, retailer_key,
                   (SELECT COUNT(*) FROM community_url_proposals
                    WHERE url=%s AND status='pending') AS total_pending,
                   is_correction, current_cid, current_price_cents
            FROM community_url_proposals
            WHERE url=%s AND status='pending'
            ORDER BY created_at DESC
            LIMIT 1
        """, (url, url))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        confirmed_price_cents = row[7]
        current_price_cents = row[15]
        return {
            "proposal_id": row[0],
            "proposed_brand": row[1],
            "proposed_line": row[2],
            "proposed_vitola": row[3],
            "proposed_size": row[4],
            "proposed_wrapper": row[5],  # bucket name like "Maduro"
            "proposed_box_qty": row[6],
            "confirmed_price": (
                round(confirmed_price_cents / 100.0, 2)
                if confirmed_price_cents is not None else None
            ),
            "scraped_title": row[8],
            "observer_source": row[9],
            "created_at": str(row[10]) if row[10] else None,
            "retailer_key": row[11],
            "total_pending": row[12] or 1,
            # Correction context — when is_correction=true the operator
            # popup shows a distinct "consumer disagrees" banner and
            # surfaces what the consumer says is wrong vs. what we were
            # showing them at the moment they reported it.
            "is_correction": bool(row[13]),
            "current_cid": row[14],
            "current_price": (
                round(current_price_cents / 100.0, 2)
                if current_price_cents is not None else None
            ),
        }
    except Exception as e:
        logger.warning("lookup_community_proposal error: %s", e)
        return None


def _lookup_seen(url: str, retailer_key: str) -> Tuple[Optional[str], Optional[str]]:
    """Has the user already touched this URL via the extension or weekly agent?

    Returns (status, cid). status is one of:
      - "extension_pending" / "extension_published" — staged by this extension
      - "agent_approved" / "agent_published" / "agent_rejected" — from the
        weekly discovery agent (existing url_staged_matches)
      - "skipped" — clicked Skip in the popup
    None when the URL has never been seen.

    Note: community_url_proposals are handled separately by
    _lookup_community_proposal() and exposed as `community_proposal`
    on the response rather than collapsing into the seen-status enum.
    The operator wants to see consumer-proposed metadata, not just be
    told "this URL is under review".
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

        # If this approval resolves a consumer proposal, mark it approved
        # and stamp the final CID. The consumer-side popup polls or
        # re-fetches url-status on next visit, sees the URL is now matched,
        # and shows the comparison card — closing the contribution loop.
        # We also resolve ALL other pending proposals for the same URL
        # (consumers may have submitted multiple times) so the queue
        # collapses to a single decision per URL.
        resolved_proposal_count = 0
        if body.community_proposal_id:
            cur.execute("""
                UPDATE community_url_proposals
                   SET status='approved',
                       resolved_cid=%s,
                       reviewed_at=NOW()
                 WHERE url=%s
                   AND status='pending'
            """, (cid, body.url))
            resolved_proposal_count = cur.rowcount or 0

        conn.commit()
        conn.close()

        # Live overlay: mutate the in-memory URL index immediately so
        # the consumer popup, /compare page, and any other caller of
        # _cache_state["url_index"] see this approval within the same
        # request — no need to wait for the next cache refresh, the
        # publisher script, a git push, or a Railway redeploy. The
        # next _refresh_cache call will re-overlay this row from
        # extension_staged_approvals so it survives until the
        # publisher drains it to CSV.
        try:
            merge_cid_into_url_index(
                _cache_state["url_index"],
                body.url,
                body.retailer_key,
                cid,
            )
        except Exception as e:
            logger.warning("live url_index overlay update failed: %s", e)

        # Bust the website's product cache too so /compare reflects
        # the new mapping on the next request. Without this the
        # /compare endpoint serves stale Product lists for up to
        # CACHE_TTL_SECONDS after approval.
        try:
            from app.main import _product_cache  # type: ignore
            _product_cache["data"] = None
            _product_cache["timestamp"] = 0
        except Exception as e:
            logger.warning("/compare cache bust after approval failed: %s", e)

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
            # Surfaced so the popup can show "Approved consumer's submission"
            # toast and the smoke-test dashboard can verify the loop closed.
            "resolved_consumer_proposals": resolved_proposal_count,
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
        # Include extractor_status per row so the local publisher can decide
        # between "bare row" (active retailer — scraper will fill price/title
        # next run) and "full row" (blocked/dormant — manual entry is the
        # only data source). Resolved here rather than at publish time so
        # the publisher stays a thin shell over this endpoint.
        try:
            from app.main import get_extractor_status  # type: ignore
        except Exception:
            get_extractor_status = lambda _k: "active"  # type: ignore  # noqa: E731
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
                "extractor_status": get_extractor_status(r[2]),
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


@router.get("/retailer-requests")
async def retailer_requests(request: Request):
    """Aggregated view of community_retailer_requests for operator triage.

    Returns each requested hostname with: total requesters, latest request
    timestamp, fulfilled flag (NULL if any are unfulfilled), and a sample
    URL. Useful for prioritizing which anti-bot retailers to onboard next
    — high requester count = strong signal that users want it.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT hostname,
                   COUNT(DISTINCT observer_id) AS requesters,
                   COUNT(*) AS total_requests,
                   MAX(requested_at) AS latest_requested_at,
                   MIN(fulfilled_at) AS earliest_fulfilled_at,
                   BOOL_AND(fulfilled_at IS NOT NULL) AS all_fulfilled,
                   (ARRAY_AGG(url ORDER BY requested_at DESC))[1] AS sample_url
            FROM community_retailer_requests
            GROUP BY hostname
            ORDER BY requesters DESC, latest_requested_at DESC
            LIMIT 200
        """)
        rows = cur.fetchall()
        conn.close()
        return {"requests": [
            {
                "hostname": r[0],
                "requesters": int(r[1]),
                "total_requests": int(r[2]),
                "latest_requested_at": str(r[3]) if r[3] else None,
                "earliest_fulfilled_at": str(r[4]) if r[4] else None,
                "all_fulfilled": bool(r[5]),
                "sample_url": r[6],
            }
            for r in rows
        ]}
    except Exception as e:
        logger.exception("retailer_requests failed: %s", e)
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


# ── POST /api/admin/cleanup-orphan-observations ────────────────────────
#
# One-time pre-launch cleanup. Targets the kinds of rows we KNOW are
# garbage and would never get written by the post-fix code path:
#   1. Non-product paths (homepage /, /collections, /cart, /search, etc.)
#   2. URLs that still carry tracking/variant query params (variant=,
#      utm_*, gclid, fbclid, …) — these are pre-canonicalization-fix
#      duplicates of their canonical-URL counterparts.
#   3. Rows where price_cents IS NULL AND scraped_title IS NULL — fully
#      empty observations that couldn't have come from a real product.

# Same path tokens as extension/background.js looksLikeProductPage().
# Kept here as a list rather than regex so the SQL can use LIKE matches
# directly.
_NON_PRODUCT_PATH_LIKE = (
    "/collections/", "/collections",
    "/categories/", "/categories",
    "/category/",   "/category",
    "/search/",     "/search",
    "/cart/",       "/cart",
    "/checkout/",   "/checkout",
    "/account/",    "/account",
    "/login/",      "/login",
    "/pages/",
    "/blog/", "/blogs/",
    "/policy/", "/policies/",
    "/sitemap",
    "/api/",
)
_TRACKING_PARAM_LIKE = (
    "%?variant=%", "%&variant=%",
    "%?utm_%",    "%&utm_%",
    "%?gclid=%",  "%&gclid=%",
    "%?fbclid=%", "%&fbclid=%",
    "%?msclkid=%", "%&msclkid=%",
)


@router.post("/cleanup-orphan-observations")
async def cleanup_orphan_observations(
    request: Request,
    dry_run: bool = Query(True, description="Preview only; pass false to actually delete"),
):
    """Delete observed_prices rows that should never have been written.

    Pre-launch hygiene. Admin-gated. Defaults to dry_run=true so you can
    review what would be deleted before committing.

    Returns:
      {
        "dry_run": bool,
        "deleted": {
          "non_product_paths": int,
          "tracking_params":   int,
          "fully_empty":       int,
          "total":             int
        },
        "samples": {
          "non_product_paths": [up to 10 URLs],
          "tracking_params":   [up to 10 URLs],
          "fully_empty":       [up to 10 IDs]
        }
      }
    """
    auth = _check_admin(request)
    if auth:
        return auth

    import re
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # ── Bucket 1: non-product paths ──────────────────────────────
        # We match the path portion of the URL. Since observed_prices.url
        # is a full URL, we use a position-aware LIKE: '%://%/pattern'.
        non_product_conds = []
        non_product_params: List = []
        for tok in _NON_PRODUCT_PATH_LIKE:
            non_product_conds.append("url ~* %s")
            # Anchor at '<host>/pattern' so we don't match query strings.
            # The regex form 'https?://[^/]+(/...)' is simpler in PG with
            # POSIX regex via ~* (case-insensitive).
            non_product_params.append(rf"^https?://[^/]+{re.escape(tok)}")
        # Also catch bare-host (path == '' or '/').
        bare_host_re = r"^https?://[^/]+/?$"
        non_product_conds.append("url ~* %s")
        non_product_params.append(bare_host_re)

        non_product_where = "(" + " OR ".join(non_product_conds) + ")"

        cur.execute(
            f"SELECT id, url FROM observed_prices WHERE {non_product_where} "
            "ORDER BY observed_at DESC LIMIT 10",
            non_product_params,
        )
        non_product_samples = [{"id": r[0], "url": r[1]} for r in cur.fetchall()]

        cur.execute(
            f"SELECT COUNT(*) FROM observed_prices WHERE {non_product_where}",
            non_product_params,
        )
        non_product_count = cur.fetchone()[0]

        # ── Bucket 2: URLs still carrying tracking/variant params ─────
        tracking_conds = " OR ".join(["url LIKE %s"] * len(_TRACKING_PARAM_LIKE))
        cur.execute(
            f"SELECT id, url FROM observed_prices WHERE {tracking_conds} "
            "ORDER BY observed_at DESC LIMIT 10",
            list(_TRACKING_PARAM_LIKE),
        )
        tracking_samples = [{"id": r[0], "url": r[1]} for r in cur.fetchall()]

        cur.execute(
            f"SELECT COUNT(*) FROM observed_prices WHERE {tracking_conds}",
            list(_TRACKING_PARAM_LIKE),
        )
        tracking_count = cur.fetchone()[0]

        # ── Bucket 3: fully empty rows ────────────────────────────────
        # No price AND no title → the scrape captured literally nothing
        # useful. Safe to delete regardless.
        empty_where = "(price_cents IS NULL AND (scraped_title IS NULL OR scraped_title = ''))"
        cur.execute(
            f"SELECT id, url FROM observed_prices WHERE {empty_where} "
            "ORDER BY observed_at DESC LIMIT 10",
        )
        empty_samples = [{"id": r[0], "url": r[1]} for r in cur.fetchall()]

        cur.execute(f"SELECT COUNT(*) FROM observed_prices WHERE {empty_where}")
        empty_count = cur.fetchone()[0]

        deleted_total = 0
        if not dry_run:
            cur.execute(
                f"DELETE FROM observed_prices WHERE {non_product_where}",
                non_product_params,
            )
            d1 = cur.rowcount
            cur.execute(
                f"DELETE FROM observed_prices WHERE {tracking_conds}",
                list(_TRACKING_PARAM_LIKE),
            )
            d2 = cur.rowcount
            cur.execute(f"DELETE FROM observed_prices WHERE {empty_where}")
            d3 = cur.rowcount
            conn.commit()
            # Re-report the actual deleted counts (may differ slightly
            # from the COUNT(*) above if rows overlap multiple buckets).
            deleted_total = d1 + d2 + d3
            non_product_count, tracking_count, empty_count = d1, d2, d3

        conn.close()

        return {
            "dry_run": dry_run,
            "deleted": {
                "non_product_paths": non_product_count,
                "tracking_params":   tracking_count,
                "fully_empty":       empty_count,
                "total":             non_product_count + tracking_count + empty_count
                                      if dry_run else deleted_total,
            },
            "samples": {
                "non_product_paths": non_product_samples,
                "tracking_params":   tracking_samples,
                "fully_empty":       empty_samples,
            },
        }
    except Exception as e:
        logger.exception("cleanup_orphan_observations failed: %s", e)
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

@router.get("/dedup-stats")
async def dedup_stats(request: Request):
    """Surface load_all_products dedup counters for the smoke-test dashboard.

    Reports how many website-form community submissions were dropped on
    the last cache refresh because a CSV or observed row already covered
    the same (URL or retailer+CID). Lets the operator verify Sprint 3.5
    dedup is firing without grep'ing Railway logs.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    try:
        from app.main import _dedup_stats as stats  # type: ignore
        return dict(stats)
    except Exception as e:
        logger.exception("dedup_stats failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/community-prices-recent")
async def community_prices_recent(
    request: Request,
    limit: int = Query(20, ge=1, le=200),
):
    """Newest /api/community-price (website form) submissions.

    Lets the smoke-test dashboard verify Test 5 (legacy form still writes)
    without a Postgres client.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, cid, url, price_cents, retailer_name,
                   brand, line, wrapper, vitola, size, box_qty,
                   free_shipping, active, downvotes, submitted_at
              FROM community_prices
             ORDER BY id DESC
             LIMIT %s
        """, (limit,))
        cols = [c[0] for c in cur.description]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            if d.get("submitted_at"):
                d["submitted_at"] = str(d["submitted_at"])
            rows.append(d)
        conn.close()
        return {"results": rows, "count": len(rows)}
    except Exception as e:
        logger.exception("community_prices_recent failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/observer-counts")
async def observer_counts(request: Request, observer_id: str = Query(...)):
    """Row counts across every observer-keyed table for a given observer_id.

    Used by Test 7 in the smoke-test dashboard ("forget me") so the
    operator can verify deletion zeroed everything out.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    obs = (observer_id or "").strip()
    if not obs:
        return JSONResponse({"error": "observer_id required"}, status_code=400)
    try:
        conn = _get_conn()
        cur = conn.cursor()
        counts = {}
        for table in ("observed_prices", "community_url_proposals", "community_retailer_requests"):
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE observer_id = %s", (obs,))
                counts[table] = int(cur.fetchone()[0])
            except Exception as inner:
                counts[table] = f"error: {inner}"
        conn.close()
        return {"observer_id": obs, "counts": counts}
    except Exception as e:
        logger.exception("observer_counts failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/community-proposals")
async def community_proposals(
    request: Request,
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=500),
    include_candidates: bool = Query(True),
):
    """Paginated list of consumer-submitted metadata proposals.

    When ``include_candidates=True`` (default), each row also gets a
    ``top_candidate`` field — the highest-confidence CID match the
    matcher can derive from the proposal's URL + scraped_title +
    proposed brand/line/vitola/box_qty. This powers the
    /admin/review?source=community one-click approve flow: HIGH-confidence
    rows get an "Approve {CID}" button; lower-confidence rows fall
    back to "Open in extension" so the operator can edit via the popup.
    """
    auth = _check_admin(request)
    if auth:
        return auth
    try:
        _refresh_cache()
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, url, retailer_key, proposed_brand, proposed_line,
                   proposed_vitola, proposed_size, proposed_wrapper,
                   proposed_box_qty, scraped_title, observer_id,
                   observer_source, status, operator_notes, resolved_cid,
                   created_at, reviewed_at,
                   confirmed_price_cents,
                   is_correction, current_cid, current_price_cents
              FROM community_url_proposals
             WHERE status = %s
             ORDER BY created_at DESC
             LIMIT %s
        """, (status, limit))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()

        if include_candidates and rows:
            master = _cache_state.get("master") or []
            for row in rows:
                # Synthesize a title from the proposed metadata so the
                # matcher has the same signal an extractor would feed it.
                bits = [
                    row.get("proposed_brand"),
                    row.get("proposed_line"),
                    row.get("proposed_vitola"),
                    row.get("proposed_size"),
                ]
                synth_title = " ".join(b for b in bits if b)
                title = row.get("scraped_title") or synth_title
                try:
                    cands = find_top_candidates(
                        row.get("url") or "",
                        title,
                        master,
                        limit=3,
                    )
                except Exception as e:
                    logger.warning(
                        "candidate match failed for proposal %s: %s",
                        row.get("id"), e,
                    )
                    cands = []
                # Filter to candidates whose box_qty matches the
                # proposal's — wrong box quantity is the single
                # most-common reason a HIGH-confidence text match
                # is actually wrong (singles vs box).
                proposed_box = row.get("proposed_box_qty")
                if proposed_box:
                    same_box = []
                    for c in cands:
                        cid = c.get("cigar_id") or ""
                        parts = cid.split("|")
                        # CID format: ...|BOXQTY where BOXQTY is "BOX25"
                        bq_str = parts[-1] if parts else ""
                        try:
                            bq = int(re.sub(r"[^0-9]", "", bq_str) or "0")
                        except Exception:
                            bq = 0
                        if bq == int(proposed_box):
                            same_box.append(c)
                    if same_box:
                        cands = same_box
                row["candidates"] = cands[:3]
                row["top_candidate"] = cands[0] if cands else None

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


# ── Auto-publish spot-check report (Is this the cigar? confirmations) ──


@router.get("/auto-publish-report")
async def auto_publish_report(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    status: Optional[str] = Query(None,
        description="Filter by status: 'pending', 'published', 'rejected'. "
                    "Omit to include all."),
    limit: int = Query(200, ge=1, le=1000),
):
    """Daily spot-check feed for "Is this the cigar?" consumer confirmations.

    Every row staged with source='consumer_auto' goes live immediately
    via the URL-index overlay — operator backstop is reviewing these
    here. If a row looks wrong, POST /api/admin/reject-auto-publish
    flips its status to 'rejected', which (a) removes it from the live
    overlay on the next refresh and (b) keeps the publisher from
    drainage to the retailer CSV.

    Defaults to the last 7 days so the operator can sweep a week's worth
    in one sitting; widen with ?days=30 when needed.
    """
    auth = _check_admin(request)
    if auth:
        return auth

    try:
        conn = _get_conn()
        cur = conn.cursor()
        params: List[Any] = [days]
        sql = """
            SELECT id, cid, retailer_key, url, status,
                   brand, line, vitola, size, wrapper, wrapper_code, box_qty,
                   title, price, in_stock,
                   created_at, published_at
              FROM extension_staged_approvals
             WHERE source = 'consumer_auto'
               AND created_at >= NOW() - (%s || ' days')::INTERVAL
        """
        if status:
            sql += " AND status = %s"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, tuple(params))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Per-status totals so the dashboard can show a small summary
        # without re-querying. Same WHERE filter on the time window.
        cur.execute(
            """
            SELECT status, COUNT(*)
              FROM extension_staged_approvals
             WHERE source = 'consumer_auto'
               AND created_at >= NOW() - (%s || ' days')::INTERVAL
             GROUP BY status
            """,
            (days,),
        )
        counts = {row[0]: row[1] for row in cur.fetchall()}
        conn.close()
        return {
            "results": rows,
            "count": len(rows),
            "window_days": days,
            "counts_by_status": counts,
        }
    except Exception as e:
        logger.exception("auto_publish_report failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


class RejectAutoPublishBody(BaseModel):
    """Operator reverses a consumer auto-publish that turned out wrong."""
    staged_id: int = Field(..., ge=1)
    reason: Optional[str] = Field(None, max_length=500)


@router.post("/reject-auto-publish")
async def reject_auto_publish(request: Request, body: RejectAutoPublishBody):
    """Mark a consumer_auto staged approval as rejected.

    Effect: (a) the row stays for the audit trail but is excluded from
    the live URL-index overlay on the next cache refresh; (b) the
    publisher's daily drain skips it so it never reaches the retailer
    CSV. The operator can re-approve via the normal stage_approval flow
    if the reject was a mistake.
    """
    auth = _check_admin(request)
    if auth:
        return auth

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE extension_staged_approvals
               SET status = 'rejected'
             WHERE id = %s
               AND source = 'consumer_auto'
               AND status IN ('pending','published')
             RETURNING id, url, retailer_key, cid, status
            """,
            (body.staged_id,),
        )
        row = cur.fetchone()
        conn.commit()
        conn.close()
    except Exception as e:
        logger.exception("reject_auto_publish failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    if not row:
        return JSONResponse(
            {"error": "not_found",
             "detail": "No consumer_auto row in pending/published status with that id."},
            status_code=404,
        )

    # Force the URL-index overlay to drop this row on the next refresh
    # so the live site stops serving the now-rejected mapping.
    try:
        _refresh_cache(force=True)
    except Exception as e:
        logger.warning("cache refresh after reject_auto_publish failed: %s", e)

    return {
        "ok": True,
        "rejected": {
            "id": row[0], "url": row[1], "retailer_key": row[2],
            "cid": row[3], "status": row[4],
        },
    }
