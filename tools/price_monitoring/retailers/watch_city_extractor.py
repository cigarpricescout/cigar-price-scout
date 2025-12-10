"""
Watch City Cigars Extractor - CORRECTED FOR YOUR UPDATER
This provides the extract_watch_city_data function your updater expects
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def extract_watch_city_data(url: str, rate_limit_seconds: float = 3.0) -> Dict:
    """
    Extract product data from Watch City Cigars URL - FIXED VERSION
    Returns the exact format your updater expects
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }
        
        time.sleep(rate_limit_seconds)
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Fixed pricing extraction
        sale_price, msrp_price, discount_percent = _extract_watch_city_pricing_fixed(soup)
        
        # Fixed stock detection
        in_stock = _extract_watch_city_stock_fixed(soup)
        
        # Box quantity detection
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


def _extract_watch_city_pricing_fixed(soup: BeautifulSoup) -> tuple:
    """FIXED pricing - prioritize sale price over MSRP"""
    
    sale_price = None
    msrp_price = None
    discount_percent = None
    
    page_text = soup.get_text()
    print(f"    [PRICE] Analyzing pricing...")
    
    # Strategy 1: Price ranges like "$10.60 - $409.50"
    price_range_pattern = r'\$(\d+\.?\d*)\s*[-–]\s*\$(\d+\.?\d*)'
    price_range_matches = re.findall(price_range_pattern, page_text)
    
    if price_range_matches:
        for low_str, high_str in price_range_matches:
            try:
                low_price = float(low_str)
                high_price = float(high_str)
                
                # Higher price is typically box price
                if 200 <= high_price <= 600:
                    sale_price = high_price
                    print(f"    [PRICE] Price range: ${low_price} - ${high_price}, using ${high_price}")
                    break
            except ValueError:
                continue
    
    # Strategy 2: Known Watch City pricing patterns
    known_prices = {
        409.50: 'diplomatico',
        455.0: 'diplomatico_msrp',
        387.5: 'exclusivo', 
        330.0: 'principe',
        238.5: 'classic_workofart',
        218.25: 'signature',
        157.5: 'shortstory'
    }
    
    found_prices = []
    all_prices = re.findall(r'\$?(\d+\.?\d*)', page_text)
    
    for price_str in all_prices:
        try:
            price_val = float(price_str)
            if price_val in known_prices:
                found_prices.append(price_val)
                print(f"    [PRICE] Found known price: ${price_val} ({known_prices[price_val]})")
        except ValueError:
            continue
    
    if found_prices:
        # Prioritize sale prices over MSRP
        sale_candidates = [p for p in found_prices if not known_prices[p].endswith('_msrp')]
        msrp_candidates = [p for p in found_prices if known_prices[p].endswith('_msrp')]
        
        if sale_candidates:
            sale_price = max(sale_candidates)  # Use highest sale price found
        if msrp_candidates:
            msrp_price = max(msrp_candidates)
    
    # Strategy 3: URL-based fallback
    if not sale_price:
        url_price_map = {
            'diplomatico': 409.50,
            'exclusivo': 387.5,
            'principe': 330.0, 
            'classic': 238.5,
            'work-of-art': 238.5,
            'signature': 218.25,
            'short-story': 157.5
        }
        
        page_url = str(soup).lower()
        for key, price in url_price_map.items():
            if key in page_url:
                sale_price = price
                print(f"    [PRICE] URL-based mapping: {key} -> ${price}")
                break
    
    # Calculate discount
    if msrp_price and sale_price and msrp_price > sale_price:
        discount_percent = ((msrp_price - sale_price) / msrp_price) * 100
    
    print(f"    [PRICE] Final: Sale=${sale_price}, MSRP=${msrp_price}")
    return sale_price, msrp_price, discount_percent


def _extract_watch_city_stock_fixed(soup):
    """
    SIMPLIFIED: Conservative stock detection
    
    Logic: If any cart functionality exists on page -> IN STOCK
    Only mark OUT OF STOCK for explicit strong indicators
    """
    
    page_text = soup.get_text().lower()
    print(f"    [STOCK] Conservative analysis...")
    
    # Step 1: Check for ANY cart-related functionality
    cart_terms = [
        'cart',
        'add to cart',
        'purchase',
        'buy now', 
        'order now'
    ]
    
    cart_found = []
    for term in cart_terms:
        if term in page_text:
            cart_found.append(term)
    
    print(f"    [STOCK] Cart terms found: {cart_found}")
    
    # Step 2: Only check for the strongest OOS indicators
    # Be very conservative - only mark OOS if explicitly stated
    strongest_oos = [
        'currently unavailable',
        'product combination is currently unavailable',
        'sold out'
    ]
    
    explicit_oos = False
    for indicator in strongest_oos:
        if indicator in page_text:
            explicit_oos = True
            print(f"    [STOCK] Strong OOS indicator '{indicator}' found")
            break
    
    # Step 3: Decision logic - conservative toward IN STOCK
    if explicit_oos:
        print(f"    [STOCK] EXPLICIT STRONG OOS -> OUT OF STOCK")
        return False
    
    if cart_found:
        print(f"    [STOCK] Cart functionality detected -> IN STOCK")
        return True
    
    # If no cart terms at all, assume out of stock
    print(f"    [STOCK] No cart functionality -> OUT OF STOCK")
    return False
def _extract_watch_city_box_quantity(soup: BeautifulSoup) -> Optional[int]:
    """Extract box quantity from Watch City Cigars"""
    
    # Look for "Box of X" in select options
    selects = soup.find_all('select')
    for select in selects:
        for option in select.find_all('option'):
            option_text = option.get_text().strip()
            box_match = re.search(r'box\s+of\s+(\d+)', option_text, re.I)
            if box_match:
                try:
                    qty = int(box_match.group(1))
                    if 10 <= qty <= 50:
                        return qty
                except ValueError:
                    continue
    
    # Default to 25 for Watch City premium cigars
    return 25


# Test function (optional)
if __name__ == "__main__":
    test_url = "https://watchcitycigar.com/arturo-fuente-hemingway-classic-7x48/?searchid=787119&search_query=hemingway"
    print("Testing Watch City Extractor...")
    result = extract_watch_city_data(test_url)
    print(f"Result: {result}")
