#!/usr/bin/env python3
"""
Nick's Cigar World - Complete Retailer Extraction Rules
Trained on 3 product examples:
1. Romeo y Julieta 1875 Churchill - Single price, in stock, Box of 25
2. Hemingway Classic - Multiple package options, in stock, Box of 25
3. Opus X Robusto - Single price, out of stock, single cigar

Key Learning: Custom platform with package options and clear stock indicators
Platform: Custom E-commerce, Tier 1 compliance
"""

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time

def extract_nicks_cigars_data(url):
    """
    Extract price and stock data from Nick's Cigar World product pages
    Handles both single pricing and multiple package options
    """
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        # Rate limiting - 1 request per second for politeness
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        result = {
            'url': url,
            'retailer': "Nick's Cigar World",
            'extracted_at': datetime.now().isoformat(),
            'method': 'nicks_cigars_rules',
            'success': False,
            'price': None,
            'in_stock': None,
            'box_quantity': None,
            'discount_percent': None,
            'debug_info': {}
        }
        
        # STEP 1: Check for stock status first (affects pricing logic)
        stock_status = None
        page_text = soup.get_text().upper()
        
        # Check for explicit out of stock indicators
        if 'OUT OF STOCK' in page_text:
            stock_status = False
            result['debug_info']['stock_indicator'] = 'OUT OF STOCK text found'
        
        # Check button text for stock status
        buttons = soup.find_all(['button', 'a', 'input'])
        for button in buttons:
            button_text = button.get_text().strip().upper()
            button_class = ' '.join(button.get('class', [])).lower()
            
            # In stock indicators
            if any(phrase in button_text for phrase in ['ADD TO CART', 'BUY NOW']):
                stock_status = True
                result['debug_info']['stock_button'] = button_text
                break
                
            # Out of stock indicators
            elif any(phrase in button_text for phrase in [
                'EMAIL WHEN STOCK AVAILABLE',
                'NOTIFY ME',
                'EMAIL WHEN AVAILABLE',
                'OUT OF STOCK'
            ]):
                stock_status = False
                result['debug_info']['stock_button'] = button_text
                break
        
        result['in_stock'] = stock_status
        
        # STEP 2: Extract pricing - check for package options first
        price = None
        box_quantity = None
        
        # Look for "PACKAGE SIZE" section with multiple options
        package_section = soup.find(string=re.compile(r'PACKAGE\s+SIZE', re.I))
        
        if package_section:
            # Multiple package options scenario (like Hemingway)
            result['debug_info']['pricing_method'] = 'package_options'
            
            # Look for the box option specifically
            parent_section = package_section.find_parent()
            if parent_section:
                # Look for "BOX OF X" option within this section
                box_options = parent_section.find_all(string=re.compile(r'BOX\s+OF\s+\d+', re.I))
                
                for box_option in box_options:
                    # Extract box quantity
                    qty_match = re.search(r'BOX\s+OF\s+(\d+)', box_option, re.I)
                    if qty_match:
                        box_quantity = int(qty_match.group(1))
                        
                        # Find the price associated with this box option
                        # Look for price near this text element
                        option_parent = box_option.parent if hasattr(box_option, 'parent') else None
                        if option_parent:
                            # Search in the same row/container for price
                            price_elements = option_parent.find_all_next(['span', 'div', 'td'], limit=5)
                            for price_elem in price_elements:
                                price_text = price_elem.get_text().strip()
                                price_match = re.search(r'\$([0-9,]+\.?\d*)', price_text.replace(',', ''))
                                if price_match:
                                    try:
                                        price = float(price_match.group(1))
                                        result['debug_info']['box_price_text'] = price_text
                                        result['debug_info']['box_quantity_text'] = box_option
                                        break
                                    except ValueError:
                                        continue
                        
                        if price:
                            break
        
        # If no package options found, look for single main price
        if not price:
            result['debug_info']['pricing_method'] = 'single_price'
            
            # Look for main price display (large red price)
            price_selectors = [
                '.price',
                '[class*="price"]',
                'span',
                'div'
            ]
            
            for selector in price_selectors:
                price_elements = soup.select(selector)
                for elem in price_elements:
                    # Check if element contains a price and is prominently displayed
                    price_text = elem.get_text().strip()
                    price_match = re.search(r'\$([0-9,]+\.?\d*)', price_text.replace(',', ''))
                    
                    if price_match:
                        # Check if this looks like a main price (not a small incidental price)
                        elem_style = elem.get('style', '')
                        elem_class = ' '.join(elem.get('class', []))
                        parent_context = elem.parent.get_text() if elem.parent else ''
                        
                        try:
                            price_val = float(price_match.group(1))
                            
                            # Filter out very small prices (likely singles when we want boxes)
                            # and very large prices (likely mistakes)
                            if 10 < price_val < 5000:
                                # Check if this is the main prominent price
                                if ('font-size' in elem_style and 'large' in elem_style) or \
                                   'price' in elem_class.lower() or \
                                   len(price_text.strip()) < 20:  # Short text likely to be just price
                                    price = price_val
                                    result['debug_info']['main_price_text'] = price_text
                                    result['debug_info']['main_price_element'] = f"{elem.name}.{elem_class}"
                                    break
                        except ValueError:
                            continue
                
                if price:
                    break
        
        result['price'] = price
        result['box_quantity'] = box_quantity
        
        # STEP 3: If we didn't find box quantity in package options, look elsewhere
        if not box_quantity:
            # Look for box quantity in product details or additional information
            details_section = soup.find(string=re.compile(r'ADDITIONAL\s+INFORMATION', re.I))
            if details_section:
                details_parent = details_section.find_parent()
                if details_parent:
                    details_text = details_parent.get_text()
                    qty_match = re.search(r'(?:QUANTITY|SIZE)[:\s]*(?:BOX\s+OF\s+)?(\d+)', details_text, re.I)
                    if qty_match:
                        box_quantity = int(qty_match.group(1))
                        result['debug_info']['quantity_from_details'] = details_text
            
            # Fallback: look anywhere in page for "BOX OF X" pattern
            if not box_quantity:
                all_text = soup.get_text()
                qty_match = re.search(r'BOX\s+OF\s+(\d+)', all_text, re.I)
                if qty_match:
                    box_quantity = int(qty_match.group(1))
                    result['debug_info']['quantity_fallback'] = qty_match.group(0)
        
        result['box_quantity'] = box_quantity
        
        # STEP 4: Look for any discount information (MSRP vs sale price)
        # This would be similar to other retailers - look for crossed out prices
        discount_percent = None
        
        # Look for crossed-out or strikethrough prices
        strikethrough_elems = soup.find_all(['del', 's'])
        strikethrough_elems.extend(soup.find_all(attrs={'style': re.compile(r'text-decoration.*line-through', re.I)}))
        
        for elem in strikethrough_elems:
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$([0-9,]+\.?\d*)', price_text.replace(',', ''))
            if price_match:
                try:
                    msrp = float(price_match.group(1))
                    if price and msrp > price:
                        discount_percent = ((msrp - price) / msrp) * 100
                        result['debug_info']['msrp'] = msrp
                        result['debug_info']['discount_text'] = price_text
                    break
                except ValueError:
                    continue
        
        result['discount_percent'] = discount_percent
        result['success'] = (price is not None and stock_status is not None)
        
        return result
        
    except Exception as e:
        return {
            'url': url,
            'retailer': "Nick's Cigar World",
            'extracted_at': datetime.now().isoformat(),
            'success': False,
            'error': str(e),
            'price': None,
            'in_stock': None,
            'box_quantity': None
        }

