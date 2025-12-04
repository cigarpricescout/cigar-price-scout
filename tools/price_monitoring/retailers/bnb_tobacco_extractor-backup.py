"""
BnB Tobacco Extractor - ULTRA-PREMIUM VERSION
Handles box prices from $100 to $5000+ for premium and ultra-premium cigars
Proper validation for Opus X, aged Cubans, limited editions, etc.

Key Features:
1. No upper price limit (handles $2000+ boxes)
2. Variant-specific extraction
3. Multiple extraction strategies
4. Proper validation (only rejects <$100)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import json
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs

def extract_bnb_tobacco_data(url: str, target_vitola: str = None, target_packaging: str = "Box of 25") -> Dict:
    """
    Extract data from BnB Tobacco URL with variant-specific targeting
    Handles ultra-premium pricing (no upper limit)
    """
    try:
        variant_id = _extract_variant_id(url)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title_elem = soup.find(['h1', 'h2'], class_=re.compile(r'title|product', re.I))
        product_title = title_elem.get_text().strip() if title_elem else "Unknown Product"
        
        # Extract pricing using multiple strategies
        pricing_data = _extract_variant_pricing(soup, variant_id, url)
        
        stock_status = _extract_stock_status(soup)
        box_qty = _extract_box_quantity_from_page(soup, target_packaging)
        
        # Validate pricing - only reject unreasonably low prices (under $100)
        current_price = pricing_data.get('current_price')
        if current_price and current_price < 100:
            print(f"  [WARNING] Rejected unreasonable box price: ${current_price} (too low for box)")
            # Try alternative pricing extraction
            alternative_price = _extract_alternative_pricing(soup, variant_id)
            if alternative_price and alternative_price >= 100:
                current_price = alternative_price
                pricing_data['current_price'] = current_price
            else:
                current_price = None
                pricing_data['current_price'] = None
        elif current_price:
            print(f"  [INFO] Accepted box price: ${current_price}")
        
        return {
            'success': True,
            'product_title': product_title,
            'price': current_price,
            'original_price': pricing_data.get('original_price'),
            'discount_percent': pricing_data.get('discount_percent'),
            'in_stock': stock_status,
            'box_quantity': box_qty,
            'variant_id': variant_id,
            'has_target_config': bool(current_price and box_qty),
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'product_title': None,
            'price': None,
            'original_price': None,
            'discount_percent': None,
            'in_stock': False,
            'box_quantity': None,
            'variant_id': None,
            'has_target_config': False,
            'error': str(e)
        }


def _extract_variant_id(url: str) -> Optional[str]:
    """Extract variant ID from BnB Tobacco URL"""
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        variant_id = query_params.get('variant', [None])[0]
        return variant_id
    except:
        return None


def _extract_variant_pricing(soup: BeautifulSoup, variant_id: str = None, url: str = None) -> dict:
    """Extract pricing using multiple strategies focusing on variant-specific data"""
    
    current_price = None
    original_price = None
    discount_percent = None
    
    # Strategy 1: Shopify product JSON with variant data
    if variant_id:
        current_price = _extract_from_shopify_json(soup, variant_id)
    
    # Strategy 2: Current selected variant price in page elements
    if not current_price:
        current_price = _extract_from_price_elements(soup)
    
    # Strategy 3: Data attributes or meta tags
    if not current_price:
        current_price = _extract_from_meta_data(soup)
    
    # Strategy 4: Structured data (JSON-LD)
    if not current_price:
        current_price = _extract_from_structured_data(soup)
    
    # Extract original/compare price
    original_price = _extract_original_price(soup)
    
    # Calculate discount percentage
    if current_price and original_price and original_price > current_price:
        discount_percent = ((original_price - current_price) / original_price) * 100
    
    return {
        'current_price': current_price,
        'original_price': original_price,
        'discount_percent': discount_percent
    }


def _extract_from_shopify_json(soup: BeautifulSoup, variant_id: str) -> Optional[float]:
    """Extract price from Shopify product JSON data"""
    try:
        script_tags = soup.find_all('script', string=re.compile(r'product|variant', re.I))
        
        for script in script_tags:
            script_content = script.get_text()
            
            if variant_id in script_content:
                # Pattern for variant-specific pricing
                variant_pattern = rf'["\']?{variant_id}["\']?\s*:\s*{{[^}}]*["\']?price["\']?\s*:\s*["\']?(\d+)["\']?'
                match = re.search(variant_pattern, script_content)
                if match:
                    price_cents = int(match.group(1))
                    price_dollars = price_cents / 100
                    if price_dollars >= 50:  # Only minimum check
                        return price_dollars
                
                # Alternative pattern for variant arrays
                variant_array_pattern = rf'{{"[^"]*variant[^"]*"[^}}]*"id":\s*{variant_id}[^}}]*"price":\s*(\d+)'
                match = re.search(variant_array_pattern, script_content)
                if match:
                    price_cents = int(match.group(1))
                    price_dollars = price_cents / 100
                    if price_dollars >= 50:
                        return price_dollars
        
        return None
        
    except Exception:
        return None


def _extract_from_price_elements(soup: BeautifulSoup) -> Optional[float]:
    """Extract price from standard price elements"""
    try:
        price_selectors = [
            '.price',
            '.product-price', 
            '.current-price',
            '.money',
            '[class*="price"]',
            '[data-price]'
        ]
        
        for selector in price_selectors:
            elements = soup.select(selector)
            for elem in elements:
                # Check data attributes first
                if elem.has_attr('data-price'):
                    try:
                        price = float(elem['data-price'])
                        if price >= 100:  # Only minimum validation for boxes
                            return price
                    except:
                        pass
                
                # Check text content
                text = elem.get_text().strip()
                price_match = re.search(r'\$(\d+\.?\d*)', text)
                if price_match:
                    try:
                        price = float(price_match.group(1))
                        if price >= 100:  # Only minimum validation for boxes
                            return price
                    except:
                        continue
        
        return None
        
    except Exception:
        return None


def _extract_from_meta_data(soup: BeautifulSoup) -> Optional[float]:
    """Extract price from meta tags and data attributes"""
    try:
        # Check meta tags
        meta_price = soup.find('meta', attrs={'property': 'product:price:amount'})
        if meta_price and meta_price.get('content'):
            try:
                price = float(meta_price['content'])
                if price >= 100:
                    return price
            except:
                pass
        
        # Check data attributes on product area
        product_area = soup.find(['div', 'section'], class_=re.compile(r'product', re.I))
        if product_area:
            for attr in ['data-price', 'data-product-price', 'data-variant-price']:
                if product_area.has_attr(attr):
                    try:
                        price = float(product_area[attr])
                        if price >= 100:
                            return price
                    except:
                        pass
        
        return None
        
    except Exception:
        return None


def _extract_from_structured_data(soup: BeautifulSoup) -> Optional[float]:
    """Extract price from JSON-LD structured data"""
    try:
        json_scripts = soup.find_all('script', type='application/ld+json')
        
        for script in json_scripts:
            try:
                data = json.loads(script.get_text())
                
                if isinstance(data, list):
                    for item in data:
                        price = _extract_price_from_json_item(item)
                        if price and price >= 100:
                            return price
                else:
                    price = _extract_price_from_json_item(data)
                    if price and price >= 100:
                        return price
                        
            except json.JSONDecodeError:
                continue
        
        return None
        
    except Exception:
        return None


def _extract_price_from_json_item(item: dict) -> Optional[float]:
    """Extract price from a JSON-LD item"""
    try:
        # Product schema
        if item.get('@type') == 'Product':
            offers = item.get('offers', {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            
            price = offers.get('price')
            if price:
                return float(price)
        
        # Offer schema
        if item.get('@type') == 'Offer':
            price = item.get('price')
            if price:
                return float(price)
        
        return None
        
    except:
        return None


def _extract_original_price(soup: BeautifulSoup) -> Optional[float]:
    """Extract original/compare price"""
    try:
        compare_elements = soup.find_all(['del', 's']) + soup.find_all(attrs={'class': re.compile(r'compare|original|was', re.I)})
        
        for elem in compare_elements:
            text = elem.get_text().strip()
            price_match = re.search(r'\$(\d+\.?\d*)', text)
            if price_match:
                try:
                    price = float(price_match.group(1))
                    if price >= 100:  # Only minimum validation
                        return price
                except:
                    continue
        
        return None
        
    except Exception:
        return None


def _extract_alternative_pricing(soup: BeautifulSoup, variant_id: str = None) -> Optional[float]:
    """Alternative pricing extraction when main methods fail"""
    try:
        page_text = soup.get_text()
        
        # Find all dollar amounts in reasonable box price range (no upper limit)
        price_matches = re.findall(r'\$(\d{3}\.\d{2}|\d{3,})', page_text)
        
        valid_prices = []
        for match in price_matches:
            try:
                price = float(match)
                if price >= 100:  # Only minimum check - no upper limit for ultra-premium
                    valid_prices.append(price)
            except:
                continue
        
        if valid_prices:
            # Return the most common price in the valid range
            from collections import Counter
            price_counts = Counter(valid_prices)
            most_common_price = price_counts.most_common(1)[0][0]
            return most_common_price
        
        return None
        
    except Exception:
        return None


def _extract_stock_status(soup: BeautifulSoup) -> bool:
    """Extract stock status"""
    try:
        out_of_stock_patterns = [
            r'out\s*of\s*stock',
            r'sold\s*out', 
            r'unavailable',
            r'notify\s*me',
            r'back\s*in\s*stock'
        ]
        
        page_text = soup.get_text().lower()
        
        for pattern in out_of_stock_patterns:
            if re.search(pattern, page_text):
                return False
        
        # Look for add to cart button
        add_to_cart = soup.find(['button', 'input'], string=re.compile(r'add\s*to\s*cart', re.I))
        if add_to_cart:
            return True
        
        return True
        
    except Exception:
        return True


def _extract_box_quantity_from_page(soup: BeautifulSoup, target_packaging: str) -> Optional[int]:
    """Extract box quantity from page content"""
    try:
        page_text = soup.get_text()
        
        box_patterns = [
            rf'box\s*of\s*(\d+)',
            rf'(\d+)\s*count',
            rf'quantity[:\s]*(\d+)'
        ]
        
        for pattern in box_patterns:
            matches = re.finditer(pattern, page_text, re.IGNORECASE)
            for match in matches:
                try:
                    qty = int(match.group(1))
                    if 10 <= qty <= 100:  # Reasonable box quantity range
                        return qty
                except:
                    continue
        
        # Default extraction from target_packaging
        if target_packaging:
            qty_match = re.search(r'(\d+)', target_packaging)
            if qty_match:
                return int(qty_match.group(1))
        
        return None
        
    except Exception:
        return None


# Test function
if __name__ == "__main__":
    test_urls = [
        "https://www.bnbtobacco.com/products/ashton-vsg?variant=33403166659",
        "https://www.bnbtobacco.com/products/oliva-serie-v-natural?variant=33403256515"
    ]
    
    for url in test_urls:
        print(f"\n=== Testing: {url} ===")
        result = extract_bnb_tobacco_data(url)
        print(f"Price: ${result.get('price')} (Should be $100+, no upper limit)")
        print(f"Box Qty: {result.get('box_quantity')}")
        print(f"In Stock: {result.get('in_stock')}")
        print(f"Variant ID: {result.get('variant_id')}")
        print(f"Success: {result.get('success')}")
        print(f"Error: {result.get('error')}")
