#!/usr/bin/env python3
"""
Targeted extractor for Cigar Place based on actual page layout
Handles the specific case where MSRP=$0.00 and You Save=0%
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime

def extract_cigarplace_opusx_data(url):
    """
    Extract box price and stock status based on the actual Cigar Place layout
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
        
        # Strategy 1: Look for the pricing table/box structure
        # Based on screenshot, there should be "Box of 29", "MSRP", "Price", "You Save" structure
        
        # Find "Box of 29" section
        box_section = None
        box_elements = soup.find_all(string=re.compile(r'box\s*of\s*29', re.I))
        
        if box_elements:
            # Found "Box of 29" text, now find the associated price
            for box_element in box_elements:
                # Look in the parent elements for price structure
                current_element = box_element.parent if hasattr(box_element, 'parent') else None
                
                # Traverse up a few levels to find the pricing container
                for _ in range(5):  # Look up to 5 parent levels
                    if current_element:
                        # Look for price patterns in this container
                        container_text = current_element.get_text()
                        
                        # Look for the main price (not MSRP)
                        price_matches = re.findall(r'\$([0-9,]+\.?[0-9]*)', container_text)
                        
                        if len(price_matches) >= 2:  # Should have MSRP and Price
                            # Parse the prices found
                            prices = []
                            for match in price_matches:
                                try:
                                    price_val = float(match.replace(',', ''))
                                    prices.append(price_val)
                                except ValueError:
                                    continue
                            
                            # Based on screenshot: MSRP=$0.00, Price=$667.95
                            # So we want the non-zero price
                            non_zero_prices = [p for p in prices if p > 0]
                            if non_zero_prices:
                                box_price = max(non_zero_prices)  # Take highest non-zero price
                                result['raw_data']['box_section_found'] = {
                                    'container_text': container_text[:200],
                                    'all_prices': prices,
                                    'selected_price': box_price
                                }
                                break
                        
                        current_element = current_element.parent if hasattr(current_element, 'parent') else None
                    else:
                        break
                
                if result['raw_data'].get('box_section_found'):
                    break
        
        # Strategy 2: Look for specific price patterns if Strategy 1 failed
        if not result['raw_data'].get('box_section_found'):
            # Look for common price display patterns
            price_patterns = [
                r'Price[:\s]*\$([0-9,]+\.?[0-9]*)',  # "Price: $667.95"
                r'\$([0-9,]+\.?[0-9]*)\s*Box',       # "$667.95 Box"
                r'Box[^$]*\$([0-9,]+\.?[0-9]*)'      # "Box ... $667.95"
            ]
            
            page_text = soup.get_text()
            for pattern in price_patterns:
                matches = re.findall(pattern, page_text, re.I)
                if matches:
                    try:
                        candidate_price = float(matches[0].replace(',', ''))
                        if 100 < candidate_price < 2000:  # Reasonable range
                            result['raw_data']['pattern_match'] = {
                                'pattern': pattern,
                                'price': candidate_price
                            }
                            break
                    except ValueError:
                        continue
        
        # Determine final price
        box_price = None
        if result['raw_data'].get('box_section_found'):
            box_price = result['raw_data']['box_section_found']['selected_price']
        elif result['raw_data'].get('pattern_match'):
            box_price = result['raw_data']['pattern_match']['price']
        
        # Strategy 3: Handle MSRP=$0.00 and You Save=0% case (as shown in screenshot)
        msrp_zero = False
        you_save_zero = False
        
        page_text = soup.get_text()
        if re.search(r'MSRP[:\s]*\$0\.00', page_text, re.I):
            msrp_zero = True
            result['raw_data']['msrp_zero'] = True
            
        if re.search(r'You\s+Save[:\s]*0%', page_text, re.I):
            you_save_zero = True
            result['raw_data']['you_save_zero'] = True
        
        if msrp_zero and you_save_zero:
            result['raw_data']['manual_review_reason'] = "MSRP=$0.00 and You Save=0% - using displayed price"
            # In this case, use the displayed price as-is
            
        result['price'] = box_price
        
        # Stock status detection - look for "Notify Me" vs "Add to Cart"
        stock_status = None
        
        # Look for the specific button text
        notify_buttons = soup.find_all(string=re.compile(r'notify\s*me', re.I))
        add_cart_buttons = soup.find_all(string=re.compile(r'add\s*to\s*cart', re.I))
        
        if notify_buttons:
            stock_status = False  # Out of stock
            result['raw_data']['stock_indicator'] = "Notify Me button found"
        elif add_cart_buttons:
            stock_status = True   # In stock
            result['raw_data']['stock_indicator'] = "Add to Cart button found"
        
        # Also check button elements
        all_buttons = soup.find_all(['button', 'input', 'a'])
        for button in all_buttons:
            button_text = button.get_text(strip=True).lower()
            if 'notify me' in button_text:
                stock_status = False
                result['raw_data']['stock_button'] = "Notify Me"
                break
            elif 'add to cart' in button_text:
                stock_status = True
                result['raw_data']['stock_button'] = "Add to Cart"
                break
        
        result['in_stock'] = stock_status
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

# Test with enhanced debugging
if __name__ == "__main__":
    url = "https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html"
    
    print("Testing TARGETED Cigar Place OpusX extraction...")
    print("=" * 60)
    print("Based on screenshot analysis:")
    print("- Expected: Box of 29 = $667.95")
    print("- Expected: MSRP = $0.00, You Save = 0%")
    print("- Expected: 'Notify Me' button = Out of Stock")
    print("=" * 60)
    
    result = extract_cigarplace_opusx_data(url)
    
    print("\nExtraction Result:")
    print(json.dumps(result, indent=2))
    
    if result['success']:
        print(f"\n[SUCCESS]")
        print(f"   Box Price: ${result['price']}")
        print(f"   In Stock: {result['in_stock']}")
        
        # Validation against expected values
        expected_price = 667.95
        expected_stock = False
        
        print(f"\n[VALIDATION AGAINST SCREENSHOT]")
        
        if result['price']:
            if abs(result['price'] - expected_price) < 1:
                print(f"   [OK] Price matches expected: ${expected_price}")
            else:
                print(f"   [MISMATCH] Expected ${expected_price}, got ${result['price']}")
        
        if result['in_stock'] == expected_stock:
            print(f"   [OK] Stock status matches expected: Out of Stock")
        else:
            actual_stock = "In Stock" if result['in_stock'] else "Out of Stock"
            expected_stock_text = "In Stock" if expected_stock else "Out of Stock"
            print(f"   [MISMATCH] Expected {expected_stock_text}, got {actual_stock}")
        
        # Show extraction details
        if 'raw_data' in result:
            print(f"\n[EXTRACTION DETAILS]")
            for key, value in result['raw_data'].items():
                print(f"   {key}: {value}")
                
    else:
        print(f"\n[FAILED] {result.get('error', 'Unknown error')}")
        print("This means the page structure is different than expected.")
        print("We may need to analyze the actual HTML structure.")
