#!/usr/bin/env python3
"""
Hybrid Price Monitor for Cigar Websites
- Tries simple extraction first (fast)
- Flags JavaScript-heavy sites for manual review
- Integrates with existing manual audit workflow
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import csv
from pathlib import Path

# Known problematic sites that require special handling
JAVASCRIPT_HEAVY_SITES = [
    'cigarplace.biz',
    'famous-smoke.com',
    'thompson.com',
    # Add more as you discover them
]

MANUAL_PRICE_OVERRIDES = {
    # When automation fails, use manually verified prices
    'https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html': {
        'price': 667.95,
        'in_stock': False,
        'last_verified': '2025-11-09',
        'verification_method': 'manual_screenshot',
        'notes': 'JavaScript-heavy site, requires manual verification'
    }
    # Add more URLs as needed
}

def is_javascript_heavy(url):
    """Check if URL is from a known JavaScript-heavy site"""
    for domain in JAVASCRIPT_HEAVY_SITES:
        if domain in url:
            return True
    return False

def extract_with_simple_method(url):
    """Try simple BeautifulSoup extraction first"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        result = {
            'method': 'simple_extraction',
            'success': False,
            'price': None,
            'in_stock': None,
            'confidence': 'low',
            'issues': []
        }
        
        # Check for JavaScript dependency
        page_text = soup.get_text()
        if 'javascript' in page_text.lower() and 'disabled' in page_text.lower():
            result['issues'].append('JavaScript dependency detected')
        
        # Look for prices
        price_matches = re.findall(r'\$([0-9,]+\.?[0-9]*)', page_text)
        if price_matches:
            prices = []
            for match in price_matches:
                try:
                    price_val = float(match.replace(',', ''))
                    if 50 < price_val < 5000:  # Reasonable range
                        prices.append(price_val)
                except ValueError:
                    continue
            
            if len(prices) == 1:
                result['price'] = prices[0]
                result['confidence'] = 'medium'
            elif len(prices) > 1:
                # Multiple prices found - ambiguous
                result['issues'].append(f'Multiple prices found: {prices}')
                result['price'] = max(prices)  # Guess highest is box price
                result['confidence'] = 'low'
        else:
            result['issues'].append('No prices found')
        
        # Basic stock detection
        if any(phrase in page_text.lower() for phrase in ['notify me', 'out of stock']):
            result['in_stock'] = False
        elif any(phrase in page_text.lower() for phrase in ['add to cart', 'buy now']):
            result['in_stock'] = True
        else:
            result['issues'].append('Stock status unclear')
        
        result['success'] = (result['price'] is not None and len(result['issues']) <= 1)
        
        return result
        
    except Exception as e:
        return {
            'method': 'simple_extraction',
            'success': False,
            'error': str(e),
            'issues': ['Network or parsing error']
        }

def get_manual_override(url):
    """Get manually verified data if available"""
    if url in MANUAL_PRICE_OVERRIDES:
        data = MANUAL_PRICE_OVERRIDES[url].copy()
        data['method'] = 'manual_override'
        data['success'] = True
        return data
    return None

def extract_price_and_stock(url):
    """
    Hybrid extraction approach:
    1. Check for manual override first
    2. Try simple extraction
    3. Flag for manual review if needed
    """
    
    result = {
        'url': url,
        'extracted_at': datetime.now().isoformat(),
        'success': False,
        'price': None,
        'in_stock': None,
        'method': None,
        'confidence': 'low',
        'manual_review_needed': False,
        'issues': []
    }
    
    # Step 1: Check for manual override
    manual_data = get_manual_override(url)
    if manual_data:
        result.update(manual_data)
        return result
    
    # Step 2: Check if this is a known problematic site
    if is_javascript_heavy(url):
        result['manual_review_needed'] = True
        result['issues'].append('Known JavaScript-heavy site')
        result['method'] = 'flagged_for_manual'
        return result
    
    # Step 3: Try simple extraction
    simple_result = extract_with_simple_method(url)
    result.update(simple_result)
    
    # Step 4: Validate results and decide if manual review needed
    if result['success']:
        # Additional validation
        if result['confidence'] == 'low':
            result['manual_review_needed'] = True
            result['issues'].append('Low confidence in extraction')
        
        # Price validation
        if result['price']:
            if result['price'] < 100:
                result['issues'].append('Price seems too low')
                result['manual_review_needed'] = True
            elif result['price'] > 2000:
                result['issues'].append('Price seems too high') 
                result['manual_review_needed'] = True
        
        # Stock validation
        if result['in_stock'] is None:
            result['issues'].append('Could not determine stock status')
            result['manual_review_needed'] = True
    else:
        result['manual_review_needed'] = True
        result['issues'].append('Extraction failed')
    
    return result

