#!/usr/bin/env python3
"""
URL-Specific Price Monitor for Cigar Place OpusX Robusto
https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html

This script extracts:
1. Box of 29 price (ignoring single/3-pack prices)
2. Stock status based on button text ("Add to Cart" vs "Notify Me")
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime

def extract_cigarplace_opusx_data(url):
    """
    Extract box price and stock status for Cigar Place OpusX Robusto
    
    Returns:
    {
        'price': 667.95,
        'in_stock': False,
        'extracted_at': '2025-11-09T...',
        'raw_data': {...}  # For debugging
    }
    """
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        result = {
            'url': url,
            'extracted_at': datetime.now().isoformat(),
            'success': False,
            'price': None,
            'in_stock': None,
            'raw_data': {}
        }
        
        # Strategy 1: Look for product options/variants section
        # Most cigar sites have a dropdown or radio buttons for quantities
        box_price = None
        
        # Look for common patterns for box pricing
        price_patterns = [
            # Pattern 1: Look for "Box of 29" or "29 Cigars" text near price
            {'text_pattern': r'box\s*of\s*29|29\s*cigars', 'price_selector': None},
            # Pattern 2: Look for highest price (usually box price)
            {'text_pattern': None, 'price_selector': '.price, .cost, .money, [class*="price"]'},
            # Pattern 3: Look for specific quantity selectors
            {'text_pattern': None, 'price_selector': '[data-quantity="29"], [value="29"]'}
        ]
        
        # Extract all prices on page first
        price_elements = soup.find_all(text=re.compile(r'\$\d+[\d,]*\.?\d*'))
        prices_found = []
        
        for price_text in price_elements:
            # Clean and parse price
            price_match = re.search(r'\$([0-9,]+\.?[0-9]*)', str(price_text))
            if price_match:
                try:
                    price_value = float(price_match.group(1).replace(',', ''))
                    prices_found.append({
                        'price': price_value,
                        'context': str(price_text.parent.get_text(strip=True) if price_text.parent else price_text)[:100]
                    })
                except ValueError:
                    continue
        
        result['raw_data']['prices_found'] = prices_found
        
        # Strategy: Use MSRP and "You Save" calculation for accurate box pricing
        if prices_found:
            msrp_price = None
            actual_price = None
            you_save_percentage = None
            
            # Step 1: Find MSRP
            for price_info in prices_found:
                context_lower = price_info['context'].lower()
                if any(msrp_keyword in context_lower for msrp_keyword in ['msrp', 'retail', 'list price', 'suggested']):
                    msrp_price = price_info['price']
                    result['raw_data']['msrp_found'] = {'price': msrp_price, 'context': price_info['context']}
                    break
            
            # Step 2: Find "You Save" percentage
            you_save_elements = soup.find_all(text=re.compile(r'you save|save.*%|discount', re.I))
            for save_text in you_save_elements:
                # Look for percentage in the save text or nearby elements
                save_match = re.search(r'(\d+)%', str(save_text))
                if save_match:
                    you_save_percentage = int(save_match.group(1))
                    result['raw_data']['you_save'] = {'percentage': you_save_percentage, 'text': str(save_text)[:100]}
                    break
                
                # Also check parent element for percentage
                if hasattr(save_text, 'parent') and save_text.parent:
                    parent_text = save_text.parent.get_text()
                    save_match = re.search(r'(\d+)%', parent_text)
                    if save_match:
                        you_save_percentage = int(save_match.group(1))
                        result['raw_data']['you_save'] = {'percentage': you_save_percentage, 'text': parent_text[:100]}
                        break
            
            # Step 3: Calculate actual price from MSRP and discount
            if msrp_price and you_save_percentage:
                calculated_price = msrp_price * (1 - you_save_percentage / 100)
                result['raw_data']['calculated_price'] = calculated_price
                
                # Find the actual displayed price to verify calculation
                non_msrp_prices = [p for p in prices_found 
                                 if 'msrp' not in p['context'].lower() 
                                 and 'retail' not in p['context'].lower()
                                 and 'list price' not in p['context'].lower()]
                
                # Look for price closest to calculated price (within $5)
                for price_info in non_msrp_prices:
                    if abs(price_info['price'] - calculated_price) < 5:
                        actual_price = price_info['price']
                        result['raw_data']['verified_price'] = {'price': actual_price, 'context': price_info['context']}
                        break
                
                # If no matching displayed price, use calculated price
                if actual_price is None:
                    actual_price = round(calculated_price, 2)
                    result['raw_data']['using_calculated'] = True
                
            # Step 4: Handle edge cases
            elif you_save_percentage == 0:
                # No discount - trigger manual review
                result['raw_data']['manual_review_needed'] = "You Save is 0% - no discount detected"
                # Use MSRP as price if available
                if msrp_price:
                    actual_price = msrp_price
                    result['raw_data']['using_msrp_no_discount'] = True
                    
            elif msrp_price and you_save_percentage is None:
                # Found MSRP but no "You Save" - try to find actual price
                result['raw_data']['manual_review_needed'] = "Found MSRP but no 'You Save' percentage"
                non_msrp_prices = [p for p in prices_found 
                                 if 'msrp' not in p['context'].lower()]
                if non_msrp_prices:
                    # Take the highest non-MSRP price (likely box price)
                    actual_price = max([p['price'] for p in non_msrp_prices])
                    
            else:
                # Fallback to original logic
                result['raw_data']['fallback_logic'] = "No MSRP or You Save found - using fallback"
                # Look for box-related context
                box_price_candidates = []
                for price_info in prices_found:
                    context_lower = price_info['context'].lower()
                    if any(keyword in context_lower for keyword in ['box', '20', '25', '29', 'case']):
                        box_price_candidates.append(price_info['price'])
                
                if box_price_candidates:
                    actual_price = max(box_price_candidates)
                elif prices_found:
                    # Last resort - highest price that's not obviously MSRP
                    sorted_prices = sorted([p['price'] for p in prices_found], reverse=True)
                    actual_price = sorted_prices[1] if len(sorted_prices) > 1 else sorted_prices[0]
            
            box_price = actual_price
        
        result['price'] = box_price
        
        # Extract stock status - look for button text
        stock_indicators = {
            'in_stock': ['add to cart', 'buy now', 'purchase', 'order now', 'add to bag'],
            'out_of_stock': ['notify me', 'out of stock', 'sold out', 'unavailable', 'email me']
        }
        
        # Look for buttons or stock indicators
        button_elements = soup.find_all(['button', 'input', 'a'], 
                                       class_=re.compile(r'btn|button|cart|buy|purchase', re.I))
        
        stock_status = None
        button_texts = []
        
        for button in button_elements:
            button_text = button.get_text(strip=True).lower()
            button_texts.append(button_text)
            
            # Check for stock indicators
            for status, keywords in stock_indicators.items():
                if any(keyword in button_text for keyword in keywords):
                    stock_status = (status == 'in_stock')
                    break
            
            if stock_status is not None:
                break
        
        # Also check for explicit stock messages
        if stock_status is None:
            stock_messages = soup.find_all(text=re.compile(r'in stock|out of stock|available|unavailable', re.I))
            for message in stock_messages:
                message_text = str(message).lower()
                if any(keyword in message_text for keyword in stock_indicators['out_of_stock']):
                    stock_status = False
                elif any(keyword in message_text for keyword in stock_indicators['in_stock']):
                    stock_status = True
                break
        
        result['in_stock'] = stock_status
        result['raw_data']['button_texts'] = button_texts
        result['success'] = (box_price is not None)
        
        return result
        
    except Exception as e:
        return {
            'url': url,
            'extracted_at': datetime.now().isoformat(),
            'success': False,
            'error': str(e),
            'price': None,
            'in_stock': None
        }

def update_csv_with_new_data(csv_path, url, new_price, new_stock_status):
    """
    Update the CSV file with new price and stock data for the specific URL
    """
    import csv
    from pathlib import Path
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"CSV file not found: {csv_path}")
        return False
    
    # Read current data
    rows = []
    headers = None
    target_row_index = None
    
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        for i, row in enumerate(reader):
            if row['url'] == url:
                target_row_index = i
                # Update the row
                if new_price is not None:
                    row['price'] = str(new_price)
                if new_stock_status is not None:
                    row['in_stock'] = 'true' if new_stock_status else 'false'
            rows.append(row)
    
    if target_row_index is None:
        print(f"URL not found in CSV: {url}")
        return False
    
    # Write back updated data
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Updated CSV: {csv_path}")
    print(f"  Price: {new_price}")
    print(f"  In Stock: {new_stock_status}")
    return True

# Test the extraction
if __name__ == "__main__":
    url = "https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html"
    
    print("Testing Cigar Place OpusX extraction...")
    result = extract_cigarplace_opusx_data(url)
    
    print("\nExtraction Result:")
    print(json.dumps(result, indent=2))
    
    if result['success']:
        print(f"\n✅ SUCCESS:")
        print(f"   Box Price: ${result['price']}")
        print(f"   In Stock: {result['in_stock']}")
        
        # Enhanced validation checks
        print(f"\n🔍 VALIDATION:")
        
        # Price validation
        if result['price']:
            if result['price'] < 100:
                print(f"   ⚠️  WARNING: Price ${result['price']} seems low for OpusX box")
            elif result['price'] > 2000:
                print(f"   ⚠️  WARNING: Price ${result['price']} seems high for OpusX box")
            else:
                print(f"   ✅ Price ${result['price']} is in reasonable range")
        
        # Stock validation
        if result['in_stock'] is None:
            print(f"   ⚠️  WARNING: Could not determine stock status")
        else:
            print(f"   ✅ Stock status determined: {'In Stock' if result['in_stock'] else 'Out of Stock'}")
        
        # MSRP and discount validation
        if 'raw_data' in result:
            if result['raw_data'].get('manual_review_needed'):
                print(f"   🔍 MANUAL REVIEW: {result['raw_data']['manual_review_needed']}")
            
            if result['raw_data'].get('you_save', {}).get('percentage') == 0:
                print(f"   ⚠️  ALERT: You Save is 0% - manual review recommended")
            
            if result['raw_data'].get('msrp_found') and result['raw_data'].get('you_save'):
                msrp = result['raw_data']['msrp_found']['price']
                discount = result['raw_data']['you_save']['percentage']
                expected_price = msrp * (1 - discount / 100)
                print(f"   📊 CALCULATION: MSRP ${msrp} - {discount}% = ${expected_price:.2f}")
                if abs(result['price'] - expected_price) < 1:
                    print(f"   ✅ Price calculation verified")
                else:
                    print(f"   ⚠️  Price mismatch: Expected ${expected_price:.2f}, Got ${result['price']}")
        
        # Show detailed extraction info
        print(f"\n🔍 EXTRACTION DETAILS:")
        if 'raw_data' in result:
            if result['raw_data'].get('msrp_found'):
                msrp_data = result['raw_data']['msrp_found']
                print(f"   MSRP: ${msrp_data['price']} ({msrp_data['context'][:50]}...)")
            
            if result['raw_data'].get('you_save'):
                save_data = result['raw_data']['you_save']
                print(f"   You Save: {save_data['percentage']}% ({save_data['text'][:50]}...)")
            
            if result['raw_data'].get('verified_price'):
                verify_data = result['raw_data']['verified_price']
                print(f"   Verified Price: ${verify_data['price']} ({verify_data['context'][:50]}...)")
            
            if result['raw_data'].get('using_calculated'):
                print(f"   ℹ️  Using calculated price (no exact match found)")
            
            if result['raw_data'].get('button_texts'):
                print(f"   Button texts: {result['raw_data']['button_texts']}")
        
        print(f"\n💾 TO UPDATE CSV:")
        print(f"   update_csv_with_new_data('static/data/cigarplace.csv', '{url}', {result['price']}, {result['in_stock']})")
        
    else:
        print(f"\n❌ FAILED: {result.get('error', 'Unknown error')}")
    
    # Automation recommendations
    print(f"\n" + "="*60)
    print("AUTOMATION RECOMMENDATIONS")
    print("="*60)
    print("✅ This script can reliably extract:")
    print("   - Box price using MSRP and 'You Save' calculation")
    print("   - Stock status from button text")
    print("⚠️  Manual review triggers:")
    print("   - You Save = 0% (no discount)")
    print("   - Price changes > 20% from previous")
    print("   - Cannot find MSRP or You Save percentage")
    print("💡 Recommended automation:")
    print("   - Run daily/weekly for all URLs")
    print("   - Flag anomalies for manual review") 
    print("   - Update CSV files automatically for normal cases")
