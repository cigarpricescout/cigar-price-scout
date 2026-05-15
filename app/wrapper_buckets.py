"""
Consumer-friendly wrapper buckets.

CIDs encode wrappers as one of ~14 canonical codes (CT, MAD, HAB, NAT, SUN,
CAM, CORO, MEX, DOM, CL, MD, ECU, CON, NIC). Consumers don't know those
codes — they know "Natural", "Maduro", "Habano", "Sun Grown". This module
maps the four consumer buckets to the canonical codes so the consumer
Chrome extension can ask the user a friendly question and the operator's
review surface can still narrow CID candidates precisely.

The buckets were chosen from a wrapper-distribution audit of the master
catalog: each one covers an industry-recognized cluster, and together they
cover ~100% of the catalog. See AGENTS.md §7 for the CID format.

Typical usage:

    from app.wrapper_buckets import codes_for_bucket, bucket_for_code
    candidate_codes = codes_for_bucket("Maduro")  # -> {"MAD","MEX","MD","DOM"}
    # use candidate_codes to narrow brand×line×vitola CID matches
"""
from __future__ import annotations

from typing import Dict, Optional, Set

# Public label for the light-wrappers cluster (incl. Cameroon, which is
# extremely common on Arturo Fuente lines such as Hemingway). Older builds
# used the shorter name — see _LEGACY_BUCKET_ALIASES.
NATURAL_LIGHT_WRAPPER_BUCKET = "Natural / Connecticut / Cameroon"

# Order matters — UI surfaces iterate this dict and the order is what the
# consumer sees in the <select>. "Not sure" is implied as the empty/None case;
# we don't store it as a real bucket.
WRAPPER_BUCKETS: Dict[str, Set[str]] = {
    NATURAL_LIGHT_WRAPPER_BUCKET: {"NAT", "CT", "CAM", "CL"},
    "Habano":                     {"HAB", "CORO", "CON"},
    "Sun Grown":                  {"SUN", "ECU", "NIC"},
    "Maduro":                     {"MAD", "MEX", "MD", "DOM"},
}

# Older submissions / CSV notes may still carry the pre-Cameroon label.
_LEGACY_BUCKET_ALIASES: Dict[str, str] = {
    "Natural / Connecticut": NATURAL_LIGHT_WRAPPER_BUCKET,
}

# Inverse index, built once at import time. Not exposed; consumers should
# call bucket_for_code() instead so we can change the storage shape later
# without touching call sites.
_CODE_TO_BUCKET: Dict[str, str] = {
    code: bucket
    for bucket, codes in WRAPPER_BUCKETS.items()
    for code in codes
}

# Keyword patterns the consumer scraper uses to pre-fill the wrapper select
# from product page text. Order is intentional: more specific terms (e.g.
# "sun grown") must come before broader terms ("natural") because the first
# match wins.
SCRAPE_KEYWORDS = [
    # phrase, bucket
    ("sun grown",           "Sun Grown"),
    ("sungrown",            "Sun Grown"),
    ("ecuadorian sumatra",  "Sun Grown"),
    ("maduro",              "Maduro"),
    ("oscuro",              "Maduro"),
    ("san andres",          "Maduro"),
    ("san andr",            "Maduro"),   # handles "san andr�s"/"san andrés"
    ("broadleaf",           "Maduro"),
    ("habano",              "Habano"),
    ("corojo",              "Habano"),
    ("connecticut",         NATURAL_LIGHT_WRAPPER_BUCKET),
    ("cameroon",            NATURAL_LIGHT_WRAPPER_BUCKET),
    ("claro",               NATURAL_LIGHT_WRAPPER_BUCKET),
    ("natural",             NATURAL_LIGHT_WRAPPER_BUCKET),
]


def bucket_names() -> list:
    """Ordered list of bucket names for UI rendering."""
    return list(WRAPPER_BUCKETS.keys())


def codes_for_bucket(bucket: Optional[str]) -> Set[str]:
    """Return the set of canonical wrapper codes that belong to a bucket.

    Returns an empty set when ``bucket`` is None / unknown — callers should
    treat that as "no filter" (consumer picked 'Not sure').
    """
    if not bucket:
        return set()
    b = (bucket or "").strip()
    b = _LEGACY_BUCKET_ALIASES.get(b, b)
    return set(WRAPPER_BUCKETS.get(b, set()))


def bucket_for_code(code: Optional[str]) -> Optional[str]:
    """Return the bucket a canonical wrapper code belongs to (or None)."""
    if not code:
        return None
    return _CODE_TO_BUCKET.get(code.strip().upper())


def detect_bucket_from_text(text: Optional[str]) -> Optional[str]:
    """Best-effort wrapper-bucket detection from arbitrary product page text.

    Used by the consumer extension's scrape pre-fill so most of the time the
    user just confirms the dropdown choice rather than picking from scratch.
    """
    if not text:
        return None
    haystack = str(text).lower()
    for phrase, bucket in SCRAPE_KEYWORDS:
        if phrase in haystack:
            return bucket
    return None
