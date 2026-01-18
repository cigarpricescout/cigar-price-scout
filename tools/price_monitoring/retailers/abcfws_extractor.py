#!/usr/bin/env python3
"""
ABC Fine Wine & Spirits Working Extractor
Following the proven pattern from Hiland's extractor - actual data extraction
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class ABCFWSExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from ABC Fine Wine & Spirits URL
        Returns: {
            'box_price': float or None,
            'box_qty': int or None,
            'in_stock': bool,
            'discount_percent': float or None,
            'error': str or None
        }
        """
        try:
            # Rate limiting - 1 request per second
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from product title
            box_qty = self._extract_box_quantity(soup)
            
            # Extract pricing information
            box_price, discount_percent = self._extract_pricing(soup)
            
            # Check stock status
            in_stock = self._check_stock_status(soup)
            
            return {
                'box_price': box_price,
                'box_qty': box_qty,
                'in_stock': in_stock,
                'discount_percent': discount_percent,
                'error': None
            }
            
        except Exception as e:
            return {
                'box_price': None,
                'box_qty': None,
                'in_stock': False,
                'discount_percent': None,
                'error': str(e)
            }
    
    def _extract_box_quantity(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract box quantity from product title or description"""
        
        # Look in product title and SKU area
        title_selectors = ['h1', '.product-title', '.product_title', 'h1.product-title', '[class*="sku"]']
        for selector in title_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text().strip()
                
                # Check for "1 Stick" indicator (single cigar)
                if re.search(r'1\s+Stick', text, re.IGNORECASE):
                    return 1
                
                # ABC's pattern - "Box of X" in title
                qty_match = re.search(r'box\s+of\s+(\d+)', text, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 1:
                        return qty
                
                # Alternative patterns
                qty_match = re.search(r'(\d+)\s*pack', text, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 1:
                        return qty
        
        # Default to None - box quantity will come from master file
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract box price and discount percentage"""
        
        # ABC shows prices clearly - current price and sometimes original (strikethrough) price
        current_price = None
        original_price = None
        
        # Method 1: Look for Open Graph meta tags (most reliable)
        og_price = soup.find('meta', property='product:price:amount')
        if og_price:
            try:
                current_price = float(og_price.get('content'))
            except (ValueError, TypeError):
                pass
        
        # Also check for original price in OG tags
        og_standard = soup.find('meta', property='og:price:standard_amount')
        if og_standard:
            try:
                original_price = float(og_standard.get('content'))
            except (ValueError, TypeError):
                pass
        
        # Method 2: Look for price in common CSS selectors if OG tags didn't work
        if current_price is None:
            price_patterns = [
                # Look for main price display (red sale price or regular price)
                (r'\$(\d+\.?\d*)', ['[class*="price"]', '.price', '[class*="product-price"]']),
            ]
            
            for pattern, selectors in price_patterns:
                for selector in selectors:
                    elements = soup.select(selector)
                    for elem in elements:
                        price_text = elem.get_text().strip()
                        
                        # Check if this is a strikethrough/original price
                        is_original = (
                            elem.find_parent(['del', 's']) or
                            'line-through' in str(elem.get('style', '')).lower() or
                            'strikethrough' in ' '.join(elem.get('class', [])).lower() or
                            'was' in price_text.lower()
                        )
                        
                        # Extract price value
                        price_match = re.search(pattern, price_text.replace(',', ''))
                        if price_match:
                            try:
                                price = float(price_match.group(1))
                                # Reasonable price range for cigars
                                if 5 <= price <= 2000:
                                    if is_original:
                                        if original_price is None or price > original_price:
                                            original_price = price
                                    else:
                                        if current_price is None or price > current_price:
                                            current_price = price
                            except ValueError:
                                continue
                
                # If we found a current price, stop searching
                if current_price is not None:
                    break
        
        # Calculate discount percentage
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock based on shipping availability"""
        
        # ABC Fine Wine & Spirits shows availability in the shipping section:
        # <span class="available">Available</span> for ground shipping = IN STOCK
        # <span class="unavailable">Unavailable</span> for ground shipping = OUT OF STOCK
        # IMPORTANT: They show BOTH spans but hide one with display:none
        
        # DEBUG: Check what we're finding
        debug_mode = True  # Set to True to see debug output
        
        def is_visible(element):
            """Check if element is visible (not display:none)"""
            style = element.get('style', '').lower().replace(' ', '')
            
            # Check for display:none (element is hidden)
            if 'display:none' in style:
                if debug_mode:
                    print(f"    [DEBUG] Element has display:none in style: {element.get('style', '')}")
                return False
            
            # Check for explicit display:block (element is visible)
            if 'display:block' in style:
                if debug_mode:
                    print(f"    [DEBUG] Element has display:block in style")
                return True
            
            # If no display style, assume visible
            return True
        
        # ABC Fine Wine & Spirits uses heavy JavaScript, so static HTML is unreliable
        # Last resort: check JSON-LD structured data for availability
        
        json_scripts = soup.find_all('script', type='application/ld+json')
        if debug_mode:
            print(f"  [DEBUG] Found {len(json_scripts)} JSON-LD scripts")
        
        for script in json_scripts:
            try:
                import json
                data = json.loads(script.string)
                if debug_mode:
                    print(f"  [DEBUG] Checking JSON-LD data...")
                
                # Check for Product schema with offers
                if isinstance(data, dict):
                    offers = data.get('offers', {})
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    
                    availability = offers.get('availability', '')
                    if debug_mode:
                        print(f"    - Availability: {availability}")
                    
                    if availability:
                        # Check availability URL patterns
                        if 'instock' in availability.lower():
                            if debug_mode:
                                print("  [DEBUG] Returning True (JSON-LD shows InStock)")
                            return True
                        elif 'outofstock' in availability.lower() or 'soldout' in availability.lower():
                            if debug_mode:
                                print("  [DEBUG] Returning False (JSON-LD shows OutOfStock)")
                            return False
            except Exception as e:
                if debug_mode:
                    print(f"    - Error parsing JSON-LD: {e}")
                continue
        
        # Look for stock label elements - check the exact class name including __outstock
        stock_labels = soup.find_all(class_=lambda x: x and ('stocklabel' in str(x).lower() or 'productview-stocklabel' in str(x).lower()))
        
        if debug_mode:
            print(f"  [DEBUG] Found {len(stock_labels)} stock label elements")
        
        for label in stock_labels:
            classes = label.get('class', [])
            if debug_mode:
                print(f"    - Raw classes list: {classes}")
                print(f"    - Classes as string: {' '.join(classes)}")
                print(f"    - Text: {label.get_text().strip()}")
            
            # Check each class in the list
            for cls in classes:
                if debug_mode:
                    print(f"    - Checking class: '{cls}'")
                
                # Check for outstock indicator
                if 'outstock' in cls.lower():
                    if debug_mode:
                        print(f"  [DEBUG] Found outstock in class: {cls}")
                        print("  [DEBUG] Returning False (out of stock)")
                    return False
        
        # If we found stock labels but none had outstock, it's in stock
        if stock_labels:
            if debug_mode:
                print("  [DEBUG] Returning True (stock label found, no outstock class)")
            return True
        
        if debug_mode:
            print("  [DEBUG] No stock label elements found, checking other methods...")
        
        # Check for shipping availability spans
        available_shipping_span = soup.find('span', id='shipping-option-available-message')
        unavailable_shipping_span = soup.find('span', id='shipping-option-unavailable-message')
        
        if debug_mode:
            print(f"  [DEBUG] Shipping availability spans found:")
            print(f"    - Available span exists: {available_shipping_span is not None}")
            print(f"    - Unavailable span exists: {unavailable_shipping_span is not None}")
        
        # Check for "ADD TO CART" button more carefully
        # Look specifically for button with exact text "ADD TO CART"
        all_buttons = soup.find_all('button')
        add_to_cart_found = False
        
        for button in all_buttons:
            button_text = button.get_text().strip().upper()
            if debug_mode and ('ADD' in button_text or 'CART' in button_text):
                print(f"  [DEBUG] Found button with relevant text: '{button_text}'")
            
            if button_text == 'ADD TO CART':
                add_to_cart_found = True
                is_disabled = button.get('disabled') is not None
                if debug_mode:
                    print(f"  [DEBUG] ADD TO CART button found, disabled: {is_disabled}")
                if not is_disabled:
                    if debug_mode:
                        print("  [DEBUG] Returning True (ADD TO CART button enabled)")
                    return True
                else:
                    if debug_mode:
                        print("  [DEBUG] Returning False (ADD TO CART button disabled)")
                    return False
        
        if debug_mode and not add_to_cart_found:
            print("  [DEBUG] No ADD TO CART button found")
        
        # If we can't determine, default to False (conservative)
        if debug_mode:
            print("  [DEBUG] No stock indicators found, defaulting to False")
        return False


def extract_abcfws_data(url: str) -> Dict:
    """
    Main extraction function for ABC Fine Wine & Spirits
    Compatible with CSV update workflow
    """
    extractor = ABCFWSExtractor()
    result = extractor.extract_product_data(url)
    
    return {
        'success': result['error'] is None,
        'price': result['box_price'], 
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'discount_percent': result['discount_percent'],
        'error': result['error']
    }


def test_extractor():
    """Test the extractor with multiple provided URLs"""
    
    test_cases = [
        {
            'url': "https://abcfws.com/cigars/padron-1964-anniversary-series-maduro-diplomatico-churchill/684271",
            'expected_price': 404.79,
            'expected_stock': True,
            'notes': "In stock, ground shipping available"
        },
        {
            'url': "https://abcfws.com/cigars/arturo-fuente-canones-natural/101770",
            'expected_price': 12.99,
            'expected_stock': False,
            'notes': "Out of stock, unavailable for ground shipping"
        },
        {
            'url': "https://abcfws.com/cigars/quorum-assorted-variety-toro-gift-bundle/787970",
            'expected_price': 29.99,
            'expected_stock': False,
            'notes': "Sale price $29.99 (was $39.99), out of stock"
        }
    ]
    
    print("Testing ABC Fine Wine & Spirits extraction...")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['url'].split('/')[-2].replace('-', ' ').title()}")
        print(f"Expected: ${test_case['expected_price']}, {'In Stock' if test_case['expected_stock'] else 'Out of Stock'}")
        print(f"Notes: {test_case['notes']}")
        print("-" * 40)
        
        result = extract_abcfws_data(test_case['url'])
        
        if result['error']:
            print(f"ERROR: {result['error']}")
        else:
            print("SUCCESS!")
            print(f"  Price: ${result['price']}")
            print(f"  In Stock: {result['in_stock']}")
            if result['discount_percent']:
                print(f"  Discount: {result['discount_percent']:.1f}% off")
            
            # Validation
            price_match = result['price'] == test_case['expected_price'] if result['price'] else False
            stock_match = result['in_stock'] == test_case['expected_stock']
            
            print(f"  Price Match: {'[PASS]' if price_match else '[FAIL]'}")
            print(f"  Stock Match: {'[PASS]' if stock_match else '[FAIL]'}")
            
            # Debug: show what text was found for stock detection
            if not stock_match:
                print(f"  [DEBUG] Expected stock: {test_case['expected_stock']}, Got: {result['in_stock']}")


if __name__ == "__main__":
    test_extractor()
