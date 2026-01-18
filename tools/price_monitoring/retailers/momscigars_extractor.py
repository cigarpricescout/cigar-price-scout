#!/usr/bin/env python3
"""
Mom's Cigars Test Extractor
Tests extraction from momscigars.com with table-based product layout
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class MomsCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Mom's Cigars URL
        """
        try:
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # DEBUG: Find all select elements
            all_selects = soup.find_all('select')
            print(f"  [DEBUG] Found {len(all_selects)} select elements")
            
            for i, select in enumerate(all_selects):
                print(f"    Select #{i+1}:")
                print(f"      Name: {select.get('name', 'none')}")
                print(f"      Class: {select.get('class', 'none')}")
                print(f"      ID: {select.get('id', 'none')}")
                options = select.find_all('option')
                print(f"      Options: {len(options)}")
                if options:
                    # Show first option text
                    first_text = options[0].get_text().strip()
                    print(f"      First option: {first_text[:100]}")
            
            # Try different ways to find the product select
            product_select = None
            
            # Method 1: Look for select with 'id' name
            product_select = soup.find('select', {'name': 'id'})
            if product_select:
                print(f"  [DEBUG] Found select via name='id'")
            
            # Method 2: Look for select with product-related class
            if not product_select:
                product_select = soup.find('select', class_=lambda x: x and 'product' in str(x).lower())
                if product_select:
                    print(f"  [DEBUG] Found select via product class")
            
            # Method 3: Look for select with variant in class
            if not product_select:
                product_select = soup.find('select', class_=lambda x: x and 'variant' in str(x).lower())
                if product_select:
                    print(f"  [DEBUG] Found select via variant class")
            
            # Method 4: Just take the first select if it has options with prices
            if not product_select and all_selects:
                for select in all_selects:
                    options = select.find_all('option')
                    for opt in options:
                        if '$' in opt.get_text():
                            product_select = select
                            print(f"  [DEBUG] Found select via $ in option text")
                            break
                    if product_select:
                        break
            
            box_price = None
            box_qty = None
            in_stock = False
            
            if product_select:
                options = product_select.find_all('option')
                print(f"  [DEBUG] Processing {len(options)} options")
                
                for option in options:
                    option_text = option.get_text().strip()
                    
                    # Look for "Box of X" in the option text
                    if 'box of' in option_text.lower():
                        print(f"  [DEBUG] Found box option: {option_text[:80]}")
                        
                        # Extract box quantity
                        qty_match = re.search(r'box of (\d+)', option_text, re.IGNORECASE)
                        if qty_match:
                            qty = int(qty_match.group(1))
                            print(f"    Quantity: {qty}")
                            
                            # Extract price from option text
                            price_match = re.search(r'\$(\d+\.?\d*)', option_text)
                            if price_match:
                                price = float(price_match.group(1))
                                print(f"    Price: ${price}")
                                
                                # Check if this option is selected
                                is_selected = option.get('selected') == 'selected'
                                print(f"    Selected: {is_selected}")
                                
                                # Save the first box found, or prefer selected option
                                if box_price is None or is_selected:
                                    box_price = price
                                    box_qty = qty
            else:
                print("  [DEBUG] No product select found!")
            
            # Check stock status
            stock_div = soup.find('div', class_='tabin-stock-availability')
            if stock_div:
                stock_text = stock_div.get_text().lower()
                print(f"  [DEBUG] Stock text: {stock_text[:100]}")
                if 'in stock' in stock_text or 'available' in stock_text:
                    in_stock = True
                elif 'out of stock' in stock_text or 'unavailable' in stock_text:
                    in_stock = False
            else:
                print("  [DEBUG] No stock div found")
            
            return {
                'box_price': box_price,
                'box_qty': box_qty,
                'in_stock': in_stock,
                'discount_percent': None,
                'error': None
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'box_price': None,
                'box_qty': None,
                'in_stock': False,
                'discount_percent': None,
                'error': str(e)
            }


def extract_momscigars_data(url: str) -> Dict:
    """Main extraction function for Mom's Cigars"""
    extractor = MomsCigarsExtractor()
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
    """Test the extractor with provided URLs"""
    
    test_cases = [
        {
            'url': "https://www.momscigars.com/products/arturo-fuente-hemingway",
            'expected_price': 163.99,
            'expected_qty': 25,
            'expected_stock': True,
            'notes': "Short Story Box of 25, in stock"
        },
        {
            'url': "https://www.momscigars.com/products/herrera-esteli-norteno",
            'expected_price': 169.99,
            'expected_qty': 25,
            'expected_stock': False,
            'notes': "Lonsdale Deluxe Box of 25, out of stock"
        }
    ]
    
    print("Testing Mom's Cigars extraction...")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['url'].split('/')[-1].replace('-', ' ').title()}")
        print(f"Expected: ${test_case['expected_price']}, Box of {test_case['expected_qty']}, {'In Stock' if test_case['expected_stock'] else 'Out of Stock'}")
        print(f"Notes: {test_case['notes']}")
        print("-" * 40)
        
        result = extract_momscigars_data(test_case['url'])
        
        if result['error']:
            print(f"ERROR: {result['error']}")
        else:
            print("SUCCESS!")
            print(f"  Price: ${result['price']}")
            print(f"  Box Quantity: {result['box_quantity']}")
            print(f"  In Stock: {result['in_stock']}")
            
            # Validation
            price_match = result['price'] == test_case['expected_price'] if result['price'] else False
            qty_match = result['box_quantity'] == test_case['expected_qty'] if result['box_quantity'] else False
            stock_match = result['in_stock'] == test_case['expected_stock']
            
            print(f"  Price Match: {'[PASS]' if price_match else '[FAIL]'}")
            print(f"  Qty Match: {'[PASS]' if qty_match else '[FAIL]'}")
            print(f"  Stock Match: {'[PASS]' if stock_match else '[FAIL]'}")


if __name__ == "__main__":
    test_extractor()
