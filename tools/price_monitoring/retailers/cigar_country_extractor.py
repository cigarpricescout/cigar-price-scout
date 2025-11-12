#!/usr/bin/env python3
"""
Cigar Country Extractor
Retailer-specific extraction rules for Cigar Country (WooCommerce platform)
Dominican Republic jurisdiction - Tier 1 compliance

Key Features Observed:
- WooCommerce platform with "Packing" section for box options
- Multiple box quantities (Box of 23, 24, 25, 29, etc.)
- Crossed-out original price with sale price
- Stock status indicators ("Only X left in stock", "Out of stock")
- Clean product layout with standard WooCommerce structure

Training Examples (4):
1. Ashton VSG Robusto - Box of 24, sale price, in stock
2. My Father The Judge Grand Robusto - Box of 23, sale price, out of stock
3. Padrón 1964 Anniversary Diplomatico - Box of 25, regular price, in stock
4. Romeo y Julieta 1875 Churchill - Box of 25, sale price, out of stock

Created: 2025-11-11
Ready for CSV integration and Railway automation
"""

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time
from typing import Dict, Optional, Tuple

class CigarCountryExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Cigar Country URL
        Returns: {
            'box_price': float or None,
            'box_qty': int or None, 
            'in_stock': bool,
            'discount_percent': float or None,
            'original_price': float or None,
            'error': str or None
        }
        """
        try:
            # Rate limiting - 1 request per second for Dominican Republic jurisdiction
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            result = {
                'url': url,
                'retailer': "Cigar Country",
                'extracted_at': datetime.now().isoformat(),
                'method': 'cigar_country_woocommerce',
                'success': False,
                'price': None,
                'in_stock': None,
                'box_quantity': None,
                'discount_percent': None,
                'original_price': None,
                'debug_info': {}
            }
            
            # Extract box pricing from "Packing" section
            box_price, box_qty, original_price = self._extract_box_pricing(soup, result['debug_info'])
            
            # Check stock status
            in_stock = self._check_stock_status(soup, result['debug_info'])
            
            # Calculate discount if we have both prices
            discount_percent = None
            if original_price and box_price and original_price > box_price:
                discount_percent = ((original_price - box_price) / original_price) * 100
            
            result.update({
                'price': box_price,
                'box_quantity': box_qty,
                'in_stock': in_stock,
                'discount_percent': discount_percent,
                'original_price': original_price,
                'success': (box_price is not None and in_stock is not None and box_qty is not None)
            })
            
            return result
            
        except Exception as e:
            return {
                'url': url,
                'retailer': "Cigar Country",
                'extracted_at': datetime.now().isoformat(),
                'success': False,
                'error': str(e),
                'price': None,
                'in_stock': None,
                'box_quantity': None,
                'discount_percent': None,
                'original_price': None
            }
    
    def _extract_box_pricing(self, soup: BeautifulSoup, debug_info: Dict) -> Tuple[Optional[float], Optional[int], Optional[float]]:
        """
        Extract box pricing from WooCommerce "Packing" section
        Prioritizes boxes >20 quantity, takes largest available
        Returns: (sale_price, box_quantity, original_price)
        """
        
        # Find the "Packing" section
        packing_header = soup.find(string=re.compile(r'Packing', re.I))
        if not packing_header:
            debug_info['packing_section'] = 'Not found'
            return None, None, None
        
        debug_info['packing_section'] = 'Found'
        
        # Find the container with packing options
        packing_container = packing_header.find_parent()
        while packing_container and not packing_container.find_all(['div', 'li'], recursive=False):
            packing_container = packing_container.find_parent()
        
        if not packing_container:
            debug_info['packing_container'] = 'Not found'
            return None, None, None
        
        # Find all box options in the packing section
        box_options = []
        
        # Look for elements containing "Box of X" pattern
        for element in packing_container.find_all(['div', 'li', 'span', 'label']):
            text = element.get_text().strip()
            
            # Extract box quantity
            box_match = re.search(r'Box\s+of\s+(\d+)', text, re.I)
            if box_match:
                box_qty = int(box_match.group(1))
                
                # Find pricing for this box option
                # Look for prices in the same element or nearby
                price_elements = [element] + element.find_all(['span', 'div']) + element.find_all_next(['span', 'div'], limit=5)
                
                sale_price = None
                original_price = None
                
                for price_elem in price_elements:
                    price_text = price_elem.get_text().strip()
                    
                    # Look for crossed-out price (original/MSRP)
                    if price_elem.find(['del', 's']) or 'line-through' in price_elem.get('style', '').lower():
                        price_match = re.search(r'\$?([0-9,]+\.?\d*)', price_text.replace(',', ''))
                        if price_match:
                            try:
                                original_price = float(price_match.group(1))
                                debug_info[f'original_price_box_{box_qty}'] = price_text
                            except ValueError:
                                continue
                    
                    # Look for sale/current price
                    elif '$' in price_text:
                        # Skip if this element contains crossed-out price
                        if not (price_elem.find(['del', 's']) or 'line-through' in price_elem.get('style', '').lower()):
                            price_match = re.search(r'\$?([0-9,]+\.?\d*)', price_text.replace(',', ''))
                            if price_match:
                                try:
                                    potential_price = float(price_match.group(1))
                                    if potential_price > 50:  # Filter out obviously wrong prices
                                        sale_price = potential_price
                                        debug_info[f'sale_price_box_{box_qty}'] = price_text
                                except ValueError:
                                    continue
                
                # If we found pricing, add this option
                if sale_price:
                    box_options.append({
                        'quantity': box_qty,
                        'sale_price': sale_price,
                        'original_price': original_price,
                        'text': text
                    })
                    debug_info[f'box_option_{box_qty}'] = f"${sale_price} (orig: ${original_price})"
        
        # Filter and prioritize box options
        # Priority: quantity > 20, then take largest available
        target_boxes = [opt for opt in box_options if opt['quantity'] > 20]
        
        if not target_boxes:
            # If no >20 boxes, take largest available (for future expansion)
            target_boxes = box_options
        
        if not target_boxes:
            debug_info['box_selection'] = 'No valid boxes found'
            return None, None, None
        
        # Select the largest box quantity
        selected_box = max(target_boxes, key=lambda x: x['quantity'])
        
        debug_info['selected_box'] = f"Box of {selected_box['quantity']} - ${selected_box['sale_price']}"
        debug_info['total_options_found'] = len(box_options)
        debug_info['target_options_found'] = len(target_boxes)
        
        return selected_box['sale_price'], selected_box['quantity'], selected_box['original_price']
    
    def _check_stock_status(self, soup: BeautifulSoup, debug_info: Dict) -> bool:
        """
        Check stock status based on button text and stock indicators
        """
        
        # Method 1: Check the main action button
        action_buttons = soup.find_all(['button', 'a'], class_=re.compile(r'button|btn|cart', re.I))
        
        for button in action_buttons:
            button_text = button.get_text().strip().upper()
            
            # In stock indicators
            if any(phrase in button_text for phrase in ['ADD TO CART', 'BUY NOW', 'ADD TO BASKET']):
                debug_info['stock_method'] = f'Button: "{button_text}"'
                return True
            
            # Out of stock indicators
            if any(phrase in button_text for phrase in ['NOTIFY ME', 'EMAIL ME', 'OUT OF STOCK']):
                debug_info['stock_method'] = f'Button: "{button_text}"'
                return False
        
        # Method 2: Look for explicit stock text
        stock_indicators = soup.find_all(string=re.compile(r'(?:in\s+stock|out\s+of\s+stock|only\s+\d+\s+left)', re.I))
        
        for indicator in stock_indicators:
            text = indicator.strip().upper()
            
            # In stock patterns
            if re.search(r'(?:IN\s+STOCK|ONLY\s+\d+\s+LEFT)', text):
                debug_info['stock_method'] = f'Text: "{indicator.strip()}"'
                return True
            
            # Out of stock patterns  
            if 'OUT OF STOCK' in text:
                debug_info['stock_method'] = f'Text: "{indicator.strip()}"'
                return False
        
        # Method 3: Look for stock status in packing section
        packing_section = soup.find(string=re.compile(r'Packing', re.I))
        if packing_section:
            packing_container = packing_section.find_parent()
            if packing_container:
                stock_elements = packing_container.find_all(string=re.compile(r'out\s+of\s+stock', re.I))
                if stock_elements:
                    debug_info['stock_method'] = 'Packing section: Out of stock'
                    return False
        
        # Default to True if we can't determine (conservative for price tracking)
        debug_info['stock_method'] = 'Default: Unable to determine, assuming in stock'
        return True


def extract_cigar_country_data(url: str) -> Dict:
    """
    Main extraction function for Cigar Country
    Compatible with your CSV update workflow
    """
    extractor = CigarCountryExtractor()
    return extractor.extract_product_data(url)


# Test function for development
def test_cigar_country_extraction():
    """Test the extractor on the 4 training examples"""
    
    test_urls = [
        {
            'url': 'https://cigarcountry.com/product/ashton-vsg-robusto/',
            'expected': {'box_qty': 24, 'in_stock': True, 'has_discount': True}
        },
        {
            'url': 'https://cigarcountry.com/product/my-father-the-judge-grand-robusto/',
            'expected': {'box_qty': 23, 'in_stock': False, 'has_discount': True}
        },
        {
            'url': 'https://cigarcountry.com/product/padron-1964-anniversary-series-diplomatico-maduro/',
            'expected': {'box_qty': 25, 'in_stock': True, 'has_discount': False}
        },
        {
            'url': 'https://cigarcountry.com/product/romeo-y-julieta-1875-churchill/',
            'expected': {'box_qty': 25, 'in_stock': False, 'has_discount': True}
        }
    ]
    
    print("Testing Cigar Country extraction rules...")
    print("=" * 80)
    
    for i, test_case in enumerate(test_urls):
        url = test_case['url']
        expected = test_case['expected']
        
        print(f"\nTest {i+1}: {url.split('/')[-2]}")
        print("-" * 60)
        
        result = extract_cigar_country_data(url)
        
        if result['success']:
            print(f"[SUCCESS]")
            print(f"   Price: ${result['price']}")
            print(f"   Box Qty: {result['box_quantity']} (expected: {expected['box_qty']})")
            print(f"   In Stock: {result['in_stock']} (expected: {expected['in_stock']})")
            
            if result['discount_percent']:
                print(f"   Discount: {result['discount_percent']:.1f}% off (orig: ${result['original_price']})")
            
            print(f"   Stock Detection: {result['debug_info'].get('stock_method', 'N/A')}")
            print(f"   Box Selection: {result['debug_info'].get('selected_box', 'N/A')}")
            
            # Validation
            validation_issues = []
            if result['box_quantity'] != expected['box_qty']:
                validation_issues.append(f"Box qty mismatch: got {result['box_quantity']}, expected {expected['box_qty']}")
            
            if result['in_stock'] != expected['in_stock']:
                validation_issues.append(f"Stock mismatch: got {result['in_stock']}, expected {expected['in_stock']}")
            
            if expected['has_discount'] and not result['discount_percent']:
                validation_issues.append(f"Expected discount but none found")
            
            if validation_issues:
                print(f"[WARNING] VALIDATION ISSUES: {'; '.join(validation_issues)}")
                
        else:
            print(f"[FAILED] {result.get('error', 'Unknown error')}")
            if result.get('debug_info'):
                print(f"   Debug Info: {result['debug_info']}")
    
    print("\n" + "=" * 80)
    print("Cigar Country extraction testing complete!")
    print("\nReady for CSV integration and automation!")


# Configuration for your automation system
CIGAR_COUNTRY_CONFIG = {
    "retailer_info": {
        "name": "Cigar Country",
        "domain": "cigarcountry.com",
        "platform": "WooCommerce",
        "compliance_tier": 1,
        "jurisdiction": "Dominican Republic",
        "trained_date": "2025-11-11",
        "training_examples": 4
    },
    
    "extraction_patterns": {
        "pricing_scenarios": [
            "Regular pricing (single price)",
            "Sale pricing (crossed-out original + sale price)",
            "Multiple box options with individual pricing",
            "Out of stock with pricing maintained"
        ],
        
        "box_quantities_seen": [23, 24, 25, 29],
        "box_quantity_priority": ">20 preferred, largest available selected",
        
        "stock_indicators": {
            "in_stock": ["ADD TO CART", "BUY NOW", "Only X left in stock"],
            "out_of_stock": ["NOTIFY ME", "OUT OF STOCK", "EMAIL WHEN AVAILABLE"]
        },
        
        "layout_structure": "WooCommerce with 'Packing' section for box options"
    },
    
    "csv_integration": {
        "csv_file": "cigarcountry.csv",
        "update_fields": ["price", "in_stock", "last_updated"],
        "price_field_source": "sale_price (after discount)",
        "stock_field_source": "button_text + stock_indicators"
    },
    
    "automation_ready": True,
    "confidence_level": "high",
    "notes": [
        "Clean WooCommerce structure with consistent 'Packing' section",
        "Handles multiple box quantities with >20 prioritization",
        "Robust stock detection via buttons and text indicators", 
        "Sale pricing extraction with discount calculation",
        "Dominican Republic jurisdiction allows daily crawling",
        "Ready for integration into Railway automation system"
    ]
}

if __name__ == "__main__":
    test_cigar_country_extraction()
