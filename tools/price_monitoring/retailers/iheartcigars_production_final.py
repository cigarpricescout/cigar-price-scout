"""
iHeartCigars Extractor - Shopify JSON API
Uses /products/{handle}.json for reliable variant-level pricing.
Falls back to HTML scraping if the JSON endpoint fails.

COMPLIANCE: 3s delay between requests
"""

import requests
from bs4 import BeautifulSoup
import time
import re
from urllib.parse import urlparse


def _get_product_handle(url):
    """Extract the Shopify product handle from any iHeartCigars product URL."""
    path = urlparse(url).path
    match = re.search(r'/products/([^/?#]+)', path)
    return match.group(1) if match else None


def _extract_via_shopify_json(handle):
    """Primary extraction method: Shopify product JSON API."""
    json_url = f"https://iheartcigars.com/products/{handle}.json"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }

    resp = requests.get(json_url, headers=headers, timeout=10)
    resp.raise_for_status()
    product = resp.json().get('product', {})
    variants = product.get('variants', [])

    if not variants:
        return None

    box_variant = None
    for v in variants:
        title = (v.get('title') or '').lower()
        if 'box' in title:
            box_variant = v
            break

    if not box_variant:
        box_variant = variants[0]

    price = float(box_variant.get('price', 0))
    compare_at = box_variant.get('compare_at_price')
    retail_price = float(compare_at) if compare_at else None
    available = box_variant.get('available')

    box_qty = None
    title_text = (box_variant.get('title') or '')
    qty_match = re.search(r'(\d+)', title_text)
    if qty_match and 'box' in title_text.lower():
        box_qty = int(qty_match.group(1))

    if box_qty is None:
        body = product.get('body_html') or ''
        body_match = re.search(r'box of (\d+)', body, re.I)
        if body_match:
            box_qty = int(body_match.group(1))

    if box_qty is None:
        full_title = product.get('title') or ''
        title_match = re.search(r'box of (\d+)', full_title, re.I)
        if title_match:
            box_qty = int(title_match.group(1))

    in_stock = available if available is not None else True

    print(f"    [JSON] handle={handle} variant='{box_variant.get('title')}' "
          f"price=${price} retail=${retail_price} qty={box_qty} stock={in_stock}")

    return {
        'price': price if price > 0 else None,
        'retail_price': retail_price,
        'box_qty': box_qty or 25,
        'in_stock': in_stock,
    }


def _extract_via_html(url):
    """Fallback: scrape the rendered HTML page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, 'html.parser')

    current_price = None
    retail_price = None
    el = soup.select_one('.product-price-current')
    if el:
        m = re.search(r'\$([\d,]+(?:\.\d{2})?)', el.get_text())
        if m:
            current_price = float(m.group(1).replace(',', ''))
    el_list = soup.select_one('.product-price-list')
    if el_list:
        m = re.search(r'\$([\d,]+(?:\.\d{2})?)', el_list.get_text())
        if m:
            retail_price = float(m.group(1).replace(',', ''))

    page_text = soup.get_text().lower()
    in_stock = True
    for indicator in ['sold out', 'out of stock', 'currently unavailable']:
        if indicator in page_text:
            in_stock = False
            break

    box_qty = 25
    qty_matches = re.findall(r'box of (\d+)', soup.get_text(), re.I)
    if qty_matches:
        box_qty = int(qty_matches[0])

    print(f"    [HTML] price=${current_price} retail=${retail_price} qty={box_qty} stock={in_stock}")

    return {
        'price': current_price,
        'retail_price': retail_price,
        'box_qty': box_qty,
        'in_stock': in_stock,
    }


def extract_iheartcigars_data_production(url):
    """
    iHeartCigars extractor — Shopify JSON primary, HTML fallback.
    Always targets the 'Box' variant when multiple options exist.
    """
    time.sleep(3.0)

    handle = _get_product_handle(url)
    if not handle:
        print(f"    [ERROR] Could not parse product handle from URL: {url}")
        return None

    try:
        result = _extract_via_shopify_json(handle)
        if result and result['price']:
            return result
        print(f"    [WARN] JSON returned no price, falling back to HTML")
    except Exception as e:
        print(f"    [WARN] JSON failed ({e}), falling back to HTML")

    try:
        return _extract_via_html(url)
    except Exception as e:
        print(f"    [ERROR] HTML fallback also failed: {e}")
        return None


if __name__ == "__main__":
    test_urls = [
        ('Liga Privada No.9 Robusto', 'https://iheartcigars.com/products/no-9-robusto'),
        ('Opus X Belicoso XXX', 'https://iheartcigars.com/products/opusx-belicosos-xxx'),
        ('Hemingway Classic', 'https://iheartcigars.com/products/hemingway-classic-natural'),
        ('VSG Robusto', 'https://iheartcigars.com/products/vsg-robusto'),
    ]

    print("iHeartCigars Extractor Test")
    print("=" * 60)
    for name, url in test_urls:
        print(f"\n--- {name} ---")
        r = extract_iheartcigars_data_production(url)
        if r:
            stock = "In Stock" if r['in_stock'] else "Out of Stock"
            print(f"  -> ${r['price']} | Box {r['box_qty']} | {stock}")
        else:
            print("  -> FAILED")
    print("\n" + "=" * 60)
