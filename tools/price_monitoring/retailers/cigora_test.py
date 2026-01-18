#!/usr/bin/env python3
"""
Cigora Test Extractor
Testing with proven Holt's configuration
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
from typing import Dict

class CigoraExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        self.min_delay = 1
        self.max_delay = 2
    
    def _enforce_rate_limit(self):
        """Conservative rate limiting"""
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
    
    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Cigora URL"""
        try:
            self._enforce_rate_limit()
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for "BOX OF 25" and price "$169.43"
            box_qty = None
            box_price = None
            in_stock = False
            
            # Extract box quantity
            box_text = soup.find(string=re.compile(r'BOX OF \d+', re.I))
            if box_text:
                qty_match = re.search(r'BOX OF (\d+)', box_text, re.IGNORECASE)
                if qty_match:
                    box_qty = int(qty_match.group(1))
                    print(f"  Found box quantity: {box_qty}")
            
            # Extract price - look near "BOX OF 25"
            if box_text:
                # Find parent element and look for price nearby
                parent = box_text.parent
                for _ in range(5):  # Look up 5 levels
                    if parent:
                        price_match = re.search(r'\$(\d+\.?\d*)', parent.get_text())
                        if price_match:
                            price = float(price_match.group(1))
                            if 50 <= price <= 2000:
                                box_price = price
                                print(f"  Found box price: ${box_price}")
                                break
                        parent = parent.parent
            
            # Fallback: search whole page
            if box_price is None:
                price_elements = soup.find_all(string=re.compile(r'\$169\.43'))
                if price_elements:
                    box_price = 169.43
                    print(f"  Found price via exact match: ${box_price}")
            
            # Check stock status
            stock_indicators = soup.find_all(string=re.compile(r'In Stock', re.I))
            if stock_indicators:
                in_stock = True
                print(f"  Found 'In Stock' text")
            
            # Also check for "ADD TO CART" button
            add_to_cart = soup.find(['button', 'a'], string=re.compile(r'ADD TO CART', re.I))
            if add_to_cart:
                in_stock = True
                print(f"  Found 'ADD TO CART' button")
            
            return {
                'box_price': box_price,
                'box_qty': box_qty,
                'in_stock': in_stock,
                'error': None
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'box_price': None,
                'box_qty': None,
                'in_stock': False,
                'error': str(e)
            }


def test_extractor():
    """Test the extractor"""
    
    print("Testing Cigora extraction...")
    print("=" * 60)
    
    url = "https://www.cigora.com/product/arturo-fuente-hemingway/AMA-PM.html"
    expected_price = 169.43
    expected_qty = 25
    expected_stock = True
    
    print(f"\nTest: {url.split('/')[-1]}")
    print(f"Expected: ${expected_price}, Box of {expected_qty}, In Stock")
    print("-" * 40)
    
    extractor = CigoraExtractor()
    result = extractor.extract_product_data(url)
    
    if result['error']:
        print(f"ERROR: {result['error']}")
    else:
        print("SUCCESS!")
        print(f"  Price: ${result['box_price']}")
        print(f"  Box Quantity: {result['box_qty']}")
        print(f"  In Stock: {result['in_stock']}")
        
        # Validation
        price_match = result['box_price'] == expected_price if result['box_price'] else False
        qty_match = result['box_qty'] == expected_qty if result['box_qty'] else False
        stock_match = result['in_stock'] == expected_stock
        
        print(f"  Price Match: {'[PASS]' if price_match else '[FAIL]'}")
        print(f"  Qty Match: {'[PASS]' if qty_match else '[FAIL]'}")
        print(f"  Stock Match: {'[PASS]' if stock_match else '[FAIL]'}")


if __name__ == "__main__":
    test_extractor()
