"""
Shared helpers for Shopify storefront JSON API (/products/{handle}.json).

Avoids HTML scraping and many bot challenges when the public JSON endpoint is enabled.
Used by iHeart-style extractors and retailers that migrated to Shopify.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def product_handle_from_url(url: str) -> Optional[str]:
    m = re.search(r"/products/([^/?#]+)", url, re.I)
    return m.group(1) if m else None


def _variant_id_from_url(url: str) -> Optional[str]:
    q = parse_qs(urlparse(url).query)
    vid = (q.get("variant") or [None])[0]
    return str(vid) if vid else None


def _price_to_dollars(raw: Any) -> float:
    """Shopify .json prices are decimal strings. The .js endpoint uses integer cents."""
    if raw is None or raw == "":
        return 0.0
    if isinstance(raw, int):
        return raw / 100.0
    text = str(raw).strip()
    if text.isdigit():
        return int(text) / 100.0
    return float(text)


def fetch_shopify_product(url: str, delay_s: float = 0.25) -> Optional[dict]:
    """GET the public product JSON and return the product dict, or None.

    Tries /products/{handle}.json (dollar strings) then .js (integer cents).
    """
    if delay_s:
        time.sleep(delay_s)
    parsed = urlparse(url)
    handle = product_handle_from_url(url)
    if not handle or not parsed.netloc:
        return None
    scheme = parsed.scheme or "https"
    headers = {"User-Agent": _DEFAULT_UA, "Accept": "application/json"}
    for suffix in (".json", ".js"):
        endpoint = f"{scheme}://{parsed.netloc}/products/{handle}{suffix}"
        try:
            resp = requests.get(endpoint, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            product = data.get("product") if isinstance(data, dict) and "product" in data else data
            if isinstance(product, dict) and product.get("variants"):
                return product
        except Exception:
            continue
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def pick_variant_for_moms(
    variants: List[dict],
    target_vitola: Optional[str] = None,
    target_packaging: Optional[str] = None,
) -> Optional[dict]:
    """Match Hemingway-style variant lines (option1 / option2 or combined title)."""
    if not variants:
        return None
    tv = _norm(target_vitola) if target_vitola else ""
    tp = _norm(target_packaging) if target_packaging else ""

    def score(v: dict) -> int:
        t = _norm(v.get("title") or "")
        o1 = _norm(v.get("option1") or "")
        o2 = _norm(v.get("option2") or "")
        blob = f"{t} {o1} {o2}"
        s = 0
        if "box" in blob:
            s += 10
        if tv and tv in blob:
            s += 50
        if tp and tp in blob:
            s += 50
        return s

    if tv or tp:
        ranked = sorted(variants, key=score, reverse=True)
        if score(ranked[0]) > 0:
            return ranked[0]

    for v in variants:
        blob = _norm(f"{v.get('title','')} {v.get('option1','')} {v.get('option2','')}")
        if "box" in blob:
            return v
    return variants[0]


def _variant_blob(v: dict) -> str:
    return _norm(
        f"{v.get('title') or ''} {v.get('option1') or ''} {v.get('option2') or ''} {v.get('option3') or ''}"
    )


def _box_qty_from_variant(v: dict) -> Optional[int]:
    blob = _variant_blob(v)
    m = re.search(r"box(?:\s+of)?\s+(\d+)", blob, re.I)
    return int(m.group(1)) if m else None


def pick_variant_box_default(
    variants: List[dict],
    variant_id: Optional[str] = None,
) -> Optional[dict]:
    """Prefer the URL's variant, otherwise the largest box (not a 5-pack or single)."""
    if not variants:
        return None
    if variant_id:
        for v in variants:
            if str(v.get("id")) == str(variant_id):
                return v
    boxes = [(qty, v) for v in variants if (qty := _box_qty_from_variant(v))]
    if boxes:
        boxes.sort(key=lambda item: item[0], reverse=True)
        return boxes[0][1]
    for v in variants:
        if "box" in _variant_blob(v):
            return v
    return variants[0]


def variant_to_price_result(
    product: dict,
    variant: dict,
    *,
    discount_from_compare: bool = True,
) -> Dict[str, Any]:
    """Normalize Shopify variant fields into extractor-style dict."""
    try:
        price = _price_to_dollars(variant.get("price"))
    except (TypeError, ValueError):
        price = 0.0
    compare = variant.get("compare_at_price")
    try:
        original = _price_to_dollars(compare) if compare not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        original = None
    if original is not None and original <= 0:
        original = None

    box_qty = _box_qty_from_variant(variant)

    # Inventory: older public JSON may omit "available"; assume purchasable if priced.
    inv_available = variant.get("available")
    if inv_available is None:
        in_stock = price > 0
    else:
        in_stock = bool(inv_available)

    discount_percent = None
    if discount_from_compare and original and original > price > 0:
        discount_percent = round((1 - price / original) * 100, 1)

    return {
        "success": price > 0,
        "product_title": product.get("title"),
        "price": price if price > 0 else None,
        "original_price": original,
        "discount_percent": discount_percent,
        "in_stock": in_stock,
        "box_quantity": box_qty,
        "error": None if price > 0 else "no price on variant",
    }


def extract_shopify_product_url(
    url: str,
    *,
    target_vitola: Optional[str] = None,
    target_packaging: Optional[str] = None,
    moms_style_variants: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Full pipeline: URL -> product JSON -> pick variant -> price dict.
    moms_style_variants: use pick_variant_for_moms when variant titles carry vitola/pack rows.
    """
    product = fetch_shopify_product(url)
    if not product:
        return None
    variants = product.get("variants") or []
    variant_id = _variant_id_from_url(url)
    if variant_id:
        v = pick_variant_box_default(variants, variant_id=variant_id)
    elif moms_style_variants and (target_vitola or target_packaging):
        v = pick_variant_for_moms(variants, target_vitola, target_packaging)
    else:
        v = pick_variant_box_default(variants)
    if not v:
        return None
    out = variant_to_price_result(product, v)
    out["target_found"] = bool(out.get("price"))
    return out
