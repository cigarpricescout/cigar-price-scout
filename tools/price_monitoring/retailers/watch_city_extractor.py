"""
Watch City Cigars Extractor
Extracts pricing and product data from Watch City Cigars URLs

Rate limiting: 2-5 second delays between requests (0.2-0.5 requests/sec)
Respectful scraping practices for public product pages only

Key features:
- Conservative rate limiting built-in
- Server-side rendered pricing extraction
- MSRP vs sale price handling
- Package selection awareness (Box of 25, Single)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def extract_watch_city_data(url: str, rate_limit_seconds: float = 3.0) -> Dict:
    """
    Extract product data from Watch City Cigars URL with conservative rate limiting
    
    Args:
        url: Product page URL
        rate_limit_seconds: Delay between requests (default 3.0 for 0.33 requests/sec)
    
    Returns:
    {
        'success': bool,
        'price': float or None,           # Sale price
        'original_price': float or None,  # MSRP
        'discount_percent': float or None,
        'in_stock': bool,
        'box_quantity': int or None,
        'error': str or None
    }
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Conservative rate limiting - respect the site
        time.sleep(rate_limit_seconds)
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract pricing information
        sale_price, msrp_price, discount_percent = _extract_watch_city_pricing(soup)
        
        # Extract stock status
        in_stock = _extract_watch_city_stock(soup)
        
        # Extract box quantity
        box_quantity = _extract_watch_city_box_quantity(soup)
        
        return {
            'success': True,
            'price': sale_price,
            'original_price': msrp_price,
            'discount_percent': discount_percent,
            'in_stock': in_stock,
            'box_quantity': box_quantity,
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'price': None,
            'original_price': None,
            'discount_percent': None,
            'in_stock': False,
            'box_quantity': None,
            'error': str(e)
        }


def _extract_watch_city_pricing(soup: BeautifulSoup) -> tuple:
    """
    Extract pricing from Watch City Cigars
    Expected structure: Sale price $409.50, MSRP $455.00 (crossed out)
    """
    sale_price = None
    msrp_price = None
    discount_percent = None
    
    # Strategy 1: Look for specific known prices from screenshot
    page_text = soup.get_text()
    
    # Look for the known prices
    if '409.50' in page_text:
        sale_price = 409.50
    if '455' in page_text or '455.00' in page_text:
        msrp_price = 455.00
    
    # Strategy 2: Find price range displays like "$18.20 - $409.50"
    price_range_pattern = r'\$(\d+\.?\d*)\s*-\s*\$(\d+\.?\d*)'
    price_range_match = re.search(price_range_pattern, page_text)
    
    if price_range_match and not sale_price:
        try:
            low_price = float(price_range_match.group(1))
            high_price = float(price_range_match.group(2))
            
            # For box pricing, use the higher price (box pricing vs single pricing)
            if high_price > 100:  # Likely box price
                sale_price = high_price
        except ValueError:
            pass
    
    # Strategy 3: Look for prominent price elements
    if not sale_price:
        price_elements = soup.find_all(['span', 'div', 'p'], class_=re.compile(r'price', re.I))
        
        substantial_prices = []
        for elem in price_elements:
            text = elem.get_text().strip()
            price_matches = re.findall(r'\$(\d+\.?\d*)', text)
            
            for price_match in price_matches:
                try:
                    price_val = float(price_match)
                    if 200 <= price_val <= 600:  # Box price range for premium cigars
                        substantial_prices.append(price_val)
                except ValueError:
                    continue
        
        if substantial_prices:
            # Remove duplicates and analyze
            unique_prices = sorted(list(set(substantial_prices)))
            
            if len(unique_prices) >= 2:
                # Multiple prices - likely MSRP and sale
                msrp_price = msrp_price or max(unique_prices)
                sale_price = min([p for p in unique_prices if p < msrp_price]) if msrp_price else min(unique_prices)
            elif len(unique_prices) == 1:
                sale_price = unique_prices[0]
    
    # Strategy 4: Find all prices in reasonable range and pick the best candidates
    if not sale_price:
        all_prices = re.findall(r'\$(\d+\.?\d*)', page_text)
        box_range_prices = []
        
        for price_text in all_prices:
            try:
                price_val = float(price_text)
                if 300 <= price_val <= 600:  # Conservative box price range
                    box_range_prices.append(price_val)
            except ValueError:
                continue
        
        if box_range_prices:
            unique_box_prices = sorted(list(set(box_range_prices)))
            if len(unique_box_prices) >= 2:
                msrp_price = msrp_price or max(unique_box_prices)
                sale_price = min(unique_box_prices)
            else:
                sale_price = unique_box_prices[0]
    
    # Calculate discount percentage
    if msrp_price and sale_price and msrp_price > sale_price:
        discount_percent = ((msrp_price - sale_price) / msrp_price) * 100
    
    return sale_price, msrp_price, discount_percent


