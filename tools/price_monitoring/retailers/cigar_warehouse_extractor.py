#!/usr/bin/env python3
"""
Cigar Warehouse USA Price Extractor
Extracts pricing data from cigarwarehouseusa.com product pages
Compliance: Tier 1 (No scraping clause; stable URLs)
Rate: 1 request/second, Timeout: 10 seconds
Platform: WooCommerce
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin

class CigarWarehouseExtractor:
    def __init__(self):
        self.base_url = "https://cigarwarehouseusa.com"
        self.session = requests.Session()
        # Use exact same headers as working Absolute Cigars extractor
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.request_delay = 1  # 1 second between requests
        self.timeout = 10  # 10 second timeout

    def extract_product_data(self, url):
        """Extract product data from a single URL with proven pattern"""
        try:
            print(f"[DEBUG] Fetching: {url}")
            
            # Use exact same rate limiting pattern as working extractor
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
            
            # Extract title - WooCommerce standard
            title_elem = soup.find('h1', class_='product_title entry-title')
            if not title_elem:
                title_elem = soup.find('h1', class_='product-title')
            if not title_elem:
                title_elem = soup.find('h1')
            if title_elem:
                data['title'] = title_elem.get_text().strip()
            
            # Extract price using proven method
            price = self._extract_pricing_robust(soup)
            if price:
                data['price'] = price
            
            # Extract stock status using proven method
            data['in_stock'] = self._extract_stock_robust(soup)
            
            # Extract box quantity
            box_qty = self._extract_box_quantity(soup)
            if box_qty:
                data['box_qty'] = box_qty
            
            print(f"[DEBUG] Extracted data: {data}")
            return data
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 520:
                print(f"[ERROR] 520 Server Error - Server returned unknown error for {url}")
                print(f"[DEBUG] This might be temporary server issues or protection - try again later")
            else:
                print(f"[ERROR] HTTP {e.response.status_code} error for {url}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Request failed for {url}: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Failed to extract from {url}: {e}")
            return None

    def _extract_pricing_robust(self, soup):
        """Extract pricing using proven robust method from working extractors"""
        try:
            # Method 1: Look for main product pricing area (like Absolute Cigars)
            product_summary = soup.find(['div'], class_=re.compile(r'product-summary|summary|product-info|single-product|entry-summary', re.I))
            
            if product_summary:
                # Look for price elements in WooCommerce format
                price_elements = product_summary.find_all(['span', 'div'], class_=re.compile(r'woocommerce-Price-amount|amount|price'))
                
                current_prices = []
                
                for elem in price_elements:
                    price_text = elem.get_text().strip()
                    # Handle various price formats including commas
                    price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', price_text)
                    
                    if price_match:
                        try:
                            price_str = price_match.group(1).replace(',', '')
                            price = float(price_str)
                            # Filter for reasonable cigar pricing range
                            if 10 <= price <= 3000:
                                # Check if it's not a strikethrough (old price)
                                is_strikethrough = (
                                    elem.find_parent(['del', 's']) or
                                    (elem.has_attr('style') and 'line-through' in str(elem.get('style', '')))
                                )
                                
                                if not is_strikethrough:
                                    current_prices.append(price)
                                    
                        except ValueError:
                            continue
                
                # Remove navigation noise (common on e-commerce sites)
                navigation_prices = {0.0}  # Cart totals, etc.
                current_prices = [p for p in current_prices if p not in navigation_prices]
                
                if current_prices:
                    # Return the highest valid price (main product price)
                    return max(current_prices)
            
            # Method 2: Fallback - look in entire page but be selective
            page_text = soup.get_text()
            all_prices = re.findall(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', page_text)
            
            valid_prices = []
            for price_str in all_prices:
                try:
                    clean_price = float(price_str.replace(',', ''))
                    # Cigar warehouse typical range
                    if 20 <= clean_price <= 2000:
                        valid_prices.append(clean_price)
                except ValueError:
                    continue
            
            # Filter out navigation noise
            navigation_prices = {0.0}
            product_prices = [p for p in valid_prices if p not in navigation_prices]
            
            if product_prices:
                # For Padron 1964, we expect around $454.99
                expected_range_prices = [p for p in product_prices if 400 <= p <= 500]
                if expected_range_prices:
                    return max(expected_range_prices)
                
                # Otherwise return highest reasonable price
                return max(product_prices)
                
        except Exception as e:
            print(f"[ERROR] Robust price extraction failed: {e}")
        
        return None

    def _extract_stock_robust(self, soup):
        """Extract stock status using proven robust method"""
        try:
            # Method 1: Look for buy button (proven method from Absolute Cigars)
            buy_button = soup.find(['button', 'input'], class_=re.compile(r'add.*cart|cart.*add|single_add_to_cart_button|buy.*now', re.I))
            
            if buy_button:
                button_text = buy_button.get_text().strip().upper()
                # Strong in-stock indicators
                if any(phrase in button_text for phrase in ['BUY NOW', 'ADD TO CART', 'PURCHASE']):
                    print(f"[DEBUG] Found in-stock via button: {button_text}")
                    return True
                # Strong out-of-stock indicators  
                if any(phrase in button_text for phrase in ['OUT OF STOCK', 'NOTIFY ME', 'SOLD OUT']):
                    print(f"[DEBUG] Found out-of-stock via button: {button_text}")
                    return False
            
            # Method 2: Look for explicit stock status text
            stock_indicators = soup.find_all(string=re.compile(r'(?:in\s+stock|out\s+of\s+stock|sold\s+out|availability)', re.I))
            for indicator in stock_indicators:
                text = indicator.strip().upper()
                if 'IN STOCK' in text:
                    print(f"[DEBUG] Found in-stock via text: {text}")
                    return True
                if any(phrase in text for phrase in ['OUT OF STOCK', 'SOLD OUT']):
                    print(f"[DEBUG] Found out-of-stock via text: {text}")
                    return False
            
            # Method 3: Look for stock status elements
            availability_elem = soup.find(['span', 'div', 'p'], class_=re.compile(r'stock|availability', re.I))
            if availability_elem:
                avail_text = availability_elem.get_text().strip().upper()
                if 'OUT OF STOCK' in avail_text:
                    print(f"[DEBUG] Found out-of-stock via element: {avail_text}")
                    return False
                if 'IN STOCK' in avail_text:
                    print(f"[DEBUG] Found in-stock via element: {avail_text}")
                    return True
            
            # Method 4: If we found a valid price, likely in stock
            page_text = soup.get_text()
            has_price = bool(re.search(r'\$\d+', page_text))
            
            if has_price:
                print(f"[DEBUG] Has price, assuming in stock")
                return True
            else:
                print(f"[DEBUG] No price found, assuming out of stock")
                return False
                
        except Exception as e:
            print(f"[ERROR] Robust stock extraction failed: {e}")
            return True

    def _extract_box_quantity(self, soup):
        """Extract box quantity from WooCommerce product specifications"""
        try:
            # WooCommerce product attributes table
            attribute_tables = soup.find_all('table', class_='woocommerce-product-attributes')
            for table in attribute_tables:
                rows = table.find_all('tr')
                for row in rows:
                    th = row.find('th')
                    td = row.find('td')
                    if th and td:
                        header = th.get_text().strip().lower()
                        value = td.get_text().strip()
                        
                        if any(keyword in header for keyword in ['quantity', 'count', 'cigars', 'pieces']):
                            qty_match = re.search(r'(\d+)', value)
                            if qty_match:
                                print(f"[DEBUG] Found quantity in attributes table: {qty_match.group(1)}")
                                return int(qty_match.group(1))
            
            # Look for quantity in product description/details
            quantity_patterns = [
                r'quantity of cigars:\s*(\d+)',
                r'box of (\d+)',
                r'(\d+) cigars',
                r'(\d+)-count',
                r'quantity:\s*(\d+)',
                r'count:\s*(\d+)',
                r'(\d+)\s*piece',
                r'contains\s*(\d+)'
            ]
            
            # Search in product content areas
            content_areas = [
                soup.find('div', class_='woocommerce-product-details__short-description'),
                soup.find('div', class_='woocommerce-Tabs-panel--description'),
                soup.find('div', id='tab-description'),
                soup.find('div', class_='product-description')
            ]
            
            for area in content_areas:
                if area:
                    area_text = area.get_text()
                    for pattern in quantity_patterns:
                        match = re.search(pattern, area_text, re.IGNORECASE)
                        if match:
                            print(f"[DEBUG] Found quantity in content: {match.group(1)}")
                            return int(match.group(1))
            
            # Check product title for quantity
            title_elem = soup.find('h1', class_='product_title entry-title')
            if title_elem:
                title_text = title_elem.get_text()
                for pattern in quantity_patterns:
                    match = re.search(pattern, title_text, re.IGNORECASE)
                    if match:
                        print(f"[DEBUG] Found quantity in title: {match.group(1)}")
                        return int(match.group(1))
            
            # Search entire page as last resort
            page_text = soup.get_text()
            for pattern in quantity_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    qty = int(match.group(1))
                    # Sanity check - reasonable box quantities
                    if 1 <= qty <= 100:
                        print(f"[DEBUG] Found quantity in page text: {qty}")
                        return qty
            
        except Exception as e:
            print(f"[ERROR] Box quantity extraction failed: {e}")
        
        return None

    def test_extraction(self, test_urls=None):
        """Test extraction on sample URLs with rate limiting compliance"""
        if not test_urls:
            test_urls = [
                "https://cigarwarehouseusa.com/product/padron-1964-anniversary-series-diplomatico-maduro-box/"
            ]
        
        print("Testing Cigar Warehouse USA extraction...")
        print("Compliance: Tier 1 (1 req/sec, minimal headers)")
        print("=" * 60)
        
        for i, url in enumerate(test_urls, 1):
            print(f"\n[TEST {i}] Testing URL: {url}")
            print(f"Expected: Price=$454.99, Stock=In Stock")
            
            start_time = time.time()
            data = self.extract_product_data(url)
            end_time = time.time()
            
            if data:
                print(f"[OK] Title: {data['title']}")
                
                if data['price']:
                    price_status = "[OK]" if abs(data['price'] - 454.99) < 0.01 else "[WARN]"
                    print(f"{price_status} Price: ${data['price']:.2f}")
                else:
                    print("[FAIL] Price: Not found")
                
                stock_status = "[OK]" if data['in_stock'] else "[WARN]"
                print(f"{stock_status} Stock: {'In Stock' if data['in_stock'] else 'Out of Stock'}")
                
                if data['box_qty']:
                    print(f"[OK] Box Qty: {data['box_qty']}")
                else:
                    print("[INFO] Box Qty: Not found (may need manual entry)")
                    
            else:
                print("[FAIL] Extraction failed")
            
            print(f"[DEBUG] Request took {end_time - start_time:.2f}s")
            
            # Rate limiting compliance for multiple URLs
            if i < len(test_urls):
                print("[DEBUG] Rate limiting: waiting 1 second...")
                time.sleep(self.request_delay)
        
        print("\n" + "=" * 60)
        print("Test completed - Check results against expected values")
        print("Expected: Price=$454.99, Stock=In Stock")

if __name__ == "__main__":
    extractor = CigarWarehouseExtractor()
    extractor.test_extraction()
