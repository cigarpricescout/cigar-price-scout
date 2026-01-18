#!/usr/bin/env python3
"""
ABC Fine Wine & Spirits Test Extractor
Tests accessibility and identifies extraction patterns for ABCFWS.com
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import random

class ABCFWSExtractor:
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
        """Test ABC Fine Wine & Spirits access and data extraction"""
        
        try:
            print("ABC FINE WINE & SPIRITS ACCESS TEST")
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
            structured_result = self._test_structured_data(soup)
            
            return {
                'success': True,
                'anti_bot': None,
                'price_extraction': price_result,
                'stock_detection': stock_result,
                'quantity_extraction': quantity_result,
                'structured_data': structured_result,
                'recommendation': 'Proceed with full extractor development'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'anti_bot': 'Network or parsing error'
            }
    
    def _test_price_extraction(self, soup, content_text):
        """Test price extraction methods"""
        print("PRICE EXTRACTION:")
        results = {'methods': [], 'expected_found': False}
        
        # Test for expected price from screenshot ($404.79)
        if '404.79' in content_text:
            print("  Found expected price $404.79 in page content")
            results['expected_found'] = True
        
        # Method 1: Structured data (JSON-LD)
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
                            break
        except Exception:
            pass
        
        # Method 2: Open Graph meta tags
        og_price = soup.find('meta', property='og:price:amount')
        if og_price:
            price = og_price.get('content')
            print(f"  Open Graph price: ${price}")
            results['methods'].append('Open Graph')
        
        # Method 3: Price CSS selectors
        price_selectors = [
            '.price',
            '.product-price',
            '.current-price', 
            '.sale-price',
            '[data-price]'
        ]
        
        for selector in price_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text(strip=True)
                price_match = re.search(r'\$?(\d+\.?\d*)', text.replace(',', ''))
                if price_match:
                    price = float(price_match.group(1))
                    if 300 <= price <= 600:  # Reasonable range for Padron 1964
                        print(f"  CSS selector price ({selector}): ${price}")
                        results['methods'].append(f'CSS {selector}')
                        break
        
        # Method 4: Text pattern search
        price_patterns = [
            r'\$(\d+\.?\d*)',
            r'price[:\s]*\$?(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*dollar'
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            for match in matches:
                price = float(match)
                if 300 <= price <= 600:
                    print(f"  Text pattern price: ${price}")
                    results['methods'].append('Text pattern')
                    break
            if results['methods'] and 'Text pattern' in results['methods']:
                break
        
        if not results['methods']:
            print("  No price extraction methods successful")
        
        return results
    
    def _test_stock_detection(self, soup, content_text):
        """Test stock status detection methods"""
        print("\nSTOCK DETECTION:")
        results = {'methods': [], 'in_stock_indicators': [], 'out_stock_indicators': []}
        
        # Test for expected indicators from screenshot
        if 'available for ground shipping' in content_text:
            print("  Found 'Available for ground shipping' - indicates in stock")
            results['in_stock_indicators'].append('Available for ground shipping')
        
        if 'ship it' in content_text:
            print("  Found 'Ship It' option")
            results['in_stock_indicators'].append('Ship It option')
        
        # Method 1: Button text analysis
        buttons = soup.find_all(['button', 'input', 'a'])
        for button in buttons:
            text = button.get_text(strip=True).lower()
            
            if 'add to cart' in text:
                print(f"  Stock button found: 'ADD TO CART'")
                results['methods'].append('Add to Cart button')
                results['in_stock_indicators'].append('Add to Cart button')
            
            elif 'ship it' in text:
                print(f"  Stock button found: 'Ship It'")
                results['methods'].append('Ship It button')
                results['in_stock_indicators'].append('Ship It button')
            
            elif 'notify' in text or 'out of stock' in text:
                print(f"  Out of stock indicator: '{text}'")
                results['out_stock_indicators'].append(text)
        
        # Method 2: Text indicators
        stock_phrases = [
            'in stock',
            'available',
            'ship it',
            'ground shipping',
            'add to cart'
        ]
        
        for phrase in stock_phrases:
            if phrase in content_text:
                print(f"  Stock phrase found: '{phrase}'")
                results['in_stock_indicators'].append(phrase)
        
        out_stock_phrases = [
            'out of stock',
            'sold out',
            'unavailable',
            'notify me'
        ]
        
        for phrase in out_stock_phrases:
            if phrase in content_text:
                print(f"  Out of stock phrase: '{phrase}'")
                results['out_stock_indicators'].append(phrase)
        
        return results
    
    def _test_quantity_extraction(self, soup, content_text):
        """Test box quantity extraction"""
        print("\nQUANTITY EXTRACTION:")
        results = {'methods': [], 'quantities_found': []}
        
        # Method 1: Title and description text
        title = soup.find('title')
        if title:
            title_text = title.get_text().lower()
            box_matches = re.findall(r'box of (\d+)', title_text)
            if box_matches:
                print(f"  Title box quantities: {box_matches}")
                results['quantities_found'].extend(box_matches)
                results['methods'].append('Title text')
        
        # Method 2: Page content patterns
        quantity_patterns = [
            r'box of (\d+)',
            r'(\d+) pack',
            r'(\d+) count',
            r'quantity[:\s]*(\d+)'
        ]
        
        for pattern in quantity_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            for match in matches:
                qty = int(match)
                if 5 <= qty <= 100:  # Reasonable cigar box range
                    print(f"  Quantity pattern ({pattern}): {qty}")
                    results['quantities_found'].append(str(qty))
                    results['methods'].append(f'Pattern: {pattern}')
        
        # Method 3: Product details sections
        details_sections = soup.find_all(['div', 'section'], class_=re.compile(r'detail', re.I))
        for section in details_sections:
            section_text = section.get_text().lower()
            box_matches = re.findall(r'(\d+)\s*cigars?', section_text)
            for match in box_matches:
                qty = int(match)
                if 5 <= qty <= 100:
                    print(f"  Details section quantity: {qty}")
                    results['quantities_found'].append(str(qty))
                    results['methods'].append('Details section')
        
        # Remove duplicates
        results['quantities_found'] = list(set(results['quantities_found']))
        
        if not results['quantities_found']:
            print("  No quantity extraction successful")
        
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
            
            # Check for pricing-specific OG tags
            og_price = soup.find('meta', property='og:price:amount')
            if og_price:
                print(f"    OG price tag: ${og_price.get('content')}")
        
        # Schema.org microdata
        microdata_elements = soup.find_all(attrs={'itemprop': True})
        results['microdata'] = len(microdata_elements)
        if microdata_elements:
            print(f"  Found {len(microdata_elements)} microdata element(s)")
            
            # Check for price-specific microdata
            price_elements = soup.find_all(attrs={'itemprop': re.compile(r'price', re.I)})
            if price_elements:
                print(f"    Price microdata elements: {len(price_elements)}")
        
        return results


def main():
    """Main test function"""
    print("TESTING ABC FINE WINE & SPIRITS")
    print("=" * 60)
    
    extractor = ABCFWSExtractor()
    test_url = "https://abcfws.com/cigars/padron-1964-anniversary-series-maduro-diplomatico-churchill/684271"
    
    result = extractor.test_access(test_url)
    
    print("\n" + "=" * 60)
    print("FINAL ASSESSMENT")
    print("=" * 60)
    
    if result['success']:
        print("SUCCESS: ABC Fine Wine & Spirits is accessible")
        print("Anti-bot protection: None detected")
        
        # Evaluate extraction capabilities
        methods_count = 0
        if result['price_extraction']['methods']:
            methods_count += len(result['price_extraction']['methods'])
            print(f"Price extraction methods: {len(result['price_extraction']['methods'])}")
        
        if result['stock_detection']['in_stock_indicators']:
            print(f"Stock detection indicators: {len(result['stock_detection']['in_stock_indicators'])}")
            methods_count += 1
        
        if result['quantity_extraction']['quantities_found']:
            print(f"Quantity extraction: {result['quantity_extraction']['quantities_found']}")
            methods_count += 1
        
        structured_data = result['structured_data']
        if structured_data['json_ld'] or structured_data['open_graph']:
            print("Structured data: Available")
            methods_count += 1
        
        print(f"\nTotal extraction methods available: {methods_count}")
        
        if methods_count >= 3:
            print("RECOMMENDATION: Excellent candidate - proceed with full extractor")
        elif methods_count >= 2:
            print("RECOMMENDATION: Good candidate - proceed with extractor development")
        else:
            print("RECOMMENDATION: Limited extraction capabilities - consider alternative approaches")
        
    else:
        print(f"FAILED: {result['error']}")
        if result.get('anti_bot'):
            print(f"Anti-bot protection: {result['anti_bot']}")
        print("RECOMMENDATION: Skip ABC Fine Wine & Spirits - not suitable for automation")


if __name__ == "__main__":
    main()
