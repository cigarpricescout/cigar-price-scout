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
    scraped_title: Optional[str] = Field(None, max_length=500)
    observer_source: Optional[str] = "consumer"


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


# ── POST /api/community/report-correction ──────────────────────────────

# "Loose" guardrails for the report-incorrect flow. Picked deliberately
# wide so we accept legit clearance prices and seasonal sales, but
# narrow enough to block obvious typos ($140 → $14) and bot mischief.
# The operator still reviews every correction; these guards exist so
# we don't *queue* obviously-bad data.
_REPORT_PRICE_MIN_CENTS = 500           # $5 — below this is almost certainly a typo
_REPORT_PRICE_MAX_CENTS = 500_000       # $5,000 — most expensive boxes top out well below this
_REPORT_PRICE_MAX_DEVIATION = 0.75      # ±75% of the price we were showing
_VALID_BOX_QTYS = {1, 5, 10, 15, 20, 24, 25, 50}


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
      2. At least one proposed field must differ from current. If everything
         matches, return 200 with status='no_changes_detected' and DO NOT
         insert. (The popup renders this as "Thanks — no changes detected".)
      3. proposed_price must be in [$5, $5000] AND within ±75% of
         current_price (when current_price is provided).
      4. proposed_box_qty must be in {1, 5, 10, 15, 20, 24, 25, 50}.
      5. proposed_brand/line/vitola, when supplied, must be ≤ 80 chars.

    On success, inserts into community_url_proposals with is_correction=TRUE
    so the operator-review UI can highlight it as a correction (vs. a
    fresh proposal for an unmatched URL).
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
            if deviation > _REPORT_PRICE_MAX_DEVIATION:
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
    if nothing_changed and not text_fields_sent:
        return {
            "ok": True,
            "status": "no_changes_detected",
            "proposal_id": None,
        }

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO community_url_proposals
              (url, retailer_key, proposed_brand, proposed_line, proposed_vitola,
               proposed_wrapper, proposed_box_qty,
               confirmed_price_cents, current_cid, current_price_cents,
               is_correction,
               scraped_title, observer_id, observer_source, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s,'pending')
            RETURNING id
        """, (
            body.url, retailer_key,
            _trim(body.proposed_brand), _trim(body.proposed_line),
            _trim(body.proposed_vitola), _trim(body.proposed_wrapper),
            body.proposed_box_qty, proposed_price_cents,
            _trim(body.current_cid), current_price_cents,
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
                "       proposed_box_qty, proposed_wrapper "
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
                    }
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

    Returns a dict with cid/score/confidence/wrapper_code/box_qty when the
    proposal matches a master CID with HIGH confidence AND the consumer's
    wrapper bucket (if provided) is compatible AND box_qty matches
    exactly. Returns None otherwise so the caller falls back to the
    standard "in review" UX.

    This powers the Gap 2 instant-comparison feedback: when we can
    confidently auto-resolve, the consumer sees the price comparison
    card immediately instead of "thanks, in review" — even though the
    operator still does the final approval.

    Conservative on purpose: HIGH-only, wrapper-bucket-checked, exact
    box_qty match. Wrong auto-matches would surface a misleading
    comparison; we'd rather show "in review" than wrong data.
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
        from app.cid_matcher import find_top_candidates  # type: ignore
    except Exception as e:
        logger.warning("find_top_candidates unavailable: %s", e)
        return None

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
                # Sprint 3 provenance. The popup uses these to render a
                # "Last observed YYYY-MM-DD" stamp on anti-bot rows so
                # users know the price is consumer-contributed, not live.
                "price_source": getattr(p, "price_source", "csv"),
                "observed_at": getattr(p, "observed_at", None),
                "observation_count": getattr(p, "observation_count", 0),
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
            # Gap 3: master-only fields, now JOINed into Product at load
            # time. Empty when the CID isn't in master yet (in-flight).
            "strength": getattr(first, "strength", "") or "",
            "country":  getattr(first, "country", "")  or "",
            "zip": zip or None,
            "state": state,
            "results": results[:limit],
            "total_retailers": len(distinct_retailers),
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
