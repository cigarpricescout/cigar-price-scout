#!/usr/bin/env python3
"""
Thompson Cigars Test Extractor
Quick test to check for anti-bot protection and identify extraction patterns
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time

def test_thompson_access(url):
    """Test Thompson Cigars for anti-bot measures and data extraction"""
    
    # Add delay before request
    print("Waiting 3 seconds before request...")
    time.sleep(3)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Referer': 'https://www.google.com/',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        print("Testing Thompson Cigars access...")
        print(f"URL: {url}")
        print("-" * 50)
        
        response = requests.get(url, headers=headers, timeout=15)
        print(f"Status Code: {response.status_code}")
        print(f"Response Length: {len(response.content)} bytes")
        
        if response.status_code != 200:
            return {
                'success': False,
                'error': f'HTTP {response.status_code}',
                'anti_bot': 'Unknown'
            }
        
        # Check for common anti-bot indicators
        content_text = response.text.lower()
        anti_bot_indicators = [
            'cloudflare',
            'access denied', 
            'blocked',
            'captcha',
            'security check',
            'ray id',
            'ddos protection'
        ]
        
        detected_protection = []
        for indicator in anti_bot_indicators:
            if indicator in content_text:
                detected_protection.append(indicator)
        
        if detected_protection:
            print(f"WARNING: ANTI-BOT PROTECTION DETECTED: {', '.join(detected_protection)}")
            return {
                'success': False,
                'error': 'Anti-bot protection detected',
                'anti_bot': detected_protection
            }
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check for actual product content
        title = soup.find('title')
        if title:
            print(f"Page Title: {title.get_text(strip=True)}")
        
        print("\nPRICE EXTRACTION TESTS:")
        test_price_extraction(soup)
        
        print("\nSTOCK DETECTION TESTS:")
        test_stock_detection(soup)
        
        print("\nBOX QUANTITY TESTS:")
        test_quantity_extraction(soup)
        
        print("\nSTRUCTURED DATA TESTS:")
        test_structured_data(soup)
        
        return {
            'success': True,
            'anti_bot': None,
            'has_content': True
        }
        
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'error': 'Request timeout - possible anti-bot protection',
            'anti_bot': 'Timeout protection'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'anti_bot': 'Unknown error'
        }

def test_price_extraction(soup):
    """Test various price extraction methods"""
    
    # Method 1: Look for sale/current price
    current_price = None
    
    # Common price selectors
    price_selectors = [
        '.price',
        '.current-price',
        '.sale-price', 
        '[data-price]',
        '.product-price'
    ]
    
    for selector in price_selectors:
        elements = soup.select(selector)
        for elem in elements:
            text = elem.get_text(strip=True)
            price_match = re.search(r'\$?(\d+\.?\d*)', text.replace(',', ''))
            if price_match:
                price = float(price_match.group(1))
                if 50 <= price <= 500:  # Reasonable range for this product
                    print(f"  Found price via {selector}: ${price}")
                    current_price = price
                    break
        if current_price:
            break
    
    # Method 2: Search for $169.43 specifically
    page_text = soup.get_text()
    if '169.43' in page_text:
        print(f"  Found expected price $169.43 in page text")
    
    # Method 3: Look for MSRP vs current
    msrp_elements = soup.find_all(string=re.compile(r'\$194\.75|\$169\.43'))
    if msrp_elements:
        print(f"  Found price elements: {[elem.strip() for elem in msrp_elements if elem.strip()]}")

def test_stock_detection(soup):
    """Test stock status detection methods"""
    
    # Look for "ADD TO CART" button
    add_to_cart = soup.find('button', string=re.compile(r'add to cart', re.I))
    if add_to_cart:
        print("  Found 'ADD TO CART' button - indicates in stock")
    
    # Look for "In Stock" text
    stock_indicators = soup.find_all(string=re.compile(r'in stock|out of stock', re.I))
    if stock_indicators:
        print(f"  Found stock indicators: {[s.strip() for s in stock_indicators if s.strip()]}")
    
    # Check button elements
    buttons = soup.find_all(['button', 'input'])
    for button in buttons:
        text = button.get_text(strip=True).lower()
        if 'add to cart' in text or 'buy' in text:
            print(f"  Found purchase button: '{text}'")

def test_quantity_extraction(soup):
    """Test box quantity extraction"""
    
    # Look for "Box of 25" text
    page_text = soup.get_text()
    box_matches = re.findall(r'box of (\d+)', page_text.lower())
    if box_matches:
        print(f"  Found box quantities: {box_matches}")
    
    # Look in title
    title = soup.find('title')
    if title and 'box' in title.get_text().lower():
        print(f"  Box info in title: {title.get_text()}")

def test_structured_data(soup):
    """Test for JSON-LD and other structured data"""
    
    # JSON-LD scripts
    json_scripts = soup.find_all('script', type='application/ld+json')
    if json_scripts:
        print(f"  Found {len(json_scripts)} JSON-LD script(s)")
        for i, script in enumerate(json_scripts):
            try:
                data = json.loads(script.string.strip())
                if 'offers' in data or 'price' in str(data).lower():
                    print(f"    Script {i+1}: Contains pricing data")
                    if 'offers' in data:
                        offers = data['offers']
                        if isinstance(offers, list):
                            offers = offers[0]
                        if 'price' in offers:
                            print(f"    Price in JSON-LD: ${offers['price']}")
            except Exception:
                print(f"    Script {i+1}: Could not parse JSON")
    
    # Open Graph tags
    og_price = soup.find('meta', property='og:price:amount')
    if og_price:
        print(f"  Found Open Graph price: ${og_price.get('content')}")
    
    # Schema.org microdata
    price_elements = soup.find_all(attrs={'itemprop': re.compile(r'price', re.I)})
    if price_elements:
        print(f"  Found {len(price_elements)} microdata price element(s)")

if __name__ == "__main__":
    test_url = "https://www.thompsoncigar.com/p/arturo-fuente-hemingway-short-story-perfecto-cameroon/73670/#p-143939"
    
    result = test_thompson_access(test_url)
    
    print("="*50)
    print("THOMPSON CIGARS ACCESS TEST RESULTS")
    print("="*50)
    
    if result['success']:
        print("SUCCESS: Can access Thompson Cigars")
        print("No anti-bot protection detected")
        print("Ready for extractor development")
    else:
        print(f"FAILED: {result['error']}")
        if result['anti_bot']:
            print(f"Anti-bot protection: {result['anti_bot']}")
            print("Thompson Cigars may not be suitable for automated extraction")


def test_multiple_urls():
    """Test multiple URLs with delays between requests"""
    test_urls = [
        "https://www.thompsoncigar.com/p/arturo-fuente-hemingway-short-story-perfecto-cameroon/73670/#p-143939"
    ]
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Referer': 'https://www.google.com/',
        'Upgrade-Insecure-Requests': '1'
    })
    
    for i, url in enumerate(test_urls):
        if i > 0:
            print(f"\nWaiting 5 seconds between requests...")
            time.sleep(5)
        
        print(f"\n{'='*60}")
        print(f"TESTING URL {i+1}")
        print('='*60)
        
        result = test_thompson_access_with_session(url, session)
        
        if not result['success']:
            print(f"Stopping tests after failure: {result['error']}")
            break


def test_thompson_access_with_session(url, session):
    """Test Thompson Cigars access using existing session"""
    try:
        print(f"Testing: {url}")
        
        response = session.get(url, timeout=20)
        print(f"Status Code: {response.status_code}")
        print(f"Response Length: {len(response.content)} bytes")
        
        if response.status_code == 403:
            return {
                'success': False,
                'error': 'HTTP 403 Forbidden - likely anti-bot protection',
                'anti_bot': 'IP blocking or bot detection'
            }
        
        if response.status_code != 200:
            return {
                'success': False,
                'error': f'HTTP {response.status_code}',
                'anti_bot': 'HTTP error'
            }
        
        # Check content
        content_text = response.text.lower()
        if len(content_text) < 1000:
            return {
                'success': False,
                'error': 'Response too short - possible blocking',
                'anti_bot': 'Content blocking'
            }
        
        # Check for anti-bot indicators
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
        
        # Parse and test
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.find('title')
        if title:
            print(f"Page Title: {title.get_text(strip=True)}")
        
        # Quick tests
        if 'hemingway' in content_text and '169.43' in content_text:
            print("Found expected product and price data")
        
        return {'success': True, 'anti_bot': None}
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'anti_bot': 'Network or parsing error'
        }
