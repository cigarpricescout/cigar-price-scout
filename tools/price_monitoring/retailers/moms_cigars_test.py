#!/usr/bin/env python3
"""
Mom's Cigars Test Extractor
Tests accessibility and identifies extraction patterns for momscigars.com
Focuses on multi-product table extraction similar to Holt's approach
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import random

class MomsCigarsExtractor:
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
        """Test Mom's Cigars access and data extraction capabilities"""
        
        try:
            print("MOM'S CIGARS ACCESS TEST")
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
            
            # Test data extraction for table-based layout
            print("\nPRODUCT TABLE ANALYSIS:")
            print("-" * 30)
            
            table_result = self._analyze_product_table(soup, content_text)
            structured_result = self._test_structured_data(soup)
            
            return {
                'success': True,
                'anti_bot': None,
                'table_analysis': table_result,
                'structured_data': structured_result,
                'recommendation': self._generate_recommendation(table_result, structured_result)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'anti_bot': 'Network or parsing error'
            }
    
    def _analyze_product_table(self, soup, content_text):
        """Analyze the product table structure and extraction capabilities"""
        results = {
            'table_found': False,
            'products_found': [],
            'extraction_methods': {},
            'expected_product_found': False
        }
        
        # Look for table structures
        tables = soup.find_all('table')
        print(f"Found {len(tables)} HTML table(s)")
        
        # Also check for div-based table structures
        table_divs = soup.find_all('div', class_=re.compile(r'table|product-grid|product-list', re.I))
        print(f"Found {len(table_divs)} div-based table structure(s)")
        
        all_table_elements = tables + table_divs
        results['table_found'] = len(all_table_elements) > 0
        
        if not all_table_elements:
            print("No table structures found")
            return results
        
        # Analyze each table/grid for product data
        for i, table_elem in enumerate(all_table_elements):
            print(f"\nAnalyzing table/grid {i+1}:")
            
            # Look for rows
            rows = table_elem.find_all(['tr', 'div'])
            print(f"  Found {len(rows)} potential product rows")
            
            products_in_table = 0
            
            for row in rows:
                row_text = row.get_text().lower()
                
                # Check if this row contains the expected Short Story product
                if 'short story' in row_text and '163.99' in row_text:
                    print("  FOUND EXPECTED PRODUCT: Short Story $163.99")
                    results['expected_product_found'] = True
                    products_in_table += 1
                    
                    # Analyze this specific row for extraction patterns
                    row_analysis = self._analyze_product_row(row, 'Short Story')
                    results['products_found'].append({
                        'product': 'Short Story',
                        'analysis': row_analysis
                    })
                
                # Look for other Hemingway products
                elif any(hemingway in row_text for hemingway in ['classic', 'masterpiece', 'signature', 'work of art']):
                    # Extract product name
                    product_match = None
                    for hemingway in ['classic', 'masterpiece', 'signature', 'work of art']:
                        if hemingway in row_text:
                            product_match = hemingway.title()
                            break
                    
                    if product_match:
                        print(f"  Found Hemingway product: {product_match}")
                        products_in_table += 1
                        
                        row_analysis = self._analyze_product_row(row, product_match)
                        results['products_found'].append({
                            'product': product_match,
                            'analysis': row_analysis
                        })
            
            print(f"  Products found in table {i+1}: {products_in_table}")
        
        # Determine extraction methods
        if results['products_found']:
            methods = set()
            for product in results['products_found']:
                methods.update(product['analysis']['successful_methods'])
            results['extraction_methods']['successful'] = list(methods)
        
        return results
    
    def _analyze_product_row(self, row, product_name):
        """Analyze a specific product row for extraction patterns"""
        analysis = {
            'product_name': product_name,
            'successful_methods': [],
            'price_data': {},
            'stock_data': {},
            'quantity_data': {}
        }
        
        row_text = row.get_text()
        
        # Price extraction
        print(f"    Testing price extraction for {product_name}:")
        
        # Method 1: Look for MSRP vs Sale price pattern
        msrp_match = re.search(r'\$(\d+\.?\d*)', row_text)
        prices_found = re.findall(r'\$(\d+\.?\d*)', row_text)
        
        if len(prices_found) >= 2:
            # Multiple prices - likely MSRP and sale
            prices = [float(p) for p in prices_found]
            prices.sort(reverse=True)  # Highest first (MSRP)
            analysis['price_data']['msrp'] = prices[0]
            analysis['price_data']['sale'] = prices[1]
            analysis['successful_methods'].append('MSRP/Sale price pattern')
            print(f"      MSRP/Sale prices: ${prices[0]} / ${prices[1]}")
        elif len(prices_found) == 1:
            # Single price
            price = float(prices_found[0])
            analysis['price_data']['price'] = price
            analysis['successful_methods'].append('Single price')
            print(f"      Single price: ${price}")
        
        # Method 2: Look for strikethrough pricing
        strikethrough_elements = row.find_all(['s', 'del', 'strike'])
        if strikethrough_elements:
            for elem in strikethrough_elements:
                strikethrough_text = elem.get_text()
                price_match = re.search(r'\$(\d+\.?\d*)', strikethrough_text)
                if price_match:
                    analysis['price_data']['original'] = float(price_match.group(1))
                    analysis['successful_methods'].append('Strikethrough MSRP')
                    print(f"      Strikethrough MSRP: ${price_match.group(1)}")
        
        # Stock detection
        print(f"    Testing stock detection for {product_name}:")
        
        # Method 1: Look for checkmark indicators
        checkmarks = row.find_all(['span', 'div', 'i'], class_=re.compile(r'check|tick|success|stock', re.I))
        if checkmarks:
            analysis['stock_data']['in_stock'] = True
            analysis['successful_methods'].append('Checkmark indicator')
            print(f"      Stock checkmark found")
        
        # Method 2: Look for "ADD" button
        add_buttons = row.find_all(['button', 'input', 'a'], string=re.compile(r'add', re.I))
        if add_buttons:
            analysis['stock_data']['add_button'] = True
            analysis['successful_methods'].append('ADD button')
            print(f"      ADD button found")
        
        # Method 3: Text indicators
        if 'in stock' in row_text.lower():
            analysis['stock_data']['text_indicator'] = True
            analysis['successful_methods'].append('Stock text')
            print(f"      'In stock' text found")
        
        # Quantity extraction
        print(f"    Testing quantity extraction for {product_name}:")
        
        # Look for box quantities
        box_matches = re.findall(r'box of (\d+)', row_text.lower())
        if box_matches:
            analysis['quantity_data']['box_quantities'] = [int(q) for q in box_matches]
            analysis['successful_methods'].append('Box quantity pattern')
            print(f"      Box quantities: {box_matches}")
        
        # Look for pack quantities
        pack_matches = re.findall(r'(\d+) pack', row_text.lower())
        if pack_matches:
            analysis['quantity_data']['pack_quantities'] = [int(q) for q in pack_matches]
            analysis['successful_methods'].append('Pack quantity pattern')
            print(f"      Pack quantities: {pack_matches}")
        
        return analysis
    
    def _test_structured_data(self, soup):
        """Test for structured data availability"""
        print("\nSTRUCTURED DATA ANALYSIS:")
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
    
    def _generate_recommendation(self, table_result, structured_result):
        """Generate recommendation based on analysis results"""
        score = 0
        
        # Table extraction capabilities
        if table_result['expected_product_found']:
            score += 3  # High value for finding expected product
        
        if table_result['products_found']:
            score += len(table_result['products_found'])  # Points per product found
        
        if table_result.get('extraction_methods', {}).get('successful'):
            score += len(table_result['extraction_methods']['successful'])
        
        # Structured data bonus
        if structured_result['json_ld'] > 0:
            score += 2
        if structured_result['open_graph']:
            score += 1
        
        print(f"\nEXTRACTION CAPABILITY SCORE: {score}")
        
        if score >= 8:
            return "Excellent candidate - proceed with full extractor development (similar to Holt's approach)"
        elif score >= 5:
            return "Good candidate - proceed with extractor development with careful testing"
        elif score >= 3:
            return "Moderate candidate - consider if worth development effort"
        else:
            return "Poor candidate - limited extraction capabilities"


