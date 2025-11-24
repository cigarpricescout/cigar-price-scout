#!/usr/bin/env python3
"""
Big Humidor Extractor
Extracts pricing data from bighumidor.com product pages
Based on ColdFusion e-commerce platform structure observed in screenshot
Compliance: Tier 1 (1 req/sec, minimal headers)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

class BigHumidorExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Use exact same headers as working extractors
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.request_delay = 1  # 1 second between requests
        self.timeout = 10  # 10 second timeout

    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Big Humidor URL"""
        try:
            print(f"[DEBUG] Fetching: {url}")
            
            # Rate limiting compliance
            time.sleep(self.request_delay)
            
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Initialize data structure
            data = {
                'price': None,
                'in_stock': False,
                'box_qty': None,
                'title': None
            }
            
            # Extract title
            title = self._extract_title(soup)
            if title:
                data['title'] = title
            
            # Extract price - from screenshot shows "Price: $439.95"
            price = self._extract_price(soup)
            if price:
                data['price'] = price
            
            # Extract stock status - screenshot shows "Add to Cart" button
            data['in_stock'] = self._extract_stock_status(soup)
            
            # Extract box quantity - screenshot shows "Box of 25 Cigars"
            box_qty = self._extract_box_quantity(soup)
            if box_qty:
                data['box_qty'] = box_qty
            
            print(f"[DEBUG] Extracted data: {data}")
            return data
            
        except requests.exceptions.HTTPError as e:
            print(f"[ERROR] HTTP {e.response.status_code} error for {url}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Request failed for {url}: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Failed to extract from {url}: {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from Big Humidor page"""
        try:
            # Method 1: Look for the main product title in content area
            # Big Humidor often has the product name in h1, h2, or h3 in the main content
            content_headers = soup.find_all(['h1', 'h2', 'h3'])
            
            for header in content_headers:
                title_text = header.get_text().strip()
                # Skip navigation text and look for actual product names
                if (len(title_text) > 5 and 
                    title_text not in ['Big Humidor', 'Buy Online'] and
                    not title_text.startswith('Cigars') and
                    any(brand in title_text.lower() for brand in ['arturo', 'fuente', 'padron', 'romeo', 'julieta', 'perdomo', 'my father', 'tabak'])):
                    print(f"[DEBUG] Found product title in header: {title_text}")
                    return title_text
            
            # Method 2: Look in the page title and extract product part
            page_title_elem = soup.find('title')
            if page_title_elem:
                page_title = page_title_elem.get_text().strip()
                print(f"[DEBUG] Page title: '{page_title}'")
                
                # Extract product name from titles like "Romeo y Julieta 1875 Churchill - Big Humidor"
                if ' - ' in page_title and 'Big Humidor' in page_title:
                    product_part = page_title.split(' - ')[0].strip()
                    if len(product_part) > 5 and product_part != 'Big Humidor':
                        print(f"[DEBUG] Found title from page title: {product_part}")
                        return product_part
                
                # Handle titles without separator but with brand names
                if any(brand in page_title.lower() for brand in ['arturo', 'fuente', 'padron', 'romeo', 'julieta', 'perdomo', 'my father']) and 'Big Humidor' not in page_title:
                    print(f"[DEBUG] Found title from full page title: {page_title}")
                    return page_title
            
            # Method 3: Look for product info in the main content area
            main_content = soup.find(['div', 'td'], class_=re.compile(r'product|main|content', re.I))
            if main_content:
                # Look for text that appears to be a product name
                text_content = main_content.get_text()
                
                # Look for lines that start with brand names
                for line in text_content.split('\n'):
                    line = line.strip()
                    if (len(line) > 5 and len(line) < 100 and
                        any(brand in line.lower() for brand in ['arturo fuente', 'padron', 'romeo y julieta', 'perdomo', 'my father']) and
                        'box of' not in line.lower() and
                        'ring size' not in line.lower()):
                        print(f"[DEBUG] Found title in content: {line}")
                        return line
            
            print(f"[WARNING] Could not extract specific product title")
            return "Product Title Not Found"
                        
        except Exception as e:
            print(f"[ERROR] Title extraction failed: {e}")
        
        return None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract current price - prioritize sale prices over regular prices"""
        try:
            page_text = soup.get_text()
            print(f"[DEBUG] Searching for sale price patterns in page text...")
            
            # Method 1: Look for regular price FIRST to establish baseline
            regular_price = None
            regular_patterns = [
                r'price:\s*\$(\d+(?:,\d{3})*(?:\.\d{2})?)',  # "Price: $183.95"
            ]
            
            for pattern in regular_patterns:
                price_match = re.search(pattern, page_text, re.IGNORECASE)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    price = float(price_str)
                    if 10 <= price <= 3000:
                        regular_price = price
                        print(f"[DEBUG] Found regular price: ${price}")
                        break
            
            # Method 2: Look for sale price ONLY in context of the regular price
            if regular_price:
                # Look for sale price in text following the regular price
                price_pattern = r'price:\s*\$' + str(regular_price).replace('.', r'\.')
                match = re.search(price_pattern, page_text, re.IGNORECASE)
                if match:
                    match_end = match.end()
                    following_text = page_text[match_end:match_end+100]
                    print(f"[DEBUG] Following text after regular price: '{following_text[:50]}...'")
                    
                    # Look for sale price in following text (must be lower than regular price)
                    sale_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', following_text, re.IGNORECASE)
                    if sale_match:
                        sale_price_str = sale_match.group(1).replace(',', '')
                        sale_price = float(sale_price_str)
                        # Sale price must be lower than regular price and in reasonable range
                        if 10 <= sale_price < regular_price and sale_price <= 3000:
                            print(f"[DEBUG] FOUND SALE PRICE in context: ${sale_price} (lower than regular ${regular_price})")
                            return sale_price
                        else:
                            print(f"[DEBUG] Found price ${sale_price} but not valid sale price (not lower than ${regular_price})")
            
            # Method 3: If no sale price found in context, use regular price
            if regular_price:
                print(f"[DEBUG] Using regular price (no valid sale price found): ${regular_price}")
                return regular_price
            
            # Method 4: Fallback - look for any price near product title
            title_area = soup.find(['h1', 'h2', 'h3'])
            if title_area:
                title_parent = title_area.find_parent()
                if title_parent:
                    title_area_text = title_parent.get_text()
                    print(f"[DEBUG] Looking for price near title area...")
                    
                    # Look for prices in title area
                    prices_in_title_area = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', title_area_text)
                    valid_prices = []
                    
                    for price_str in prices_in_title_area:
                        try:
                            clean_price = float(price_str.replace(',', ''))
                            if 50 <= clean_price <= 3000:  # Reasonable cigar box price range
                                valid_prices.append(clean_price)
                        except ValueError:
                            continue
                    
                    if valid_prices:
                        # Use highest price (likely the main product price)
                        max_price = max(valid_prices)
                        print(f"[DEBUG] Found price in title area: ${max_price}")
                        return max_price
            
            print(f"[DEBUG] No valid price found")
            return None
                
        except Exception as e:
            print(f"[ERROR] Price extraction failed: {e}")
            import traceback
            traceback.print_exc()
        
        return None

    def _extract_stock_status(self, soup: BeautifulSoup) -> bool:
        """Extract stock status - enhanced to detect Big Humidor out of stock patterns"""
        try:
            # Method 1: Look for explicit out of stock text (from second screenshot)
            out_of_stock_patterns = [
                r'this\s+item\s+is\s+currently\s+out\s+of\s+stock',
                r'out\s+of\s+stock',
                r'sold\s+out',
                r'unavailable',
                r'discontinued\s+gone',  # From screenshot: "DISCONTINUED GONE!!"
                r'temporarily\s+unavailable'
            ]
            
            page_text = soup.get_text().lower()
            
            for pattern in out_of_stock_patterns:
                if re.search(pattern, page_text):
                    print(f"[DEBUG] Found out of stock text: {pattern}")
                    return False
            
            # Method 2: Look for "Add to Cart" button (first screenshot shows in-stock)
            button_selectors = [
                'input[type="submit"]', 'input[type="button"]', 'button',
                '[value*="Add"]', '[value*="Cart"]', '[alt*="Add"]'
            ]
            
            for selector in button_selectors:
                button_elem = soup.select_one(selector)
                if button_elem:
                    # Check value attribute and alt text
                    button_text = (button_elem.get('value', '') + ' ' + 
                                 button_elem.get('alt', '') + ' ' + 
                                 button_elem.get_text()).upper()
                    
                    if 'ADD TO CART' in button_text or 'ADD' in button_text:
                        print(f"[DEBUG] Found Add to Cart button - In Stock")
                        return True
                    
                    if any(phrase in button_text for phrase in ['OUT OF STOCK', 'SOLD OUT', 'UNAVAILABLE']):
                        print(f"[DEBUG] Found out of stock button")
                        return False
            
            # Method 3: Look for quantity input field (indicates can purchase)
            qty_input = soup.find('input', {'name': re.compile(r'qty|quantity', re.I)})
            if qty_input:
                print(f"[DEBUG] Found quantity input - likely in stock")
                return True
            
            # Method 4: Look for stock status in specific elements
            stock_elements = soup.find_all(['span', 'div', 'p', 'td'], text=re.compile(r'stock|available', re.I))
            for elem in stock_elements:
                elem_text = elem.get_text().lower()
                if 'out of stock' in elem_text:
                    print(f"[DEBUG] Found out of stock element")
                    return False
                if 'in stock' in elem_text:
                    print(f"[DEBUG] Found in stock element")
                    return True
            
            # Method 5: If we found a price but no explicit out-of-stock indicators, assume in stock
            has_price = bool(re.search(r'\$\d+', soup.get_text()))
            if has_price:
                print(f"[DEBUG] Has price and no out-of-stock indicators - assuming in stock")
                return True
            
            print(f"[DEBUG] No clear stock indicators, defaulting to out of stock")
            return False
            
        except Exception as e:
            print(f"[ERROR] Stock status extraction failed: {e}")
            return True

    def _extract_box_quantity(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract box quantity - must work for ALL products"""
        try:
            page_text = soup.get_text()
            print(f"[DEBUG] Searching for box quantity patterns...")
            
            # Most specific patterns first - include debug output
            quantity_patterns = [
                r'box\s+of\s+(\d+)\s+cigars',  # "Box of 25 Cigars" 
                r'box\s+of\s+(\d+)',           # "Box of 25"
                r'(\d+)\s+cigars?\s+including', # "5 Cigars including:"
                r'(\d+)\s+cigars?\s+per\s+box', # "25 cigars per box"
                r'(\d+)\s*ct\s+box',           # "25ct box"
                r'(\d+)\s*count\s+box'         # "25 count box"
            ]
            
            for i, pattern in enumerate(quantity_patterns):
                print(f"[DEBUG] Trying quantity pattern {i+1}: {pattern}")
                qty_match = re.search(pattern, page_text, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    # Filter for reasonable box quantities (avoid ring gauges like 50, 52, 54)
                    if 5 <= qty <= 50 and qty not in [46, 48, 50, 52, 54, 56, 58, 60]:  # Exclude common ring gauges
                        print(f"[DEBUG] FOUND quantity via pattern '{pattern}': {qty}")
                        return qty
                    else:
                        print(f"[DEBUG] Found quantity {qty} but filtered out (likely ring gauge)")
            
            # More flexible search - look for "Box of X" anywhere in page
            all_box_matches = re.findall(r'box\s+of\s+(\d+)', page_text, re.IGNORECASE)
            print(f"[DEBUG] All 'box of X' matches found: {all_box_matches}")
            
            for qty_str in all_box_matches:
                qty = int(qty_str)
                if 5 <= qty <= 50 and qty not in [46, 48, 50, 52, 54, 56, 58, 60]:
                    print(f"[DEBUG] FOUND valid box quantity from all matches: {qty}")
                    return qty
            
            # Look in more structured areas - product description tables/cells
            product_cells = soup.find_all(['td', 'div', 'span'], string=re.compile(r'box.*\d+|cigars.*\d+', re.I))
            print(f"[DEBUG] Found {len(product_cells)} cells with box/cigar text")
            
            for cell in product_cells:
                cell_text = cell.get_text()
                print(f"[DEBUG] Checking cell text: '{cell_text[:100]}...'")
                # Be very specific about box quantity context
                if 'box of' in cell_text.lower():
                    qty_match = re.search(r'box\s+of\s+(\d+)', cell_text, re.IGNORECASE)
                    if qty_match:
                        qty = int(qty_match.group(1))
                        if 5 <= qty <= 50 and qty not in [46, 48, 50, 52, 54, 56, 58, 60]:
                            print(f"[DEBUG] FOUND quantity in cell: {qty}")
                            return qty
            
            # Final fallback: Look for quantity in title but be more careful
            title_elem = soup.select_one('h3, h2, h1, title')
            if title_elem:
                title_text = title_elem.get_text()
                print(f"[DEBUG] Checking title for quantity: '{title_text}'")
                # Only look for box quantities in title, not ring gauges
                box_match = re.search(r'box\s+of\s+(\d+)', title_text, re.IGNORECASE)
                if box_match:
                    qty = int(box_match.group(1))
                    if 5 <= qty <= 50:
                        print(f"[DEBUG] FOUND quantity in title: {qty}")
                        return qty
            
            print(f"[ERROR] No valid box quantity found - this is a critical failure")
            return None
            
        except Exception as e:
            print(f"[ERROR] Box quantity extraction failed: {e}")
            import traceback
            traceback.print_exc()
        
        return None

    def test_extraction(self, test_urls=None):
        """Test extraction on Big Humidor URLs"""
        if not test_urls:
            test_urls = [
                "https://www.bighumidor.com/index.cfm?ref=80200&ref2=245",   # Padron 1964, $439.95, In Stock, Box of 25
                "https://www.bighumidor.com/index.cfm?ref=80200&ref2=2745",  # Tabak Especiale, $29.95, Out of Stock, Box of 5  
                "https://www.bighumidor.com/index.cfm?ref=80200&ref2=1455",  # Arturo Fuente, Regular $409.95, Sale $375.95, In Stock, Box of 25
                "https://www.bighumidor.com/index.cfm?ref=80200&ref2=363"    # Romeo y Julieta 1875 Churchill - PROBLEM URL
            ]
        
        print("Testing Big Humidor extraction...")
        print("Compliance: Tier 1 (1 req/sec, minimal headers)")
        print("=" * 60)
        
        expected_results = [
            {"price": 439.95, "stock": True, "qty": 25, "name": "Padron 1964"},
            {"price": 29.95, "stock": False, "qty": 5, "name": "Tabak Especiale"},
            {"price": 375.95, "stock": True, "qty": 25, "name": "Arturo Fuente (SALE PRICE)"},
            {"price": "Unknown", "stock": True, "qty": 25, "name": "Romeo y Julieta 1875 Churchill"}
        ]
        
        for i, url in enumerate(test_urls, 1):
            expected = expected_results[i-1] if i <= len(expected_results) else {}
            
            print(f"\n[TEST {i}] Testing URL: {url}")
            if expected.get('name'):
                print(f"Expected: {expected['name']}")
            if expected.get('price') != "Unknown":
                print(f"Price=${expected.get('price', 'Unknown')}, Stock={'In' if expected.get('stock') else 'Out of'} Stock, Qty={expected.get('qty', 'Unknown')}")
            
            if expected.get('name') == "Arturo Fuente (SALE PRICE)":
                print(f"NOTE: Should extract SALE price $375.95, NOT regular price $409.95")
            
            start_time = time.time()
            data = self.extract_product_data(url)
            end_time = time.time()
            
            if data:
                print(f"[RESULT] Title: {data['title']}")
                
                if data['price']:
                    expected_price = expected.get('price')
                    if expected_price != "Unknown" and expected_price and abs(data['price'] - expected_price) < 1.0:
                        price_status = "[OK]"
                    elif expected_price == "Unknown":
                        price_status = "[INFO]"
                    elif expected_price:
                        price_status = "[WARN]"
                    else:
                        price_status = "[INFO]"
                    print(f"{price_status} Price: ${data['price']:.2f}")
                else:
                    print("[FAIL] Price: Not found")
                
                expected_stock = expected.get('stock')
                if expected_stock is not None:
                    stock_status = "[OK]" if data['in_stock'] == expected_stock else "[WARN]"
                else:
                    stock_status = "[INFO]"
                print(f"{stock_status} Stock: {'In Stock' if data['in_stock'] else 'Out of Stock'}")
                
                if data['box_qty']:
                    expected_qty = expected.get('qty')
                    if expected_qty and data['box_qty'] == expected_qty:
                        qty_status = "[OK]"
                    elif expected_qty:
                        qty_status = "[WARN]"
                    else:
                        qty_status = "[INFO]"
                    print(f"{qty_status} Box Qty: {data['box_qty']}")
                else:
                    print("[INFO] Box Qty: Not found")
                    
            else:
                print("[FAIL] Extraction failed")
            
            print(f"[DEBUG] Request took {end_time - start_time:.2f}s")
            
            # Rate limiting for multiple URLs
            if i < len(test_urls):
                print("[DEBUG] Rate limiting: waiting 1 second...")
                time.sleep(self.request_delay)
        
        print("\n" + "=" * 60)
        print("Test completed - Check all results against expected values")
        print("CRITICAL: Test 3 must show $375.95 (sale price), NOT $409.95 (regular price)")
        print("CRITICAL: Test 4 (Romeo y Julieta) must extract title and price correctly")

if __name__ == "__main__":
    extractor = BigHumidorExtractor()
    extractor.test_extraction()
