"""
Cigar Page Extractor
Extracts pricing and product data from Cigar Page URLs with tabular layout

Key features:
- Handles tabular product listings with multiple package sizes
- Server-side rendered pricing (no JavaScript issues)
- MSRP vs sale price detection
- Package size matching (BOX OF 25, BOX OF 20, etc.)
- Clear stock status indicators
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, List

def extract_cigar_page_data(url: str, target_box_qty: int = None) -> Dict:
    """
    Extract product data from Cigar Page URL with tabular layout
    
    Args:
        url: Product page URL
        target_box_qty: Target box quantity to extract (e.g., 25 for BOX OF 25)
    
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
        
        # Standard rate limiting
        time.sleep(1.0)
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract pricing information from table structure
        pricing_data = _extract_cigar_page_pricing(soup, target_box_qty)
        
        return pricing_data
        
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


def _extract_cigar_page_pricing(soup: BeautifulSoup, target_box_qty: int = None) -> Dict:
    """
    Extract pricing from Cigar Page tabular layout
    Handles multiple package sizes and finds the target box quantity
    """
    
    # Strategy 1: Look for product table rows
    # Cigar Page uses a structured table format with product variants
    
    product_rows = []
    
    # Find all table rows or div elements that contain product information
    potential_rows = soup.find_all(['tr', 'div'], class_=re.compile(r'product|item|row', re.I))
    
    # Also check for any elements containing pricing patterns
    all_elements = soup.find_all(['div', 'span', 'td', 'tr'])
    
    for elem in all_elements:
        elem_text = elem.get_text().strip()
        
        # Look for elements containing box quantities and pricing
        if ('BOX OF' in elem_text.upper() or 'CIGARS' in elem_text.upper()) and '$' in elem_text:
            product_rows.append(elem)
    
    print(f"  [DEBUG] Found {len(product_rows)} potential product rows")
    
    # Strategy 2: Parse each row for pricing data
    best_match = None
    all_matches = []
    
    for row in product_rows:
        row_text = row.get_text().strip()
        
        # Extract package information
        package_info = _extract_package_info(row_text)
        if not package_info:
            continue
        
        # Extract pricing information
        pricing_info = _extract_pricing_info(row, row_text)
        if not pricing_info:
            continue
        
        # Extract stock status
        stock_status = _extract_stock_status(row, row_text)
        
        # Combine all information
        match = {
            'package': package_info,
            'pricing': pricing_info,
            'in_stock': stock_status,
            'box_quantity': package_info.get('quantity'),
            'price': pricing_info.get('sale_price'),
            'original_price': pricing_info.get('msrp_price'),
            'discount_percent': pricing_info.get('discount_percent')
        }
        
        all_matches.append(match)
        
        print(f"  [DEBUG] Found: {package_info.get('package_type')} - ${pricing_info.get('sale_price')} (MSRP ${pricing_info.get('msrp_price')})")
        
        # Check if this matches our target box quantity
        if target_box_qty and package_info.get('quantity') == target_box_qty:
            best_match = match
            print(f"  [DEBUG] Target match found: BOX OF {target_box_qty}")
            break
    
    # If no specific target, use the largest box size
    if not best_match and all_matches:
        best_match = max(all_matches, key=lambda x: x.get('box_quantity', 0))
        print(f"  [DEBUG] Using largest box size: BOX OF {best_match.get('box_quantity')}")
    
    if best_match:
        return {
            'success': True,
            'price': best_match.get('price'),
            'original_price': best_match.get('original_price'),
            'discount_percent': best_match.get('discount_percent'),
            'in_stock': best_match.get('in_stock'),
            'box_quantity': best_match.get('box_quantity'),
            'error': None
        }
    else:
        return {
            'success': False,
            'price': None,
            'original_price': None,
            'discount_percent': None,
            'in_stock': False,
            'box_quantity': None,
            'error': 'No matching product packages found'
        }


def _extract_package_info(text: str) -> Optional[Dict]:
    """Extract package type and quantity from text"""
    
    text_upper = text.upper()
    
    # Look for "BOX OF XX" pattern
    box_match = re.search(r'BOX\s+OF\s+(\d+)', text_upper)
    if box_match:
        quantity = int(box_match.group(1))
        return {
            'package_type': f'BOX OF {quantity}',
            'quantity': quantity
        }
    
    # Look for "XX CIGARS" pattern
    cigars_match = re.search(r'(\d+)\s+CIGARS?', text_upper)
    if cigars_match:
        quantity = int(cigars_match.group(1))
        return {
            'package_type': f'{quantity} CIGARS',
            'quantity': quantity
        }
    
    # Look for "5-PACK" or similar
    pack_match = re.search(r'(\d+)-?PACK', text_upper)
    if pack_match:
        quantity = int(pack_match.group(1))
        return {
            'package_type': f'{quantity}-PACK',
            'quantity': quantity
        }
    
    return None