def process_csv_urls(csv_path):
    """Process all URLs in a CSV file and flag those needing manual review"""
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"CSV file not found: {csv_path}")
        return
    
    results = []
    manual_review_needed = []
    
    # Read URLs from CSV
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Processing {len(rows)} URLs from {csv_path}")
    print("=" * 50)
    
    for i, row in enumerate(rows, 1):
        url = row.get('url', '')
        if not url:
            continue
            
        print(f"[{i}/{len(rows)}] Processing: {url[:60]}...")
        
        result = extract_price_and_stock(url)
        result['csv_row'] = row  # Include original CSV data
        results.append(result)
        
        if result['manual_review_needed']:
            manual_review_needed.append(result)
            print(f"   [MANUAL REVIEW] {result['method']} - {', '.join(result['issues'])}")
        elif result['success']:
            print(f"   [OK] ${result['price']} - {'In Stock' if result['in_stock'] else 'Out of Stock'}")
        else:
            print(f"   [FAILED] {result.get('error', 'Unknown error')}")
    
    # Summary
    print("\n" + "=" * 50)
    print("PROCESSING SUMMARY")
    print("=" * 50)
    print(f"Total URLs processed: {len(results)}")
    print(f"Successful extractions: {sum(1 for r in results if r['success'] and not r['manual_review_needed'])}")
    print(f"Manual review needed: {len(manual_review_needed)}")
    
    # Show manual review items
    if manual_review_needed:
        print(f"\nURLs REQUIRING MANUAL REVIEW:")
        for item in manual_review_needed:
            print(f"  - {item['url']}")
            print(f"    Reason: {', '.join(item['issues'])}")
            print(f"    Method: {item['method']}")
            print()
    
    return results

# Test single URL
if __name__ == "__main__":
    print("Hybrid Cigar Price Extractor")
    print("=" * 50)
    
    # Test the problematic URL
    test_url = "https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html"
    
    print("Testing hybrid approach on Cigar Place OpusX...")
    result = extract_price_and_stock(test_url)
    
    print("\nResult:")
    print(json.dumps(result, indent=2))
    
    if result['manual_review_needed']:
        print(f"\n[MANUAL REVIEW NEEDED]")
        print(f"Reason: {', '.join(result['issues'])}")
        print(f"Method: {result['method']}")
        print("\nThis URL will be flagged for your manual audit process.")
    elif result['success']:
        print(f"\n[AUTOMATED SUCCESS]")
        print(f"Price: ${result['price']}")
        print(f"Stock: {'In Stock' if result['in_stock'] else 'Out of Stock'}")
        print(f"Confidence: {result['confidence']}")
    
    print(f"\n" + "="*50)
    print("INTEGRATION WITH YOUR WORKFLOW")
    print("="*50)
    print("✅ This approach works with your existing manual audits:")
    print("1. Run script on all URLs")
    print("2. Get automated data for simple sites")
    print("3. Manual review list for complex sites") 
    print("4. Update MANUAL_PRICE_OVERRIDES with your verified data")
    print("5. Re-run script - now it uses your manual data")
    
    # Example of processing a whole CSV
    print(f"\nTo process a whole CSV file:")
    print(f"results = process_csv_urls('static/data/cigarplace.csv')")