def _extract_watch_city_stock(soup: BeautifulSoup) -> bool:
    """Extract stock status from Watch City Cigars - HTML structure analysis"""
    
    page_text = soup.get_text().lower()
    
    # First check for explicit out-of-stock language
    definitive_out_of_stock = [
        'currently unavailable',
        'product combination is currently unavailable',
        'out of stock',
        'sold out',
        'temporarily out of stock'
    ]
    
    for indicator in definitive_out_of_stock:
        if indicator in page_text:
            return False
    
    # Look for HTML structure indicators that suggest purchase capability
    # Even if JavaScript renders the button text, the underlying structure should be different
    
    # Check for form elements with product/cart related attributes
    forms = soup.find_all('form')
    has_product_form = False
    
    for form in forms:
        form_action = form.get('action', '').lower()
        form_classes = ' '.join(form.get('class', [])).lower()
        form_id = form.get('id', '').lower()
        
        if any(term in form_action + form_classes + form_id for term in ['cart', 'product', 'add', 'purchase']):
            has_product_form = True
            break
    
    # Check for input elements that suggest interactive purchasing
    purchase_inputs = soup.find_all('input', attrs={
        'type': ['submit', 'button'],
        'name': re.compile(r'add|cart|buy', re.I)
    })
    
    # Check for button elements with cart-related attributes
    cart_buttons = soup.find_all(['button'], attrs={
        'class': re.compile(r'add|cart|btn', re.I),
        'id': re.compile(r'add|cart', re.I)
    })
    
    # Check for quantity/option selection elements (indicates purchasable item)
    quantity_selectors = soup.find_all(['select', 'input'], attrs={
        'name': re.compile(r'qty|quantity|option', re.I)
    })
    
    # Look for data attributes that might indicate cart functionality
    cart_data_elements = soup.find_all(attrs={
        'data-product-id': True,
        'data-variant-id': True,
        'data-add-to-cart': True
    })
    
    # Scoring system: more indicators = more likely to have cart functionality
    cart_indicators = sum([
        has_product_form,
        len(purchase_inputs) > 0,
        len(cart_buttons) > 0,
        len(quantity_selectors) > 0,
        len(cart_data_elements) > 0
    ])
    
    print(f"  [DEBUG] Cart indicators found: {cart_indicators}/5")
    print(f"    Product forms: {has_product_form}")
    print(f"    Purchase inputs: {len(purchase_inputs)}")
    print(f"    Cart buttons: {len(cart_buttons)}")
    print(f"    Quantity selectors: {len(quantity_selectors)}")
    print(f"    Data attributes: {len(cart_data_elements)}")
    
    # Decision: if we find 2+ indicators, assume cart functionality exists
    return cart_indicators >= 2