def _extract_pricing_info(elem, text: str) -> Optional[Dict]:
    """Extract sale price and MSRP from element"""
    
    # Look for price patterns in the element and its children
    price_elements = elem.find_all(string=re.compile(r'\$\d+'))
    
    prices = []
    msrp_price = None
    sale_price = None
    
    # Extract all prices from the element
    all_price_text = text + ' ' + ' '.join([p_elem.strip() for p_elem in price_elements])
    price_matches = re.findall(r'\$(\d+\.?\d*)', all_price_text)
    
    for price_match in price_matches:
        try:
            price_val = float(price_match)
            if 10 <= price_val <= 2000:  # Reasonable price range
                prices.append(price_val)
        except ValueError:
            continue
    
    if not prices:
        return None
    
    # Look for MSRP indicators
    if 'MSRP' in text.upper():
        msrp_matches = re.findall(r'MSRP[:\s]*\$(\d+\.?\d*)', text, re.I)
        if msrp_matches:
            try:
                msrp_price = float(msrp_matches[0])
            except ValueError:
                pass
    
    # Determine sale price
    unique_prices = sorted(list(set(prices)))
    
    if len(unique_prices) >= 2:
        # Multiple prices - assume higher is MSRP, lower is sale
        if not msrp_price:
            msrp_price = max(unique_prices)
        sale_price = min([p for p in unique_prices if p < (msrp_price or 9999)])
        
        if not sale_price:
            sale_price = min(unique_prices)
    else:
        # Single price
        sale_price = unique_prices[0]
    
    # Calculate discount
    discount_percent = None
    if msrp_price and sale_price and msrp_price > sale_price:
        discount_percent = ((msrp_price - sale_price) / msrp_price) * 100
    
    return {
        'sale_price': sale_price,
        'msrp_price': msrp_price,
        'discount_percent': discount_percent
    }


def _extract_stock_status(elem, text: str) -> bool:
    """Extract stock status from element"""
    
    text_lower = text.lower()
    
    # Look for explicit stock indicators
    if 'in stock' in text_lower:
        return True
    
    if any(indicator in text_lower for indicator in ['out of stock', 'sold out', 'unavailable']):
        return False
    
    # Look for "Add" buttons (indicates available)
    if 'add' in text_lower and ('cart' in text_lower or 'button' in text_lower):
        return True
    
    # Default to available if no clear indicators
    return True


# Test function
if __name__ == "__main__":
    test_cases = [
        {
            "url": "https://www.cigarpage.com/romeo-y-julieta-1875-ks-roa.html",
            "target_box_qty": 25,
            "expected_price": 200.81,
            "expected_msrp": 267.75,
            "expected_qty": 25,
            "expected_stock": True,
            "description": "Romeo y Julieta Churchill - In Stock"
        },
        {
            "url": "https://www.cigarpage.com/my-father-the-judge.html",
            "target_box_qty": 23,
            "expected_price": 217.19,
            "expected_msrp": 306.90,
            "expected_qty": 23,
            "expected_stock": False,
            "description": "My Father Judge Grand Robusto - Sold Out"
        }
    ]
    
    print("=== TESTING CIGAR PAGE EXTRACTOR ===")
    print("Testing multiple scenarios: in stock vs sold out")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n[TEST {i}] {test_case['description']}")
        print(f"URL: {test_case['url']}")
        print(f"Target: BOX OF {test_case['target_box_qty']}")
        print(f"Expected: ${test_case['expected_price']} (Sale) | MSRP ${test_case['expected_msrp']} | Stock: {test_case['expected_stock']}")
        print("-" * 50)
        
        result = extract_cigar_page_data(test_case['url'], target_box_qty=test_case['target_box_qty'])
        
        print("Results:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        if result.get('price') and result.get('box_quantity'):
            per_stick = result['price'] / result['box_quantity']
            print(f"  price_per_stick: ${per_stick:.2f}")
        
        # Validation
        if result.get('success'):
            price_ok = result.get('price') and abs(result['price'] - test_case['expected_price']) < 5.0
            msrp_ok = result.get('original_price') and abs(result['original_price'] - test_case['expected_msrp']) < 5.0
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
