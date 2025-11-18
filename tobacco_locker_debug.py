#!/usr/bin/env python3
"""
Debug script to see exactly what prices are found on Tobacco Locker pages
This will help us understand why we're getting $245.44 instead of $1,400
"""

import requests
from bs4 import BeautifulSoup
import re
import time

def debug_tobacco_locker_prices(url: str):
    """Debug function to see all prices found on the page"""
    
    print(f"=== DEBUGGING TOBACCO LOCKER PRICE EXTRACTION ===")
    print(f"URL: {url}")
    print("=" * 60)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Strategy 1: Find ALL elements containing prices
        print("1. SEARCHING FOR PRICE ELEMENTS:")
        price_selectors = [
            '[class*="price"]',
            '[data-price]', 
            '.product-price',
            '.price-box',
            '.current-price'
        ]
        
        found_elements = []
        for selector in price_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text().strip()
                if '$' in text:
                    found_elements.append({
                        'selector': selector,
                        'text': text,
                        'classes': elem.get('class', []),
                        'tag': elem.name
                    })
        
        for elem in found_elements:
            print(f"  Selector: {elem['selector']}")
            print(f"  Text: '{elem['text']}'")
            print(f"  Classes: {elem['classes']}")
            print(f"  Tag: {elem['tag']}")
            print("  ---")
        
        # Strategy 2: Find ALL dollar amounts in page text
        print("\n2. ALL DOLLAR AMOUNTS IN PAGE TEXT:")
        page_text = soup.get_text()
        all_prices = re.findall(r'\$(\d{1,4}\.?\d{0,2})', page_text)
        
        unique_prices = sorted(list(set([float(p) for p in all_prices])))
        print(f"  Found prices: {unique_prices}")
        
        # Strategy 3: Look for specific known patterns
        print("\n3. LOOKING FOR MAIN PRODUCT PRICE:")
        
        # Try to find the main price display
        main_price_selectors = [
            'h1 + div [class*="price"]',  # Price near product title
            '.product-price',
            '[data-price-cents]',
            '.price:not(.was-price)',
            'span[class*="price"]:not([class*="compare"])'
        ]
        
        for selector in main_price_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text().strip()
                if '$' in text:
                    price_match = re.search(r'\$(\d{1,4}\.?\d{0,2})', text)
                    if price_match:
                        price_val = float(price_match.group(1))
                        print(f"  Selector '{selector}': ${price_val} from text '{text}'")
        
        # Strategy 4: Look around the product title
        print("\n4. SEARCHING NEAR PRODUCT TITLE:")
        title_elem = soup.find('h1')
        if title_elem:
            print(f"  Product title: '{title_elem.get_text().strip()}'")
            
            # Look for price elements near the title
            parent = title_elem.parent
            if parent:
                price_near_title = parent.find_all(text=re.compile(r'\$\d'))
                for price_text in price_near_title:
                    print(f"  Price near title: '{price_text.strip()}'")
        
        # Strategy 5: Check for JavaScript/dynamic content
        print("\n5. CHECKING FOR JAVASCRIPT PRICE DATA:")
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and ('price' in script.string.lower() or '$' in script.string):
                # Look for price in JavaScript
                js_prices = re.findall(r'["\']?\$?(\d{3,4}\.?\d{0,2})["\']?', script.string)
                if js_prices:
                    print(f"  Found in JS: {js_prices}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    # Test with the Opus X URL
    opus_url = "https://tobaccolocker.com/products/opus_x_robusto_cigars_box?variant=44022945382574"
    debug_tobacco_locker_prices(opus_url)
    
    print("\n" + "=" * 60)
    print("This debug output will help us see exactly what prices")
    print("are being found and why $245.44 is being selected")
    print("instead of the correct $1,400.00")
