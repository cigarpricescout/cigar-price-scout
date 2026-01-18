#!/usr/bin/env python3
"""
Hiland's Cigars Test Extractor
Tests accessibility and identifies extraction patterns for hilandscigars.com
Focuses on single-product page with clear pricing structure and detailed product info
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import random

class HilandsCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': 'https://www.google.com/',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Conservative rate limiting
        self.min_delay = 2
        self.max_delay = 4
    
    def _enforce_rate_limit(self):
        """Enforce 2-4 second delay with jitter"""
        delay = random.uniform(self.min_delay, self.max_delay)
        print(f"[RATE LIMIT] Waiting {delay:.1f} seconds")
        time.sleep(delay)
    
    def test_access(self, url):
        """Test Hiland's Cigars access and data extraction capabilities"""
        
        try:
            print("HILAND'S CIGARS ACCESS TEST")
            print("=" * 50)
            print(f"Testing: {url}")
            
            self._enforce_rate_limit()
            
            response = self.session.get(url, timeout=15)
            print(f"Status Code: {response.status_code}")
            print(f"Response Length: {len(response.content)} bytes")
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}',
                    'anti_bot': f'HTTP {response.status_code} error'
                }
            
            # Check for anti-bot protection
            content_text = response.text.lower()
            anti_bot_indicators = [
                'cloudflare',
                'access denied',
                'blocked',
                'captcha',
                'security check',
                'ray id'
            ]
            
            detected_protection = []
            for indicator in anti_bot_indicators:
                if indicator in content_text:
                    detected_protection.append(indicator)
            
            if detected_protection:
                return {
                    'success': False,
                    'error': f'Anti-bot protection detected: {", ".join(detected_protection)}',
                    'anti_bot': detected_protection
                }
            
            print("SUCCESS: Page loaded successfully")
            
            # Parse and analyze
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get page title
            title = soup.find('title')
            if title:
                print(f"Page Title: {title.get_text(strip=True)}")
            
            # Test data extraction
            print("\nDATA EXTRACTION ANALYSIS:")
            print("-" * 30)
            
            price_result = self._test_price_extraction(soup, content_text)
            stock_result = self._test_stock_detection(soup, content_text)
            quantity_result = self._test_quantity_extraction(soup, content_text)
            product_result = self._test_product_details(soup, content_text)
            structured_result = self._test_structured_data(soup)
            
            return {
                'success': True,
                'anti_bot': None,
                'price_extraction': price_result,
                'stock_detection': stock_result,
                'quantity_extraction': quantity_result,
                'product_details': product_result,
                'structured_data': structured_result,
                'recommendation': self._generate_recommendation(price_result, stock_result, quantity_result, structured_result)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'anti_bot': 'Network or parsing error'
            }
    
    def _test_price_extraction(self, soup, content_text):
        """Test price extraction methods for Hiland's Cigars"""
        print("PRICE EXTRACTION:")
        results = {'methods': [], 'expected_found': False, 'prices': {}}
        
        # Test for expected prices from screenshot
        if '186.40' in content_text:
            print("  Found expected sale price $186.40 in page content")
            results['expected_found'] = True
            results['prices']['sale'] = 186.40
        
        if '211.00' in content_text:
            print("  Found expected original price $211.00 in page content")
            results['prices']['original'] = 211.00
        
        # Method 1: JSON-LD structured data
        try:
            json_scripts = soup.find_all('script', type='application/ld+json')
            for i, script in enumerate(json_scripts):
                if script.string:
                    data = json.loads(script.string.strip())
                    if 'offers' in data:
                        offers = data['offers']
                        if isinstance(offers, list):
                            offers = offers[0]
                        if 'price' in offers:
                            price = float(offers['price'])
                            print(f"  JSON-LD price found: ${price}")
                            results['methods'].append('JSON-LD')
                            results['prices']['json_ld'] = price
                            break
        except Exception:
            pass
        
        # Method 2: Open Graph meta tags
        og_price = soup.find('meta', property='og:price:amount')
        if og_price:
            try:
                price = float(og_price.get('content'))
                print(f"  Open Graph price: ${price}")
                results['methods'].append('Open Graph')
                results['prices']['og'] = price
            except:
                pass
        
        # Method 3: WooCommerce price classes
        woocommerce_selectors = [
            '.woocommerce-Price-amount',
            '.price .amount',
            '.price ins .amount',
            '.price del .amount',
            '.current-price',
            '.sale-price'
        ]
        
        for selector in woocommerce_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text(strip=True).replace('$', '').replace(',', '')
                price_match = re.search(r'(\d+\.?\d*)', text)
                if price_match:
                    price = float(price_match.group(1))
                    if 150 <= price <= 300:  # Reasonable range for this product
                        print(f"  WooCommerce price ({selector}): ${price}")
                        results['methods'].append(f'WooCommerce {selector}')
                        results['prices'][f'woo_{selector}'] = price
                        break
        
        # Method 4: Look for strikethrough original price
        strikethrough_elements = soup.find_all(['s', 'del', 'strike'])
        for elem in strikethrough_elements:
            text = elem.get_text(strip=True).replace('$', '').replace(',', '')
            price_match = re.search(r'(\d+\.?\d*)', text)
            if price_match:
                price = float(price_match.group(1))
                if 150 <= price <= 300:
                    print(f"  Strikethrough original price: ${price}")
                    results['methods'].append('Strikethrough')
                    results['prices']['strikethrough'] = price
        
        # Method 5: Look for "Sale!" badge context
        sale_badges = soup.find_all(string=re.compile(r'sale', re.I))
        if sale_badges:
            print("  Found 'Sale!' badge - indicates sale pricing")
            results['methods'].append('Sale badge')
        
        # Method 6: General price patterns
        price_patterns = [
            r'\$(\d+\.?\d*)',
            r'price[:\s]*\$?(\d+\.?\d*)'
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            for match in matches:
                price = float(match)
                if 150 <= price <= 300:
                    if price not in results['prices'].values():
                        print(f"  Text pattern price: ${price}")
                        results['methods'].append('Text pattern')
                        results['prices'][f'text_{price}'] = price
                        break
        
        if not results['methods']:
            print("  No price extraction methods successful")
        
        return results
    
    def _test_stock_detection(self, soup, content_text):
        """Test stock status detection methods"""
        print("\nSTOCK DETECTION:")
        results = {'methods': [], 'in_stock_indicators': [], 'stock_status': None}
        
        # Method 1: "Add to cart" button (primary indicator from screenshot)
        add_buttons = soup.find_all(['button', 'input', 'a'], string=re.compile(r'add to cart', re.I))
        if add_buttons:
            print("  Found 'Add to cart' button - indicates in stock")
            results['methods'].append('Add to cart button')
            results['in_stock_indicators'].append('Add to cart button')
            results['stock_status'] = True
        
        # Method 2: Button text and class analysis
        buttons = soup.find_all(['button', 'input', 'a'])
        for button in buttons:
            text = button.get_text(strip=True).lower()
            classes = ' '.join(button.get('class', [])).lower()
            
            if 'add to cart' in text:
                print(f"  Stock button found: 'Add to cart'")
                results['methods'].append('Add to cart text')
                results['in_stock_indicators'].append('Add to cart text')
                results['stock_status'] = True
            
            elif 'out of stock' in text or 'sold out' in text:
                print(f"  Out of stock button: '{text}'")
                results['stock_status'] = False
            
            elif 'notify' in text and ('available' in text or 'stock' in text):
                print(f"  Notify when available: '{text}'")
                results['stock_status'] = False
        
        # Method 3: WooCommerce stock classes
        woocommerce_stock_indicators = [
            '.stock.in-stock',
            '.in-stock',
            '.stock.out-of-stock',
            '.out-of-stock'
        ]
        
        for indicator in woocommerce_stock_indicators:
            elements = soup.select(indicator)
            if elements:
                if 'in-stock' in indicator:
                    print(f"  WooCommerce in-stock class found")
                    results['methods'].append('WooCommerce in-stock class')
                    results['in_stock_indicators'].append('WooCommerce in-stock')
                    results['stock_status'] = True
                elif 'out-of-stock' in indicator:
                    print(f"  WooCommerce out-of-stock class found")
                    results['stock_status'] = False
        
        # Method 4: Stock status text
        stock_phrases = [
            'in stock',
            'available now',
            'ready to ship',
            'ships today'
        ]
        
        for phrase in stock_phrases:
            if phrase in content_text:
                print(f"  Stock phrase found: '{phrase}'")
                results['in_stock_indicators'].append(phrase)
                results['stock_status'] = True
        
        # Method 5: Out of stock phrases
        out_stock_phrases = [
            'out of stock',
            'sold out',
            'temporarily unavailable',
            'notify when available',
            'backorder'
        ]
        
        for phrase in out_stock_phrases:
            if phrase in content_text:
                print(f"  Out of stock phrase: '{phrase}'")
                results['stock_status'] = False
        
        # Method 6: Quantity input presence
        quantity_inputs = soup.find_all('input', {'type': ['number', 'text']})
        for inp in quantity_inputs:
            input_attrs = str(inp.get('name', '')) + str(inp.get('id', ''))
            if 'qty' in input_attrs.lower() or 'quantity' in input_attrs.lower():
                print("  Quantity input found - indicates in stock")
                results['methods'].append('Quantity input')
                results['in_stock_indicators'].append('Quantity input')
                if results['stock_status'] is None:
                    results['stock_status'] = True
                break
        
        return results
    
    def _test_quantity_extraction(self, soup, content_text):
        """Test box quantity extraction"""
        print("\nQUANTITY EXTRACTION:")
        results = {'methods': [], 'quantities_found': []}
        
        # Method 1: Title contains "Box of 25" (from screenshot)
        if 'box of 25' in content_text.lower():
            print("  Found 'Box of 25' in page content")
            results['quantities_found'].append(25)
            results['methods'].append('Box of 25 text')
        
        # Method 2: Product title and headers
        headers = soup.find_all(['h1', 'h2', 'h3'])
        for header in headers:
            header_text = header.get_text().lower()
            # Look for box of X pattern
            box_matches = re.findall(r'box of (\d+)', header_text)
            if box_matches:
                print(f"  Header box quantities: {box_matches}")
                for qty_str in box_matches:
                    qty = int(qty_str)
                    if qty not in results['quantities_found']:
                        results['quantities_found'].append(qty)
                        results['methods'].append('Product header')
            
            # Look for size dimensions that might indicate quantity
            if '4.5' in header_text and '55' in header_text:
                print("  Found cigar dimensions: 4.5x55")
        
        # Method 3: Breadcrumb navigation (from screenshot shows box info)
        breadcrumbs = soup.find_all(class_=re.compile(r'breadcrumb', re.I))
        for breadcrumb in breadcrumbs:
            breadcrumb_text = breadcrumb.get_text().lower()
            box_matches = re.findall(r'box of (\d+)', breadcrumb_text)
            if box_matches:
                print(f"  Breadcrumb box quantities: {box_matches}")
                for qty_str in box_matches:
                    qty = int(qty_str)
                    if qty not in results['quantities_found']:
                        results['quantities_found'].append(qty)
                        results['methods'].append('Breadcrumb navigation')
        
        # Method 4: Product specifications table
        spec_tables = soup.find_all('table')
        for table in spec_tables:
            table_text = table.get_text().lower()
            if 'quantity' in table_text or 'box' in table_text:
                qty_matches = re.findall(r'(\d+)', table_text)
                for qty_str in qty_matches:
                    qty = int(qty_str)
                    if 5 <= qty <= 100:
                        if qty not in results['quantities_found']:
                            print(f"  Spec table quantity: {qty}")
                            results['quantities_found'].append(qty)
                            results['methods'].append('Specifications table')
        
        # Method 5: General page content patterns
        quantity_patterns = [
            r'box of (\d+)',
            r'(\d+) pack',
            r'(\d+) count',
            r'(\d+) cigars?'
        ]
        
        for pattern in quantity_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            for match in matches:
                qty = int(match)
                if 5 <= qty <= 100:  # Reasonable cigar box range
                    if qty not in results['quantities_found']:
                        print(f"  Quantity pattern ({pattern}): {qty}")
                        results['quantities_found'].append(qty)
                        results['methods'].append(f'Pattern: {pattern}')
        
        # Remove duplicates and sort
        results['quantities_found'] = sorted(list(set(results['quantities_found'])))
        
        if not results['quantities_found']:
            print("  No quantity extraction successful")
        
        return results
    
    def _test_product_details(self, soup, content_text):
        """Test extraction of detailed product information"""
        print("\nPRODUCT DETAILS EXTRACTION:")
        results = {'methods': [], 'details': {}}
        
        # Look for SKU (from screenshot: 8995)
        sku_patterns = [
            r'sku[:\s]*(\w+)',
            r'product\s+id[:\s]*(\w+)',
            r'item[:\s]*#?(\w+)'
        ]
        
        for pattern in sku_patterns:
            sku_match = re.search(pattern, content_text, re.I)
            if sku_match:
                sku = sku_match.group(1)
                if sku.isdigit() and len(sku) >= 3:  # Reasonable SKU
                    print(f"  Found SKU: {sku}")
                    results['details']['sku'] = sku
                    results['methods'].append('SKU pattern')
                    break
        
        # Look for length (4.5 from screenshot)
        length_pattern = r'length[:\s]*(\d+(?:\.\d+)?)'
        length_match = re.search(length_pattern, content_text, re.I)
        if length_match:
            length = length_match.group(1)
            print(f"  Found length: {length}")
            results['details']['length'] = length
            results['methods'].append('Length specification')
        
        # Look for ring gauge (55 from screenshot)
        ring_patterns = [
            r'ring gauge[:\s]*(\d+)',
            r'ring[:\s]*(\d+)'
        ]
        
        for pattern in ring_patterns:
            ring_match = re.search(pattern, content_text, re.I)
            if ring_match:
                ring = ring_match.group(1)
                print(f"  Found ring gauge: {ring}")
                results['details']['ring_gauge'] = ring
                results['methods'].append('Ring gauge specification')
                break
        
        # Look for shape (Figurado from screenshot)
        shape_pattern = r'shape[:\s]*(\w+)'
        shape_match = re.search(shape_pattern, content_text, re.I)
        if shape_match:
            shape = shape_match.group(1)
            print(f"  Found shape: {shape}")
            results['details']['shape'] = shape
            results['methods'].append('Shape specification')
        
        # Look for wrapper type
        if 'natural' in content_text.lower():
            print("  Found wrapper: Natural")
            results['details']['wrapper'] = 'Natural'
            results['methods'].append('Wrapper text')
        
        # Extract size from title pattern
        size_pattern = r'(\d+(?:\.\d+)?)\s*x\s*(\d+)'
        size_matches = re.findall(size_pattern, content_text)
        if size_matches:
            for length, ring in size_matches:
                size_str = f"{length}x{ring}"
                print(f"  Found size: {size_str}")
                results['details']['size'] = size_str
                results['methods'].append('Size pattern')
                break
        
        return results
    
    def _test_structured_data(self, soup):
        """Test for structured data availability"""
        print("\nSTRUCTURED DATA:")
        results = {'json_ld': 0, 'open_graph': False, 'microdata': 0, 'woocommerce': False}
        
        # JSON-LD scripts
        json_scripts = soup.find_all('script', type='application/ld+json')
        results['json_ld'] = len(json_scripts)
        if json_scripts:
            print(f"  Found {len(json_scripts)} JSON-LD script(s)")
            for i, script in enumerate(json_scripts):
                try:
                    data = json.loads(script.string.strip())
                    data_str = str(data).lower()
                    if 'product' in data_str or 'offer' in data_str or 'price' in data_str:
                        print(f"    Script {i+1}: Contains product/pricing data")
                except Exception:
                    print(f"    Script {i+1}: Could not parse JSON")
        
        # Open Graph tags
        og_tags = soup.find_all('meta', property=re.compile(r'^og:', re.I))
        if og_tags:
            print(f"  Found {len(og_tags)} Open Graph meta tag(s)")
            results['open_graph'] = True
        
        # WooCommerce detection
        woo_indicators = soup.find_all(class_=re.compile(r'woocommerce', re.I))
        if woo_indicators:
            print(f"  WooCommerce platform detected ({len(woo_indicators)} elements)")
            results['woocommerce'] = True
        
        # Schema.org microdata
        microdata_elements = soup.find_all(attrs={'itemprop': True})
        results['microdata'] = len(microdata_elements)
        if microdata_elements:
            print(f"  Found {len(microdata_elements)} microdata element(s)")
        
        return results
    
    def _generate_recommendation(self, price_result, stock_result, quantity_result, structured_result):
        """Generate recommendation based on analysis results"""
        score = 0
        
        # Price extraction scoring
        if price_result['expected_found']:
            score += 3  # High value for finding expected price
        if 'original' in price_result['prices'] or 'strikethrough' in price_result['prices']:
            score += 2  # Bonus for finding original price
        if 'Sale badge' in price_result['methods']:
            score += 1  # Bonus for sale badge detection
        score += len(price_result['methods'])
        
        # Stock detection scoring
        if stock_result['stock_status'] is True:
            score += 2  # Correctly detected in stock
        score += len(stock_result['methods'])
        
        # Quantity extraction scoring
        if 25 in quantity_result['quantities_found']:
            score += 2  # Found expected box of 25
        score += len(quantity_result['methods'])
        
        # Structured data bonus
        if structured_result['json_ld'] > 0:
            score += 2
        if structured_result['open_graph']:
            score += 1
        if structured_result['woocommerce']:
            score += 1  # WooCommerce is usually extraction-friendly
        
        print(f"\nEXTRACTION CAPABILITY SCORE: {score}")
        
        if score >= 12:
            return "Excellent candidate - proceed with full extractor development (WooCommerce platform advantage)"
        elif score >= 8:
            return "Good candidate - proceed with extractor development"
        elif score >= 5:
            return "Moderate candidate - worth testing further"
        else:
            return "Poor candidate - limited extraction capabilities"


def main():
    """Main test function"""
    print("TESTING HILAND'S CIGARS")
    print("=" * 60)
    
    extractor = HilandsCigarsExtractor()
    test_url = "https://www.hilandscigars.com/shop/cigars/arturo-fuente/a-fuente-hemingway/arturo-fuente-hemingway-series-best-seller-natural/"
    
    result = extractor.test_access(test_url)
    
    print("\n" + "=" * 60)
    print("FINAL ASSESSMENT")
    print("=" * 60)
    
    if result['success']:
        print("SUCCESS: Hiland's Cigars is accessible")
        print("Anti-bot protection: None detected")
        
        # Detailed results
        price_result = result['price_extraction']
        if price_result['expected_found']:
            print("Expected pricing found: $186.40 sale price")
        if 'original' in price_result['prices']:
            print(f"Original price found: ${price_result['prices']['original']}")
        print(f"Price extraction methods: {len(price_result['methods'])}")
        
        stock_result = result['stock_detection']
        print(f"Stock detection methods: {len(stock_result['methods'])}")
        if stock_result['stock_status']:
            print("Stock status: In stock detected")
        
        quantity_result = result['quantity_extraction']
        if quantity_result['quantities_found']:
            print(f"Quantities found: {quantity_result['quantities_found']}")
        
        product_result = result['product_details']
        if product_result['details']:
            print(f"Product details extracted: {list(product_result['details'].keys())}")
        
        structured_result = result['structured_data']
        if structured_result['woocommerce']:
            print("Platform: WooCommerce detected (extraction-friendly)")
        
        print(f"\nRECOMMENDATION: {result['recommendation']}")
        
    else:
        print(f"FAILED: {result['error']}")
        if result.get('anti_bot'):
            print(f"Anti-bot protection: {result['anti_bot']}")
        print("RECOMMENDATION: Skip Hiland's Cigars - not suitable for automation")


if __name__ == "__main__":
    main()
