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
    scraped_title: Optional[str] = Field(None, max_length=500)
    observer_source: Optional[str] = "consumer"


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


def _resolve_cigar_id_from_url(url: str, retailer_key: Optional[str]) -> Optional[str]:
    """If the URL is already in the live retailer CSV, return its CID."""
    if not retailer_key:
        return None
    try:
        from app.extension_endpoints import _cache_state  # type: ignore
        live = _cache_state.get("url_index", {}).get(url)
        if live and live[0] == retailer_key:
            return live[1]
    except Exception:
        pass
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

    retailer_key = _resolve_retailer_key(body.url)
    cigar_id = _resolve_cigar_id_from_url(body.url, retailer_key)
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

    retailer_key = _resolve_retailer_key(body.url)
    source = (body.observer_source or "consumer").lower()
    if source not in {"operator", "consumer"}:
        source = "consumer"

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO community_url_proposals
              (url, retailer_key, proposed_brand, proposed_line, proposed_vitola,
               proposed_size, proposed_wrapper, proposed_box_qty,
               scraped_title, observer_id, observer_source, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
            RETURNING id
        """, (
            body.url, retailer_key, _trim(body.brand), _trim(body.line),
            _trim(body.vitola), _trim(body.size), _trim(body.wrapper),
            body.box_qty, _trim(body.scraped_title), observer, source,
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
