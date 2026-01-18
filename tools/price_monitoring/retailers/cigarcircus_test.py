#!/usr/bin/env python3
"""
Cigar Circus Extractor
Clean traditional layout with radio button package selection
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict

class CigarCircusExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Use exact same headers as working extractors
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Cigar Circus URL"""
        try:
            # Rate limiting - 1 request per second
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract data
            box_qty = None
            box_price = None
            in_stock = False
            
            # Look for "Box of 25" text first to establish context
            page_text = soup.get_text()
            box_match = re.search(r'Box of (\d+)', page_text, re.IGNORECASE)
            if box_match:
                box_qty = int(box_match.group(1))
                print(f"  Found box quantity: {box_qty}")
            
            # Find all prices on the page using multiple methods
            all_prices = []
            
            # Method 1: Find spans with price/currency in class
            price_elements = soup.find_all('span', class_=re.compile(r'price|currency|value', re.I))
            for elem in price_elements:
                price_text = elem.get_text().strip()
                price_match = re.search(r'(\d+\.?\d*)', price_text.replace(',', ''))
                if price_match:
                    try:
                        price = float(price_match.group(1))
                        if 10 <= price <= 2000:
                            all_prices.append(price)
                            print(f"  Found price in span: ${price}")
                    except ValueError:
                        continue
            
            # Method 2: Look for all dollar amounts in text
            all_dollar_matches = re.findall(r'\$\s*(\d+\.?\d*)', soup.get_text())
            for match in all_dollar_matches:
                try:
                    price = float(match)
                    if 10 <= price <= 2000:
                        all_prices.append(price)
                        print(f"  Found price via regex: ${price}")
                except ValueError:
                    continue
            
            # Method 3: Look specifically for oe_currency_value class (from screenshot)
            oe_price_elems = soup.find_all(class_='oe_currency_value')
            for elem in oe_price_elems:
                price_text = elem.get_text().strip()
                try:
                    price = float(price_text.replace(',', ''))
                    if 10 <= price <= 2000:
                        all_prices.append(price)
                        print(f"  Found price in oe_currency_value: ${price}")
                except ValueError:
                    continue
            
            # Remove duplicates and sort
            unique_prices = sorted(list(set(all_prices)))
            print(f"  All unique prices found: {unique_prices}")
            
            # The box price is typically the highest price
            if unique_prices:
                box_price = max(unique_prices)
                print(f"  Selected box price (highest): ${box_price}")
            
            # Alternative: Look specifically for price near "Box of 25" text
            if not box_price and box_qty:
                # Find elements containing "Box of X"
                box_elements = soup.find_all(string=re.compile(r'Box of \d+', re.I))
                for box_elem in box_elements:
                    # Look for price in nearby elements
                    parent = box_elem.parent if hasattr(box_elem, 'parent') else None
                    if parent:
                        # Search siblings and nearby elements
                        for sibling in parent.find_next_siblings(limit=10):
                            price_match = re.search(r'\$\s*(\d+\.?\d*)', sibling.get_text())
                            if price_match:
                                try:
                                    price = float(price_match.group(1))
                                    if 100 <= price <= 2000:
                                        box_price = price
                                        print(f"  Found box price near 'Box of {box_qty}': ${box_price}")
                                        break
                                except ValueError:
                                    continue
                        if box_price:
                            break
            
            # Check stock status more thoroughly
            # Method 1: Look for "Add to cart" button
            add_to_cart_buttons = soup.find_all(['button', 'input', 'a'])
            for button in add_to_cart_buttons:
                button_text = button.get_text().strip().lower()
                if 'add to cart' in button_text:
                    is_disabled = button.get('disabled') is not None or 'disabled' in button.get('class', [])
                    in_stock = not is_disabled
                    print(f"  Found 'Add to cart' button, disabled: {is_disabled}")
                    break
            
            # Method 2: Check page text for stock indicators
            if not in_stock:
                page_lower = page_text.lower()
                if 'in stock' in page_lower or 'available' in page_lower:
                    in_stock = True
                    print(f"  Found 'in stock' or 'available' text")
                elif 'out of stock' not in page_lower and 'sold out' not in page_lower:
                    # If no explicit out of stock message and we have an add to cart button, assume in stock
                    if any('add to cart' in btn.get_text().lower() for btn in add_to_cart_buttons):
                        in_stock = True
                        print(f"  Has Add to cart button, no out of stock text -> in stock")
            
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
    
    print("Testing Cigar Circus extraction...")
    print("=" * 60)
    
    url = "https://www.cigarcircus.com/shop/arturo-fuente-hemingway-hemingway-short-story-21607#attribute_values=2731,2806,2823,2891,2935,3116,3156,3001"
    expected_price = 207.90
    expected_qty = 25
    expected_stock = True
    
    print(f"\nTest: Arturo Fuente Hemingway Short Story")
    print(f"Expected: ${expected_price}, Box of {expected_qty}, In Stock")
    print("-" * 40)
    
    extractor = CigarCircusExtractor()
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
