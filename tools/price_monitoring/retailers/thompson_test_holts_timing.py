#!/usr/bin/env python3
"""
Thompson Cigars Test Extractor with Holt's Timing Strategy
Uses sophisticated rate limiting and session management for anti-bot evasion
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import random
from urllib.parse import urlparse

class ThompsonCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Use professional user agent similar to Holt's approach
        self.session.headers.update({
            'User-Agent': 'CigarPriceScoutBot/1.0 (+https://cigarpricescout.com/contact)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': 'https://www.google.com/',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Conservative rate limiting similar to Holt's approach
        self.min_delay = 4  # Longer than Holt's 3 seconds
        self.max_delay = 8  # Extended delay for Thompson
        
        # Backoff settings for 403/429 responses
        self.backoff_delay = 15  # 15 second backoff
        self.max_backoff_attempts = 3
    
    def _enforce_rate_limit(self):
        """Enforce 4-8 second delay with jitter for conservative access"""
        delay = random.uniform(self.min_delay, self.max_delay)
        print(f"[RATE LIMIT] Waiting {delay:.1f} seconds (conservative anti-bot strategy)")
        time.sleep(delay)
    
    def _handle_403_backoff(self, attempt=1):
        """Handle 403 responses with exponential backoff"""
        if attempt <= self.max_backoff_attempts:
            backoff_time = self.backoff_delay * (2 ** (attempt - 1))  # Exponential backoff
            print(f"[BACKOFF] 403 received, attempt {attempt}/{self.max_backoff_attempts}")
            print(f"[BACKOFF] Waiting {backoff_time} seconds before retry...")
            time.sleep(backoff_time)
            return True
        return False
    
    def test_access_with_backoff(self, url: str):
        """Test Thompson access with sophisticated backoff strategy"""
        
        for attempt in range(1, self.max_backoff_attempts + 1):
            try:
                print(f"\n=== ATTEMPT {attempt}/{self.max_backoff_attempts} ===")
                
                # Rate limiting before each attempt
                if attempt > 1:
                    self._handle_403_backoff(attempt - 1)
                else:
                    self._enforce_rate_limit()
                
                print(f"Testing: {url}")
                
                response = self.session.get(url, timeout=20)
                print(f"Status Code: {response.status_code}")
                print(f"Response Length: {len(response.content)} bytes")
                
                # Handle different response codes
                if response.status_code == 200:
                    print("SUCCESS: 200 OK received")
                    return self._analyze_successful_response(response)
                
                elif response.status_code == 403:
                    print(f"WARNING: 403 Forbidden on attempt {attempt}")
                    if attempt < self.max_backoff_attempts:
                        print("Will retry with longer backoff...")
                        continue
                    else:
                        print("Max attempts reached - Thompson likely has strong anti-bot protection")
                        return {
                            'success': False,
                            'error': f'403 Forbidden after {self.max_backoff_attempts} attempts',
                            'anti_bot': 'Strong IP-based blocking detected',
                            'recommendation': 'Skip Thompson - add to abandoned retailers list'
                        }
                
                elif response.status_code == 429:
                    print(f"Rate limited (429) on attempt {attempt}")
                    continue
                
                else:
                    print(f"Unexpected status code: {response.status_code}")
                    return {
                        'success': False,
                        'error': f'HTTP {response.status_code}',
                        'anti_bot': f'HTTP {response.status_code} error'
                    }
                    
            except requests.exceptions.Timeout:
                print(f"Request timeout on attempt {attempt}")
                if attempt < self.max_backoff_attempts:
                    continue
                return {
                    'success': False,
                    'error': 'Request timeout after multiple attempts',
                    'anti_bot': 'Possible timeout-based protection'
                }
            
            except Exception as e:
                print(f"Network error on attempt {attempt}: {str(e)}")
                if attempt < self.max_backoff_attempts:
                    continue
                return {
                    'success': False,
                    'error': str(e),
                    'anti_bot': 'Network or connection error'
                }
        
        # If we get here, all attempts failed
        return {
            'success': False,
            'error': 'All attempts exhausted',
            'anti_bot': 'Persistent access denied',
            'recommendation': 'Skip Thompson - not suitable for automation'
        }
    
    def _analyze_successful_response(self, response):
        """Analyze a successful response for extractable data"""
        try:
            content_text = response.text.lower()
            
            # Check for anti-bot indicators even in 200 responses
            anti_bot_indicators = [
                'cloudflare',
                'access denied',
                'security check',
                'captcha',
                'ray id'
            ]
            
            detected_protection = []
            for indicator in anti_bot_indicators:
                if indicator in content_text:
                    detected_protection.append(indicator)
            
            if detected_protection:
                return {
                    'success': False,
                    'error': f'Anti-bot protection in content: {", ".join(detected_protection)}',
                    'anti_bot': detected_protection
                }
            
            # Parse HTML for data extraction tests
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get page title
            title = soup.find('title')
            if title:
                print(f"Page Title: {title.get_text(strip=True)}")
            
            # Quick data extraction tests
            print("\nDATA EXTRACTION TESTS:")
            self._test_price_extraction(soup, content_text)
            self._test_stock_detection(soup, content_text) 
            self._test_quantity_extraction(soup, content_text)
            self._test_structured_data(soup)
            
            return {
                'success': True,
                'anti_bot': None,
                'extractable': True,
                'recommendation': 'Proceed with full extractor development'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Response analysis failed: {str(e)}',
                'anti_bot': 'Parsing error'
            }
    
    def _test_price_extraction(self, soup, content_text):
        """Test price extraction capabilities"""
        print("  Price Extraction:")
        
        # Test for expected price from screenshot
        if '169.43' in content_text:
            print("    Found expected price $169.43 in page content")
        
        if '194.75' in content_text:
            print("    Found MSRP price $194.75 in page content")
        
        # Look for price elements
        price_found = False
        price_selectors = ['.price', '.current-price', '.sale-price', '[data-price]']
        
        for selector in price_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text(strip=True)
                if '$' in text and any(char.isdigit() for char in text):
                    print(f"    Price element found via {selector}: {text}")
                    price_found = True
                    break
            if price_found:
                break
        
        if not price_found:
            print("    No clear price elements detected")
    
    def _test_stock_detection(self, soup, content_text):
        """Test stock status detection"""
        print("  Stock Detection:")
        
        # Look for expected stock indicators from screenshot
        if 'in stock' in content_text:
            print("    Found 'In Stock' text")
        
        if 'add to cart' in content_text:
            print("    Found 'ADD TO CART' button text")
        
        # Look for buttons
        buttons = soup.find_all(['button', 'input'])
        for button in buttons:
            text = button.get_text(strip=True).lower()
            if 'add to cart' in text or 'add' in text:
                print(f"    Stock button found: '{text}'")
                break
    
    def _test_quantity_extraction(self, soup, content_text):
        """Test box quantity extraction"""
        print("  Quantity Extraction:")
        
        # Look for expected "Box of 25" from screenshot
        if 'box of 25' in content_text:
            print("    Found expected 'Box of 25'")
        
        # Look for other quantity patterns
        box_matches = re.findall(r'box of (\d+)', content_text)
        if box_matches:
            print(f"    Box quantities found: {box_matches}")
    
    def _test_structured_data(self, soup):
        """Test for structured data availability"""
        print("  Structured Data:")
        
        # JSON-LD
        json_scripts = soup.find_all('script', type='application/ld+json')
        if json_scripts:
            print(f"    Found {len(json_scripts)} JSON-LD script(s)")
            for i, script in enumerate(json_scripts):
                try:
                    data = json.loads(script.string.strip())
                    if 'offers' in data or 'price' in str(data).lower():
                        print(f"      Script {i+1}: Contains pricing data")
                except Exception:
                    print(f"      Script {i+1}: Could not parse")
        
        # Open Graph
        og_price = soup.find('meta', property='og:price:amount')
        if og_price:
            print(f"    Open Graph price: ${og_price.get('content')}")
        
        # Microdata
        price_elements = soup.find_all(attrs={'itemprop': re.compile(r'price', re.I)})
        if price_elements:
            print(f"    Found {len(price_elements)} microdata price element(s)")


def main():
    """Main test function"""
    print("THOMPSON CIGARS ACCESS TEST WITH HOLT'S STRATEGY")
    print("=" * 60)
    
    extractor = ThompsonCigarsExtractor()
    test_url = "https://www.thompsoncigar.com/p/arturo-fuente-hemingway-short-story-perfecto-cameroon/73670/#p-143939"
    
    result = extractor.test_access_with_backoff(test_url)
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    
    if result['success']:
        print("SUCCESS: Thompson Cigars accessible")
        print("Recommendation:", result.get('recommendation', 'Unknown'))
        print("Ready for full extractor development")
    else:
        print(f"FAILED: {result['error']}")
        print(f"Anti-bot protection: {result.get('anti_bot', 'Unknown')}")
        if 'recommendation' in result:
            print(f"Recommendation: {result['recommendation']}")
        else:
            print("Recommendation: Consider skipping Thompson for automated extraction")


if __name__ == "__main__":
    main()