def main():
    """Main test function"""
    print("TESTING MOM'S CIGARS")
    print("=" * 60)
    
    extractor = MomsCigarsExtractor()
    test_url = "https://www.momscigars.com/products/arturo-fuente-hemingway"
    
    result = extractor.test_access(test_url)
    
    print("\n" + "=" * 60)
    print("FINAL ASSESSMENT")
    print("=" * 60)
    
    if result['success']:
        print("SUCCESS: Mom's Cigars is accessible")
        print("Anti-bot protection: None detected")
        
        table_result = result['table_analysis']
        if table_result['expected_product_found']:
            print("Expected product found: Short Story $163.99")
        
        print(f"Total products found: {len(table_result['products_found'])}")
        
        if table_result.get('extraction_methods', {}).get('successful'):
            methods = table_result['extraction_methods']['successful']
            print(f"Extraction methods available: {len(methods)}")
            for method in methods:
                print(f"  - {method}")
        
        print(f"\nRECOMMENDATION: {result['recommendation']}")
        
    else:
        print(f"FAILED: {result['error']}")
        if result.get('anti_bot'):
            print(f"Anti-bot protection: {result['anti_bot']}")
        print("RECOMMENDATION: Skip Mom's Cigars - not suitable for automation")


if __name__ == "__main__":
    main()
