#!/usr/bin/env python3
"""
Casa de Montecristo Test Extractor
Clean traditional layout with clear product information
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict

class CasaDeMonteExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Use exact same headers as working extractors
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Casa de Montecristo URL"""
        try:
            # Rate limiting - 1 request per second
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            print(f"  Status: {response.status_code}")
            print(f"  Content length: {len(response.text)} characters")
            
            # Quick checks
            if '314.88' in response.text:
                print(f"  Found '314.88' in raw HTML")
            else:
                print(f"  '314.88' NOT in raw HTML")
            
            if 'Cedar Chest of 25' in response.text:
                print(f"  Found 'Cedar Chest of 25' in raw HTML")
            else:
                print(f"  'Cedar Chest of 25' NOT in raw HTML")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract data
            box_qty = None
            box_price = None
            in_stock = False
            
            # Look for "Cedar Chest of 25" text
            page_text = soup.get_text()
            
            # Extract box quantity
            qty_patterns = [
                r'Cedar Chest of (\d+)',
                r'Box of (\d+)',
                r'(\d+) count'
            ]
            
            for pattern in qty_patterns:
                qty_match = re.search(pattern, page_text, re.IGNORECASE)
                if qty_match:
                    box_qty = int(qty_match.group(1))
                    print(f"  Found box quantity: {box_qty}")
                    break
            
            # Extract price - look for $314.88
            # Try multiple methods
            
            # Method 1: Look for price near "TOTAL" or main price display
            price_match = re.search(r'\$(\d+\.?\d*)', page_text)
            if price_match:
                box_price = float(price_match.group(1))
                print(f"  Found price: ${box_price}")
            
            # Method 2: Look in meta tags or structured data
            if not box_price:
                price_meta = soup.find('meta', {'property': 'og:price:amount'})
                if price_meta:
                    try:
                        box_price = float(price_meta.get('content', ''))
                        print(f"  Found price in meta: ${box_price}")
                    except ValueError:
                        pass
            
            # Check for "ADD TO CART" button (indicates in stock)
            add_to_cart = soup.find(['button', 'input', 'a'], string=re.compile(r'ADD TO CART', re.I))
            if add_to_cart:
                is_disabled = add_to_cart.get('disabled') is not None
                in_stock = not is_disabled
                print(f"  Found ADD TO CART button, disabled: {is_disabled}")
            
            # Also check page text
            if not in_stock:
                page_lower = page_text.lower()
                if 'add to cart' in page_lower and 'out of stock' not in page_lower:
                    in_stock = True
                    print(f"  Found 'add to cart' text, no out of stock -> in stock")
            
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
    
    print("Testing Casa de Montecristo extraction...")
    print("=" * 60)
    
    url = "https://www.casademontecristo.com/item/arturo-fuente-hemingway/classic/AFHC.html"
    expected_price = 314.88
    expected_qty = 25
    expected_stock = True
    
    print(f"\nTest: Arturo Fuente Hemingway Classic")
    print(f"Expected: ${expected_price}, Cedar Chest of {expected_qty}, In Stock")
    print("-" * 40)
    
    extractor = CasaDeMonteExtractor()
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
