"""
Generic Shopify storefront extractor for any retailer using /products/{handle}.json.

Use when a site is on Shopify but does not need custom HTML logic.
"""

from __future__ import annotations

from typing import Any, Dict

try:
    from .shopify_json_extract import extract_shopify_product_url
except ImportError:
    from shopify_json_extract import extract_shopify_product_url


def extract_shopify_store_data(url: str) -> Dict[str, Any]:
    """Return price/stock dict compatible with run_weekly_discovery normalization."""
    shop = extract_shopify_product_url(url, moms_style_variants=False)
    if not shop or not shop.get("price"):
        return {
            "success": False,
            "price": None,
            "in_stock": False,
            "error": shop.get("error") if shop else "shopify json unavailable",
        }
    return {
        "success": True,
        "price": shop["price"],
        "in_stock": shop.get("in_stock"),
        "error": None,
    }
