"""
Standalone CID matching primitives for the URL → CID Chrome extension flow.

This module deliberately has zero non-stdlib dependencies (no anthropic, no
pandas) so it is safe to import inside the FastAPI app on Railway. The scoring
logic mirrors `tools/ai/url_discoverer.py` so the extension and the weekly
discovery agent rank candidates the same way.

Public surface:
    parse_cid(cid)                       -> dict | None
    build_cid(parts)                     -> str
    canonical_cigar_id_for_comparison(cid) -> str
    slug_from_url(url)                   -> str
    programmatic_score(cid_parts, url, title=None) -> (score, details)
    load_master_cigars(csv_path)         -> list[dict]
    find_unique_metadata_match(brand, line, vitola, box_qty, wrapper_bucket, master) -> dict | None
    find_top_candidates(url, title, master, limit=5) -> list[dict]
    hostname_to_retailer_key(hostname, registry) -> str | None
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query parameters we strip from URLs before any URL-index lookup or
# observation-row insert. These are virtually never part of the canonical
# product identity — they're tracking, affiliate, or per-variant selectors.
# Stripping them lets baysidecigars.com/products/foo?variant=12345 match the
# CSV row keyed on baysidecigars.com/products/foo.
_TRACKING_QUERY_PARAMS = {
    "variant",                              # Shopify variant selector
    "gclid", "fbclid", "msclkid",           # ad click IDs
    "mc_cid", "mc_eid",                     # Mailchimp
    "ref", "aff", "affid", "affiliate",     # generic affiliate
    "sca_ref",                              # Stockist
    "_pos", "_psq", "_ss", "_v", "_sid",    # Shopify search/collection nav
    "yclid",                                # Yandex
    "igshid", "_branch_match_id",           # social referrers
    "trk_contact", "trk_msg", "trk_module", "trk_sid",  # ActiveCampaign
}
_TRACKING_QUERY_PREFIXES = ("utm_", "matomo_", "mtm_", "pk_", "piwik_")


def canonicalize_url(url: str) -> str:
    """Return a stable form of `url` safe for equality lookups.

    Lowercases scheme + host, strips fragment, drops tracking / variant
    query params, and removes a single trailing slash from the path.
    Preserves any non-tracking query params (some retailers genuinely use
    them, e.g. ?product_id=N).

    Idempotent: canonicalize_url(canonicalize_url(u)) == canonicalize_url(u).
    """
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip()
    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower()
    path = p.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    kept = []
    for k, v in parse_qsl(p.query, keep_blank_values=False):
        lk = k.lower()
        if lk in _TRACKING_QUERY_PARAMS:
            continue
        if any(lk.startswith(pre) for pre in _TRACKING_QUERY_PREFIXES):
            continue
        kept.append((k, v))
    query = urlencode(kept, doseq=True) if kept else ""
    return urlunparse((scheme, netloc, path, p.params, query, ""))




WRAPPER_CODES: Dict[str, List[str]] = {
    "MAD": ["maduro", "mad"],
    "NAT": ["natural", "nat", "connecticut shade", "connecticut"],
    "CAM": ["cameroon", "cam"],
    "ECU": ["ecuadorian", "ecuador", "ecu", "ecuadorian habano", "ecuadorian connecticut"],
    "HAB": ["habano", "hab", "cuban", "corojo"],
    "SUM": ["sumatra", "sumatran", "sum"],
    "BRZ": ["brazilian", "brazil", "brz", "arapiraca"],
    "MEX": ["mexican", "mexico", "san andres", "mex"],
    "NIC": ["nicaraguan", "nicaragua", "nic"],
    "HON": ["honduran", "honduras", "hon"],
    "DOM": ["dominican", "dom"],
    "OSC": ["oscuro", "osc"],
    "CON": ["connecticut", "con", "connecticut shade"],
    "CORO": ["corojo", "coro"],
    "CRIO": ["criollo", "crio"],
    "ROS": ["rosado", "ros"],
    "SUN": ["sun grown", "sungrown", "sun", "sumatra sun grown"],
    "CAND": ["candela", "cand"],
    "OLOR": ["olor", "dominican olor"],
}

WRAPPER_CODE_TO_NAMES: Dict[str, List[str]] = {
    code: [n.lower() for n in names] for code, names in WRAPPER_CODES.items()
}


def parse_cid(cid: str) -> Optional[Dict[str, str]]:
    """Decompose an 8-part pipe-delimited CID into a dict.

    Returns None for malformed CIDs. Trailing/leading whitespace is stripped.
    """
    if not cid:
        return None
    parts = [p.strip() for p in cid.split("|")]
    if len(parts) < 8:
        return None
    return {
        "brand": parts[0],
        "parent_brand": parts[1],
        "line": parts[2],
        "vitola": parts[3],
        "vitola2": parts[4],
        "size": parts[5],
        "wrapper_code": parts[6],
        "box_qty_str": parts[7],
        "raw": cid,
    }


def build_cid(parts: Dict[str, object]) -> str:
    """Build the canonical 8-part CID string from a parts dict.

    Components are normalized to match the master_cigars convention:
      * brand/parent_brand/line/vitola/vitola2/wrapper_code:
        internal whitespace stripped and UPPERCASED
        (e.g. "Aging Room" -> "AGINGROOM", "Corona Gorda" -> "CORONAGORDA")
      * size: whitespace stripped and lowercased (e.g. "6 x 50" -> "6x50")
      * box_qty: normalized to BOX<N>

    Callers may pass either a pre-formatted "box_qty_str" (e.g. "BOX25") or a
    bare integer/string "box_qty".

    IMPORTANT: only the CID string is normalized this way. The natural-form
    values (e.g. "Corona Gorda") should be preserved separately in the
    `extension_staged_approvals` row and written verbatim to master_cigars'
    human-readable columns (Brand, Line, Vitola, ...) so the website
    displays them properly.
    """
    raw_box = parts.get("box_qty_str") or parts.get("box_qty") or ""
    box = str(raw_box).strip()
    if box and not box.upper().startswith("BOX"):
        box_digits = re.sub(r"\D", "", box)
        box = f"BOX{box_digits}" if box_digits else ""
    else:
        box = box.upper()

    def cid_part(v: object) -> str:
        s = ("" if v is None else str(v)).strip()
        return re.sub(r"\s+", "", s).upper()

    def cid_size(v: object) -> str:
        s = ("" if v is None else str(v)).strip()
        return re.sub(r"\s+", "", s).lower()

    # Parent segment: many master rows use an empty middle slot (`BRAND||LINE`)
    # when there is no distinct parent company in the catalog. Only when
    # `parent_brand` is explicitly non-empty do we emit it (e.g. PADRON|PADRON|…).
    pb_raw = parts.get("parent_brand")
    parent_seg = (
        cid_part(pb_raw)
        if pb_raw is not None and str(pb_raw).strip() != ""
        else ""
    )

    return "|".join([
        cid_part(parts.get("brand")),
        parent_seg,
        cid_part(parts.get("line")),
        cid_part(parts.get("vitola")),
        cid_part(parts.get("vitola2")) or cid_part(parts.get("vitola")),
        cid_size(parts.get("size")),
        cid_part(parts.get("wrapper_code")),
        box,
    ])


# Wrapper codes occasionally mistyped in staged rows; map to master catalog
# codes for cross-retailer comparison joins only (storage may keep the typo).
_COMPARISON_WRAPPER_ALIASES = {
    "CAN": "CAM",  # Cameroon is CAM in master; "CAN" is a common typo
}


def canonical_cigar_id_for_comparison(cid: Optional[str]) -> str:
    """Return a normalized CID for equality checks across retailer rows.

    Master catalog often uses an empty parent segment (``BRAND||LINE``) while
    some staged/legacy rows duplicated the house brand (``BRAND|BRAND|LINE``).
    Those are the same product but would not match with raw ``==``.

    Used by consumer comparison builders so a URL mapped to a legacy-shaped
    CID still joins other retailers' rows that share the canonical master key.
    """
    if not cid:
        return ""
    raw = cid.strip()
    p = parse_cid(raw)
    if not p:
        return raw

    def seg(s: str) -> str:
        return re.sub(r"\s+", "", (s or "").strip()).upper()

    brand_u = seg(p["brand"])
    parent_raw = (p.get("parent_brand") or "").strip()
    parent_u = seg(parent_raw) if parent_raw else ""
    # Collapse duplicate house-brand parent to empty (matches master ``||``).
    parent_for_build = "" if (parent_u and parent_u == brand_u) else parent_raw

    wc = seg(p.get("wrapper_code"))
    wc = _COMPARISON_WRAPPER_ALIASES.get(wc, wc)

    parts: Dict[str, object] = {
        "brand": p["brand"],
        "parent_brand": parent_for_build,
        "line": p["line"],
        "vitola": p["vitola"],
        "vitola2": (p.get("vitola2") or "").strip() or p["vitola"],
        "size": p["size"],
        "wrapper_code": wc,
        "box_qty_str": p["box_qty_str"],
    }
    return build_cid(parts)


def slug_from_url(url: str) -> str:
    """Extract a search-friendly slug from a product URL."""
    try:
        path = urlparse(url).path.rstrip("/")
    except Exception:
        return ""
    slug = path.split("/")[-1] if "/" in path else path
    return slug.lower().replace("-", " ").replace("_", " ").replace("%20", " ")


def _normalize_text(s: str) -> str:
    return re.sub(r"[^a-z0-9\s.]", " ", (s or "").lower())


# Matches "5x52", "5.5x52", "5 x 52", "5.5 x 50" anywhere in a haystack.
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*x\s*(\d+)")

# Maximum length-in-inches difference between a CID's size and a size on the
# retailer page that we still treat as the same vitola. Retailers routinely
# round 5.5 to 5 (or vice versa) when they reprint manufacturer specs, so
# without tolerance the same physical cigar would score as a near-miss.
SIZE_LENGTH_TOLERANCE_IN = 0.5


def _parse_size(s: str) -> Optional[Tuple[float, int]]:
    """Return (length_inches, ring_gauge) for the first 'LxR' in ``s``.

    Returns None if no parseable size is present.
    """
    if not s:
        return None
    m = _SIZE_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(1)), int(m.group(2))
    except (ValueError, TypeError):
        return None


def _size_match(
    cid_size: str,
    haystack: str,
) -> Tuple[bool, bool]:
    """Compare a CID size against any size present in the haystack.

    Returns (is_match, is_exact). ``is_match`` is True when ring gauges agree
    and lengths are within ``SIZE_LENGTH_TOLERANCE_IN``. ``is_exact`` is True
    only when the length matches to the tenth of an inch (so callers can
    still distinguish 5.5x52 vs 5x52 if they want to).
    """
    cid_parsed = _parse_size(cid_size)
    if not cid_parsed:
        return False, False
    cid_len, cid_ring = cid_parsed
    for m in _SIZE_RE.finditer(haystack):
        try:
            url_len = float(m.group(1))
            url_ring = int(m.group(2))
        except (ValueError, TypeError):
            continue
        if cid_ring != url_ring:
            continue
        delta = abs(cid_len - url_len)
        if delta <= SIZE_LENGTH_TOLERANCE_IN:
            return True, delta < 0.05
    return False, False


def programmatic_score(
    cid_parts: Dict[str, str],
    url: str,
    title: Optional[str] = None,
) -> Tuple[float, Dict[str, bool]]:
    """Score how well a URL (and optional scraped title) matches a CID.

    Returns (score 0-1, details dict with per-component booleans). ``details``
    also includes ``size_exact`` to distinguish exact size matches from
    tolerance matches; ``size_match`` remains True for either case so the
    confidence buckets pick up both.
    """
    slug_text = slug_from_url(url)
    haystack = slug_text + " " + _normalize_text(title or "")

    brand = (cid_parts.get("brand") or "").lower().replace("_", " ")
    line_raw = (cid_parts.get("line") or "").lower().replace("_", " ")
    line_spaced = re.sub(r"(\d+)([a-z])", r"\1 \2", line_raw, flags=re.I)
    line_spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", line_spaced).lower()
    vitola = (cid_parts.get("vitola") or "").lower().replace("_", " ")
    wrapper_code = cid_parts.get("wrapper_code") or ""
    box_qty_str = cid_parts.get("box_qty_str") or ""
    size = (cid_parts.get("size") or "").lower()

    details = {
        "brand_match": False,
        "line_match": False,
        "vitola_match": False,
        "wrapper_match": False,
        "box_qty_match": False,
        "size_match": False,
        "size_exact": False,
    }

    score = 0.0
    # Vitola is what physically defines a cigar (Robusto vs Toro vs Torpedo).
    # Retailers often round the printed size (5.5"x52 vs 5"x52) for the same
    # SKU, so we weight vitola higher than size and treat size as a tiebreaker
    # rather than a primary signal.
    weights = {
        "brand": 0.25,
        "line": 0.30,
        "vitola": 0.22,
        "wrapper": 0.10,
        "box_qty": 0.07,
        "size": 0.06,
    }

    brand_words = [w for w in brand.split() if w]
    if brand_words:
        if all(w in haystack for w in brand_words):
            score += weights["brand"]
            details["brand_match"] = True
        elif any(w in haystack for w in brand_words if len(w) > 3):
            score += weights["brand"] * 0.5
            details["brand_match"] = True

    line_words = [w for w in line_spaced.split() if len(w) > 2]
    if line_words:
        matched = sum(1 for w in line_words if w in haystack)
        ratio = matched / len(line_words)
        if ratio >= 0.7:
            score += weights["line"]
            details["line_match"] = True
        elif ratio >= 0.4:
            score += weights["line"] * 0.5
            details["line_match"] = True

    vitola_words = [w for w in vitola.split() if len(w) > 2]
    if vitola_words:
        if all(w in haystack for w in vitola_words):
            score += weights["vitola"]
            details["vitola_match"] = True
        elif any(w in haystack for w in vitola_words):
            score += weights["vitola"] * 0.5
            details["vitola_match"] = True

    wrapper_names = WRAPPER_CODE_TO_NAMES.get(wrapper_code, [])
    if any(name in haystack for name in wrapper_names):
        score += weights["wrapper"]
        details["wrapper_match"] = True

    box_qty_num = re.search(r"\d+", box_qty_str)
    if box_qty_num:
        qty = box_qty_num.group()
        if re.search(rf"\bbox(?: of)? {qty}\b", haystack) or re.search(
            rf"\b{qty}[ -]?(count|pack|ct)\b", haystack
        ):
            score += weights["box_qty"]
            details["box_qty_match"] = True

    # Size: ring gauge must match exactly, length is allowed to drift by
    # SIZE_LENGTH_TOLERANCE_IN. Exact length matches get full weight; tolerance
    # matches get 60% so they still help but don't fully outweigh a vitola
    # mismatch on a near-duplicate.
    matched, exact = _size_match(size, haystack)
    if matched:
        score += weights["size"] if exact else weights["size"] * 0.6
        details["size_match"] = True
        details["size_exact"] = exact

    return min(score, 1.0), details


def _confidence_label(score: float, details: Dict[str, bool]) -> str:
    """Bucket a numeric score into HIGH / MEDIUM / LOW for UI use."""
    strong = details.get("brand_match") and details.get("line_match")
    if score >= 0.75 and strong:
        return "HIGH"
    if score >= 0.50 and strong:
        return "MEDIUM"
    if score >= 0.35:
        return "LOW"
    return "VERY_LOW"


def load_master_cigars(csv_path: Path) -> List[Dict[str, str]]:
    """Load master_cigars.csv into a list of plain dicts.

    Returns rows with normalized keys (lowercased, spaces -> underscores) plus
    the original CID parsed into convenient fields. Safe to cache.
    """
    if not csv_path.exists():
        return []
    out: List[Dict[str, str]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = (row.get("cigar_id") or "").strip()
            if not cid:
                continue
            parts = parse_cid(cid)
            if not parts:
                continue
            box_qty_str = parts["box_qty_str"]
            box_qty_int: Optional[int]
            m = re.search(r"\d+", box_qty_str)
            box_qty_int = int(m.group()) if m else None
            out.append({
                "cigar_id": cid,
                "brand": (row.get("Brand") or "").strip(),
                "line": (row.get("Line") or "").strip(),
                "vitola": (row.get("Vitola") or "").strip(),
                "wrapper": (row.get("Wrapper") or "").strip(),
                "wrapper_code": parts["wrapper_code"],
                "size": parts["size"],
                "box_qty": box_qty_int,
                "_parts": parts,
            })
    return out


def _norm_catalog_field(value: Optional[str]) -> str:
    """Lowercase, trim, collapse internal whitespace for human-field compare."""
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def find_unique_metadata_match(
    brand: str,
    line: str,
    vitola: str,
    box_qty: int,
    wrapper_bucket: Optional[str],
    master: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return the single master row that matches catalog identity fields, or None.

    This is the simple mental model for community proposals: the form asks
    for brand, line, vitola, box quantity, and (optionally) a wrapper bucket.
    Those fields are the same axes the master CSV is keyed on for humans.
    When they narrow to exactly one row, that row's ``cigar_id`` is the only
    sensible recommendation — no URL slug heuristics or title scoring required.

    ``wrapper_bucket`` should be one of the consumer bucket labels from
    ``app.wrapper_buckets`` (or empty / unknown → no wrapper filter).

    Returns a ``find_top_candidates``-shaped dict, or None when zero or many
    rows match (caller should fall back to URL+title scoring).
    """
    nb = _norm_catalog_field(brand)
    nl = _norm_catalog_field(line)
    nv = _norm_catalog_field(vitola)
    if not nb or not nl or not nv:
        return None
    try:
        bq = int(box_qty)
    except (TypeError, ValueError):
        return None
    if bq <= 0:
        return None

    allowed_codes: Optional[Set[str]] = None
    if wrapper_bucket and str(wrapper_bucket).strip():
        try:
            from app.wrapper_buckets import codes_for_bucket  # type: ignore

            ac = codes_for_bucket(wrapper_bucket.strip())
            if ac:
                allowed_codes = {c.upper() for c in ac}
        except Exception:
            allowed_codes = None

    matches: List[Dict[str, Any]] = []
    for row in master:
        try:
            row_bq = int(row.get("box_qty") or 0)
        except (TypeError, ValueError):
            continue
        if row_bq != bq:
            continue
        if _norm_catalog_field(row.get("brand")) != nb:
            continue
        if _norm_catalog_field(row.get("line")) != nl:
            continue
        if _norm_catalog_field(row.get("vitola")) != nv:
            continue
        wc = (str(row.get("wrapper_code") or "")).strip().upper()
        if allowed_codes is not None and wc and wc not in allowed_codes:
            continue
        matches.append(row)

    if len(matches) != 1:
        return None

    row = matches[0]
    details: Dict[str, bool] = {
        "brand_match": True,
        "line_match": True,
        "vitola_match": True,
        "metadata_unique_match": True,
    }
    return {
        "cigar_id": row["cigar_id"],
        "score": 1.0,
        "confidence": "HIGH",
        "details": details,
        "brand": row.get("brand"),
        "line": row.get("line"),
        "vitola": row.get("vitola"),
        "wrapper": row.get("wrapper"),
        "wrapper_code": row.get("wrapper_code"),
        "size": row.get("size"),
        "box_qty": row.get("box_qty"),
    }


