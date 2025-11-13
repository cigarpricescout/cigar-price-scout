"""
CigarPlace.biz Extractor - SIMPLIFIED VERSION
Avoids complex class attribute processing that was causing errors
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def extract_cigarplace_data(url: str) -> Dict:
    """
    Extract data from CigarPlace.biz product pages - simplified approach
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract product title
        title_elem = soup.find('h1') or soup.find('h2')
        product_title = title_elem.get_text().strip() if title_elem else "Unknown Product"
        
        print(f"DEBUG: Product title: {product_title}")
        
        # Get page text for analysis
        page_text = soup.get_text()
        print(f"DEBUG: Page contains {len(page_text)} characters")
        
        # Look for specific text that should be near prices
        price_keywords = ['msrp', 'price', 'save', 'you save', '$']
        for keyword in price_keywords:
            if keyword.lower() in page_text.lower():
                # Find the context around this keyword
                keyword_pos = page_text.lower().find(keyword.lower())
                start = max(0, keyword_pos - 50)
                end = min(len(page_text), keyword_pos + 100)
                context = page_text[start:end]
                print(f"DEBUG: Context around '{keyword}': ...{context}...")
        
        # Also check if there are any elements with price-related attributes
        price_attrs = soup.find_all(attrs={'data-price': True})
        if price_attrs:
            for elem in price_attrs[:3]:
                print(f"DEBUG: Element with data-price: {elem.get('data-price')}")
        
        value_attrs = soup.find_all(attrs={'value': re.compile(r'\d+', re.I)})
        if value_attrs:
            for elem in value_attrs[:3]:
                val = elem.get('value')
                if val and re.search(r'\d+', str(val)):
                    print(f"DEBUG: Element with numeric value: {val}")
        
        # Extract all prices on the page with more flexible patterns
        # Look for various price formats: $123.45, $123, 123.45, etc.
        price_patterns = [
            r'\$(\d+\.\d{2})',  # $123.45
            r'\$(\d+)',         # $123  
            r'(\d+\.\d{2})',    # 123.45
            r'price[:\s]*\$?(\d+\.?\d*)',  # price: $123 or price: 123
            r'msrp[:\s]*\$?(\d+\.?\d*)',   # msrp: $123
        ]
        
        all_prices = []
        for pattern in price_patterns:
            matches = re.findall(pattern, page_text, re.I)
            all_prices.extend([float(p) for p in matches])
        
        # Remove duplicates and filter to reasonable range
        price_values = list(set([p for p in all_prices if 50 <= p <= 2000]))
        price_values.sort()  # Sort for easier analysis
        
        print(f"DEBUG: Found prices: {price_values}")
        
        # Also search in HTML for price elements specifically
        price_elements = soup.find_all(['span', 'div', 'p'], string=re.compile(r'\$\d+', re.I))
        print(f"DEBUG: Found {len(price_elements)} potential price elements")
        
        for elem in price_elements[:5]:  # Check first 5
            elem_text = elem.get_text().strip()
            print(f"DEBUG: Price element text: '{elem_text}'")
            price_match = re.search(r'\$(\d+\.?\d*)', elem_text)
            if price_match:
                price_val = float(price_match.group(1))
                if 50 <= price_val <= 2000 and price_val not in price_values:
                    price_values.append(price_val)
        
        print(f"DEBUG: Final price list: {sorted(price_values)}")
        
        # Logic for CigarPlace pricing structure:
        # - Usually has MSRP (higher) and Sale Price (lower)
        # - If only one price, that's the current price
        current_price = None
        original_price = None
        
        if len(price_values) == 1:
            current_price = price_values[0]
        elif len(price_values) >= 2:
            # Assume highest price is MSRP, lowest is sale price
            current_price = min(price_values)
            original_price = max(price_values)
            
            # But if they're too close, might be the same price repeated
            if original_price - current_price < 10:
                current_price = price_values[0]
                original_price = None
        
        # Extract stock status - look for key button text
        stock_status = True  # Default to in stock
        
        if re.search(r'notify\s*me', page_text, re.I):
            stock_status = False
            print("DEBUG: Found 'Notify Me' - marking as out of stock")
        elif re.search(r'add\s*to\s*cart', page_text, re.I):
            stock_status = True
            print("DEBUG: Found 'Add to Cart' - marking as in stock")
        elif re.search(r'out\s*of\s*stock', page_text, re.I):
            stock_status = False
            print("DEBUG: Found 'Out of Stock' text")
        
        # Extract box quantity
        box_qty = None
        
        # Look for "Box of X" in title first
        title_match = re.search(r'box\s*of\s*(\d+)', product_title, re.I)
        if title_match:
            box_qty = int(title_match.group(1))
            print(f"DEBUG: Found box quantity in title: {box_qty}")
        
        # Look for box quantity in page text
        if not box_qty:
            box_matches = re.findall(r'box\s*of\s*(\d+)', page_text, re.I)
            for match in box_matches:
                qty = int(match)
                if 5 <= qty <= 100:  # Reasonable range
                    box_qty = qty
                    print(f"DEBUG: Found box quantity in page: {box_qty}")
                    break
        
        # Calculate discount percentage
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        # Look for explicit discount percentage
        discount_match = re.search(r'save\s*(\d+)%|(\d+)%\s*off', page_text, re.I)
        if discount_match and not discount_percent:
            discount_percent = float(discount_match.group(1) or discount_match.group(2))
        
        print(f"DEBUG: Final results - Price: {current_price}, MSRP: {original_price}, Stock: {stock_status}, Box Qty: {box_qty}")
        
        return {
            'success': True,
            'product_title': product_title,
            'price': current_price,
            'original_price': original_price,
            'discount_percent': discount_percent,
            'in_stock': stock_status,
            'box_quantity': box_qty,
            'error': None
        }
        
    except Exception as e:
        print(f"DEBUG: Exception occurred: {e}")
        return {
            'success': False,
            'product_title': None,
            'price': None,
            'original_price': None,
            'discount_percent': None,
            'in_stock': False,
            'box_quantity': None,
            'error': str(e)
        }


# Test function
if __name__ == "__main__":
    test_urls = [
        "https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html",
        "https://www.cigarplace.biz/arturo-fuente-hemingway-natural-classic.html"
    ]
    
    print("=" * 70)
    print("CIGARPLACE.BIZ EXTRACTOR TEST - SIMPLIFIED")
    print("=" * 70)
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n[{i}] Testing: {url}")
        print("-" * 50)
        
        result = extract_cigarplace_data(url)
        
        print(f"Success: {result['success']}")
        print(f"Title: {result['product_title']}")
        print(f"Price: ${result['price']}" if result['price'] else "Price: None")
        print(f"MSRP: ${result['original_price']}" if result['original_price'] else "MSRP: None")
        print(f"Box Qty: {result['box_quantity']}")
        print(f"In Stock: {result['in_stock']}")
        
        if result['discount_percent']:
            print(f"Discount: {result['discount_percent']:.1f}%")
        
        if result['price'] and result['box_quantity']:
            per_stick = result['price'] / result['box_quantity']
            print(f"Price per stick: ${per_stick:.2f}")
        
        if not result['success']:
            print(f"Error: {result['error']}")
