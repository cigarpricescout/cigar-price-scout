#!/usr/bin/env python3
"""
Fixed URL-Specific Price Monitor for Cigar Place OpusX Robusto
Windows-compatible version with improved price extraction
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime

def extract_cigarplace_opusx_data(url):
    """
    Extract box price and stock status for Cigar Place OpusX Robusto
    Fixed version with better price detection and Windows compatibility
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
        
        # Step 1: Find MSRP using more targeted approach
        msrp_price = None
        msrp_elements = soup.find_all(['span', 'div', 'p'], string=re.compile(r'MSRP|retail|list price', re.I))
        
        for element in msrp_elements:
            # Look for price near MSRP text
            parent = element.parent if element.parent else element
            msrp_text = parent.get_text()
            msrp_match = re.search(r'\$([0-9,]+\.?[0-9]*)', msrp_text)
            if msrp_match:
                try:
                    msrp_price = float(msrp_match.group(1).replace(',', ''))
                    result['raw_data']['msrp_found'] = {
                        'price': msrp_price, 
                        'context': msrp_text.strip()[:100]
                    }
                    break
                except ValueError:
                    continue
        
        # Step 2: Find "You Save" percentage using more targeted approach
        you_save_percentage = None
        save_elements = soup.find_all(['span', 'div', 'p'], string=re.compile(r'you save|save', re.I))
        
        for element in save_elements:
            parent = element.parent if element.parent else element
            save_text = parent.get_text()
            save_match = re.search(r'(\d+)%', save_text)
            if save_match:
                you_save_percentage = int(save_match.group(1))
                result['raw_data']['you_save'] = {
                    'percentage': you_save_percentage,
                    'text': save_text.strip()[:100]
                }
                break
        
        # Step 3: Find actual displayed price (avoid JavaScript and other noise)
        actual_price = None
        
        # Look for common price selectors
        price_selectors = [
            '.price', '.cost', '.money', '[class*="price"]',
            '#price', '[id*="price"]', '.product-price'
        ]
        
        for selector in price_selectors:
            price_elements = soup.select(selector)
            for element in price_elements:
                price_text = element.get_text(strip=True)
                # Skip if it looks like JavaScript or contains non-price text
                if ('window.' in price_text or 'var ' in price_text or 
                    'function' in price_text or len(price_text) > 50):
                    continue
                    
                price_match = re.search(r'\$([0-9,]+\.?[0-9]*)', price_text)
                if price_match:
                    try:
                        candidate_price = float(price_match.group(1).replace(',', ''))
                        # Skip obviously wrong prices
                        if candidate_price < 1 or candidate_price > 5000:
                            continue
                        actual_price = candidate_price
                        result['raw_data']['displayed_price'] = {
                            'price': actual_price,
                            'context': price_text[:100]
                        }
                        break
                    except ValueError:
                        continue
            if actual_price:
                break
        
        # Step 4: Calculate final price
        box_price = None
        
        if msrp_price and you_save_percentage is not None:
            # Use MSRP and discount calculation
            calculated_price = msrp_price * (1 - you_save_percentage / 100)
            result['raw_data']['calculated_price'] = round(calculated_price, 2)
            
            # Verify against displayed price
            if actual_price and abs(actual_price - calculated_price) < 5:
                box_price = actual_price
                result['raw_data']['price_verified'] = True
            else:
                box_price = round(calculated_price, 2)
                result['raw_data']['using_calculated'] = True
                
        elif you_save_percentage == 0:
            # No discount - flag for review
            result['raw_data']['manual_review_needed'] = "You Save is 0% - no discount detected"
            box_price = msrp_price if msrp_price else actual_price
            
        elif actual_price:
            # Use displayed price as fallback
            box_price = actual_price
            result['raw_data']['using_displayed_price'] = True
            
        else:
            result['raw_data']['manual_review_needed'] = "Could not find reliable price"
        
        result['price'] = box_price
        
        # Step 5: Extract stock status - improved button detection
        stock_status = None
        
        # Look for specific button text patterns
        all_buttons = soup.find_all(['button', 'input', 'a'])
        button_texts = []
        
        for button in all_buttons:
            button_text = button.get_text(strip=True).lower()
            if button_text:  # Skip empty buttons
                button_texts.append(button_text)
                
                # Check for out of stock indicators
                if any(phrase in button_text for phrase in ['notify me', 'out of stock', 'sold out', 'unavailable']):
                    stock_status = False
                    break
                # Check for in stock indicators  
                elif any(phrase in button_text for phrase in ['add to cart', 'buy now', 'purchase', 'add to bag']):
                    stock_status = True
                    break
        
        # Also check for stock messages in text
        if stock_status is None:
            page_text = soup.get_text().lower()
            if 'notify me' in page_text or 'out of stock' in page_text:
                stock_status = False
            elif 'add to cart' in page_text:
                stock_status = True
        
        result['in_stock'] = stock_status
        result['raw_data']['button_texts'] = button_texts[:10]  # Limit to first 10
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
    """Update the CSV file with new price and stock data"""
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

# Test the extraction (Windows-compatible)
if __name__ == "__main__":
    url = "https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html"
    
    print("Testing Cigar Place OpusX extraction...")
    print("=" * 50)
    result = extract_cigarplace_opusx_data(url)
    
    print("\nExtraction Result:")
    print(json.dumps(result, indent=2))
    
    if result['success']:
        print(f"\n[SUCCESS]")
        print(f"   Box Price: ${result['price']}")
        print(f"   In Stock: {result['in_stock']}")
        
        # Enhanced validation checks
        print(f"\n[VALIDATION]")
        
        if result['price']:
            if result['price'] < 100:
                print(f"   [WARNING] Price ${result['price']} seems low for OpusX box")
            elif result['price'] > 2000:
                print(f"   [WARNING] Price ${result['price']} seems high for OpusX box")
            else:
                print(f"   [OK] Price ${result['price']} is in reasonable range")
        
        if result['in_stock'] is None:
            print(f"   [WARNING] Could not determine stock status")
        else:
            status_text = 'In Stock' if result['in_stock'] else 'Out of Stock'
            print(f"   [OK] Stock status: {status_text}")
        
        # Show calculation details
        if 'raw_data' in result:
            print(f"\n[DETAILS]")
            
            if result['raw_data'].get('manual_review_needed'):
                print(f"   [REVIEW NEEDED] {result['raw_data']['manual_review_needed']}")
            
            if result['raw_data'].get('msrp_found'):
                msrp_data = result['raw_data']['msrp_found']
                print(f"   MSRP: ${msrp_data['price']}")
            
            if result['raw_data'].get('you_save'):
                save_data = result['raw_data']['you_save']
                print(f"   You Save: {save_data['percentage']}%")
            
            if result['raw_data'].get('calculated_price'):
                calc_price = result['raw_data']['calculated_price']
                print(f"   Calculated Price: ${calc_price}")
            
            if result['raw_data'].get('button_texts'):
                button_text = ', '.join(result['raw_data']['button_texts'][:3])
                print(f"   Buttons found: {button_text}")
        
        print(f"\n[UPDATE CSV]")
        print(f"   Command: update_csv_with_new_data('static/data/cigarplace.csv', '{url}', {result['price']}, {result['in_stock']})")
        
    else:
        print(f"\n[FAILED] {result.get('error', 'Unknown error')}")
    
    print(f"\n" + "="*50)
    print("AUTOMATION STATUS")
    print("="*50)
    print("Ready for automation if:")
    print("- Price is in reasonable range (100-2000)")
    print("- Stock status is determined")  
    print("- No manual review flags")
