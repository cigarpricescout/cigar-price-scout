"""
Cigar Page Extractor - ENHANCED ANTI-DETECTION VERSION
Advanced techniques to avoid 403 Forbidden errors

Enhanced anti-detection features:
- More comprehensive browser headers with sec-ch-ua
- Realistic session cookies
- Google referer to appear like natural browsing
- Longer random delays (8-15 seconds)
- Progressive backoff on failures
- Alternative extraction patterns
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
from typing import Dict, Optional

# Global session for connection reuse
session = None

def get_session():
    """Get or create a session with enhanced anti-detection headers"""
    global session
    if session is None:
        session = requests.Session()
        
        # More comprehensive and realistic browser headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/',  # Google referer to appear natural
        }
        
        session.headers.update(headers)
        
        # Set some cookies to appear more like a regular browser
        session.cookies.update({
            'session_id': f"sess_{random.randint(100000, 999999)}",
            'visited': '1',
            'preference': 'desktop'
        })
    
    return session


def extract_cigar_page_data(url: str, target_box_qty: int = None, retries: int = 3) -> Dict:
    """
    Extract product data from Cigar Page URL with enhanced anti-detection
    """
    
    session_obj = get_session()
    
    for attempt in range(retries + 1):
        try:
            print(f"    [EXTRACT] Fetching Cigar Page... (attempt {attempt + 1})")
            
            # Much longer delays to appear more human
            if attempt == 0:
                delay = random.uniform(8.0, 12.0)  # Initial request: 8-12s
            else:
                delay = random.uniform(15.0, 25.0)  # Retries: 15-25s
            
            print(f"    [DELAY] Waiting {delay:.1f}s for enhanced compliance...")
            time.sleep(delay)
            
            # Simulate human behavior: visit homepage first on first attempt
            if attempt == 0:
                try:
                    print(f"    [HUMAN] Visiting homepage first...")
                    homepage_response = session_obj.get('https://www.cigarpage.com/', timeout=10)
                    time.sleep(random.uniform(2.0, 4.0))
                except:
                    pass  # Continue even if homepage fails
            
            response = session_obj.get(url, timeout=20)
            
            if response.status_code == 429:
                wait_time = 60 * (2 ** attempt)  # Longer backoff: 60s, 120s, 240s
                print(f"    [RATE LIMIT] Waiting {wait_time}s before retry {attempt + 1}")
                time.sleep(wait_time)
                continue
            
            if response.status_code == 403:
                if attempt < retries:
                    wait_time = 30 * (attempt + 2)  # Progressive backoff: 60s, 90s, 120s
                    print(f"    [403 BLOCKED] Enhanced wait {wait_time}s before retry {attempt + 1}")
                    time.sleep(wait_time)
                    
                    # Reset session on 403 to get fresh fingerprint
                    print(f"    [RESET] Creating fresh session...")
                    global session
                    session = None
                    session_obj = get_session()
                    continue
                else:
                    print(f"    [403 PERMANENT] Site appears to be blocking automated requests")
            
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract pricing information using structure-aware approach
            pricing_data = _extract_cigar_page_pricing_fixed(soup, target_box_qty)
            
            return pricing_data
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if '403' in error_msg:
                print(f"    [403 ERROR] Site blocking request: {error_msg}")
            elif '429' in error_msg:
                print(f"    [RATE LIMIT] Too many requests: {error_msg}")
            else:
                print(f"    [NETWORK] Request failed: {error_msg}")
                
            if attempt < retries:
                wait_time = 20 * (attempt + 1)  # 20s, 40s, 60s
                print(f"    [RETRY] Waiting {wait_time}s before next attempt...")
                time.sleep(wait_time)
                continue
            else:
                return {
                    'success': False,
                    'price': None,
                    'original_price': None,
                    'discount_percent': None,
                    'in_stock': False,
                    'box_quantity': None,
                    'error': f'Request failed after {retries + 1} attempts: {str(e)}'
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


def _extract_cigar_page_pricing_fixed(soup: BeautifulSoup, target_box_qty: int = None) -> Dict:
    """
    Extract pricing using the actual Cigar Page structure
    Based on analysis: uses .product-item containers, clear price patterns, BOX OF X format
    """
    
    print(f"    [EXTRACT] Using structure-aware extraction...")
    
    # Strategy 1: Look for product-item containers first
    product_items = soup.find_all('div', class_='product-item')
    print(f"    [DEBUG] Found {len(product_items)} product-item containers")
    
    # Strategy 2: Also check the main product area and forms
    all_containers = product_items + soup.find_all(['form', 'table', 'div'], class_=re.compile(r'product|option|variant', re.I))
    
    # Strategy 3: Get all text and look for patterns (fallback)
    page_text = soup.get_text()
    
    # Extract all pricing information
    all_prices = []
    box_quantities = []
    
    # Find all price patterns in the entire page
    price_matches = re.findall(r'\$(\d+\.?\d*)', page_text)
    for price_text in price_matches:
        try:
            price_val = float(price_text)
            if 10 <= price_val <= 2000:  # Reasonable range
                all_prices.append(price_val)
        except ValueError:
            continue
    
    # Find all box quantity patterns
    box_matches = re.findall(r'BOX\s+OF\s+(\d+)', page_text, re.I)
    for box_text in box_matches:
        try:
            box_val = int(box_text)
            if 5 <= box_val <= 100:  # Reasonable range
                box_quantities.append(box_val)
        except ValueError:
            continue
    
    print(f"    [DEBUG] Found prices: {all_prices}")
    print(f"    [DEBUG] Found box quantities: {box_quantities}")
    
    # Determine the target box quantity
    selected_box_qty = None
    if target_box_qty and target_box_qty in box_quantities:
        selected_box_qty = target_box_qty
        print(f"    [DEBUG] Using target box quantity: {selected_box_qty}")
    elif box_quantities:
        selected_box_qty = max(box_quantities)  # Use largest available
        print(f"    [DEBUG] Using largest box quantity: {selected_box_qty}")
    
    # Determine pricing
    sale_price = None
    msrp_price = None
    
    if all_prices:
        unique_prices = sorted(list(set(all_prices)))
        print(f"    [DEBUG] Unique prices: {unique_prices}")
        
        if len(unique_prices) == 1:
            sale_price = unique_prices[0]
        elif len(unique_prices) >= 2:
            # Assume lower price is sale, higher is MSRP
            sale_price = min(unique_prices)
            msrp_price = max(unique_prices)
        
        print(f"    [DEBUG] Selected - Sale: ${sale_price}, MSRP: ${msrp_price}")
    
    # Calculate discount
    discount_percent = None
    if msrp_price and sale_price and msrp_price > sale_price:
        discount_percent = ((msrp_price - sale_price) / msrp_price) * 100
    
    # Determine stock status
    in_stock = _extract_stock_status_fixed(soup)
    
    if sale_price and selected_box_qty:
        return {
            'success': True,
            'price': sale_price,
            'original_price': msrp_price,
            'discount_percent': discount_percent,
            'in_stock': in_stock,
            'box_quantity': selected_box_qty,
            'error': None
        }
    else:
        missing_items = []
        if not sale_price:
            missing_items.append("price")
        if not selected_box_qty:
            missing_items.append("box quantity")
            
        return {
            'success': False,
            'price': sale_price,
            'original_price': msrp_price,
            'discount_percent': discount_percent,
            'in_stock': in_stock,
            'box_quantity': selected_box_qty,
            'error': f'Missing required data: {", ".join(missing_items)}'
        }


def _extract_stock_status_fixed(soup: BeautifulSoup) -> bool:
    """Extract stock status using Cigar Page patterns"""
    
    page_text = soup.get_text().lower()
    
    # Check for explicit stock indicators
    if 'in stock' in page_text:
        return True
    
    if any(indicator in page_text for indicator in [
        'out of stock', 'sold out', 'unavailable', 'currently unavailable',
        'temporarily unavailable', 'not available'
    ]):
        return False
    
    # Look for add to cart or purchase buttons
    buttons = soup.find_all(['button', 'input', 'a'])
    for button in buttons:
        button_text = button.get_text().lower().strip()
        if any(term in button_text for term in ['add to cart', 'buy now', 'purchase', 'add']):
            if not button.get('disabled'):
                return True
    
    # If we can't determine, assume in stock
    return True


if __name__ == "__main__":
    test_cases = [
        {
            "url": "https://www.cigarpage.com/romeo-y-julieta-1875-ks-roa.html",
            "target_box_qty": 25,
            "expected_sale": 200.81,
            "expected_msrp": 267.75,
            "description": "Romeo y Julieta 1875 Churchill"
        }
    ]
    
    print("=== TESTING ENHANCED ANTI-DETECTION CIGAR PAGE EXTRACTOR ===")
    print("Enhanced headers, longer delays, session reset on 403")
    print("=" * 70)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n[TEST {i}] {test_case['description']}")
        print(f"URL: {test_case['url']}")
        print(f"Target: BOX OF {test_case['target_box_qty']}")
        print(f"Expected: Sale ${test_case['expected_sale']}, MSRP ${test_case['expected_msrp']}")
        print("-" * 50)
        
        result = extract_cigar_page_data(test_case['url'], target_box_qty=test_case['target_box_qty'])
        
        print("\nResults:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        if result.get('price') and result.get('box_quantity'):
            per_stick = result['price'] / result['box_quantity']
            print(f"  price_per_stick: ${per_stick:.2f}")
        
        # Validation
        if result.get('success'):
            sale_ok = result.get('price') and abs(result['price'] - test_case['expected_sale']) < 5.0
            msrp_ok = not test_case.get('expected_msrp') or (
                result.get('original_price') and abs(result['original_price'] - test_case['expected_msrp']) < 5.0
            )
            qty_ok = result.get('box_quantity') == test_case['target_box_qty']
            
            if sale_ok and msrp_ok and qty_ok:
                print("SUCCESS: All extractions correct!")
            else:
                print("VALIDATION ISSUES:")
                if not sale_ok:
                    print(f"  Sale price: ${result.get('price')} vs expected ${test_case['expected_sale']}")
                if not msrp_ok:
                    print(f"  MSRP: ${result.get('original_price')} vs expected ${test_case.get('expected_msrp')}")
                if not qty_ok:
                    print(f"  Box quantity: {result.get('box_quantity')} vs expected {test_case['target_box_qty']}")
        else:
            print(f"FAILED: {result.get('error')}")