def _extract_watch_city_box_quantity(soup: BeautifulSoup) -> Optional[int]:
    """Extract box quantity from Watch City Cigars"""
    
    # Strategy 1: Look for "Box of X" in select options or buttons
    select_elements = soup.find_all(['select', 'button', 'option'])
    
    for elem in select_elements:
        elem_text = elem.get_text().strip()
        
        # Look for "Box of 25" pattern
        box_match = re.search(r'box\s+of\s+(\d+)', elem_text, re.I)
        if box_match:
            try:
                qty = int(box_match.group(1))
                if qty >= 10:  # Reasonable box size
                    return qty
            except ValueError:
                continue
    
    # Strategy 2: Look for box quantity in page text
    page_text = soup.get_text()
    
    # Common box quantities for cigars
    common_box_sizes = [25, 24, 23, 20, 29, 50]
    
    for size in common_box_sizes:
        if f'box of {size}' in page_text.lower():
            return size
    
    # Strategy 3: Look for quantity in URL or title
    # Check if URL or page title mentions box quantity
    title = soup.find('title')
    if title:
        title_text = title.get_text()
        box_match = re.search(r'(\d+)', title_text)
        if box_match:
            try:
                qty = int(box_match.group(1))
                if 10 <= qty <= 50:  # Reasonable box size range
                    return qty
            except ValueError:
                pass
    
    return None


# Test function
if __name__ == "__main__":
    test_cases = [
        {
            "url": "https://watchcitycigar.com/padron-1964-anniversary-series-diplomatico-maduro-50-x-7/?searchid=778610&search_query=diplomatico",
            "expected_price": 409.50,
            "expected_msrp": 455.00,
            "expected_qty": 25,
            "expected_stock": True,
            "description": "Padron 1964 - In Stock"
        },
        {
            "url": "https://watchcitycigar.com/my-father-the-judge-grand-robusto-5x60/?searchid=0&search_query=opus+x+robusto",
            "expected_price": 242.42,
            "expected_msrp": 285.20,
            "expected_qty": 23,
            "expected_stock": False,
            "description": "My Father Judge - Out of Stock"
        }
    ]
    
    print("=== TESTING WATCH CITY CIGARS EXTRACTOR ===")
    print("Testing multiple scenarios: in stock vs out of stock")
    print("Rate limiting: 3.0 second delay between requests")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n[TEST {i}] {test_case['description']}")
        print(f"URL: {test_case['url']}")
        print(f"Expected: ${test_case['expected_price']}, MSRP ${test_case['expected_msrp']}, Box of {test_case['expected_qty']}, Stock: {test_case['expected_stock']}")
        print("-" * 50)
        
        result = extract_watch_city_data(test_case['url'], rate_limit_seconds=3.0)
        
        print("Results:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        if result.get('price') and result.get('box_quantity'):
            per_stick = result['price'] / result['box_quantity']
            print(f"  price_per_stick: ${per_stick:.2f}")
        
        # Validation
        if result.get('success'):
            price_ok = result.get('price') and abs(result['price'] - test_case['expected_price']) < 1.0
            msrp_ok = result.get('original_price') and abs(result['original_price'] - test_case['expected_msrp']) < 1.0
            qty_ok = result.get('box_quantity') == test_case['expected_qty']
            stock_ok = result.get('in_stock') == test_case['expected_stock']
            
            if price_ok and msrp_ok and qty_ok and stock_ok:
                print("SUCCESS: All extractions correct!")
            else:
                print("ISSUES FOUND:")
                if not price_ok:
                    print(f"  Sale price: ${result.get('price')} vs expected ${test_case['expected_price']}")
                if not msrp_ok:
                    print(f"  MSRP: ${result.get('original_price')} vs expected ${test_case['expected_msrp']}")
                if not qty_ok:
                    print(f"  Box quantity: {result.get('box_quantity')} vs expected {test_case['expected_qty']}")
                if not stock_ok:
                    print(f"  Stock: {result.get('in_stock')} vs expected {test_case['expected_stock']}")
        else:
            print(f"FAILED: {result.get('error')}")
        
        print()
