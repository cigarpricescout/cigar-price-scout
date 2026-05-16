"""
Public FastAPI routes for the consumer Chrome extension's passive
observation + metadata-proposal pipeline.

Unlike `app.extension_endpoints` (which is admin-only and writes directly
into the operator's staging tables), this router is PUBLIC. Requests are
anonymous, identified only by a client-generated `observer_id` device
hash, and are stored as raw observations + community proposals. Operator
review still happens through the admin endpoints in extension_endpoints.

Tables created here:

  * observed_prices            — every per-URL price reading we capture
  * community_url_proposals    — consumer-suggested metadata for URLs not
                                 yet mapped to a CID (operator approves
                                 and turns it into a real CID)
  * review_decisions           — every operator approve/edit/reject, for
                                 future ML reviewer training

Design constraints:

  * NEVER writes to retailer CSVs or master_cigars. Postgres only.
  * NEVER auto-attaches a URL to a CID without operator action. If we
    can resolve cigar_id at observation time from the live url_index,
    we attach it (cheap, deterministic) — but unmapped URLs are stored
    with cigar_id=NULL and box rows participate in /compare only after
    an operator approves a CID for that URL.
  * Box-only feeds the comparison layer. quantity_type='box' rows go to
    /compare; pack/single rows are captured but not surfaced (until/
    unless we add singles support).
  * Rate limited per observer_id to keep abuse out without forcing
    accounts on consumers.

Mount in app/main.py with:

    from app.community_endpoints import router as community_router, init_community_tables
    init_community_tables()  # call inside startup_event()
    app.include_router(community_router)
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.cid_matcher import (
    canonical_cigar_id_for_comparison,
    canonicalize_url,
    dedupe_cid_list_preserve_order,
    merge_cid_into_url_index,
    url_index_entry_cids,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/community", tags=["community"])


# ── Rate limiting ──────────────────────────────────────────────────────
# Simple per-observer sliding window. Railway runs single-instance today,
# so an in-process bucket is fine. If we move to multi-instance we'll
# switch to a Postgres-backed counter or Redis.

_OBSERVE_MAX_PER_MIN = 60
_OBSERVE_MAX_PER_DAY = 5_000
_PROPOSE_MAX_PER_HOUR = 30

_obs_minute: Dict[str, Deque[float]] = defaultdict(deque)
_obs_day:    Dict[str, Deque[float]] = defaultdict(deque)
_prop_hour:  Dict[str, Deque[float]] = defaultdict(deque)


def _rate_limit(bucket: Dict[str, Deque[float]], key: str, window_s: float, cap: int) -> bool:
    """Return True if a hit is allowed; False if the bucket is full.

    Works with either a defaultdict(deque) or a plain dict; missing keys
    are auto-created.
    """
    now = time.time()
    q = bucket.get(key)
    if q is None:
        q = deque()
        bucket[key] = q
    while q and (now - q[0]) > window_s:
        q.popleft()
    if len(q) >= cap:
        return False
    q.append(now)
    return True


def _observer_id(body_observer_id: Optional[str], request: Request) -> str:
    """Return a non-empty observer id, falling back to the request IP.

    Clients should always send a stable per-install `observer_id` (we
    generate one in the extension and persist it in chrome.storage), but
    fall back to IP so we still rate-limit malformed clients.
    """
    candidate = (body_observer_id or "").strip()
    if candidate:
        return candidate[:128]
    return f"ip:{(request.client.host if request.client else 'unknown')}"


# ── Schema ─────────────────────────────────────────────────────────────

def init_community_tables() -> None:
    """Create the three additive community tables. Safe to call repeatedly."""
    from app.main import get_analytics_conn  # type: ignore
    try:
        conn = get_analytics_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS observed_prices (
                id BIGSERIAL PRIMARY KEY,
                url TEXT NOT NULL,
                retailer_key TEXT,
                -- NULL until an operator maps the URL to a CID.
                cigar_id TEXT,
                -- 'box' | 'pack5' | 'pack10' | 'single' | 'unknown'.
                -- Only 'box' rows participate in /compare today.
                quantity_type TEXT NOT NULL DEFAULT 'unknown',
                box_qty INTEGER,
                price_cents INTEGER,
                currency TEXT NOT NULL DEFAULT 'USD',
                in_stock BOOLEAN,
                scraped_title TEXT,
                jsonld JSONB,
                observer_id TEXT,
                -- 'operator' (you, in the admin extension) or 'consumer'
                -- (Chrome Web Store install). Lets us slice "my data" vs
                -- "everyone else's" later.
                observer_source TEXT NOT NULL DEFAULT 'consumer',
                observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS observed_prices_url_observed_at_idx
                ON observed_prices (url, observed_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS observed_prices_cigar_id_observed_at_idx
                ON observed_prices (cigar_id, observed_at DESC)
                WHERE cigar_id IS NOT NULL
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS observed_prices_retailer_observed_at_idx
                ON observed_prices (retailer_key, observed_at DESC)
                WHERE retailer_key IS NOT NULL
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS community_url_proposals (
                id BIGSERIAL PRIMARY KEY,
                url TEXT NOT NULL,
                retailer_key TEXT,
                proposed_brand TEXT,
                proposed_line TEXT,
                proposed_vitola TEXT,
                proposed_size TEXT,
                proposed_wrapper TEXT,
                proposed_box_qty INTEGER,
                -- User-confirmed price in cents. Pre-filled from scraper,
                -- editable in the propose form. Distinct from observed_prices:
                -- this is the EXPLICIT confirmation that powers /compare once
                -- the operator resolves the proposal into a CID.
                confirmed_price_cents INTEGER,
                scraped_title TEXT,
                observer_id TEXT,
                observer_source TEXT NOT NULL DEFAULT 'consumer',
                -- 'pending' | 'approved' | 'rejected' | 'duplicate'
                status TEXT NOT NULL DEFAULT 'pending',
                operator_notes TEXT,
                -- The CID this proposal resolved to (set when operator approves).
                resolved_cid TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                reviewed_at TIMESTAMPTZ
            )
        """)
        # Idempotent migration for installs that have the table pre-column.
        cur.execute("""
            ALTER TABLE community_url_proposals
                ADD COLUMN IF NOT EXISTS confirmed_price_cents INTEGER
        """)
        # "Report incorrect" flow: a consumer who lands on a matched URL can
        # submit a correction (different brand/line/vitola/box_qty/price than
        # what we currently show). is_correction lets the operator-review UI
        # tag those rows distinctly; current_cid + current_price_cents
        # capture WHAT we were showing at the moment the user disagreed,
        # so the operator can compare proposed-vs-current side by side
        # without re-querying.
        cur.execute("""
            ALTER TABLE community_url_proposals
                ADD COLUMN IF NOT EXISTS is_correction BOOLEAN NOT NULL DEFAULT FALSE
        """)
        cur.execute("""
            ALTER TABLE community_url_proposals
                ADD COLUMN IF NOT EXISTS current_cid TEXT
        """)
        cur.execute("""
            ALTER TABLE community_url_proposals
                ADD COLUMN IF NOT EXISTS current_price_cents INTEGER
        """)
        cur.execute("""
            ALTER TABLE community_url_proposals
                ADD COLUMN IF NOT EXISTS current_in_stock BOOLEAN
        """)
        cur.execute("""
            ALTER TABLE community_url_proposals
                ADD COLUMN IF NOT EXISTS proposed_in_stock BOOLEAN
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS community_url_proposals_status_created_at_idx
                ON community_url_proposals (status, created_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS community_url_proposals_url_idx
                ON community_url_proposals (url)
        """)
        cur.execute("""
            ALTER TABLE community_url_proposals
                ADD COLUMN IF NOT EXISTS needs_new_catalog_cid BOOLEAN NOT NULL DEFAULT FALSE
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS review_decisions (
                id BIGSERIAL PRIMARY KEY,
                -- 'extension_approval' | 'community_proposal_approval' |
                -- 'skip' | 'reject' | 'queue_new_retailer' | etc.
                decision_type TEXT NOT NULL,
                source_table TEXT,
                source_id BIGINT,
                url TEXT,
                retailer_key TEXT,
                proposed_cid TEXT,
                final_cid TEXT,
                proposed_metadata JSONB,
                final_metadata JSONB,
                score REAL,
                confidence_label TEXT,
                operator_id TEXT,
                notes TEXT,
                decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS review_decisions_decided_at_idx
                ON review_decisions (decided_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS review_decisions_decision_type_idx
                ON review_decisions (decision_type, decided_at DESC)
        """)
        # Per-observer "I want this retailer added" requests. Sibling to
        # pending_new_retailers (which is the operator-facing queue) — we
        # split observer linkage out so chrome.notifications can fire only
        # for users who actually asked. Same hostname can be requested by
        # many observers; each (observer_id, hostname) pair is unique.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS community_retailer_requests (
                id BIGSERIAL PRIMARY KEY,
                observer_id TEXT NOT NULL,
                hostname TEXT NOT NULL,
                url TEXT,
                requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                fulfilled_at TIMESTAMPTZ,
                UNIQUE (observer_id, hostname)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS community_retailer_requests_observer_idx
                ON community_retailer_requests (observer_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS community_retailer_requests_hostname_idx
                ON community_retailer_requests (hostname)
        """)
        conn.commit()
        conn.close()
        logger.info("Community tables initialized")
    except Exception as e:
        logger.error("init_community_tables failed: %s", e)


def _get_conn():
    from app.main import get_analytics_conn  # type: ignore
    return get_analytics_conn()


# ── Pydantic bodies ────────────────────────────────────────────────────

_VALID_QTY_TYPES = {"box", "pack5", "pack10", "pack20", "single", "unknown"}


class ObserveBody(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    observer_id: Optional[str] = None
    # All optional — capture whatever the page gave us.
    scraped_title: Optional[str] = Field(None, max_length=500)
    price: Optional[float] = None  # dollars; converted to cents server-side
    currency: Optional[str] = Field(None, max_length=8)
    in_stock: Optional[bool] = None
    quantity_type: Optional[str] = Field(None, max_length=16)
    box_qty: Optional[int] = None
    # Raw JSON-LD captured for debugging / future re-parsing. Cap so a
    # rogue page can't ship a megabyte of HTML.
    jsonld: Optional[Dict[str, Any]] = None
    # When a URL maps to multiple CIDs, the consumer extension passes the
    # user's dropdown pick so observations attach to the right variant.
    cigar_id: Optional[str] = Field(None, max_length=200)
    # 'operator' or 'consumer'. We default to 'consumer'; the operator
    # extension overrides to 'operator' so we can slice "my data" later.
    observer_source: Optional[str] = "consumer"


class ProposeMetadataBody(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    observer_id: Optional[str] = None
    brand: Optional[str] = Field(None, max_length=120)
    line: Optional[str] = Field(None, max_length=120)
    vitola: Optional[str] = Field(None, max_length=120)
    size: Optional[str] = Field(None, max_length=32)
    wrapper: Optional[str] = Field(None, max_length=120)
    box_qty: Optional[int] = None
    # The user-confirmed price (dollars, converted to cents server-side).
    # Pre-filled from the page scrape in the consumer extension but the
    # user can edit before submitting, so we treat this as ground truth.
    confirmed_price: Optional[float] = None
    scraped_title: Optional[str] = Field(None, max_length=500)
    observer_source: Optional[str] = "consumer"


class ReportCorrectionBody(BaseModel):
    """Consumer-submitted correction for a URL we already have a CID for.

    Pre-filled in the popup from the current matched comparison; user can
    edit any field. Server validates the price band before accepting.
    """
    url: str = Field(..., min_length=1, max_length=2048)
    observer_id: Optional[str] = None
    # The CID we were showing the consumer at the moment they reported it.
    # Lets the operator UI render proposed-vs-current diff cleanly.
    current_cid: Optional[str] = Field(None, max_length=200)
    # Sale price (no coupons applied) we were showing for THIS retailer
    # at the moment they reported it. In dollars. Stored in cents on the
    # row so the operator can eyeball "user says $14, we were showing
    # $140" without re-querying.
    current_price: Optional[float] = None
    # Proposed (corrected) values. All optional individually but at least
    # ONE must differ from current — the endpoint enforces that and
    # short-circuits to a no-op if everything matches.
    proposed_brand: Optional[str] = Field(None, max_length=120)
    proposed_line: Optional[str] = Field(None, max_length=120)
    proposed_vitola: Optional[str] = Field(None, max_length=120)
    proposed_wrapper: Optional[str] = Field(None, max_length=120)
    proposed_box_qty: Optional[int] = None
    # The corrected sale price the consumer claims is on the page right now.
    # Same "no coupons" rule as current_price. Validated server-side.
    proposed_price: Optional[float] = None
    # Stock: what we showed vs what the shopper says (Report incorrect form).
    current_in_stock: Optional[bool] = None
    proposed_in_stock: Optional[bool] = None
    scraped_title: Optional[str] = Field(None, max_length=500)
    observer_source: Optional[str] = "consumer"
    # When True, allow proposed_price beyond ±75% of current_price (consumer
    # confirmed a large correction after an in-popup warning).
    confirm_large_price_change: bool = False


class DeleteObservationsBody(BaseModel):
    """Consumer's 'forget me' request: delete every observation + proposal
    they've ever submitted, identified by their per-install observer_id."""
    observer_id: str = Field(..., min_length=1, max_length=128)


class RequestRetailerBody(BaseModel):
    """Consumer's 'please add this retailer' request when they land on an
    unknown hostname. observer_id lets us notify them via chrome.notifications
    when the operator brings the retailer online."""
    url: str = Field(..., min_length=1, max_length=2048)
    observer_id: str = Field(..., min_length=1, max_length=128)


# ── Helpers ────────────────────────────────────────────────────────────

def _resolve_retailer_key(url: str) -> Optional[str]:
    """Map a URL host to a known retailer_key using the extension's cache."""
    try:
        from app.extension_endpoints import _cache_state, _refresh_cache  # type: ignore
        from app.cid_matcher import hostname_to_retailer_key  # type: ignore
    except Exception:
        return None
    try:
        _refresh_cache()
        host = (urlparse(url).hostname or "").lower()
        return hostname_to_retailer_key(host, _cache_state.get("retailers", {}))
    except Exception:
        return None


_CID_QTY_RE = re.compile(r"^(?:BOX|PACK)(\d+)$")


def _cid_box_qty(cid: str) -> Optional[int]:
    """Extract the box_qty encoded in a CID's last segment.

    CIDs end in BOX{N} / PACK{N} / SINGLE. Returns the integer, or None
    if the segment is malformed.
    """
    try:
        last = cid.rsplit("|", 1)[-1].upper()
    except Exception:
        return None
    m = _CID_QTY_RE.match(last)
    if m:
        return int(m.group(1))
    if last == "SINGLE":
        return 1
    return None


def _resolve_cigar_id_from_url(
    url: str,
    retailer_key: Optional[str],
    observed_box_qty: Optional[int] = None,
    preferred_cid: Optional[str] = None,
) -> Optional[str]:
    """If the URL is already in the live retailer CSV, return its CID — but
    REFUSE to attach the CID when the observation's box_qty contradicts the
    CID's box_qty.

    Without this guard, a Shopify product page that hosts both a Box-of-25
    SKU and a Pack-of-5 SKU under one canonical URL would have BOTH
    variants' observations stamped with the Box CID. The Pack-of-5
    observation would then say "$70 for cigar_id=...BOX25" which is
    nonsensical price history.

    When observed_box_qty is None (heuristics didn't detect it), we still
    attach the CID — that's the conservative default since most product
    URLs map to one SKU and most observations are valid for that SKU.
    """
    if not retailer_key:
        return None
    try:
        from app.extension_endpoints import _cache_state  # type: ignore
        live = _cache_state.get("url_index", {}).get(url)
        if not live:
            return None
        rk, cids = url_index_entry_cids(live)
        if rk != retailer_key or not cids:
            return None
        cid = preferred_cid if preferred_cid and preferred_cid in cids else cids[0]
        if observed_box_qty is not None:
            cid_qty = _cid_box_qty(cid)
            if cid_qty is not None and cid_qty != observed_box_qty:
                return None
        return cid
    except Exception:
        return None


def _coerce_quantity_type(raw: Optional[str], box_qty: Optional[int]) -> str:
    if raw and raw.lower() in _VALID_QTY_TYPES:
        return raw.lower()
    if box_qty and box_qty >= 10:
        return "box"
    if box_qty == 5:
        return "pack5"
    if box_qty == 1:
        return "single"
    return "unknown"


def _to_price_cents(price: Optional[float]) -> Optional[int]:
    if price is None:
        return None
    try:
        cents = int(round(float(price) * 100))
        return cents if 0 < cents < 10_000_000 else None
    except (TypeError, ValueError):
        return None


# ── POST /api/community/observe ────────────────────────────────────────

@router.post("/observe")
async def observe(request: Request, body: ObserveBody):
    """Record a per-URL price observation.

    Anonymous; rate-limited per observer_id. Server-side resolves
    retailer_key from the URL hostname and (if already mapped) the
    cigar_id from the live url_index. Returns a small ack payload so
    the client can show "contributing" UX.
    """
    observer = _observer_id(body.observer_id, request)
    if not _rate_limit(_obs_minute, observer, 60, _OBSERVE_MAX_PER_MIN):
        return JSONResponse({"error": "rate_limited", "scope": "per_minute"}, status_code=429)
    if not _rate_limit(_obs_day, observer, 86_400, _OBSERVE_MAX_PER_DAY):
        return JSONResponse({"error": "rate_limited", "scope": "per_day"}, status_code=429)

    # Canonicalize at the boundary so we never write a ?variant=… URL to
    # observed_prices and so cigar_id resolution against the (already
    # canonical) url_index hits.
    body.url = canonicalize_url(body.url)

    retailer_key = _resolve_retailer_key(body.url)
    cigar_id = _resolve_cigar_id_from_url(
        body.url, retailer_key, body.box_qty, _trim(body.cigar_id) or None,
    )
    qty_type = _coerce_quantity_type(body.quantity_type, body.box_qty)
    price_cents = _to_price_cents(body.price)
    source = (body.observer_source or "consumer").lower()
    if source not in {"operator", "consumer"}:
        source = "consumer"
    currency = (body.currency or "USD")[:8].upper()

    try:
        conn = _get_conn()
        cur = conn.cursor()

        stock_to_write = body.in_stock
        if (
            stock_to_write is False
            and cigar_id
            and retailer_key
            and source == "consumer"
        ):
            # Shopper may report in-stock via report-correction while the PDP
            # scrape still reads OOS. A subsequent passive /observe must not
            # overwrite that with another false from the same stale scrape.
            try:
                cur.execute(
                    """
                    SELECT 1 FROM observed_prices
                     WHERE url = %s
                       AND retailer_key = %s
                       AND cigar_id = %s
                       AND in_stock IS TRUE
                       AND observer_source = %s
                       AND observed_at > NOW() - INTERVAL '7 days'
                     LIMIT 1
                    """,
                    (body.url, retailer_key, cigar_id, _CORRECTION_OBSERVER_SOURCE),
                )
                if cur.fetchone():
                    stock_to_write = None
            except Exception:
                pass

        cur.execute("""
            INSERT INTO observed_prices
              (url, retailer_key, cigar_id, quantity_type, box_qty,
               price_cents, currency, in_stock, scraped_title, jsonld,
               observer_id, observer_source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
            RETURNING id
        """, (
            body.url, retailer_key, cigar_id, qty_type, body.box_qty,
            price_cents, currency, stock_to_write, body.scraped_title,
            _safe_jsonb(body.jsonld), observer, source,
        ))
        row = cur.fetchone()
        conn.commit()
        conn.close()
        return {
            "ok": True,
            "id": row[0] if row else None,
            "retailer_key": retailer_key,
            "cigar_id": cigar_id,
            "quantity_type": qty_type,
            "counted": qty_type == "box" and cigar_id is not None,
        }
    except Exception as e:
        logger.exception("observe failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── POST /api/community/propose-metadata ───────────────────────────────


def _proposal_needs_new_catalog_work(body: "ProposeMetadataBody") -> bool:
    """True when (brand, line) is not an exact pair present in master_cigars.

    Used to flag proposals where the consumer typed a custom line (or an
    unknown brand): the operator path is then "add full master row + CID
    first, then map this URL" rather than a quick pick from Similar CIDs.
    """
    brand = (_trim(body.brand) or "").strip()
    line = (_trim(body.line) or "").strip()
    if not brand or not line:
        return False
    try:
        cat = _get_catalog_match_index()
    except Exception:
        return False
    brands_sorted = cat.get("brands_sorted") or []
    if brand not in brands_sorted:
        return True
    lines = (cat.get("lines_by_brand") or {}).get(brand) or []
    return line not in lines


@router.post("/propose-metadata")
async def propose_metadata(request: Request, body: ProposeMetadataBody):
    """Consumer-submitted metadata proposal for a URL that has no CID yet.

    Goes into community_url_proposals with status='pending'. The operator
    reviews each proposal via the admin UI and maps it to an existing
    master cigar_id (stage-approval). When ``needs_new_catalog_cid`` is set,
    the consumer's brand/line pair is not in master yet — add the full CSV
    row + CID to master first, then approve with that exact key.
    """
    observer = _observer_id(body.observer_id, request)
    if not _rate_limit(_prop_hour, observer, 3600, _PROPOSE_MAX_PER_HOUR):
        return JSONResponse({"error": "rate_limited", "scope": "per_hour"}, status_code=429)

    body.url = canonicalize_url(body.url)
    retailer_key = _resolve_retailer_key(body.url)
    source = (body.observer_source or "consumer").lower()
    if source not in {"operator", "consumer"}:
        source = "consumer"

    needs_new_catalog_cid = _proposal_needs_new_catalog_work(body)

    confirmed_cents = _to_price_cents(body.confirmed_price)
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO community_url_proposals
              (url, retailer_key, proposed_brand, proposed_line, proposed_vitola,
               proposed_size, proposed_wrapper, proposed_box_qty,
               confirmed_price_cents,
               scraped_title, observer_id, observer_source, status,
               needs_new_catalog_cid)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)
            RETURNING id
        """, (
            body.url, retailer_key, _trim(body.brand), _trim(body.line),
            _trim(body.vitola), _trim(body.size), _trim(body.wrapper),
            body.box_qty, confirmed_cents,
            _trim(body.scraped_title), observer, source,
            needs_new_catalog_cid,
        ))
        proposal_id = cur.fetchone()[0]
        conn.commit()
        conn.close()

        # Gap 2: hybrid instant-feedback. Try to auto-match the consumer's
        # submission against the master catalog. ONLY when we get a HIGH-
        # confidence match (box_qty exact + wrapper-bucket compatible) do
        # we attach a CID and return a comparison card. Anything less
        # falls back to the standard "pending review" UX so we never
        # surface a confidently-wrong comparison.
        comparison = None
        match_info = _try_match_proposal_to_cid(body)
        if match_info:
            matched_cid = match_info["cigar_id"]
            try:
                comparison = _build_comparison_for_cid(matched_cid, zip="", limit=3)
            except Exception as e:
                logger.warning(
                    "comparison build failed for auto-matched cid=%s: %s",
                    matched_cid, e,
                )
                comparison = None
            # Only return the comparison when we have ≥ 2 retailers
            # (consistent with the website's MIN_RETAILERS_FOR_COMPARISON
            # rule — a comparison of one isn't a comparison).
            if comparison and not comparison.get("results"):
                comparison = None

        response: Dict[str, Any] = {
            "ok": True,
            "proposal_id": proposal_id,
            "retailer_key": retailer_key,
            "status": "pending",
            "needs_new_catalog_cid": needs_new_catalog_cid,
            # Always include the comparison key so the consumer popup
            # can branch on truthiness without "key exists" checks.
            "comparison": comparison,
            "match": (
                {
                    "cigar_id": match_info["cigar_id"],
                    "confidence": match_info["confidence"],
                    "source": match_info["source"],
                }
                if match_info else None
            ),
        }
        return response
    except Exception as e:
        logger.exception("propose_metadata failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── POST /api/community/preview-candidate ──────────────────────────────
#
# The "Is this the cigar?" confirmation flow.
#
# Why this exists: when a consumer lands on an unmonitored URL and fills
# out the metadata form (brand / line / vitola / wrapper / box qty /
# price), most of the time the master catalog already has a CID that
# fits — we just need them to confirm. Old flow: submit -> 24h+ wait for
# the operator to review every single proposal. New flow:
#
#   1. Consumer fills the form, hits "Submit".
#   2. Client calls /preview-candidate. Server runs the same HIGH-
#      confidence matcher used elsewhere AND, if it finds a match, builds
#      a human-readable label (no pipes, no duplicated parts, no codes).
#   3. Consumer sees "Is this the cigar? Punch Knuckle Buster Gordo •
#      6x60 • Habano (Nicaraguan) • Box of 20"  [Yes] [No, not quite].
#   4a. YES  -> /confirm-candidate auto-publishes the URL->CID mapping
#       to extension_staged_approvals with source='consumer_auto'. Live
#       overlay picks it up immediately so the consumer ALSO sees the
#       comparison card in the same popup session. Operator sees these
#       in a daily spot-check report (GET /api/admin/auto-publish-report)
#       so a wrong auto-match can be reversed.
#   4b. NO   -> /propose-metadata (existing) puts it in
#       community_url_proposals for operator review. The operator may
#       need to create a brand-new CID.
#   4c. No candidate at all -> /propose-metadata as before.


def _build_candidate_display_label(
    cigar_id: str,
    master_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Render a CID as a reader-friendly "Is this the cigar?" preview.

    Returns a dict with the individual fields plus a single ``label``
    string the popup can drop directly into the confirmation card:

        "Punch Knuckle Buster Gordo • 6x60 • Habano (Nicaraguan) • Box of 20"

    Why this lives here (and not in the matcher): the matcher returns
    only the raw canon wrapper. To present the cigar the way the main
    site does — alias-first with the canonical name in parens — we need
    load_master_index which carries both wrapper_alias and wrapper_canon.
    """
    if not cigar_id:
        return None
    if master_index is None:
        try:
            from app.main import load_master_index  # type: ignore
            master_index = load_master_index()
        except Exception:
            return None
    row = master_index.get(cigar_id)
    if not row:
        return None

    brand = (row.get("brand") or "").strip()
    line = (row.get("line") or "").strip()
    vitola = (row.get("vitola") or "").strip()
    size = (row.get("size") or "").strip()
    box_qty = row.get("box_qty")
    wrapper_alias = (row.get("wrapper_alias") or "").strip()
    wrapper_canon = (row.get("wrapper_canon") or "").strip()

    # alias-first display, matching the main-page dropdown convention:
    # "Habano (Nicaraguan)" reads better than "Nicaraguan (Habano)"
    # when alias is the band-printed term. Falls back gracefully when
    # only one of the two is populated.
    if wrapper_alias and wrapper_canon and wrapper_alias.lower() != wrapper_canon.lower():
        wrapper_display = f"{wrapper_alias} ({wrapper_canon})"
    else:
        wrapper_display = wrapper_alias or wrapper_canon or ""

    parts: list[str] = []
    head = " ".join(p for p in (brand, line, vitola) if p)
    if head:
        parts.append(head)
    if size:
        parts.append(size)
    if wrapper_display:
        parts.append(wrapper_display)
    if box_qty:
        try:
            parts.append(f"Box of {int(box_qty)}")
        except (TypeError, ValueError):
            pass
    label = " • ".join(parts)

    return {
        "cigar_id": cigar_id,
        "label": label,
        "brand": brand,
        "line": line,
        "vitola": vitola,
        "size": size,
        "wrapper_display": wrapper_display,
        "box_qty": int(box_qty) if box_qty else None,
    }


@router.post("/preview-candidate")
async def preview_candidate(request: Request, body: ProposeMetadataBody):
    """Step 1 of the "Is this the cigar?" flow.

    Reuses the propose-metadata payload and the existing HIGH-confidence
    matcher. Returns a candidate (if any) wrapped with a human-readable
    label. Does NOT write anything — that's deliberate so the user can
    back out cleanly if the candidate is wrong.
    """
    observer = _observer_id(body.observer_id, request)
    # Reuses the propose-metadata bucket: this endpoint is one of two
    # required hops in the submit flow, so it should share the cap.
    if not _rate_limit(_prop_hour, observer, 3600, _PROPOSE_MAX_PER_HOUR):
        return JSONResponse({"error": "rate_limited", "scope": "per_hour"}, status_code=429)

    body.url = canonicalize_url(body.url)
    retailer_key = _resolve_retailer_key(body.url)

    try:
        match_info = _try_match_proposal_to_cid(body)
    except Exception as e:
        logger.exception("preview_candidate match failed: %s", e)
        match_info = None

    candidate = None
    if match_info:
        candidate = _build_candidate_display_label(match_info["cigar_id"])
        if candidate:
            candidate["confidence"] = match_info.get("confidence")
            candidate["score"] = match_info.get("score")

    return {
        "ok": True,
        "retailer_key": retailer_key,
        "candidate": candidate,  # None -> client falls through to review-queue submit
    }


# ── POST /api/community/confirm-candidate ──────────────────────────────


class ConfirmCandidateBody(BaseModel):
    """Consumer says "Yes, that's the cigar" against a preview-candidate result.

    We trust the candidate cigar_id ONLY when (a) it parses and (b) it
    exists in master_cigars — both checked server-side. The auto-publish
    path bypasses operator review on purpose; the operator backstop is
    the daily auto-publish report.
    """
    url: str = Field(..., min_length=1, max_length=2048)
    cigar_id: str = Field(..., min_length=1, max_length=200)
    observer_id: Optional[str] = None
    observer_source: Optional[str] = "consumer"
    # Scraped context (kept on the staged row for the audit trail; not
    # used to overwrite the retailer CSV during the daily drain).
    scraped_title: Optional[str] = Field(None, max_length=500)
    confirmed_price: Optional[float] = None
    in_stock: Optional[bool] = None


@router.post("/confirm-candidate")
async def confirm_candidate(request: Request, body: ConfirmCandidateBody):
    """Step 2 (YES path) of the "Is this the cigar?" flow.

    Inserts a staged-approval row with source='consumer_auto' and flips
    the in-memory URL index so the same popup session can render the
    comparison card immediately. Same idempotency guarantees as the
    operator approval path (UNIQUE on retailer_key, url, cid).
    """
    observer = _observer_id(body.observer_id, request)
    if not _rate_limit(_prop_hour, observer, 3600, _PROPOSE_MAX_PER_HOUR):
        return JSONResponse({"error": "rate_limited", "scope": "per_hour"}, status_code=429)

    body.url = canonicalize_url(body.url)
    retailer_key = _resolve_retailer_key(body.url)
    if not retailer_key:
        return JSONResponse(
            {"error": "unknown_retailer",
             "detail": "URL host is not in the active retailer registry."},
            status_code=400,
        )

    # The candidate cigar_id MUST already exist in master_cigars — this
    # whole flow only fires after a HIGH-confidence match against the
    # master catalog. Defensive recheck here so a malicious client can't
    # auto-publish an arbitrary CID.
    try:
        from app.main import load_master_index  # type: ignore
        master_index = load_master_index()
    except Exception as e:
        logger.exception("confirm_candidate: load_master_index failed: %s", e)
        return JSONResponse({"error": "master_unavailable"}, status_code=503)

    master_row = master_index.get(body.cigar_id)
    if not master_row:
        return JSONResponse(
            {"error": "unknown_cigar_id",
             "detail": "Candidate CID is not in master_cigars."},
            status_code=400,
        )

    # Parse the CID so we can populate the descriptive columns alongside
    # the master JOIN — keeps the staged row self-describing for the
    # daily report and for the publisher's CSV append.
    try:
        from app.cid_matcher import parse_cid  # type: ignore
        parts = parse_cid(body.cigar_id) or {}
    except Exception:
        parts = {}

    confirmed_cents = _to_price_cents(body.confirmed_price)
    confirmed_dollars = (
        round(confirmed_cents / 100.0, 2) if confirmed_cents is not None else None
    )

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO extension_staged_approvals
              (cid, retailer_key, url, is_new_cid,
               brand, parent_brand, line, vitola, vitola2, size,
               wrapper_code, wrapper, box_qty,
               title, price, in_stock, status, source)
            VALUES (%s,%s,%s,FALSE,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,
                    %s,%s,%s,'pending','consumer_auto')
            ON CONFLICT (retailer_key, url, cid) DO UPDATE
              SET title  = COALESCE(EXCLUDED.title,  extension_staged_approvals.title),
                  price  = COALESCE(EXCLUDED.price,  extension_staged_approvals.price),
                  in_stock = COALESCE(EXCLUDED.in_stock, extension_staged_approvals.in_stock),
                  -- Don't downgrade an operator-staged row to consumer_auto.
                  source = CASE
                    WHEN extension_staged_approvals.source = 'operator' THEN 'operator'
                    ELSE EXCLUDED.source
                  END,
                  status = CASE
                    WHEN extension_staged_approvals.status = 'published' THEN 'published'
                    ELSE 'pending'
                  END
            RETURNING id
            """,
            (
                body.cigar_id, retailer_key, body.url,
                master_row.get("brand"),
                parts.get("parent_brand") or master_row.get("brand"),
                master_row.get("line"),
                master_row.get("vitola"),
                parts.get("vitola2") or master_row.get("vitola"),
                master_row.get("size"),
                parts.get("wrapper_code"),
                master_row.get("wrapper"),
                master_row.get("box_qty"),
                _trim(body.scraped_title),
                confirmed_dollars,
                body.in_stock,
            ),
        )
        staged_id = cur.fetchone()[0]

        # If this confirmation resolves an earlier consumer proposal for
        # the same URL, mark it auto_resolved so the operator review
        # queue doesn't carry duplicates. (Mirrors what the operator
        # stage_approval handler does for body.community_proposal_id,
        # except we resolve every pending proposal for the URL.)
        cur.execute(
            """
            UPDATE community_url_proposals
               SET status='approved',
                   resolved_cid=%s,
                   reviewed_at=NOW()
             WHERE url=%s AND status='pending'
            """,
            (body.cigar_id, body.url),
        )
        resolved = cur.rowcount or 0

        conn.commit()
        conn.close()
    except Exception as e:
        logger.exception("confirm_candidate insert failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    # Live overlay: same trick as the operator stage_approval path — push
    # the mapping into the in-memory URL index so this popup session
    # immediately shows the comparison without waiting for the cache TTL.
    try:
        from app.extension_endpoints import _cache_state  # type: ignore
        merge_cid_into_url_index(
            _cache_state["url_index"],
            body.url,
            retailer_key,
            body.cigar_id,
        )
    except Exception as e:
        logger.warning("confirm_candidate live overlay failed: %s", e)

    # Bust /compare cache so the next page render reflects the new mapping.
    try:
        from app.main import _product_cache  # type: ignore
        _product_cache["data"] = None
        _product_cache["timestamp"] = 0
    except Exception:
        pass

    # Build the comparison the popup can render right away. We use the
    # same builder as propose-metadata's auto-match path so the consumer
    # sees identical UI regardless of which branch they came through.
    comparison = None
    try:
        comparison = _build_comparison_for_cid(body.cigar_id, zip="", limit=3)
        if comparison and not comparison.get("results"):
            comparison = None
    except Exception as e:
        logger.warning(
            "confirm_candidate: comparison build for cid=%s failed: %s",
            body.cigar_id, e,
        )

    return {
        "ok": True,
        "staged_id": staged_id,
        "cigar_id": body.cigar_id,
        "retailer_key": retailer_key,
        "resolved_proposal_count": resolved,
        "comparison": comparison,
    }


# ── POST /api/community/report-correction ──────────────────────────────

# "Loose" guardrails for the report-incorrect flow. Picked deliberately
# wide so we accept legit clearance prices and seasonal sales, but
# narrow enough to block obvious typos ($140 → $14) and bot mischief.
# Same-SKU volatile tweaks (≤10% price and/or stock) skip the queue;
# larger edits and metadata mismatches still go to operator review.
_REPORT_PRICE_MIN_CENTS = 500           # $5 — below this is almost certainly a typo
_REPORT_PRICE_MAX_CENTS = 500_000       # $5,000 — most expensive boxes top out well below this
_REPORT_PRICE_MAX_DEVIATION = 0.75      # ±75% of the price we were showing
# Corrections that only nudge price/stock on the *same* SKU (CID tokens match)
# apply immediately via observed_prices + merge — no operator queue.
_AUTO_APPLY_PRICE_MAX_DEVIATION = 0.10  # ±10% vs the price we were showing
_VALID_BOX_QTYS = {1, 5, 10, 15, 20, 24, 25, 50}


def _cid_slug_key(s: Optional[str]) -> str:
    """Collapse to lowercase alphanumerics for brand/line/vitola token compare."""
    if not s:
        return ""
    t = unicodedata.normalize("NFKD", str(s).strip().lower())
    t = t.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", t)


def _wrapper_bucket_matches_cid_code(bucket: Optional[str], cid_code: str) -> bool:
    """True when consumer bucket is empty/unknown, or it allows the CID's code."""
    if not bucket or not str(bucket).strip():
        return True
    try:
        from app.wrapper_buckets import codes_for_bucket  # type: ignore

        allowed = codes_for_bucket(bucket.strip())
        if not allowed:
            return True
        c = (cid_code or "").strip().upper()
        return c in {a.upper() for a in allowed}
    except Exception:
        return True


def _volatile_correction_auto_applies(
    body: ReportCorrectionBody,
    proposed_price_cents: Optional[int],
    current_price_cents: Optional[int],
) -> bool:
    """Same-SKU tweaks (stock and/or ≤10% price) trust the shopper — skip queue."""
    try:
        from app.cid_matcher import parse_cid  # type: ignore
    except Exception:
        return False

    cid_raw = _trim(body.current_cid) or ""
    parsed = parse_cid(cid_raw)
    if not parsed:
        return False

    if body.proposed_box_qty is not None:
        cbox = _cid_box_qty(cid_raw)
        if cbox is not None and int(body.proposed_box_qty) != int(cbox):
            return False

    if _cid_slug_key(body.proposed_brand) != _cid_slug_key(parsed.get("brand") or ""):
        return False
    if _cid_slug_key(body.proposed_line) != _cid_slug_key(parsed.get("line") or ""):
        return False
    pv = _cid_slug_key(body.proposed_vitola or "")
    if pv not in {
        _cid_slug_key(parsed.get("vitola") or ""),
        _cid_slug_key(parsed.get("vitola2") or ""),
    }:
        return False

    if not _wrapper_bucket_matches_cid_code(
        body.proposed_wrapper, parsed.get("wrapper_code") or "",
    ):
        return False

    stock_changed = False
    if body.proposed_in_stock is not None:
        if body.current_in_stock is None:
            stock_changed = True
        else:
            stock_changed = body.proposed_in_stock != body.current_in_stock

    price_changed = False
    if proposed_price_cents is not None and current_price_cents is not None:
        if abs(proposed_price_cents - current_price_cents) > 5:
            price_changed = True

    if not stock_changed and not price_changed:
        return False

    if price_changed:
        if not current_price_cents or current_price_cents <= 0:
            return False
        dev = abs((proposed_price_cents or 0) - current_price_cents) / current_price_cents
        if dev > _AUTO_APPLY_PRICE_MAX_DEVIATION:
            return False

    obs_cents = proposed_price_cents or current_price_cents or 0
    if obs_cents <= 0:
        return False

    return True


# Tag for observed_prices rows written from report-correction (auto or queued).
# Passive /observe must not immediately overwrite these with a scrape that
# still says "out of stock" while the shopper explicitly reported in-stock.
_CORRECTION_OBSERVER_SOURCE = "consumer_correction"


def _append_correction_observation(
    cur,
    body: ReportCorrectionBody,
    retailer_key: str,
    observer: str,
    proposed_price_cents: Optional[int],
    current_price_cents: Optional[int],
) -> bool:
    """Mirror correction into observed_prices for blocked-retailer merge."""
    obs_cid = _trim(body.current_cid)
    obs_cents = proposed_price_cents or current_price_cents or 0
    instock = body.proposed_in_stock
    if instock is None:
        instock = body.current_in_stock
    if instock is None:
        instock = True
    if not (obs_cid and obs_cents > 0):
        return False
    bq_obs = body.proposed_box_qty
    if bq_obs is None:
        bq_obs = _cid_box_qty(obs_cid)
    qty_type = _coerce_quantity_type("box", bq_obs)
    cur.execute(
        """
        INSERT INTO observed_prices
          (url, retailer_key, cigar_id, quantity_type, box_qty,
           price_cents, currency, in_stock, scraped_title, jsonld,
           observer_id, observer_source)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL::jsonb,%s,%s)
        """,
        (
            body.url,
            retailer_key,
            obs_cid,
            qty_type,
            bq_obs,
            obs_cents,
            "USD",
            instock,
            _trim(body.scraped_title),
            observer,
            _CORRECTION_OBSERVER_SOURCE,
        ),
    )
    return True


def _norm_for_compare(s: Optional[str]) -> str:
    """Lowercase + collapse whitespace for "is this field actually different"
    comparisons. We don't want to flag a casing-only or stray-space-only
    edit as a real correction."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip().lower()


@router.post("/report-correction")
async def report_correction(request: Request, body: ReportCorrectionBody):
    """Consumer-submitted correction for an already-matched URL.

    Validation pipeline (all server-side; client validation is a UX nicety):

      1. Rate-limit per observer (reuses propose-metadata bucket — same user
         shouldn't be machine-gunning either flow).
      2. At least one proposed field (including in-stock vs out-of-stock)
         must differ from current. If everything matches, return 200 with
         status='no_changes_detected' and DO NOT insert. (The popup renders
         this as "Thanks — no changes detected".)
      3. proposed_price must be in [$5, $5000] AND within ±75% of
         current_price (when current_price is provided).
      4. proposed_box_qty must be in {1, 5, 10, 15, 20, 24, 25, 50}.
      5. proposed_brand/line/vitola, when supplied, must be ≤ 80 chars.

    When the correction only adjusts **stock** and/or **price** on the same
    SKU encoded in ``current_cid`` (brand/line/vitola tokens + wrapper bucket
    match the CID) and any **price** move is within ±10% of ``current_price``,
    we **skip** ``community_url_proposals`` and write ``observed_prices``
    immediately (``status='applied_immediately'``) so /compare updates without
    operator review. Larger price swings or metadata disagreements still queue.
    """
    observer = _observer_id(body.observer_id, request)
    if not _rate_limit(_prop_hour, observer, 3600, _PROPOSE_MAX_PER_HOUR):
        return JSONResponse({"error": "rate_limited", "scope": "per_hour"}, status_code=429)

    body.url = canonicalize_url(body.url)
    retailer_key = _resolve_retailer_key(body.url)
    source = (body.observer_source or "consumer").lower()
    if source not in {"operator", "consumer"}:
        source = "consumer"

    proposed_price_cents = _to_price_cents(body.proposed_price)
    current_price_cents = _to_price_cents(body.current_price)

    # ── Field-level guards ──────────────────────────────────────────────
    if body.proposed_box_qty is not None and body.proposed_box_qty not in _VALID_BOX_QTYS:
        return JSONResponse(
            {"error": "invalid_box_qty",
             "reason": f"Box qty must be one of {sorted(_VALID_BOX_QTYS)}"},
            status_code=400,
        )
    for label, val in (
        ("brand", body.proposed_brand),
        ("line", body.proposed_line),
        ("vitola", body.proposed_vitola),
    ):
        if val and len(val) > 80:
            return JSONResponse(
                {"error": "invalid_text", "field": label,
                 "reason": f"{label} must be ≤ 80 characters"},
                status_code=400,
            )

    if proposed_price_cents is not None:
        if proposed_price_cents < _REPORT_PRICE_MIN_CENTS:
            return JSONResponse(
                {"error": "price_too_low",
                 "reason": (
                     f"Sale price must be at least "
                     f"${_REPORT_PRICE_MIN_CENTS / 100:.0f}. "
                     "If a coupon code was applied, enter the price BEFORE "
                     "the coupon — coupons are tracked separately."
                 )},
                status_code=400,
            )
        if proposed_price_cents > _REPORT_PRICE_MAX_CENTS:
            return JSONResponse(
                {"error": "price_too_high",
                 "reason": f"Sale price must be at most ${_REPORT_PRICE_MAX_CENTS / 100:.0f}."},
                status_code=400,
            )
        if current_price_cents and current_price_cents > 0:
            deviation = abs(proposed_price_cents - current_price_cents) / current_price_cents
            if (
                deviation > _REPORT_PRICE_MAX_DEVIATION
                and not body.confirm_large_price_change
            ):
                pct = int(deviation * 100)
                return JSONResponse(
                    {"error": "price_deviation_too_large",
                     "reason": (
                         f"Proposed price differs from the listed price "
                         f"by {pct}% (max {int(_REPORT_PRICE_MAX_DEVIATION * 100)}%). "
                         "If you're seeing a discount from a coupon code, "
                         "enter the price WITHOUT the coupon — coupons are "
                         "tracked separately. If the page truly shows this "
                         "price with no coupon, double-check the box quantity."
                     ),
                     "current_price_cents": current_price_cents,
                     "proposed_price_cents": proposed_price_cents},
                    status_code=400,
                )

    # ── No-op short-circuit ─────────────────────────────────────────────
    # Compare field-by-field against the supplied current values. When
    # nothing material has changed (price within $0.05, all text fields
    # equal modulo case/whitespace, box_qty matches), we return a 200
    # with status='no_changes_detected' and do NOT write a row. The popup
    # turns this into a "Thanks, no changes detected" message — no noise
    # for the operator queue.
    nothing_changed = True
    if proposed_price_cents is not None and current_price_cents is not None:
        if abs(proposed_price_cents - current_price_cents) > 5:
            nothing_changed = False
    elif proposed_price_cents is not None and current_price_cents is None:
        nothing_changed = False
    if body.proposed_box_qty is not None:
        # When current_cid carries a BOX{N} suffix, derive current box_qty
        # from it — the popup may not always send it back explicitly.
        current_box = _cid_box_qty(body.current_cid or "") if body.current_cid else None
        if current_box is not None and body.proposed_box_qty != current_box:
            nothing_changed = False
    stock_unchanged = True
    if body.current_in_stock is not None or body.proposed_in_stock is not None:
        stock_unchanged = body.proposed_in_stock == body.current_in_stock
        if not stock_unchanged:
            nothing_changed = False
    # Brand/line/vitola/wrapper: if the popup sent a value, it's the
    # consumer's "after" — we compare to whatever the popup submitted as
    # the current values would be (we don't have them server-side without
    # rebuilding the comparison). Trust the popup: if it sent a value
    # AND that value differs from the others, it means the user touched
    # the field. We can't perfectly check from the server, so we only
    # short-circuit when the price + box_qty are identical AND no
    # text fields were sent at all.
    text_fields_sent = any(
        bool(_norm_for_compare(v)) for v in (
            body.proposed_brand, body.proposed_line,
            body.proposed_vitola, body.proposed_wrapper,
        )
    )
    if nothing_changed and not text_fields_sent and stock_unchanged:
        return {
            "ok": True,
            "status": "no_changes_detected",
            "proposal_id": None,
        }

    auto_apply = _volatile_correction_auto_applies(
        body, proposed_price_cents, current_price_cents,
    )

    try:
        conn = _get_conn()
        cur = conn.cursor()
        if auto_apply:
            if _append_correction_observation(
                cur, body, retailer_key, observer,
                proposed_price_cents, current_price_cents,
            ):
                conn.commit()
                conn.close()
                try:
                    from app.main import _product_cache  # type: ignore

                    _product_cache["data"] = None
                    _product_cache["timestamp"] = 0
                except Exception:
                    pass
                return {
                    "ok": True,
                    "status": "applied_immediately",
                    "proposal_id": None,
                    "retailer_key": retailer_key,
                    "is_correction": True,
                }
            conn.rollback()

        cur.execute("""
            INSERT INTO community_url_proposals
              (url, retailer_key, proposed_brand, proposed_line, proposed_vitola,
               proposed_wrapper, proposed_box_qty,
               confirmed_price_cents, current_cid, current_price_cents,
               current_in_stock, proposed_in_stock,
               is_correction,
               scraped_title, observer_id, observer_source, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s,'pending')
            RETURNING id
        """, (
            body.url, retailer_key,
            _trim(body.proposed_brand), _trim(body.proposed_line),
            _trim(body.proposed_vitola), _trim(body.proposed_wrapper),
            body.proposed_box_qty, proposed_price_cents,
            _trim(body.current_cid), current_price_cents,
            body.current_in_stock, body.proposed_in_stock,
            _trim(body.scraped_title), observer, source,
        ))
        proposal_id = cur.fetchone()[0]
        _append_correction_observation(
            cur, body, retailer_key, observer,
            proposed_price_cents, current_price_cents,
        )
        conn.commit()
        conn.close()
        try:
            from app.main import _product_cache  # type: ignore

            _product_cache["data"] = None
            _product_cache["timestamp"] = 0
        except Exception:
            pass

        return {
            "ok": True,
            "proposal_id": proposal_id,
            "retailer_key": retailer_key,
            "status": "pending",
            "is_correction": True,
        }
    except Exception as e:
        logger.exception("report_correction failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Misc helpers ───────────────────────────────────────────────────────

def _trim(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s or None


def _safe_jsonb(d: Optional[Dict[str, Any]]) -> Optional[str]:
    """Serialize a small dict for ::jsonb cast. Cap size to keep rows lean."""
    if not d:
        return None
    try:
        import json
        s = json.dumps(d, default=str)[:16_000]
        return s
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════
# Public, no-auth API for the consumer Chrome extension.
#
# Three endpoints, all read-mostly:
#
#   GET  /api/public/retailer-registry
#       The list of hostnames the extension should activate on, plus the
#       canonical retailer_key for each. Public-safe subset of the admin
#       registry endpoint.
#
#   GET  /api/public/url-status?url=...&zip=...
#       Single round-trip the popup needs per page load. Returns:
#         - state: matched | candidate | seen | no_scraper | non_product
#         - retailer_key, hostname, canonical url
#         - matched_cid (when matched)
#         - comparison: top 3 cheapest retailers carrying that CID (when
#           matched and we have ≥ MIN_RETAILERS_FOR_COMPARISON listings)
#         - seen_status (when seen)
#
#   POST /api/community/delete-my-observations
#       GDPR-friendly "forget me": delete every observation + every
#       proposal authored by a given observer_id. Lives under /community
#       since it's a write but no admin auth needed (the observer_id
#       acts as the bearer token — only the user's own extension
#       remembers it).
# ═══════════════════════════════════════════════════════════════════════

public_router = APIRouter(prefix="/api/public", tags=["public"])


def _is_product_like_path(url: str) -> bool:
    """Backend mirror of consumer-extension/background.js looksLikeProductPage.

    Filters homepages, /collections, /cart, /search, /pages/, /blog/, etc.
    Belt-and-suspenders: the extension already filters, but a third-party
    client hitting our endpoint directly shouldn't be able to ask us to
    treat the homepage as a candidate cigar URL.
    """
    try:
        path = (urlparse(url).path or "/").lower()
    except Exception:
        return False
    if path in ("", "/"):
        return False
    BAD = (
        "/collections", "/categories", "/category",
        "/search", "/cart", "/checkout",
        "/account", "/login",
        "/pages/", "/blog/", "/blogs/", "/policy", "/policies/",
        "/sitemap", "/api/",
    )
    return not any(path.startswith(b) for b in BAD)


@public_router.get("/retailer-registry")
async def public_retailer_registry():
    """Hostnames the consumer extension should activate on.

    Public-safe subset of /api/admin/retailer-registry — no prices, no
    URLs, no admin info. Just (hostname, retailer_key) pairs so the
    extension can decide where to inject its content script.
    """
    try:
        from app.extension_endpoints import _cache_state, _refresh_cache  # type: ignore
        _refresh_cache()
        retailers = _cache_state.get("retailers", {})
        return {
            "retailers": [
                {"hostname": host, "retailer_key": key}
                for host, key in sorted(retailers.items())
            ],
            "total": len(retailers),
        }
    except Exception as e:
        logger.exception("public_retailer_registry failed: %s", e)
        return JSONResponse({"error": "internal"}, status_code=500)


# Per-IP read throttle. The url-status endpoint is the popup's main hit,
# so we keep it generous (60/min, 10k/day per IP) but capped so a runaway
# client can't hammer it.
_PUBLIC_STATUS_MAX_PER_MIN = 60
_PUBLIC_STATUS_MAX_PER_DAY = 10_000
_status_minute: Dict[str, Deque[float]] = defaultdict(deque)
_status_day:    Dict[str, Deque[float]] = defaultdict(deque)

# /api/public/guess-metadata is even cheaper than url-status (read-only,
# cached in-memory) so we let it run a little hotter — covers the case
# where a user is rapidly typing into brand/line fields and the form
# refetches per-keystroke. Still capped to keep a runaway client honest.
_PUBLIC_GUESS_MAX_PER_MIN = 120
_PUBLIC_GUESS_MAX_PER_DAY = 20_000
_guess_minute: Dict[str, Deque[float]] = defaultdict(deque)
_guess_day:    Dict[str, Deque[float]] = defaultdict(deque)


def _public_ip_key(request: Request) -> str:
    try:
        return (request.client.host if request.client else "unknown")
    except Exception:
        return "unknown"


@public_router.get("/url-status")
async def public_url_status(
    request: Request,
    url: str,
    zip: str = "",
    cid: str = "",
):
    """Single-call popup state.

    Mirrors /api/admin/url-status but without admin auth, and adds an
    inline comparison block when state='matched' so the popup can render
    top-3 cheapest in one round-trip.
    """
    ip = _public_ip_key(request)
    if not _rate_limit(_status_minute, ip, 60, _PUBLIC_STATUS_MAX_PER_MIN):
        return JSONResponse({"error": "rate_limited", "scope": "per_minute"}, status_code=429)
    if not _rate_limit(_status_day, ip, 86_400, _PUBLIC_STATUS_MAX_PER_DAY):
        return JSONResponse({"error": "rate_limited", "scope": "per_day"}, status_code=429)

    if not url or len(url) > 2048:
        return JSONResponse({"error": "invalid_url"}, status_code=400)

    url = canonicalize_url(url)
    retailer_key = _resolve_retailer_key(url)
    if not retailer_key:
        return {
            "state": "no_scraper",
            "url": url,
            "hostname": (urlparse(url).hostname or "").lower(),
        }

    if not _is_product_like_path(url):
        return {
            "state": "non_product",
            "url": url,
            "retailer_key": retailer_key,
        }

    # Live retailer CSV hit (may list multiple CIDs for one PDP).
    matched_cid: Optional[str] = None
    cigar_options: Optional[List[Dict[str, str]]] = None
    try:
        from app.extension_endpoints import _cache_state, _pick_matched_cid  # type: ignore

        live = _cache_state.get("url_index", {}).get(url)
        rk_live, cids_live = url_index_entry_cids(live)
        if rk_live == retailer_key and cids_live:
            matched_cid = _pick_matched_cid(cids_live, (cid or "").strip() or None)
            if len(cids_live) > 1:
                cigar_options = []
                for c in dedupe_cid_list_preserve_order(cids_live):
                    disp = _build_candidate_display_label(c)
                    lab = disp["label"] if disp else c
                    cigar_options.append({"cigar_id": c, "label": lab})
    except Exception:
        matched_cid = None
        cigar_options = None

    # Has the operator already touched this URL via the extension?
    # When the URL has a pending community_url_proposal, also surface
    # the proposed brand/line/vitola/box_qty/wrapper so the popup can
    # build a "Search prices on cigarpricescout.com" CTA — avoids the
    # dead-end "check back soon" UX where users contribute but get
    # nothing back.
    seen_status: Optional[str] = None
    proposed_metadata: Optional[Dict[str, Any]] = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM extension_staged_approvals "
            "WHERE url=%s AND retailer_key=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (url, retailer_key),
        )
        row = cur.fetchone()
        if row:
            # Prefix with `extension_` so the consumer popup can
            # distinguish "operator already approved this, waiting for
            # the publisher to drain it to CSV" (extension_pending /
            # extension_published) from "consumer suggested it, no
            # operator review yet" (community_pending). Without the
            # prefix the popup saw bare "pending" and incorrectly
            # rendered "Under review" even though the operator had
            # already approved.
            seen_status = f"extension_{row[0]}"
        if seen_status is None:
            cur.execute(
                "SELECT status, proposed_brand, proposed_line, proposed_vitola, "
                "       proposed_box_qty, proposed_wrapper, needs_new_catalog_cid "
                "FROM community_url_proposals "
                "WHERE url=%s ORDER BY created_at DESC LIMIT 1",
                (url,),
            )
            row = cur.fetchone()
            if row:
                seen_status = f"community_{row[0]}"
                # Only set metadata when we have at least brand+line — a
                # search URL with only a vitola is useless.
                if row[1] and row[2]:
                    proposed_metadata = {
                        "brand":   row[1],
                        "line":    row[2],
                        "vitola":  row[3] or None,
                        "box_qty": row[4] or None,
                        "wrapper": row[5] or None,  # bucket name
                        "needs_new_catalog_cid": bool(row[6]),
                    }
        conn.close()
    except Exception as e:
        logger.warning("public_url_status seen lookup failed: %s", e)

    if matched_cid:
        comparison = _build_comparison_for_cid(
            matched_cid,
            zip=zip,
            limit=3,
            focus_retailer_key=retailer_key,
            focus_url=url,
        )
        return {
            "state": "matched",
            "url": url,
            "retailer_key": retailer_key,
            "matched_cid": matched_cid,
            "cigar_options": cigar_options,
            "seen_status": seen_status,
            "comparison": comparison,
        }

    if seen_status:
        return {
            "state": "seen",
            "url": url,
            "retailer_key": retailer_key,
            "seen_status": seen_status,
            "proposed_metadata": proposed_metadata,
        }

    return {
        "state": "candidate",
        "url": url,
        "retailer_key": retailer_key,
    }


def _try_match_proposal_to_cid(
    body: "ProposeMetadataBody",
) -> Optional[Dict[str, Any]]:
    """Best-effort server-side CID match for a consumer proposal.

    Primary path: **unique master-row match** on the same fields we ask the
    user for (brand, line, vitola, box quantity, optional wrapper bucket).
    That lines up with ``master_cigars.csv``: when those fields identify
    exactly one row, that row's ``cigar_id`` is the recommendation.

    Fallback: URL + synthetic title scoring via ``find_top_candidates``,
    same as the operator extension, when metadata alone is ambiguous.

    Returns a dict with cid/score/confidence/wrapper_code/box_qty, or None
    so callers fall back to the standard "in review" UX.
    """
    if not (body.brand and body.line):
        return None
    if body.box_qty is None or int(body.box_qty) <= 0:
        return None

    # Reuse the operator extension's hot in-memory master cache when
    # possible (it's refreshed every 60s anyway) so we don't re-parse the
    # 2300-row CSV on every proposal. Fall back to a one-shot load if the
    # cache hasn't been populated yet (cold-start case).
    master = None
    try:
        from app.extension_endpoints import _cache_state, _refresh_cache  # type: ignore
        _refresh_cache(force=False)
        master = _cache_state.get("master") or None
    except Exception:
        master = None
    if not master:
        try:
            from app.cid_matcher import load_master_cigars  # type: ignore
            from pathlib import Path  # type: ignore
            here = Path(__file__).resolve().parents[1]
            master = load_master_cigars(here / "data" / "master_cigars.csv")
        except Exception as e:
            logger.warning("master catalog unavailable for proposal match: %s", e)
            return None

    try:
        from app.cid_matcher import (  # type: ignore
            find_top_candidates,
            find_unique_metadata_match,
        )
    except Exception as e:
        logger.warning("cid_matcher unavailable: %s", e)
        return None

    if body.vitola and str(body.vitola).strip():
        unique = find_unique_metadata_match(
            body.brand,
            body.line,
            body.vitola,
            int(body.box_qty),
            body.wrapper,
            master,
        )
        if unique:
            return {
                "cigar_id": unique["cigar_id"],
                "score": unique.get("score"),
                "confidence": unique.get("confidence"),
                "wrapper_code": unique.get("wrapper_code"),
                "box_qty": unique.get("box_qty"),
                "source": "metadata_unique_match",
            }

    # Synthesize a title from the proposal so the matcher has both the
    # URL (for hostname / slug hints) and a strong text signal.
    synth_title = " ".join(
        p for p in (body.brand, body.line, body.vitola, body.size) if p
    )

    try:
        cands = find_top_candidates(body.url or "", synth_title, master, limit=10)
    except Exception as e:
        logger.warning("find_top_candidates errored: %s", e)
        return None
    if not cands:
        return None

    # Optional wrapper-bucket filter. When the consumer picked a bucket
    # we restrict acceptable canonical wrapper_codes so we never auto-
    # match a CID with a wrapper the consumer disagreed with.
    allowed_codes: Optional[set] = None
    if body.wrapper:
        try:
            from app.wrapper_buckets import codes_for_bucket  # type: ignore
            ac = codes_for_bucket(body.wrapper)
            if ac:
                allowed_codes = ac
        except Exception:
            allowed_codes = None

    # Iterate the top candidates (not just [0]) — the matcher can tie
    # multiple CIDs at HIGH confidence when only box_qty or wrapper_code
    # differ, and we want to find the FIRST candidate that fully matches
    # the consumer's box_qty and bucket. This handles cases like Padron
    # 1964 Diplomatico where the catalog has both BOX10 and BOX25 CIDs
    # at the same score; the helper picks whichever one the consumer
    # actually proposed.
    target_box_qty = int(body.box_qty)
    for cand in cands:
        if (cand.get("confidence") or "").upper() != "HIGH":
            continue
        try:
            if int(cand.get("box_qty") or 0) != target_box_qty:
                continue
        except (TypeError, ValueError):
            continue
        if allowed_codes is not None:
            cand_code = (cand.get("wrapper_code") or "").upper()
            if cand_code and cand_code not in allowed_codes:
                continue
        return {
            "cigar_id": cand["cigar_id"],
            "score": cand.get("score"),
            "confidence": cand.get("confidence"),
            "wrapper_code": cand.get("wrapper_code"),
            "box_qty": cand.get("box_qty"),
            "source": "auto_match_high_confidence",
        }
    return None


def _build_comparison_for_cid(
    cid: str,
    zip: str = "",
    limit: int = 3,
    focus_retailer_key: Optional[str] = None,
    focus_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Top-N cheapest retailers for one canonical ``cigar_id``.

    Loads the same ``Product`` list as the site (``load_all_products()``) and
    uses the same shipping/tax helpers. **Rows are included only when**
    ``canonical_cigar_id_for_comparison(product.cigar_id)`` equals the
    canonical CID for the URL — no looser brand/line/vitola matching here.

    When ``focus_retailer_key`` / ``focus_url`` are set (the consumer popup
    passes the active tab), the response includes ``this_listing``: our row
    for that retailer (URL match when possible) even if it is not among
    the top-N cheapest rows.
    """
    try:
        from app.main import (  # type: ignore
            load_all_products,
            zip_to_state,
            estimate_shipping_cents,
            estimate_tax_cents,
            RETAILERS,
            MIN_RETAILERS_FOR_COMPARISON,
        )
    except Exception as e:
        logger.warning("comparison helpers unavailable: %s", e)
        return None

    try:
        state = zip_to_state(zip) if zip else "OR"
        all_products = load_all_products()
        canon_cid = canonical_cigar_id_for_comparison(cid)
        matches = [
            p for p in all_products
            if canonical_cigar_id_for_comparison(getattr(p, "cigar_id", None) or "")
            == canon_cid
        ]
        distinct_retailers = {p.retailer_key for p in matches}
        if len(distinct_retailers) < MIN_RETAILERS_FOR_COMPARISON:
            sparse: Dict[str, Any] = {
                "cigar_id": canon_cid,
                "results": [],
                "reason": (
                    f"Only {len(distinct_retailers)} retailer(s) carry this cigar. "
                    f"At least {MIN_RETAILERS_FOR_COMPARISON} are needed."
                ),
            }
            if matches:
                fp = matches[0]
                sparse.update({
                    "cigar_name": f"{fp.brand} {fp.line}".strip(),
                    "brand": fp.brand,
                    "line": fp.line,
                    "wrapper": fp.wrapper,
                    "vitola": fp.vitola,
                    "size": fp.size,
                    "box_qty": fp.box_qty,
                    "strength": getattr(fp, "strength", "") or "",
                    "country": getattr(fp, "country", "") or "",
                })
            else:
                try:
                    from app.main import load_master_index  # type: ignore

                    mi = load_master_index()
                    raw = (cid or "").strip()
                    row = mi.get(raw) or mi.get(canon_cid)
                    if not row:
                        for mk, mv in mi.items():
                            if canonical_cigar_id_for_comparison(mk) == canon_cid:
                                row = mv
                                break
                    if row:
                        bq = row.get("box_qty") or 0
                        try:
                            box_int = int(bq) if bq not in ("", None) else 0
                        except (TypeError, ValueError):
                            box_int = 0
                        sparse.update({
                            "cigar_name": f"{row.get('brand', '')} {row.get('line', '')}".strip(),
                            "brand": row.get("brand", ""),
                            "line": row.get("line", ""),
                            "wrapper": row.get("wrapper", ""),
                            "vitola": row.get("vitola", ""),
                            "size": row.get("size", ""),
                            "box_qty": box_int,
                            "strength": row.get("strength", "") or "",
                            "country": row.get("country", "") or "",
                        })
                except Exception:
                    pass
            return sparse

        retailer_lookup = {r["key"]: r for r in RETAILERS}

        def row_from_product(p) -> Dict[str, Any]:
            base = p.price_cents or 0
            ship = estimate_shipping_cents(base, p.retailer_key, state) or 0
            tax = estimate_tax_cents(base + ship, p.retailer_key, state) or 0
            delivered = base + ship + tax
            r_info = retailer_lookup.get(p.retailer_key, {})
            return {
                "retailer_key": p.retailer_key,
                "retailer_name": r_info.get("name") or p.retailer_key,
                "authorized": bool(r_info.get("authorized", False)),
                "base_cents": base,
                "shipping_cents": ship,
                "tax_cents": tax,
                "delivered_cents": delivered,
                "in_stock": bool(p.in_stock),
                "url": p.url,
                "price_source": getattr(p, "price_source", "csv"),
                "observed_at": getattr(p, "observed_at", None),
                "observation_count": getattr(p, "observation_count", 0),
                "community_id": getattr(p, "community_id", None),
            }

        results = [row_from_product(p) for p in matches]
        # Sort: in-stock first, then cheapest delivered.
        results.sort(key=lambda r: (not r["in_stock"], r["delivered_cents"]))

        this_listing: Optional[Dict[str, Any]] = None
        fk = (focus_retailer_key or "").strip()
        if fk:
            fu = canonicalize_url(focus_url) if focus_url else ""
            cand_products = [
                p for p in matches
                if p.retailer_key == fk
                and (not fu or canonicalize_url(p.url or "") == fu)
            ]
            if not cand_products:
                cand_products = [p for p in matches if p.retailer_key == fk]
            if cand_products:
                scored = [
                    (row_from_product(p), (not bool(p.in_stock), p.price_cents or 0))
                    for p in cand_products
                ]
                scored.sort(key=lambda t: t[1])
                this_listing = scored[0][0]

        first = next((p for p in matches if (p.cigar_id or "") == canon_cid), matches[0])
        return {
            "cigar_id": canon_cid,
            "cigar_name": f"{first.brand} {first.line}".strip(),
            "brand": first.brand,
            "line": first.line,
            "wrapper": first.wrapper,
            "vitola": first.vitola,
            "size": first.size,
            "box_qty": first.box_qty,
            # Gap 3: master-only fields, now JOINed into Product at load
            # time. Empty when the CID isn't in master yet (in-flight).
            "strength": getattr(first, "strength", "") or "",
            "country":  getattr(first, "country", "")  or "",
            "zip": zip or None,
            "state": state,
            "results": results[:limit],
            "total_retailers": len(distinct_retailers),
            "this_listing": this_listing,
        }
    except Exception as e:
        logger.exception("_build_comparison_for_cid failed: %s", e)
        return None


# ── POST /api/community/request-retailer ───────────────────────────────

@router.post("/request-retailer")
async def request_retailer(request: Request, body: RequestRetailerBody):
    """Consumer asks us to add a new retailer.

    Writes two rows:
      * community_retailer_requests — observer-linked, used by /my-requests
        polling so the consumer extension can show a chrome.notification
        when this retailer comes online.
      * pending_new_retailers — operator queue (same table the operator
        admin tools already consume).

    Both inserts are idempotent (ON CONFLICT DO NOTHING). No rate-limit
    layer here yet — the operator queue dedupes by (hostname, url) so
    a script can't pump duplicate rows.
    """
    url = canonicalize_url(body.url)
    observer = body.observer_id.strip()
    if not observer:
        return JSONResponse({"error": "observer_id required"}, status_code=400)
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if not host:
        return JSONResponse({"error": "hostname could not be derived"}, status_code=400)

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO community_retailer_requests (observer_id, hostname, url)
            VALUES (%s, %s, %s)
            ON CONFLICT (observer_id, hostname) DO NOTHING
            """,
            (observer, host, url),
        )
        cur.execute(
            """
            INSERT INTO pending_new_retailers (hostname, url)
            VALUES (%s, %s)
            ON CONFLICT (hostname, url) DO NOTHING
            """,
            (host, url),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "hostname": host}
    except Exception as e:
        logger.exception("request_retailer failed: %s", e)
        return JSONResponse({"error": "internal"}, status_code=500)


# ── GET /api/community/my-requests ─────────────────────────────────────

@router.get("/my-requests")
async def my_requests(observer_id: str):
    """List a consumer's pending and recently-fulfilled retailer requests.

    Polled by the consumer extension's background worker on startup and
    every few hours; the worker fires a chrome.notification for each
    hostname that has transitioned to fulfilled since the previous poll
    (tracking the "previously seen" set in chrome.storage.local).

    Auto-fulfillment lazy path: any of this observer's pending requests
    whose hostname is now present in the retailer registry get their
    fulfilled_at set as a side effect of this GET. That way the operator
    onboards a retailer via the normal RETAILERS edit + deploy and
    notifications fire on the next consumer poll — no separate admin
    action needed.
    """
    observer = (observer_id or "").strip()
    if not observer:
        return JSONResponse({"error": "observer_id required"}, status_code=400)
    try:
        from app.extension_endpoints import _cache_state, _refresh_cache  # type: ignore
        _refresh_cache()
        live_hosts = set((_cache_state.get("retailers") or {}).keys())
    except Exception:
        live_hosts = set()

    try:
        conn = _get_conn()
        cur = conn.cursor()
        if live_hosts:
            cur.execute(
                """
                UPDATE community_retailer_requests
                   SET fulfilled_at = NOW()
                 WHERE observer_id = %s
                   AND fulfilled_at IS NULL
                   AND hostname = ANY(%s)
                """,
                (observer, list(live_hosts)),
            )
        cur.execute(
            """
            SELECT hostname, url, requested_at, fulfilled_at
              FROM community_retailer_requests
             WHERE observer_id = %s
             ORDER BY requested_at DESC
             LIMIT 200
            """,
            (observer,),
        )
        rows = cur.fetchall()
        conn.commit()
        conn.close()
        requests = [
            {
                "hostname": r[0],
                "url": r[1],
                "requested_at": r[2].isoformat() if r[2] else None,
                "fulfilled_at": r[3].isoformat() if r[3] else None,
                "status": "fulfilled" if r[3] else "pending",
            }
            for r in rows
        ]
        return {
            "ok": True,
            "observer_id": observer,
            "requests": requests,
            "fulfilled_count": sum(1 for r in requests if r["status"] == "fulfilled"),
            "pending_count": sum(1 for r in requests if r["status"] == "pending"),
        }
    except Exception as e:
        logger.exception("my_requests failed: %s", e)
        return JSONResponse({"error": "internal"}, status_code=500)


# ── POST /api/community/delete-my-observations ─────────────────────────

@router.post("/delete-my-observations")
async def delete_my_observations(body: DeleteObservationsBody):
    """Forget-me request. Deletes every observation + proposal authored
    by the given observer_id. No auth: the observer_id is itself a
    bearer token — only the user's extension knows their per-install id.
    """
    observer = body.observer_id.strip()
    if not observer:
        return JSONResponse({"error": "observer_id required"}, status_code=400)
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM observed_prices WHERE observer_id=%s", (observer,))
        obs_deleted = cur.rowcount
        cur.execute("DELETE FROM community_url_proposals WHERE observer_id=%s", (observer,))
        prop_deleted = cur.rowcount
        cur.execute("DELETE FROM community_retailer_requests WHERE observer_id=%s", (observer,))
        req_deleted = cur.rowcount
        conn.commit()
        conn.close()
        return {
            "ok": True,
            "deleted": {
                "observed_prices": obs_deleted,
                "community_url_proposals": prop_deleted,
                "community_retailer_requests": req_deleted,
                "total": obs_deleted + prop_deleted + req_deleted,
            },
        }
    except Exception as e:
        logger.exception("delete_my_observations failed: %s", e)
        return JSONResponse({"error": "internal"}, status_code=500)


# ═══════════════════════════════════════════════════════════════════════
# POST /api/public/guess-metadata
# ═══════════════════════════════════════════════════════════════════════
#
# Used by the consumer extension's "candidate" state — when a shopper is
# on a product page we don't have a CID for, we ask them for brand /
# line / vitola so an operator can map the URL to a master CID. The
# extension scrapes the page's title / JSON-LD and pre-fills the form.
#
# The old client-side prefill split the title into "first 2 tokens =
# brand, next 2 = line, rest = vitola", which produced "Arturo Fuente
# Cigars" as brand and "Hemingway Best" as line on real pages — so the
# user had to delete garbage before they could submit. This endpoint
# snaps the scraped text to canonical brand / line / vitola values from
# master_cigars.csv. If we can't find the brand in the catalog we leave
# the field empty rather than guess — better an empty field than a
# wrong one the user has to clean up.
#
# Also returns the catalog whitelists (brand list + lines per brand)
# so the form can offer a <datalist> typeahead — a soft constraint, not
# a hard one (legit new brands not yet in master can still be typed and
# submitted; operator review picks them up).
#
# Read-only, idempotent, anonymous, cached. Rate limited per IP.
# ═══════════════════════════════════════════════════════════════════════

_catalog_match_cache: Dict[str, Any] = {"data": None, "timestamp": 0.0}
_CATALOG_MATCH_TTL_S = 300  # piggybacks on load_master_index()'s own 5-min cache


def _normalize_for_match(s: str) -> str:
    """Lowercase, strip everything that isn't a letter/digit/space.

    We compare a scraped product title against catalog names by looking
    for whole-token substring matches after this normalization. Stripping
    apostrophes / hyphens / parens means "Opus X (Forbidden X)" still
    matches "opus x forbidden x" in the scraped title.
    """
    if not s:
        return ""
    out_chars = []
    for ch in s.lower():
        if ch.isalnum() or ch.isspace():
            out_chars.append(ch)
        else:
            out_chars.append(" ")
    # Collapse runs of whitespace to single spaces, pad with spaces on
    # both ends so word-boundary substring checks work cleanly.
    norm = " ".join("".join(out_chars).split())
    return f" {norm} "


def _merge_arturo_fuente_anejo_reserva_catalog_lines(
    lines_by_brand: Dict[str, set],
    vitolas_by_bl: Dict[tuple, set],
    boxes_by_blv: Dict[str, set],
    codes_by_blv: Dict[str, set[str]],
    wrapper_rows_acc: Dict[str, Dict[str, Dict[str, str]]],
) -> None:
    """Treat AF 'Añejo Reserva' as the same line as 'Añejo' in extension pickers."""
    brand = "Arturo Fuente"
    lines = lines_by_brand.get(brand)
    if not lines:
        return
    reserva_lines = {ln for ln in lines if _cid_slug_key(ln) == "anejoreserva"}
    if not reserva_lines:
        return
    anejo_lines = {ln for ln in lines if _cid_slug_key(ln) == "anejo"}
    canonical = (
        sorted(anejo_lines, key=lambda s: (len(s), s.lower()))[0]
        if anejo_lines
        else "Añejo"
    )
    if not anejo_lines:
        lines.add(canonical)
    for rl in reserva_lines:
        lines.discard(rl)
        vs = vitolas_by_bl.pop((brand, rl), set())
        if vs:
            vitolas_by_bl.setdefault((brand, canonical), set()).update(vs)
        prefix_old = f"{brand}|{rl}|"
        for k in list(boxes_by_blv.keys()):
            if not k.startswith(prefix_old):
                continue
            vit = k[len(prefix_old):]
            nk = f"{brand}|{canonical}|{vit}"
            boxes_by_blv.setdefault(nk, set()).update(boxes_by_blv.pop(k))
        for k in list(codes_by_blv.keys()):
            if not k.startswith(prefix_old):
                continue
            vit = k[len(prefix_old):]
            nk = f"{brand}|{canonical}|{vit}"
            codes_by_blv.setdefault(nk, set()).update(codes_by_blv.pop(k))
        for k in list(wrapper_rows_acc.keys()):
            if not k.startswith(prefix_old):
                continue
            vit = k[len(prefix_old):]
            nk = f"{brand}|{canonical}|{vit}"
            incoming = wrapper_rows_acc.pop(k)
            tgt = wrapper_rows_acc.setdefault(nk, {})
            for dedupe_k, row in incoming.items():
                prev = tgt.get(dedupe_k)
                if not prev or len(row.get("code") or "") > len(prev.get("code") or ""):
                    tgt[dedupe_k] = row


def _get_catalog_match_index() -> Dict[str, Any]:
    """Build (and cache) the brand / line / vitola lookup index.

    Returns a dict with:
      brands_sorted: list[str]
          All catalog brands, sorted alphabetically — for the form's
          <datalist>.
      brand_match_pairs: list[tuple[str, str]]
          (normalized_brand, canonical_brand) sorted by normalized
          length desc. The matcher walks this list and picks the
          first normalized brand that appears in the scraped text —
          length-desc ordering means "Arturo Fuente" wins over
          "Fuente" when both could match.
      lines_by_brand: dict[brand, list[str]]
          Lines for each brand, sorted alphabetically — for the form's
          line <datalist> that updates when brand changes.
      line_match_pairs: dict[brand, list[tuple[str, str]]]
          Per-brand version of brand_match_pairs for line matching.
      vitolas_by_brand_line: dict[(brand, line), list[str]]
          Vitolas for each (brand, line) — both for matching the
          scraped text AND for the vitola <datalist>.
      vitola_match_pairs: dict[(brand, line), list[tuple[str, str]]]
      buckets_by_brand_line: dict["brand|line", list[str]]
          Distinct wrapper buckets that appear on any vitola for that
          brand+line (legacy cascade; vitola-first UI prefers
          ``wrapper_catalog_rows_by_blv``).
      vitolas_by_brand_line_bucket: dict["brand|line|bucket", list[str]]
          Vitolas for that brand+line whose CID maps to that consumer
          bucket. ``__UNBUCKETED__`` holds vitolas with no mapped bucket
          (shown only when wrapper is "Not sure").
      wrapper_catalog_rows_by_blv: dict["brand|line|vitola", list[dict]]
          Per-vitola rows from master: ``label`` (display string),
          ``bucket`` (consumer bucket), ``code`` (CID wrapper_code).
          Lets the extension show catalog-accurate wrapper names (e.g.
          Dominican Rosado) alongside the four generic buckets.
      boxes_by_brand_line_vitola: dict["brand|line|vitola", list[int]]
          Distinct box counts from master for that vitola (consumer form).
      buckets_by_brand_line_vitola: dict["brand|line|vitola", list[str]]
          Wrapper bucket labels present in master for that vitola.
      all_bucket_names: list[str]
          Full consumer bucket ordering (fallback when a vitola has no
          mapped codes in the four buckets).
    """
    now = time.time()
    if (_catalog_match_cache.get("data") is not None
            and (now - _catalog_match_cache.get("timestamp", 0.0)) < _CATALOG_MATCH_TTL_S):
        return _catalog_match_cache["data"]

    # Local import to avoid a circular dependency with app.main.
    from app.main import load_master_index, _format_wrapper_display  # type: ignore

    master = load_master_index()
    brands: set[str] = set()
    lines_by_brand: Dict[str, set[str]] = defaultdict(set)
    vitolas_by_bl: Dict[tuple[str, str], set[str]] = defaultdict(set)

    from app.cid_matcher import parse_cid  # type: ignore
    from app.wrapper_buckets import bucket_for_code, bucket_names  # type: ignore

    boxes_by_blv: Dict[str, set] = defaultdict(set)
    codes_by_blv: Dict[str, set[str]] = defaultdict(set)
    # blv_key -> dedupe_key (display lower) -> {label, bucket, code}
    wrapper_rows_acc: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(dict)

    for cid, row in master.items():
        brand = (row.get("brand") or "").strip()
        line = (row.get("line") or "").strip()
        vitola = (row.get("vitola") or "").strip()
        if not brand:
            continue
        brands.add(brand)
        if line:
            lines_by_brand[brand].add(line)
            if vitola:
                vitolas_by_bl[(brand, line)].add(vitola)
        if brand and line and vitola:
            blv_key = f"{brand}|{line}|{vitola}"
            parts = parse_cid(cid) if cid else None
            wc = (parts or {}).get("wrapper_code") or ""
            wc_u = str(wc).strip().upper() if wc else ""
            if wc_u:
                codes_by_blv[blv_key].add(wc_u)
                bkt = bucket_for_code(wc_u)
                if bkt:
                    wa = (row.get("wrapper_alias") or "").strip()
                    wcanon = (row.get("wrapper_canon") or "").strip()
                    disp = (_format_wrapper_display(wa, wcanon) or "").strip()
                    if not disp:
                        disp = (row.get("wrapper") or "").strip()
                    if not disp:
                        disp = bkt
                    dedupe_k = disp.lower()
                    prev = wrapper_rows_acc[blv_key].get(dedupe_k)
                    if not prev or (wc_u and len(wc_u) > len(prev.get("code") or "")):
                        wrapper_rows_acc[blv_key][dedupe_k] = {
                            "label": disp,
                            "bucket": bkt,
                            "code": wc_u,
                        }
            try:
                bq_raw = row.get("box_qty")
                bqi = int(bq_raw) if bq_raw not in (None, "", 0, "0") else 0
            except (TypeError, ValueError):
                bqi = 0
            if bqi > 0:
                boxes_by_blv[blv_key].add(bqi)

    _merge_arturo_fuente_anejo_reserva_catalog_lines(
        lines_by_brand, vitolas_by_bl, boxes_by_blv, codes_by_blv, wrapper_rows_acc
    )

    buckets_by_blv: Dict[str, List[str]] = {}
    for blv_key, codes in codes_by_blv.items():
        seen: set[str] = set()
        ordered: List[str] = []
        for c in sorted(codes):
            bkt = bucket_for_code(c)
            if bkt and bkt not in seen:
                seen.add(bkt)
                ordered.append(bkt)
        if ordered:
            buckets_by_blv[blv_key] = ordered

    buckets_by_brand_line: Dict[str, set[str]] = defaultdict(set)
    vitolas_by_brand_line_bucket: Dict[str, set[str]] = defaultdict(set)
    UNBUCKETED = "__UNBUCKETED__"

    for blv_key, bkt_list in buckets_by_blv.items():
        parts = blv_key.split("|", 2)
        if len(parts) < 3:
            continue
        b, l, v = parts[0], parts[1], parts[2]
        bl_key = f"{b}|{l}"
        for bkt in bkt_list:
            buckets_by_brand_line[bl_key].add(bkt)
            vitolas_by_brand_line_bucket[f"{bl_key}|{bkt}"].add(v)

    for (b, l), vs in vitolas_by_bl.items():
        bl_key = f"{b}|{l}"
        for v in vs:
            blv_key = f"{b}|{l}|{v}"
            if blv_key not in buckets_by_blv:
                vitolas_by_brand_line_bucket[f"{bl_key}|{UNBUCKETED}"].add(v)

    def _match_pairs(values) -> list:
        # (normalized, canonical) sorted by normalized length desc so
        # the longest viable match wins ("Arturo Fuente" beats "Fuente").
        # Ties broken alphabetically for determinism.
        return sorted(
            [(_normalize_for_match(v).strip(), v) for v in values if v],
            key=lambda p: (-len(p[0]), p[1]),
        )

    data = {
        "brands_sorted": sorted(brands),
        "brand_match_pairs": _match_pairs(brands),
        "lines_by_brand": {b: sorted(ls) for b, ls in lines_by_brand.items()},
        "line_match_pairs": {b: _match_pairs(ls) for b, ls in lines_by_brand.items()},
        "vitolas_by_brand_line": {f"{b}|{l}": sorted(vs) for (b, l), vs in vitolas_by_bl.items()},
        "vitola_match_pairs": {(b, l): _match_pairs(vs) for (b, l), vs in vitolas_by_bl.items()},
        "boxes_by_brand_line_vitola": {
            k: sorted(vs) for k, vs in boxes_by_blv.items() if vs
        },
        "buckets_by_brand_line_vitola": buckets_by_blv,
        "buckets_by_brand_line": {
            k: sorted(s) for k, s in buckets_by_brand_line.items() if s
        },
        "vitolas_by_brand_line_bucket": {
            k: sorted(vs) for k, vs in vitolas_by_brand_line_bucket.items() if vs
        },
        "wrapper_catalog_rows_by_blv": {
            k: sorted(rows.values(), key=lambda r: (r["label"].lower(), r["bucket"]))
            for k, rows in wrapper_rows_acc.items()
            if rows
        },
        "all_bucket_names": bucket_names(),
    }
    _catalog_match_cache.update({"data": data, "timestamp": now})
    return data


def _find_in_text(text_norm: str, match_pairs) -> Optional[str]:
    """Walk `match_pairs` (already sorted by length desc) and return the
    canonical form of the first whole-token match in `text_norm`.

    `text_norm` is already wrapped in leading/trailing spaces by
    _normalize_for_match, and each candidate's normalized form is
    trimmed — so `" arturo fuente "` is in `" arturo fuente cigars
    hemingway "` (substring match) but `" fuente "` would not match
    `" arturoofuente "` because of the surrounding spaces. We
    additionally require the candidate to be preceded/followed by a
    space in the haystack to enforce a whole-token boundary.
    """
    if not text_norm:
        return None
    for norm, canon in match_pairs:
        if not norm:
            continue
        needle = f" {norm} "
        if needle in text_norm:
            return canon
    return None


def _match_scraped_to_catalog(
    title: str = "",
    jsonld_name: str = "",
    jsonld_brand: str = "",
    og_description: str = "",
) -> Dict[str, str]:
    """Snap scraped product text to canonical brand/line/vitola from master.

    Returns {brand, line, vitola}. Each value is either a canonical
    catalog string or "" — never a scraped substring. We'd rather
    show the user an empty field than a wrong guess they have to delete.
    """
    out = {"brand": "", "line": "", "vitola": ""}

    haystack_parts = [title, jsonld_name, jsonld_brand, og_description]
    text_norm = _normalize_for_match(" ".join(p for p in haystack_parts if p))
    if not text_norm.strip():
        return out

    catalog = _get_catalog_match_index()

    brand = _find_in_text(text_norm, catalog["brand_match_pairs"])
    if not brand:
        return out
    out["brand"] = brand

    line_pairs = catalog["line_match_pairs"].get(brand) or []
    line = _find_in_text(text_norm, line_pairs)
    if not line:
        return out
    out["line"] = line

    vitola_pairs = catalog["vitola_match_pairs"].get((brand, line)) or []
    vitola = _find_in_text(text_norm, vitola_pairs)
    if vitola:
        out["vitola"] = vitola

    return out


class GuessMetadataBody(BaseModel):
    url: str = Field("", max_length=2048)
    title: str = Field("", max_length=500)
    jsonld_name: str = Field("", max_length=500)
    jsonld_brand: str = Field("", max_length=200)
    og_description: str = Field("", max_length=1000)


@public_router.post("/guess-metadata")
async def public_guess_metadata(request: Request, body: GuessMetadataBody):
    """Snap a scraped product title to canonical catalog values.

    See the long header comment above for the rationale. Returns:

        {
          "prefill": {"brand": "...", "line": "...", "vitola": "..."},
          "catalog": {
            "brands": [...],
            "lines_by_brand": {...},
            "vitolas_for_match": [...],  # prefill (brand,line) only
            "vitolas_by_brand_line": {...},  # full cascade map
            "boxes_by_brand_line_vitola": {...},
            "buckets_by_brand_line_vitola": {...},
            "buckets_by_brand_line": {...},
            "vitolas_by_brand_line_bucket": {...},
            "wrapper_catalog_rows_by_blv": {...},
            "all_bucket_names": [...],
          },
          "matched_via": "master_catalog" | "no_match"
        }

    Empty fields in `prefill` mean "the catalog didn't recognize that
    part of the scraped text" — the form should leave the input empty
    rather than fall back to the raw scrape.
    """
    ip = _public_ip_key(request)
    if not _rate_limit(_guess_minute, ip, 60, _PUBLIC_GUESS_MAX_PER_MIN):
        return JSONResponse({"error": "rate_limited", "scope": "per_minute"}, status_code=429)
    if not _rate_limit(_guess_day, ip, 86_400, _PUBLIC_GUESS_MAX_PER_DAY):
        return JSONResponse({"error": "rate_limited", "scope": "per_day"}, status_code=429)

    try:
        prefill = _match_scraped_to_catalog(
            title=body.title or "",
            jsonld_name=body.jsonld_name or "",
            jsonld_brand=body.jsonld_brand or "",
            og_description=body.og_description or "",
        )
        catalog = _get_catalog_match_index()
        vitolas_for_match: list = []
        if prefill["brand"] and prefill["line"]:
            key = f"{prefill['brand']}|{prefill['line']}"
            vitolas_for_match = catalog["vitolas_by_brand_line"].get(key) or []

        return {
            "prefill": prefill,
            "catalog": {
                "brands": catalog["brands_sorted"],
                "lines_by_brand": catalog["lines_by_brand"],
                "vitolas_for_match": vitolas_for_match,
                "vitolas_by_brand_line": catalog["vitolas_by_brand_line"],
                "boxes_by_brand_line_vitola": catalog["boxes_by_brand_line_vitola"],
                "buckets_by_brand_line_vitola": catalog["buckets_by_brand_line_vitola"],
                "buckets_by_brand_line": catalog["buckets_by_brand_line"],
                "vitolas_by_brand_line_bucket": catalog["vitolas_by_brand_line_bucket"],
                "wrapper_catalog_rows_by_blv": catalog["wrapper_catalog_rows_by_blv"],
                "all_bucket_names": catalog["all_bucket_names"],
            },
            "matched_via": "master_catalog" if prefill["brand"] else "no_match",
        }
    except Exception as e:
        logger.exception("public_guess_metadata failed: %s", e)
        return JSONResponse({"error": "internal"}, status_code=500)
