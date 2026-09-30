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


def _money_values(text: str) -> list:
    return [float(match) for match in re.findall(r'\$(\d+\.?\d*)', (text or '').replace(',', ''))]


def _extract_watch_city_pricing_fixed(soup: BeautifulSoup) -> tuple:
    """Read only the main product price. Related cards repeat other vitolas' prices."""
    sale_price = None
    msrp_price = None
    discount_percent = None

    view = soup.select_one('.productView-price')
    if view:
        main = view.select_one('.price--main')
        rrp = view.select_one('.price--rrp')
        if main:
            amounts = _money_values(main.get_text(' ', strip=True))
            if amounts:
                # "$7.00 - $157.50" is single through box. The high end is the box sale.
                sale_price = max(amounts)
        if rrp:
            amounts = _money_values(rrp.get_text(' ', strip=True))
            if amounts:
                msrp_price = max(amounts)

    if msrp_price and sale_price and msrp_price > sale_price:
        discount_percent = ((msrp_price - sale_price) / msrp_price) * 100

    print(f"    [PRICE] Final: Sale=${sale_price}, MSRP={msrp_price}")
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
