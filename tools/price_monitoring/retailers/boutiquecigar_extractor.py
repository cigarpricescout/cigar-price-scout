#!/usr/bin/env python3
"""
BoutiqueCigar.com Extractor
Handles dynamic dropdown menus with JavaScript-based price changes
Extracts multiple variants when available (Natural/Maduro, different sizes, etc.)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import json
from typing import Dict, Optional, List, Tuple

class BoutiqueCigarExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Minimal headers - just User-Agent (your proven approach)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from BoutiqueCigar.com URL
        Handles dynamic dropdowns and multiple variants
        Returns: {
            'box_price': float or None,
            'box_qty': int or None, 
            'in_stock': bool,
            'discount_percent': float or None,
            'variants': list of variant data,
            'error': str or None
        }
        """
        try:
            # Conservative rate limiting - Holt's approach (3 seconds)
            time.sleep(3)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract main price and quantity
            box_price, discount_percent = self._extract_pricing(soup)
            box_qty = self._extract_box_quantity(soup)
            in_stock = self._check_stock_status(soup)
            
            # Extract variant information from dropdowns
            variants = self._extract_variants(soup)
            
            return {
                'box_price': box_price,
                'box_qty': box_qty,
                'in_stock': in_stock,
                'discount_percent': discount_percent,
                'variants': variants,
                'error': None
            }
            
        except Exception as e:
            return {
                'box_price': None,
                'box_qty': None,
                'in_stock': False,
                'discount_percent': None,
                'variants': [],
                'error': str(e)
            }
    
    def _extract_box_quantity(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract box quantity from dropdown or product info"""
        
        # Priority 1: Look for quantity dropdown (from screenshots)
        quantity_selectors = [
            'select[name*="quantity"] option',
            'select[data-attribute_name="quantity"] option',
            '.quantity select option',
            '.product-quantity select option'
        ]
        
        for selector in quantity_selectors:
            options = soup.select(selector)
            for option in options:
                option_text = option.get_text().strip()
                # Look for "Box of XX" pattern
                qty_match = re.search(r'box\s+of\s+(\d+)', option_text, re.I)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 5:
                        return qty
                
                # Look for "XX-Pack" pattern  
                pack_match = re.search(r'(\d+)-pack', option_text, re.I)
                if pack_match:
                    qty = int(pack_match.group(1))
                    if qty >= 5:
                        return qty
        
        # Priority 2: Look in product title or description
        title_elem = soup.find(['h1', '.product_title', '.product-title'])
        if title_elem:
            title_text = title_elem.get_text()
            qty_match = re.search(r'box\s+of\s+(\d+)', title_text, re.I)
            if qty_match:
                return int(qty_match.group(1))
            
            pack_match = re.search(r'(\d+)-pack', title_text, re.I)
            if pack_match:
                return int(pack_match.group(1))
        
        # Priority 3: Look in size dropdown for quantity info
        size_selectors = [
            'select[data-attribute_name="size"] option',
            'select[name*="size"] option',
            '.size select option'
        ]
        
        for selector in size_selectors:
            options = soup.select(selector)
            for option in options:
                option_text = option.get_text().strip()
                qty_match = re.search(r'box\s+of\s+(\d+)', option_text, re.I)
                if qty_match:
                    return int(qty_match.group(1))
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract pricing information including discounts"""
        
        current_prices = []
        original_prices = []
        
        # Priority 1: Look for main price display area
        price_selectors = [
            '.price .woocommerce-Price-amount',
            '.product-price .amount',
            '.price .amount',
            '.woocommerce-Price-amount',
            '.price-current',
            'span.price'
        ]
        
        for selector in price_selectors:
            price_elems = soup.select(selector)
            for elem in price_elems:
                price_text = elem.get_text().strip()
                price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', price_text)
                
                if price_match:
                    try:
                        price_str = price_match.group(1).replace(',', '')
                        price = float(price_str)
                        
                        # Filter for realistic cigar pricing
                        if 50 <= price <= 2000:
                            # Check if this is a strikethrough price (original price)
                            parent_elem = elem.find_parent(['del', 's'])
                            has_strikethrough = parent_elem is not None
                            
                            if has_strikethrough:
                                original_prices.append(price)
                            else:
                                current_prices.append(price)
                                
                    except ValueError:
                        continue
        
        # Priority 2: Look for JSON-LD structured data (common in WooCommerce)
        json_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and 'offers' in data:
                    offer = data['offers']
                    if isinstance(offer, dict) and 'price' in offer:
                        price = float(offer['price'])
                        if 50 <= price <= 2000:
                            current_prices.append(price)
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
        
        # Remove duplicates and select best prices
        current_prices = list(set(current_prices))
        original_prices = list(set(original_prices))
        
        # Select the highest current price (most specific/complete price)
        current_price = max(current_prices) if current_prices else None
        original_price = max(original_prices) if original_prices else None
        
        # Calculate discount
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock"""
        
        # Priority 1: Look for explicit stock indicators
        stock_text_indicators = [
            'in stock',
            'out of stock', 
            'sold out',
            'available',
            'unavailable'
        ]
        
        page_text = soup.get_text().lower()
        
        # Check for specific stock quantities (like "3 in stock")
        stock_qty_match = re.search(r'(\d+)\s+in\s+stock', page_text)
        if stock_qty_match:
            return True
        
        # Check for out of stock indicators
        if 'out of stock' in page_text or 'sold out' in page_text:
            return False
        
        # Priority 2: Look for add to cart button
        add_to_cart_buttons = soup.find_all(['button', 'input'], string=re.compile(r'add.*cart', re.I))
        for button in add_to_cart_buttons:
            if not button.get('disabled'):
                return True
        
        # Priority 3: Check button classes and attributes
        cart_buttons = soup.select('button[name="add-to-cart"], .add_to_cart_button, .single_add_to_cart_button')
        for button in cart_buttons:
            button_text = button.get_text().strip().lower()
            if 'add to cart' in button_text and not button.get('disabled'):
                return True
            if 'out of stock' in button_text or 'sold out' in button_text:
                return False
        
        # Priority 4: Look for stock status in product meta
        stock_elements = soup.find_all(['span', 'div', 'p'], class_=re.compile(r'stock', re.I))
        for elem in stock_elements:
            elem_text = elem.get_text().lower()
            if 'out of stock' in elem_text:
                return False
            if 'in stock' in elem_text:
                return True
        
        # Default to in stock if we found a price but no clear stock indicators
        return True
    
    def _extract_variants(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract variant information from dropdowns"""
        variants = []
        
        # Look for wrapper/size/quantity dropdown options
        dropdown_selectors = [
            ('wrapper', 'select[data-attribute_name="wrapper"] option'),
            ('size', 'select[data-attribute_name="size"] option'), 
            ('quantity', 'select[data-attribute_name="quantity"] option'),
            ('pa_wrapper', 'select[name="attribute_pa_wrapper"] option'),
            ('pa_size', 'select[name="attribute_pa_size"] option')
        ]
        
        for variant_type, selector in dropdown_selectors:
            options = soup.select(selector)
            if options:
                variant_options = []
                for option in options:
                    option_text = option.get_text().strip()
                    option_value = option.get('value', '')
                    
                    # Skip empty or "Choose an option" entries
                    if option_text and option_value and 'choose' not in option_text.lower():
                        variant_options.append({
                            'text': option_text,
                            'value': option_value
                        })
                
                if variant_options:
                    variants.append({
                        'type': variant_type,
                        'options': variant_options
                    })
        
        return variants


def extract_boutiquecigar_data(url: str) -> Dict:
    """
    Main extraction function for BoutiqueCigar.com
    Compatible with CSV update workflow
    """
    extractor = BoutiqueCigarExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to expected format
    return {
        'success': result['error'] is None,
        'price': result['box_price'], 
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'discount_percent': result['discount_percent'],
        'variants': result['variants'],
        'error': result['error']
    }


# Test function for development
def test_extractor():
    """Test the extractor with the provided URLs"""
    
    test_urls = [
        'https://boutiquecigar.com/product/padron-1964-anniversary-principe-natural-maduro/',  # Natural/Maduro both $290, Box of 25
        'https://boutiquecigar.com/product/arturo-fuente-hemingway-short-stor/',                # Box of 25, $160, in stock
        'https://boutiquecigar.com/product/perdomo-10th-anniversary-champagne/',               # Box of 25, Epicure size
        'https://boutiquecigar.com/product/arturo-fuente-rare-pink-vintage-1960s-series-signature-5-pack/',  # 5-pack, one price
        'https://boutiquecigar.com/product/padron-60th-anniversary/',                          # Box of 10, $675, out of stock
    ]
    
    print("Testing BoutiqueCigar.com extraction...")
    print("=" * 70)
    
    for i, url in enumerate(test_urls):
        product_name = url.split('/')[-2].replace('-', ' ').title()
        print(f"\nTest {i+1}: {product_name}")
        print("-" * 50)
        result = extract_boutiquecigar_data(url)
        
        if result['error']:
            print(f"ERROR: {result['error']}")
        else:
            print(f"SUCCESS!")
            print(f"  Price: ${result['price']}")
            print(f"  Box Qty: {result['box_quantity']}")
            print(f"  In Stock: {result['in_stock']}")
            if result['discount_percent']:
                print(f"  Discount: {result['discount_percent']:.1f}% off")
            
            # Show variants if found
            if result['variants']:
                print(f"  Variants found:")
                for variant in result['variants']:
                    variant_options = [opt['text'] for opt in variant['options'][:3]]  # Show first 3
                    options_text = ', '.join(variant_options)
                    if len(variant['options']) > 3:
                        options_text += f" (+{len(variant['options'])-3} more)"
                    print(f"    {variant['type'].title()}: {options_text}")

if __name__ == "__main__":
    test_extractor()
