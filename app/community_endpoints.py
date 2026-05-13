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
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.cid_matcher import canonicalize_url

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
        cur.execute("""
            CREATE INDEX IF NOT EXISTS community_url_proposals_status_created_at_idx
                ON community_url_proposals (status, created_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS community_url_proposals_url_idx
                ON community_url_proposals (url)
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


class DeleteObservationsBody(BaseModel):
    """Consumer's 'forget me' request: delete every observation + proposal
    they've ever submitted, identified by their per-install observer_id."""
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
        if not (live and live[0] == retailer_key):
            return None
        cid = live[1]
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
    cigar_id = _resolve_cigar_id_from_url(body.url, retailer_key, body.box_qty)
    qty_type = _coerce_quantity_type(body.quantity_type, body.box_qty)
    price_cents = _to_price_cents(body.price)
    source = (body.observer_source or "consumer").lower()
    if source not in {"operator", "consumer"}:
        source = "consumer"
    currency = (body.currency or "USD")[:8].upper()

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO observed_prices
              (url, retailer_key, cigar_id, quantity_type, box_qty,
               price_cents, currency, in_stock, scraped_title, jsonld,
               observer_id, observer_source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
            RETURNING id
        """, (
            body.url, retailer_key, cigar_id, qty_type, body.box_qty,
            price_cents, currency, body.in_stock, body.scraped_title,
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

@router.post("/propose-metadata")
async def propose_metadata(request: Request, body: ProposeMetadataBody):
    """Consumer-submitted metadata proposal for a URL that has no CID yet.

    Goes into community_url_proposals with status='pending'. The operator
    reviews each proposal via the admin UI and decides whether to map it
    to an existing CID, create a new CID, or reject it.
    """
    observer = _observer_id(body.observer_id, request)
    if not _rate_limit(_prop_hour, observer, 3600, _PROPOSE_MAX_PER_HOUR):
        return JSONResponse({"error": "rate_limited", "scope": "per_hour"}, status_code=429)

    body.url = canonicalize_url(body.url)
    retailer_key = _resolve_retailer_key(body.url)
    source = (body.observer_source or "consumer").lower()
    if source not in {"operator", "consumer"}:
        source = "consumer"

    confirmed_cents = _to_price_cents(body.confirmed_price)
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO community_url_proposals
              (url, retailer_key, proposed_brand, proposed_line, proposed_vitola,
               proposed_size, proposed_wrapper, proposed_box_qty,
               confirmed_price_cents,
               scraped_title, observer_id, observer_source, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
            RETURNING id
        """, (
            body.url, retailer_key, _trim(body.brand), _trim(body.line),
            _trim(body.vitola), _trim(body.size), _trim(body.wrapper),
            body.box_qty, confirmed_cents,
            _trim(body.scraped_title), observer, source,
        ))
        proposal_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "retailer_key": retailer_key,
            "status": "pending",
        }
    except Exception as e:
        logger.exception("propose_metadata failed: %s", e)
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

    # Live retailer CSV hit?
    matched_cid: Optional[str] = None
    try:
        from app.extension_endpoints import _cache_state  # type: ignore
        live = _cache_state.get("url_index", {}).get(url)
        if live and live[0] == retailer_key:
            matched_cid = live[1]
    except Exception:
        matched_cid = None

    # Has the operator already touched this URL via the extension?
    seen_status: Optional[str] = None
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
            seen_status = row[0]
        if seen_status is None:
            # Also check community proposals so a previous consumer's
            # contribution surfaces as "we know about this".
            cur.execute(
                "SELECT status FROM community_url_proposals "
                "WHERE url=%s ORDER BY created_at DESC LIMIT 1",
                (url,),
            )
            row = cur.fetchone()
            if row:
                seen_status = f"community_{row[0]}"
        conn.close()
    except Exception as e:
        logger.warning("public_url_status seen lookup failed: %s", e)

    if matched_cid:
        comparison = _build_comparison_for_cid(matched_cid, zip=zip, limit=3)
        return {
            "state": "matched",
            "url": url,
            "retailer_key": retailer_key,
            "matched_cid": matched_cid,
            "seen_status": seen_status,
            "comparison": comparison,
        }

    if seen_status:
        return {
            "state": "seen",
            "url": url,
            "retailer_key": retailer_key,
            "seen_status": seen_status,
        }

    return {
        "state": "candidate",
        "url": url,
        "retailer_key": retailer_key,
    }


def _build_comparison_for_cid(
    cid: str,
    zip: str = "",
    limit: int = 3,
) -> Optional[Dict[str, Any]]:
    """Top-N cheapest in-stock retailers carrying this CID.

    Reuses app.main.load_all_products() so we stay consistent with the
    public /compare web page — same data, same filters, same delivered-
    price math. Returns None if fewer than 2 retailers carry the CID
    (consistent with the website's minimum-comparison rule).
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
        matches = [p for p in all_products if getattr(p, "cigar_id", None) == cid]
        distinct_retailers = {p.retailer_key for p in matches}
        if len(distinct_retailers) < MIN_RETAILERS_FOR_COMPARISON:
            return {
                "cigar_id": cid,
                "results": [],
                "reason": (
                    f"Only {len(distinct_retailers)} retailer(s) carry this cigar. "
                    f"At least {MIN_RETAILERS_FOR_COMPARISON} are needed."
                ),
            }

        retailer_lookup = {r["key"]: r for r in RETAILERS}
        results = []
        for p in matches:
            base = p.price_cents or 0
            ship = estimate_shipping_cents(base, p.retailer_key, state) or 0
            tax = estimate_tax_cents(base + ship, p.retailer_key, state) or 0
            delivered = base + ship + tax
            r_info = retailer_lookup.get(p.retailer_key, {})
            results.append({
                "retailer_key": p.retailer_key,
                "retailer_name": r_info.get("name") or p.retailer_key,
                "authorized": bool(r_info.get("authorized", False)),
                "base_cents": base,
                "shipping_cents": ship,
                "tax_cents": tax,
                "delivered_cents": delivered,
                "in_stock": bool(p.in_stock),
                "url": p.url,
            })
        # Sort: in-stock first, then cheapest delivered.
        results.sort(key=lambda r: (not r["in_stock"], r["delivered_cents"]))
        first = matches[0]
        return {
            "cigar_id": cid,
            "cigar_name": f"{first.brand} {first.line}".strip(),
            "brand": first.brand,
            "line": first.line,
            "wrapper": first.wrapper,
            "vitola": first.vitola,
            "size": first.size,
            "box_qty": first.box_qty,
            "zip": zip or None,
            "state": state,
            "results": results[:limit],
            "total_retailers": len(distinct_retailers),
        }
    except Exception as e:
        logger.exception("_build_comparison_for_cid failed: %s", e)
        return None


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
        conn.commit()
        conn.close()
        return {
            "ok": True,
            "deleted": {
                "observed_prices": obs_deleted,
                "community_url_proposals": prop_deleted,
                "total": obs_deleted + prop_deleted,
            },
        }
    except Exception as e:
        logger.exception("delete_my_observations failed: %s", e)
        return JSONResponse({"error": "internal"}, status_code=500)
