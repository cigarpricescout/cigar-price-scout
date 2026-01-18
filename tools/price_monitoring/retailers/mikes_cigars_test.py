#!/usr/bin/env python3
"""
Mike's Cigars Test Extractor
Tests accessibility and identifies extraction patterns for mikescigars.com
Focuses on single-product page with clear pricing structure and detailed product info
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import random

class MikesCigarsExtractor:
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
        """Test Mike's Cigars access and data extraction capabilities"""
        
        try:
            print("MIKE'S CIGARS ACCESS TEST")
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
        """Test price extraction methods for Mike's Cigars"""
        print("PRICE EXTRACTION:")
        results = {'methods': [], 'expected_found': False, 'prices': {}}
        
        # Test for expected prices from screenshot
        if '205.50' in content_text:
            print("  Found expected sale price $205.50 in page content")
            results['expected_found'] = True
            results['prices']['sale'] = 205.50
        
        if '227.50' in content_text:
            print("  Found expected MSRP $227.50 in page content")
            results['prices']['msrp'] = 227.50
        
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
        
        # Method 3: Price CSS selectors
        price_selectors = [
            '.price',
            '.product-price',
            '.current-price',
            '.sale-price',
            '.regular-price',
            '[data-price]',
            '.price-current'
        ]
        
        for selector in price_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text(strip=True).replace('$', '').replace(',', '')
                price_match = re.search(r'(\d+\.?\d*)', text)
                if price_match:
                    price = float(price_match.group(1))
                    if 150 <= price <= 300:  # Reasonable range for this product
                        print(f"  CSS selector price ({selector}): ${price}")
                        results['methods'].append(f'CSS {selector}')
                        results['prices'][f'css_{selector}'] = price
                        break
        
        # Method 4: Text-based price extraction
        price_patterns = [
            r'\$(\d+\.?\d*)',
            r'price[:\s]*\$?(\d+\.?\d*)',
            r'msrp[:\s]*\$?(\d+\.?\d*)'
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            for match in matches:
                price = float(match)
                if 150 <= price <= 300:
                    if price not in results['prices'].values():
                        print(f"  Text pattern price: ${price}")
                        results['methods'].append(f'Text pattern')
                        results['prices'][f'text_{price}'] = price
                        break
        
        if not results['methods']:
            print("  No price extraction methods successful")
        
        return results
    
    def _test_stock_detection(self, soup, content_text):
        """Test stock status detection methods"""
        print("\nSTOCK DETECTION:")
        results = {'methods': [], 'in_stock_indicators': [], 'stock_status': None}
        
        # Method 1: "ADD TO CART" button (primary indicator from screenshot)
        add_buttons = soup.find_all(['button', 'input', 'a'], string=re.compile(r'add to cart', re.I))
        if add_buttons:
            print("  Found 'ADD TO CART' button - indicates in stock")
            results['methods'].append('ADD TO CART button')
            results['in_stock_indicators'].append('ADD TO CART button')
            results['stock_status'] = True
        
        # Method 2: Button text analysis
        buttons = soup.find_all(['button', 'input', 'a'])
        for button in buttons:
            text = button.get_text(strip=True).lower()
            classes = ' '.join(button.get('class', [])).lower()
            
            if 'add to cart' in text:
                print(f"  Stock button found: 'ADD TO CART'")
                results['methods'].append('Add to cart text')
                results['in_stock_indicators'].append('Add to cart text')
                results['stock_status'] = True
            
            elif 'out of stock' in text or 'sold out' in text:
                print(f"  Out of stock button: '{text}'")
                results['stock_status'] = False
            
            elif 'notify' in text and ('available' in text or 'stock' in text):
                print(f"  Notify when available: '{text}'")
                results['stock_status'] = False
        
        # Method 3: Stock status indicators in page text
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
        
        # Method 4: Out of stock indicators
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
        
        # Method 5: Quantity input presence (usually indicates in stock)
        quantity_inputs = soup.find_all('input', {'type': ['number', 'text']})
        for inp in quantity_inputs:
            if 'qty' in str(inp.get('name', '')).lower() or 'quantity' in str(inp.get('id', '')).lower():
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
        
        # Method 1: Look for "BOX OF 25" text (from screenshot)
        if 'box of 25' in content_text.lower():
            print("  Found 'BOX OF 25' in page content")
            results['quantities_found'].append(25)
            results['methods'].append('BOX OF text')
        
        # Method 2: QUANTITY field extraction
        quantity_labels = soup.find_all(string=re.compile(r'quantity', re.I))
        for label in quantity_labels:
            parent = label.parent if label.parent else None
            if parent:
                parent_text = parent.get_text()
                box_match = re.search(r'box of (\d+)', parent_text.lower())
                if box_match:
                    qty = int(box_match.group(1))
                    print(f"  Quantity field box size: {qty}")
                    if qty not in results['quantities_found']:
                        results['quantities_found'].append(qty)
                        results['methods'].append('Quantity field')
        
        # Method 3: Product title and headers
        headers = soup.find_all(['h1', 'h2', 'h3'])
        for header in headers:
            header_text = header.get_text().lower()
            box_matches = re.findall(r'box of (\d+)', header_text)
            if box_matches:
                print(f"  Header box quantities: {box_matches}")
                for qty in box_matches:
                    qty_int = int(qty)
                    if qty_int not in results['quantities_found']:
                        results['quantities_found'].append(qty_int)
                        results['methods'].append('Product header')
        
        # Method 4: General page content patterns
        quantity_patterns = [
            r'box of (\d+)',
            r'(\d+) pack',
            r'(\d+) count',
            r'(\d+) cigars?',
            r'quantity[:\s]*(\d+)'
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
        
        # Look for SKU
        if 'afhbs' in content_text.lower():
            print("  Found expected SKU: AFHBS")
            results['details']['sku'] = 'AFHBS'
            results['methods'].append('SKU text')
        
        # Look for wrapper type
        wrapper_indicators = ['wrapper', 'african cameroon', 'cameroon']
        for indicator in wrapper_indicators:
            if indicator in content_text.lower():
                print(f"  Found wrapper indicator: {indicator}")
                results['details']['wrapper'] = 'African Cameroon'
                results['methods'].append('Wrapper text')
                break
        
        # Look for size information
        size_pattern = r'(\d+(?:\s*1/2)?)\s*(?:x|×)\s*(\d+)'
        size_matches = re.findall(size_pattern, content_text)
        if size_matches:
            for match in size_matches:
                length, ring = match
                size_str = f"{length} x {ring}"
                print(f"  Found size: {size_str}")
                results['details']['size'] = size_str
                results['methods'].append('Size pattern')
                break
        
        # Look for strength
        strength_indicators = ['medium', 'mild', 'full']
        for strength in strength_indicators:
            if strength in content_text.lower():
                print(f"  Found strength: {strength}")
                results['details']['strength'] = strength.title()
                results['methods'].append('Strength text')
                break
        
        # Look for country
        if 'dominican republic' in content_text.lower():
            print("  Found country: Dominican Republic")
            results['details']['country'] = 'Dominican Republic'
            results['methods'].append('Country text')
        
        return results
    
    def _test_structured_data(self, soup):
        """Test for structured data availability"""
        print("\nSTRUCTURED DATA:")
        results = {'json_ld': 0, 'open_graph': False, 'microdata': 0}
        
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
        if len(price_result['prices']) >= 2:
            score += 2  # Bonus for finding both sale and MSRP
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
        
        print(f"\nEXTRACTION CAPABILITY SCORE: {score}")
        
        if score >= 12:
            return "Excellent candidate - proceed with full extractor development (high reliability expected)"
        elif score >= 8:
            return "Good candidate - proceed with extractor development"
        elif score >= 5:
            return "Moderate candidate - worth testing further"
        else:
            return "Poor candidate - limited extraction capabilities"


def main():
    """Main test function"""
    print("TESTING MIKE'S CIGARS")
    print("=" * 60)
    
    extractor = MikesCigarsExtractor()
    test_url = "https://mikescigars.com/arturo-fuente-hemingway-best-seller"
    
    result = extractor.test_access(test_url)
    
    print("\n" + "=" * 60)
    print("FINAL ASSESSMENT")
    print("=" * 60)
    
    if result['success']:
        print("SUCCESS: Mike's Cigars is accessible")
        print("Anti-bot protection: None detected")
        
        # Detailed results
        price_result = result['price_extraction']
        if price_result['expected_found']:
            print("Expected pricing found: $205.50 sale price")
        if 'msrp' in price_result['prices']:
            print(f"MSRP found: ${price_result['prices']['msrp']}")
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
        
        print(f"\nRECOMMENDATION: {result['recommendation']}")
        
    else:
        print(f"FAILED: {result['error']}")
        if result.get('anti_bot'):
            print(f"Anti-bot protection: {result['anti_bot']}")
        print("RECOMMENDATION: Skip Mike's Cigars - not suitable for automation")


if __name__ == "__main__":
    main()
