"""
Tobacco Locker Extractor - CORRECTED OPUS X VERSION
Extracts pricing and product data from Tobacco Locker URLs

Based on analysis of: https://tobaccolocker.com/collections/general/products/hoyo-de-monterrey-excalibur-epicures-natural-cigar

Key features:
- Server-side rendered pricing
- Clear package options (BOX 20, 5 PACK, SINGLE)
- Stock status clearly displayed
- Clean product structure
- FIXED: Opus X premium pricing detection
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def extract_tobacco_locker_data(url: str) -> Dict:
    """
    Extract product data from Tobacco Locker URL
    
    Returns:
    {
        'success': bool,
        'price': float or None,
        'in_stock': bool,
        'box_quantity': int or None,
        'error': str or None
    }
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract pricing
        price = _extract_tobacco_locker_price(soup)
        
        # Extract stock status
        in_stock = _extract_tobacco_locker_stock(soup)
        
        # Extract box quantity
        box_quantity = _extract_tobacco_locker_box_quantity(soup)
        
        return {
            'success': True,
            'price': price,
            'in_stock': in_stock,
            'box_quantity': box_quantity,
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'price': None,
            'in_stock': False,
            'box_quantity': None,
            'error': str(e)
        }


def _extract_tobacco_locker_price(soup: BeautifulSoup) -> Optional[float]:
    """Extract price from Tobacco Locker product page - CORRECTED OPUS X VERSION"""
    
    # Strategy 1: Look for current sale price (not crossed out)
    current_price_selectors = [
        '[class*="price"]:not([class*="compare"]):not([class*="was"]):not([class*="original"])',
        '[class*="sale"]',
        '.current-price',
        '.price-box .price:not(.was-price)'
    ]
    
    for selector in current_price_selectors:
        price_elements = soup.select(selector)
        for elem in price_elements:
            # Skip if this element appears to be struck through
            if elem.find('s') or elem.find('del') or 'text-decoration: line-through' in elem.get('style', ''):
                continue
                
            text = elem.get_text().strip()
            price_match = re.search(r'\$(\d{1,4}(?:,\d{3})?(?:\.\d{2})?)', text)  # FIXED: Better regex
            if price_match:
                try:
                    price_val = float(price_match.group(1).replace(',', ''))
                    if 50 <= price_val <= 3000:  # FIXED: Increased upper limit for Opus X
                        return price_val
                except ValueError:
                    continue
    
    # Strategy 2: Look for all prices but prioritize non-crossed-out ones
    all_text = soup.get_text()
    
    # FIXED: Better regex to catch comma-separated prices
    all_prices = re.findall(r'\$(\d{1,4}(?:,\d{3})?(?:\.\d{2})?)', all_text)
    valid_prices = []
    
    for price_text in all_prices:
        try:
            price_val = float(price_text.replace(',', ''))
            if 50 <= price_val <= 3000:  # FIXED: Increased upper limit
                valid_prices.append(price_val)
        except ValueError:
            continue
    
    if valid_prices:
        # Remove duplicates and sort
        unique_prices = sorted(list(set(valid_prices)))
        
        # If we have multiple prices, apply intelligent selection
        if len(unique_prices) == 1:
            return unique_prices[0]
        elif len(unique_prices) == 2:
            # FIXED: More robust Opus X detection
            page_text = soup.get_text().lower()
            if 'opus x' in page_text or 'opusx' in page_text or 'arturo fuente opus' in page_text:
                return max(unique_prices)
            else:
                return min(unique_prices)
        else:
            # Multiple prices - FIXED: Improved Opus X handling
            page_text = soup.get_text().lower()
            if 'opus x' in page_text or 'opusx' in page_text or 'arturo fuente opus' in page_text:
                # For Opus X, look for high prices first
                high_prices = [p for p in unique_prices if p >= 1000]
                if high_prices:
                    return min(high_prices)  # Lowest of the high prices
                
                # FIXED: More aggressive Opus X fallback
                reasonable_prices = [p for p in unique_prices if p >= 400]
                if reasonable_prices:
                    # Look for the price that's most likely the box price
                    high_end = [p for p in reasonable_prices if p >= 800]
                    if high_end:
                        return max(high_end)
                    else:
                        return max(reasonable_prices)  # Highest reasonable for Opus X
            else:
                # For everything else, use original logic
                reasonable_prices = [p for p in unique_prices if p >= 100]
                if reasonable_prices:
                    return min(reasonable_prices)  # Take lowest reasonable price
                else:
                    return min(unique_prices)  # Fallback
    
    # Strategy 3: Fallback - look in specific product sections
    product_sections = soup.find_all(['div'], class_=re.compile(r'product|price', re.I))
    for section in product_sections:
        # Skip sections that look like "was price" or "compare at"
        if any(term in section.get('class', []) for term in ['was', 'compare', 'original']):
            continue
            
        section_text = section.get_text()
        price_match = re.search(r'\$(\d{1,4}(?:,\d{3})?(?:\.\d{2})?)', section_text)  # FIXED: Better regex
        if price_match:
            try:
                price_val = float(price_match.group(1).replace(',', ''))
                if 50 <= price_val <= 3000:  # FIXED: Increased upper limit
                    return price_val
            except ValueError:
                continue
    
    return None


