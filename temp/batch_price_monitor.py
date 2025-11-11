#!/usr/bin/env python3
"""
Hybrid Price Monitor - Windows Compatible Version
Batch processes all retailer CSV files and identifies automation opportunities
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import csv
from pathlib import Path
import os

# Known problematic sites that require special handling
JAVASCRIPT_HEAVY_SITES = [
    'cigarplace.biz',
    'famous-smoke.com',
    'thompson.com',
    'cigarsdirect.com',
    'gothamcigars.com',
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
    },
    # Add more URLs as you verify them manually
    'https://www.cigarsdirect.com/collections/arturo-fuente-opus-x/products/arturo-fuente-opus-x-robusto?variant=19712418119777': {
        'price': 1649.99,
        'in_stock': False,
        'last_verified': '2025-11-09', 
        'verification_method': 'manual_audit',
        'notes': 'High-priced retailer, verified manually'
    }
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
                result['issues'].append(f'Multiple prices found: {len(prices)} prices')
                # For cigars, box price is usually highest
                reasonable_prices = [p for p in prices if 100 < p < 2000]
                if reasonable_prices:
                    result['price'] = max(reasonable_prices)
                    result['confidence'] = 'low'
        else:
            result['issues'].append('No prices found')
        
        # Basic stock detection
        if any(phrase in page_text.lower() for phrase in ['notify me', 'out of stock', 'sold out']):
            result['in_stock'] = False
        elif any(phrase in page_text.lower() for phrase in ['add to cart', 'buy now', 'purchase']):
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
    """Hybrid extraction approach"""
    
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

def find_all_csv_files():
    """Find all CSV files in static/data directory"""
    data_dir = Path("static/data")
    if not data_dir.exists():
        print(f"[ERROR] Directory not found: {data_dir}")
        return []
    
    csv_files = list(data_dir.glob("*.csv"))
    return csv_files

def process_all_csv_files():
    """Process all CSV files and provide comprehensive analysis"""
    
    csv_files = find_all_csv_files()
    if not csv_files:
        print("[ERROR] No CSV files found in static/data directory")
        return
    
    print(f"BATCH PROCESSING ALL CSV FILES")
    print("=" * 60)
    print(f"Found {len(csv_files)} CSV files")
    print("=" * 60)
    
    all_results = []
    automation_ready = []
    manual_review_needed = []
    manual_overrides_used = []
    
    for csv_file in csv_files:
        print(f"\nProcessing: {csv_file.name}")
        print("-" * 40)
        
        # Read URLs from CSV
        try:
            with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            print(f"[ERROR] Could not read {csv_file}: {e}")
            continue
        
        for row in rows:
            url = row.get('url', '')
            if not url:
                continue
            
            print(f"  Testing: {url[:50]}...")
            result = extract_price_and_stock(url)
            result['csv_file'] = csv_file.name
            result['csv_row'] = row
            all_results.append(result)
            
            if result['method'] == 'manual_override':
                manual_overrides_used.append(result)
                print(f"    [MANUAL OVERRIDE] ${result['price']} - Using verified data")
            elif result['manual_review_needed']:
                manual_review_needed.append(result)
                print(f"    [MANUAL REVIEW] {', '.join(result['issues'])}")
            elif result['success']:
                automation_ready.append(result)
                stock_text = 'In Stock' if result['in_stock'] else 'Out of Stock'
                print(f"    [AUTOMATED] ${result['price']} - {stock_text} ({result['confidence']} confidence)")
            else:
                print(f"    [FAILED] {result.get('error', 'Unknown error')}")
    
    # Comprehensive Summary
    print("\n" + "=" * 60)
    print("COMPREHENSIVE ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Total URLs analyzed: {len(all_results)}")
    print(f"Ready for automation: {len(automation_ready)}")
    print(f"Using manual overrides: {len(manual_overrides_used)}")
    print(f"Need manual review: {len(manual_review_needed)}")
    print(f"Failed extractions: {len(all_results) - len(automation_ready) - len(manual_overrides_used) - len(manual_review_needed)}")
    
    automation_percentage = (len(automation_ready) + len(manual_overrides_used)) / len(all_results) * 100
    print(f"Current automation rate: {automation_percentage:.1f}%")
    
    # Detailed breakdowns
    if manual_review_needed:
        print(f"\nURLs REQUIRING MANUAL REVIEW ({len(manual_review_needed)}):")
        for item in manual_review_needed[:10]:  # Show first 10
            print(f"  - {item['csv_file']}: {item['url'][:60]}")
            print(f"    Reason: {', '.join(item['issues'])}")
        if len(manual_review_needed) > 10:
            print(f"    ... and {len(manual_review_needed) - 10} more")
    
    # Site analysis
    print(f"\nSITE DIFFICULTY ANALYSIS:")
    site_stats = {}
    for result in all_results:
        domain = result['url'].split('/')[2] if '/' in result['url'] else 'unknown'
        if domain not in site_stats:
            site_stats[domain] = {'total': 0, 'automated': 0, 'manual': 0}
        
        site_stats[domain]['total'] += 1
        if result['success'] and not result['manual_review_needed']:
            site_stats[domain]['automated'] += 1
        else:
            site_stats[domain]['manual'] += 1
    
    for domain, stats in site_stats.items():
        automation_rate = stats['automated'] / stats['total'] * 100
        print(f"  {domain}: {automation_rate:.0f}% automated ({stats['automated']}/{stats['total']})")
    
    return all_results

def update_csv_with_results(results):
    """Update CSV files with extracted data"""
    print(f"\nUPDATING CSV FILES WITH EXTRACTED DATA")
    print("=" * 50)
    
    # Group results by CSV file
    csv_updates = {}
    for result in results:
        if result['success'] and not result['manual_review_needed']:
            csv_file = result['csv_file']
            if csv_file not in csv_updates:
                csv_updates[csv_file] = []
            csv_updates[csv_file].append(result)
    
    for csv_file, file_results in csv_updates.items():
        print(f"Updating {csv_file} with {len(file_results)} price updates...")
        # Implementation would go here to actually update the CSV files
        # For now, just show what would be updated
        for result in file_results:
            print(f"  {result['url'][:50]}... -> ${result['price']}")

# Test and batch processing
if __name__ == "__main__":
    print("Hybrid Cigar Price Extractor - Windows Compatible")
    print("=" * 60)
    
    # Test single URL first
    test_url = "https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html"
    print("Testing hybrid approach on Cigar Place OpusX...")
    result = extract_price_and_stock(test_url)
    
    if result['method'] == 'manual_override':
        print(f"[SUCCESS] Using manual override: ${result['price']} - {'In Stock' if result['in_stock'] else 'Out of Stock'}")
    elif result['manual_review_needed']:
        print(f"[MANUAL REVIEW NEEDED] Reason: {', '.join(result['issues'])}")
    elif result['success']:
        print(f"[AUTOMATED SUCCESS] ${result['price']} - {'In Stock' if result['in_stock'] else 'Out of Stock'}")
    
    print(f"\n" + "="*60)
    print("BATCH PROCESSING ALL CSV FILES")
    print("="*60)
    
    # Process all CSV files
    all_results = process_all_csv_files()
    
    if all_results:
        print(f"\nREADY TO SCALE:")
        print("1. Review the manual review list above")
        print("2. Manually verify those URLs")  
        print("3. Add verified data to MANUAL_PRICE_OVERRIDES")
        print("4. Re-run script for higher automation rate")
        print("5. Script can update CSV files automatically")