# Nick's Cigar World Retailer Configuration
NICKS_CIGARS_CONFIG = {
    "retailer_info": {
        "name": "Nick's Cigar World",
        "domain": "nickscigarworld.com",
        "platform": "Custom E-commerce", 
        "compliance_tier": 1,
        "trained_date": "2025-11-10",
        "training_examples": 3
    },
    
    "extraction_patterns": {
        "pricing_scenarios": [
            "Single price display (simple products)",
            "Multiple package options with BOX OF X pricing",
            "Out of stock with price still shown"
        ],
        
        "box_quantities_seen": [25],
        "box_quantity_note": "Found in PACKAGE SIZE section or product details",
        
        "stock_indicators": {
            "in_stock": ["ADD TO CART", "BUY NOW"],
            "out_of_stock": ["OUT OF STOCK", "EMAIL WHEN STOCK AVAILABLE", "NOTIFY ME"]
        }
    },
    
    "automation_ready": True,
    "confidence_level": "high",
    "notes": [
        "Custom platform with unique package options layout",
        "Clear stock status indicators and button changes",
        "Handles both single pricing and multi-tier packaging", 
        "Box quantities in PACKAGE SIZE section or Additional Information",
        "Out of stock products still show pricing information"
    ]
}

# Test function
def test_nicks_cigars_extraction():
    """Test the extraction on the training URLs"""
    
    test_urls = [
        "https://nickscigarworld.com/shop/premium-cigars/romeo-y-julieta-1875/romeo-y-julieta-1875-churchill/",  # In stock, single price
        "https://nickscigarworld.com/shop/premium-cigars/arturo-fuente-hemingway/arturo-fuente-hemingway-classic/",  # In stock, package options
        "https://nickscigarworld.com/shop/premium-cigars/arturo-fuente-opus-x/arturo-fuente-opus-x-robusto/",  # Out of stock, single price
    ]
    
    print("Testing Nick's Cigar World extraction rules...")
    print("=" * 60)
    
    for i, url in enumerate(test_urls):
        print(f"\nTesting URL {i+1}: {url}")
        result = extract_nicks_cigars_data(url)
        
        if result['success']:
            print(f"[OK] Price: ${result['price']}")
            print(f"[OK] In Stock: {result['in_stock']}")
            print(f"[OK] Box Quantity: {result['box_quantity']}")
            if result.get('discount_percent'):
                print(f"[OK] Discount: {result['discount_percent']:.1f}% off")
            
            # Show some debug info
            if result['debug_info'].get('pricing_method'):
                print(f"     Method: {result['debug_info']['pricing_method']}")
            if result['debug_info'].get('stock_button'):
                print(f"     Stock Button: {result['debug_info']['stock_button']}")
            if result['debug_info'].get('box_quantity_text'):
                print(f"     Box Text: {result['debug_info']['box_quantity_text']}")
        else:
            print(f"[FAILED] {result.get('error', 'Unknown error')}")
            if result['debug_info']:
                print(f"     Debug: {result['debug_info']}")
    
    print("\n" + "="*60)
    print("Nick's Cigar World extraction rules training complete!")

if __name__ == "__main__":
    test_nicks_cigars_extraction()