def _extract_tobacco_locker_stock(soup: BeautifulSoup) -> bool:
    """Extract stock status from Tobacco Locker"""
    page_text = soup.get_text().lower()
    
    # Look for explicit stock indicators
    if 'in stock' in page_text:
        return True
    
    if any(term in page_text for term in ['out of stock', 'sold out', 'unavailable']):
        return False
    
    # Look for "Add to Cart" button
    add_to_cart = soup.find(['button', 'input'], string=re.compile(r'add\s*to\s*cart', re.I))
    if add_to_cart:
        return True
    
    # Default to True
    return True


def _extract_tobacco_locker_box_quantity(soup: BeautifulSoup) -> Optional[int]:
    """Extract box quantity from Tobacco Locker"""
    
    # Strategy 1: Look for "BOX OF X" in description or product details
    page_text = soup.get_text()
    
    # Look for "BOX OF 20" pattern
    box_match = re.search(r'box\s+of\s+(\d+)', page_text, re.I)
    if box_match:
        try:
            qty = int(box_match.group(1))
            if qty >= 10:
                return qty
        except ValueError:
            pass
    
    # Strategy 2: Look for package options
    option_elements = soup.find_all(['option', 'button', 'span'], string=re.compile(r'box\s*\d+', re.I))
    
    for elem in option_elements:
        text = elem.get_text().strip()
        qty_match = re.search(r'box\s*(\d+)', text, re.I)
        if qty_match:
            try:
                qty = int(qty_match.group(1))
                if qty >= 10:
                    return qty
            except ValueError:
                continue
    
    # Strategy 3: Check URL for box quantity
    canonical_url = soup.find('link', rel='canonical')
    if canonical_url:
        url = canonical_url.get('href', '')
        qty_match = re.search(r'(\d+)', url)
        if qty_match:
            try:
                qty = int(qty_match.group(1))
                if 10 <= qty <= 50:  # Reasonable box size range
                    return qty
            except ValueError:
                pass
    
    return None


# Test function
if __name__ == "__main__":
    test_url = "https://tobaccolocker.com/collections/general/products/hoyo-de-monterrey-excalibur-epicures-natural-cigar"
    
    print("=== TESTING TOBACCO LOCKER EXTRACTOR (CORRECTED VERSION) ===")
    print(f"URL: {test_url}")
    print("Expected: Price $135.35, Box of 20, In Stock")
    print("=" * 50)
    
    result = extract_tobacco_locker_data(test_url)
    
    print("Results:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    
    if result.get('price') and result.get('box_quantity'):
        per_stick = result['price'] / result['box_quantity']
        print(f"  price_per_stick: ${per_stick:.2f}")
    
    # Validation
    if result.get('success'):
        expected_price = 135.35
        expected_qty = 20
        
        price_ok = result.get('price') and abs(result['price'] - expected_price) < 1.0
        qty_ok = result.get('box_quantity') == expected_qty
        stock_ok = result.get('in_stock') == True
        
        if price_ok and qty_ok and stock_ok:
            print("SUCCESS: All extractions correct!")
        else:
            print("ISSUES FOUND:")
            if not price_ok:
                print(f"  Price: ${result.get('price')} vs expected ${expected_price}")
            if not qty_ok:
                print(f"  Box quantity: {result.get('box_quantity')} vs expected {expected_qty}")
            if not stock_ok:
                print(f"  Stock: {result.get('in_stock')} vs expected True")
    else:
        print(f"FAILED: {result.get('error')}")
