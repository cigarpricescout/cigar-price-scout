#!/usr/bin/env python3
"""
Mike's Cigars Working Extractor
Clean traditional layout with clear product information
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class MikesCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Rate limiting
        self.min_delay = 1
        self.max_delay = 2
    
    def _enforce_rate_limit(self):
        """Conservative rate limiting"""
        import random
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Mike's Cigars URL
        """
        try:
            self._enforce_rate_limit()
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from "BOX OF 25" text
            box_qty = None
            quantity_text = soup.find(string=re.compile(r'BOX OF \d+', re.I))
            if quantity_text:
                qty_match = re.search(r'BOX OF (\d+)', quantity_text, re.IGNORECASE)
                if qty_match:
                    box_qty = int(qty_match.group(1))
            
            # Extract price - look for the main price display
            box_price = None
            # Try multiple methods
            
            # Method 1: Look for price in common product price containers
            price_selectors = [
                '[class*="price"]',
                '.product-price',
                '.price',
                '[class*="product-info-price"]'
            ]
            
            for selector in price_selectors:
                price_elements = soup.select(selector)
                for elem in price_elements:
                    text = elem.get_text().strip()
                    # Look for price pattern
                    price_match = re.search(r'\$(\d+\.?\d*)', text.replace(',', ''))
                    if price_match:
                        price = float(price_match.group(1))
                        # Reasonable box price range
                        if 50 <= price <= 2000:
                            # Skip MSRP (usually higher) - prefer sale/current price
                            if 'msrp' not in text.lower() and 'was' not in text.lower():
                                if box_price is None or price < box_price:
                                    box_price = price
            
            # Method 2: Find largest price on page (often the main price)
            if box_price is None:
                all_prices = []
                price_pattern = re.findall(r'\$(\d+\.?\d*)', soup.get_text().replace(',', ''))
                for price_str in price_pattern:
                    try:
                        price = float(price_str)
                        if 50 <= price <= 2000:
                            all_prices.append(price)
                    except ValueError:
                        continue
                
                if all_prices:
                    # The product price is usually one of the larger prices
                    all_prices.sort(reverse=True)
                    box_price = all_prices[0]
            
            # Check stock status - look for "Add to Cart" button
            in_stock = False
            add_to_cart = soup.find(['button', 'input', 'a'], 
                                   string=re.compile(r'ADD TO CART', re.I))
            if add_to_cart:
                # Check if button is enabled
                is_disabled = add_to_cart.get('disabled') is not None
                in_stock = not is_disabled
            
            # Also check for explicit out of stock messages
            if in_stock:
                out_of_stock_text = soup.find_all(string=re.compile(r'out of stock|sold out|unavailable', re.I))
                if out_of_stock_text:
                    in_stock = False
            
            # Extract discount if MSRP is present
            discount_percent = None
            msrp_match = re.search(r'MSRP:\s*\$(\d+\.?\d*)', soup.get_text(), re.IGNORECASE)
            if msrp_match and box_price:
                msrp = float(msrp_match.group(1))
                if msrp > box_price:
                    discount_percent = ((msrp - box_price) / msrp) * 100
            
            return {
                'box_price': box_price,
                'box_qty': box_qty,
                'in_stock': in_stock,
                'discount_percent': discount_percent,
                'error': None
            }
            
        except Exception as e:
            return {
                'box_price': None,
                'box_qty': None,
                'in_stock': False,
                'discount_percent': None,
                'error': str(e)
            }


def extract_mikescigars_data(url: str) -> Dict:
    """Main extraction function for Mike's Cigars"""
    extractor = MikesCigarsExtractor()
    result = extractor.extract_product_data(url)
    
    return {
        'success': result['error'] is None,
        'price': result['box_price'], 
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'discount_percent': result['discount_percent'],
        'error': result['error']
    }


def test_extractor():
    """Test the extractor with provided URL"""
    
    test_cases = [
        {
            'url': "https://mikescigars.com/arturo-fuente-hemingway-classic-afhc",
            'expected_price': 283.50,
            'expected_qty': 25,
            'expected_stock': True,
            'notes': "Box of 25, in stock, $283.50"
        }
    ]
    
    print("Testing Mike's Cigars extraction...")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['url'].split('/')[-1]}")
        print(f"Expected: ${test_case['expected_price']}, Box of {test_case['expected_qty']}, {'In Stock' if test_case['expected_stock'] else 'Out of Stock'}")
        print(f"Notes: {test_case['notes']}")
        print("-" * 40)
        
        result = extract_mikescigars_data(test_case['url'])
        
        if result['error']:
            print(f"ERROR: {result['error']}")
        else:
            print("SUCCESS!")
            print(f"  Price: ${result['price']}")
            print(f"  Box Quantity: {result['box_quantity']}")
            print(f"  In Stock: {result['in_stock']}")
            if result['discount_percent']:
                print(f"  Discount: {result['discount_percent']:.1f}% off")
            
            # Validation
            price_match = result['price'] == test_case['expected_price'] if result['price'] else False
            qty_match = result['box_quantity'] == test_case['expected_qty'] if result['box_quantity'] else False
            stock_match = result['in_stock'] == test_case['expected_stock']
            
            print(f"  Price Match: {'[PASS]' if price_match else '[FAIL]'}")
            print(f"  Qty Match: {'[PASS]' if qty_match else '[FAIL]'}")
            print(f"  Stock Match: {'[PASS]' if stock_match else '[FAIL]'}")


if __name__ == "__main__":
    test_extractor()
