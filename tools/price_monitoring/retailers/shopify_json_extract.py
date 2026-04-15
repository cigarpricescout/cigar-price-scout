"""
Shared helpers for Shopify storefront JSON API (/products/{handle}.json).

Avoids HTML scraping and many bot challenges when the public JSON endpoint is enabled.
Used by iHeart-style extractors and retailers that migrated to Shopify.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def product_handle_from_url(url: str) -> Optional[str]:
    m = re.search(r"/products/([^/?#]+)", url, re.I)
    return m.group(1) if m else None


def fetch_shopify_product(url: str, delay_s: float = 0.25) -> Optional[dict]:
    """GET .../products/{handle}.json and return the product dict, or None."""
    if delay_s:
        time.sleep(delay_s)
    parsed = urlparse(url)
    handle = product_handle_from_url(url)
    if not handle or not parsed.netloc:
        return None
    scheme = parsed.scheme or "https"
    json_url = f"{scheme}://{parsed.netloc}/products/{handle}.json"
    try:
        resp = requests.get(json_url, headers={"User-Agent": _DEFAULT_UA}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("product") or None
    except Exception:
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


def pick_variant_box_default(variants: List[dict]) -> Optional[dict]:
    """Prefer a variant whose title mentions box quantity; else first."""
    if not variants:
        return None
    for v in variants:
        title = (v.get("title") or "").lower()
        if "box" in title:
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
        price = float(variant.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0
    compare = variant.get("compare_at_price")
    try:
        original = float(compare) if compare not in (None, "") else None
    except (TypeError, ValueError):
        original = None

    title = variant.get("title") or ""
    box_qty = None
    m = re.search(r"box of (\d+)", title, re.I)
    if m:
        box_qty = int(m.group(1))

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
    if moms_style_variants and (target_vitola or target_packaging):
        v = pick_variant_for_moms(variants, target_vitola, target_packaging)
    else:
        v = pick_variant_box_default(variants)
    if not v:
        return None
    out = variant_to_price_result(product, v)
    out["target_found"] = bool(out.get("price"))
    return out