def find_top_candidates(
    url: str,
    title: Optional[str],
    master: Iterable[Dict[str, str]],
    limit: int = 5,
    min_score: float = 0.20,
) -> List[Dict[str, object]]:
    """Score every master row against the URL+title and return the top N.

    Output items have: cigar_id, score, confidence, details, brand, line,
    vitola, wrapper, wrapper_code, size, box_qty.
    """
    scored: List[Tuple[float, Dict[str, object]]] = []
    for row in master:
        parts = row.get("_parts") or parse_cid(row.get("cigar_id", ""))
        if not parts:
            continue
        score, details = programmatic_score(parts, url, title)
        if score < min_score:
            continue
        scored.append((score, {
            "cigar_id": row["cigar_id"],
            "score": round(score, 3),
            "confidence": _confidence_label(score, details),
            "details": details,
            "brand": row.get("brand"),
            "line": row.get("line"),
            "vitola": row.get("vitola"),
            "wrapper": row.get("wrapper"),
            "wrapper_code": row.get("wrapper_code"),
            "size": row.get("size"),
            "box_qty": row.get("box_qty"),
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def hostname_to_retailer_key(
    hostname: str,
    registry: Dict[str, str],
) -> Optional[str]:
    """Look up a retailer_key from a request hostname.

    Tries exact match, then with/without leading 'www.', then suffix matching
    (so 'foo.bar.shopify.com' resolves to 'bar.shopify.com' if registered).
    """
    if not hostname:
        return None
    h = hostname.lower().strip()
    if h in registry:
        return registry[h]
    if h.startswith("www."):
        stripped = h[4:]
        if stripped in registry:
            return registry[stripped]
    else:
        prefixed = "www." + h
        if prefixed in registry:
            return registry[prefixed]

    # Suffix match (rare, but covers subdomain variants)
    for known_host, key in registry.items():
        if h.endswith("." + known_host) or known_host.endswith("." + h):
            return key

    return None


# Hostnames of well-known affiliate / tracking networks that retailers
# wrap product URLs in. These show up in CSVs as the URL's hostname
# even though the actual retailer is on a different domain. The
# registry builder must skip them, otherwise it'll register e.g.
# anrdoezrs.net → gothamcigars instead of gothamcigars.com → gothamcigars
# and the consumer/operator extension hostname-gating won't recognize
# the real retailer page.
_AFFILIATE_HOSTNAMES = frozenset({
    # Commission Junction (CJ) — most common in the cigar industry
    "anrdoezrs.net", "www.anrdoezrs.net",
    "kqzyfj.com",    "www.kqzyfj.com",
    "dpbolvw.net",   "www.dpbolvw.net",
    "jdoqocy.com",   "www.jdoqocy.com",
    "tkqlhce.com",   "www.tkqlhce.com",
    "emjcd.com",     "www.emjcd.com",
    "qksrv.com",     "www.qksrv.com",
    "qksrv.net",     "www.qksrv.net",
    "lduhtrp.net",   "www.lduhtrp.net",
    # Common URL shorteners
    "bit.ly", "t.co", "goo.gl", "tinyurl.com",
})


def _is_affiliate_host(host: str) -> bool:
    h = (host or "").lower()
    if h in _AFFILIATE_HOSTNAMES:
        return True
    # Soft-match any subdomain of the known networks (e.g.
    # tracking.anrdoezrs.net) without forcing the exact list above.
    for net in ("anrdoezrs.net", "kqzyfj.com", "dpbolvw.net",
                "jdoqocy.com", "tkqlhce.com", "emjcd.com",
                "qksrv.com", "qksrv.net", "lduhtrp.net"):
        if h.endswith("." + net) or h == net:
            return True
    return False


def build_retailer_registry(
    static_data_dir: Path,
    extra_hosts: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Scan static/data/*.csv and build a hostname -> retailer_key map.

    Skips files containing DORMANT/BROKEN/backup in their name. Uses the
    hostname of the first non-affiliate http(s) URL in each CSV — affiliate
    networks (CJ, etc.) are wrappers around the real retailer URL and
    must not be registered as the retailer's own host.

    ``extra_hosts`` is an optional ``{hostname: retailer_key}`` mapping
    merged into the registry. This is the mechanism for registering
    anti-bot retailers whose CSV is empty (no URL row to infer the
    hostname from) — see app.main.get_blocked_retailer_hosts().
    """
    registry: Dict[str, str] = {}
    if static_data_dir.exists():
        for csv_file in sorted(static_data_dir.glob("*.csv")):
            name = csv_file.stem
            if any(tok in name for tok in ("DORMANT", "BROKEN", "backup")):
                continue
            try:
                with csv_file.open("r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    if "url" not in (reader.fieldnames or []):
                        continue
                    for row in reader:
                        u = (row.get("url") or "").strip()
                        if not u.startswith("http"):
                            continue
                        host = urlparse(u).hostname
                        if not host:
                            continue
                        host = host.lower()
                        if _is_affiliate_host(host):
                            # Affiliate wrapper — try the next row.
                            continue
                        registry.setdefault(host, name)
                        if host.startswith("www."):
                            registry.setdefault(host[4:], name)
                        else:
                            registry.setdefault("www." + host, name)
                        break
            except Exception:
                continue
    # Merge explicit blocked-retailer hostnames. setdefault() means CSV
    # entries win on conflict — defensive choice in case an extractor
    # comes online later and the CSV has data we should trust.
    if extra_hosts:
        for host, key in extra_hosts.items():
            h = (host or "").strip().lower()
            if not h or not key:
                continue
            registry.setdefault(h, key)
            if h.startswith("www."):
                registry.setdefault(h[4:], key)
            else:
                registry.setdefault("www." + h, key)
    return registry


def merge_cid_into_url_index(
    index: Dict[str, Tuple[str, List[str]]],
    url: str,
    retailer_key: str,
    cid: str,
) -> None:
    """Attach one more CID to a canonical product URL (multi-SKU pages).

    Same retailer_key only — if another retailer already owns the URL slot,
    we skip (cross-retailer collisions on identical canonical URLs are rare
    and need human resolution).
    """
    if not url or not retailer_key or not cid:
        return
    if url not in index:
        index[url] = (retailer_key, [cid])
        return
    rk, cids = index[url]
    if rk != retailer_key:
        return
    if cid not in cids:
        cids.append(cid)


def url_index_entry_cids(
    entry: Optional[Tuple[Any, ...]],
) -> Tuple[Optional[str], List[str]]:
    """Normalize a url_index cache entry to (retailer_key, [cigar_id, ...]).

    Accepts the modern ``(retailer_key, [cid, ...])`` shape and the legacy
    ``(retailer_key, single_cid_str)`` tuple left over from older in-memory
    overlays.
    """
    if not entry:
        return None, []
    rk = entry[0]
    if rk is None:
        return None, []
    tail = entry[1] if len(entry) > 1 else None
    if isinstance(tail, list):
        return rk, [c for c in tail if isinstance(c, str) and c]
    if isinstance(tail, str) and tail:
        return rk, [tail]
    return rk, []


def load_retailer_url_index(
    static_data_dir: Path,
    retailers: Optional[Iterable[str]] = None,
) -> Dict[str, Tuple[str, List[str]]]:
    """Build ``{canonical_url: (retailer_key, [cigar_id, ...])}`` from CSVs.

    Multiple CSV rows may share the same canonical URL (e.g. one PDP for
    several box SKUs). All distinct ``cigar_id`` values are collected so
    the consumer extension can offer a per-URL picker.
    """
    index: Dict[str, Tuple[str, List[str]]] = {}
    if not static_data_dir.exists():
        return index
    keys = set(retailers) if retailers else None
    for csv_file in sorted(static_data_dir.glob("*.csv")):
        name = csv_file.stem
        if any(tok in name for tok in ("DORMANT", "BROKEN", "backup")):
            continue
        if keys is not None and name not in keys:
            continue
        try:
            with csv_file.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if "url" not in (reader.fieldnames or []) or "cigar_id" not in (reader.fieldnames or []):
                    continue
                for row in reader:
                    u = (row.get("url") or "").strip()
                    cid = (row.get("cigar_id") or "").strip()
                    if u and cid:
                        merge_cid_into_url_index(
                            index,
                            canonicalize_url(u),
                            name,
                            cid,
                        )
        except Exception:
            continue
    return index
