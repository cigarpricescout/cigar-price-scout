"""
Standalone CID matching primitives for the URL → CID Chrome extension flow.

This module deliberately has zero non-stdlib dependencies (no anthropic, no
pandas) so it is safe to import inside the FastAPI app on Railway. The scoring
logic mirrors `tools/ai/url_discoverer.py` so the extension and the weekly
discovery agent rank candidates the same way.

Public surface:
    parse_cid(cid)                       -> dict | None
    build_cid(parts)                     -> str
    slug_from_url(url)                   -> str
    programmatic_score(cid_parts, url, title=None) -> (score, details)
    load_master_cigars(csv_path)         -> list[dict]
    find_top_candidates(url, title, master, limit=5) -> list[dict]
    hostname_to_retailer_key(hostname, registry) -> str | None
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

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

    return "|".join([
        cid_part(parts.get("brand")),
        cid_part(parts.get("parent_brand")) or cid_part(parts.get("brand")),
        cid_part(parts.get("line")),
        cid_part(parts.get("vitola")),
        cid_part(parts.get("vitola2")) or cid_part(parts.get("vitola")),
        cid_size(parts.get("size")),
        cid_part(parts.get("wrapper_code")),
        box,
    ])


def slug_from_url(url: str) -> str:
    """Extract a search-friendly slug from a product URL."""
    try:
        path = urlparse(url).path.rstrip("/")
    except Exception:
        return ""
    slug = path.split("/")[-1] if "/" in path else path
    return slug.lower().replace("-", " ").replace("_", " ").replace("%20", " ")


def _normalize_text(s: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())


def programmatic_score(
    cid_parts: Dict[str, str],
    url: str,
    title: Optional[str] = None,
) -> Tuple[float, Dict[str, bool]]:
    """Score how well a URL (and optional scraped title) matches a CID.

    Returns (score 0-1, details dict with per-component booleans).
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
    }

    score = 0.0
    weights = {
        "brand": 0.25,
        "line": 0.30,
        "vitola": 0.18,
        "wrapper": 0.10,
        "box_qty": 0.07,
        "size": 0.10,
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

    # Size match (e.g. "6x50" -> look for "6 x 50" or "6x50")
    if size and "x" in size:
        size_compact = size.replace(" ", "")
        size_spaced = re.sub(r"x", " x ", size)
        if size_compact in haystack.replace(" ", "") or size_spaced in haystack:
            score += weights["size"]
            details["size_match"] = True

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


def build_retailer_registry(static_data_dir: Path) -> Dict[str, str]:
    """Scan static/data/*.csv and build a hostname -> retailer_key map.

    Skips files containing DORMANT/BROKEN/backup in their name. Uses the
    hostname of the first valid http(s) URL in each CSV.
    """
    registry: Dict[str, str] = {}
    if not static_data_dir.exists():
        return registry
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
                    if u.startswith("http"):
                        host = urlparse(u).hostname
                        if host:
                            host = host.lower()
                            registry.setdefault(host, name)
                            if host.startswith("www."):
                                registry.setdefault(host[4:], name)
                            else:
                                registry.setdefault("www." + host, name)
                        break
        except Exception:
            continue
    return registry


def load_retailer_url_index(
    static_data_dir: Path,
    retailers: Optional[Iterable[str]] = None,
) -> Dict[str, Tuple[str, str]]:
    """Build a {url: (retailer_key, cigar_id)} index from per-retailer CSVs.

    Used by /api/admin/url-status to detect URLs that are already published
    in the live data, regardless of staging state.
    """
    index: Dict[str, Tuple[str, str]] = {}
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
                        index[u] = (name, cid)
        except Exception:
            continue
    return index
