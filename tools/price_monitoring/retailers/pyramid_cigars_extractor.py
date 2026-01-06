#!/usr/bin/env python3
"""
Pyramid Cigars Extractor
Following the exact same pattern as the working Absolute Cigars extractor
Retailer - Shopify Platform
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class PyramidCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Exact same headers as proven extractors
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Pyramid Cigars URL
        Returns: {
            'box_price': float or None,
            'box_qty': int or None,
            'in_stock': bool,
            'discount_percent': float or None,
            'error': str or None
        }
        """
        try:
            # Rate limiting - 1 request per second (proven effective)
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from COUNT dropdown options
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
        """Extract box quantity from COUNT dropdown options"""
        
        # Priority 1: Look for COUNT dropdown with "Box of XX" options (from screenshots)
        count_section = soup.find(['div', 'fieldset'], string=re.compile(r'count', re.I))
        if count_section:
            parent = count_section.find_parent(['div', 'fieldset'])
            if parent:
                box_options = parent.find_all(['option', 'label', 'span'], string=re.compile(r'box\s+of\s+(\d+)', re.I))
                for option in box_options:
                    qty_match = re.search(r'box\s+of\s+(\d+)', option.get_text(), re.I)
                    if qty_match:
                        qty = int(qty_match.group(1))
                        if qty >= 5:  # Filter out single quantities
                            return qty
        
        # Priority 2: Look for any "Box of XX" text in variant options
        variant_options = soup.find_all(['option', 'button', 'label'], string=re.compile(r'box\s+of\s+\d+', re.I))
        for option in variant_options:
            option_text = option.get_text().strip()
            qty_match = re.search(r'box\s+of\s+(\d+)', option_text, re.I)
            if qty_match:
                qty = int(qty_match.group(1))
                if qty >= 5:
                    return qty
        
        # Priority 3: Look for COUNT or variant selectors
        selectors = [
            'select[data-option-index="0"] option',
            '.product-form__variants option',
            '.variant-input option',
            'input[name="id"] + label',
            '[class*="variant"] option'
        ]
        
        for selector in selectors:
            options = soup.select(selector)
            for option in options:
                option_text = option.get_text().strip()
                # Look for "Box of XX" pattern
                qty_match = re.search(r'box\s+of\s+(\d+)', option_text, re.I)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 5:
                        return qty
                
                # Alternative patterns
                qty_match = re.search(r'(\d+)\s*ct\b', option_text, re.I)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 5:
                        return qty
        
        # Priority 4: Check product title for box quantity
        title_selectors = ['h1.product__title', 'h1', '.product-title', '.product__title']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()
                qty_match = re.search(r'box\s+of\s+(\d+)', title, re.I)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 5:
                        return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract box price and discount percentage"""
        
        # Look for main product pricing area (Shopify pattern)
        price_section = soup.find(['div'], class_=re.compile(r'price|product.*price', re.I))
        
        current_prices = []
        original_prices = []
        
        if price_section:
            # Look for price elements in Shopify format
            price_elements = price_section.find_all(['span', 'div'], class_=re.compile(r'price|money', re.I))
            
            for elem in price_elements:
                price_text = elem.get_text().strip()
                # Handle prices like $344.99, $199.99, $219.99
                price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', price_text)
                
                if price_match:
                    try:
                        price_str = price_match.group(1).replace(',', '')
                        price = float(price_str)
                        # Filter for cigar box pricing range
                        if 100 <= price <= 2000:
                            # Check for sale pricing indicators
                            parent_classes = ' '.join(elem.get('class', []))
                            is_original = (
                                'compare' in parent_classes.lower() or
                                'was' in parent_classes.lower() or
                                elem.find_parent(['s', 'del']) or
                                'line-through' in str(elem.get('style', ''))
                            )
                            
                            if is_original:
                                original_prices.append(price)
                            else:
                                current_prices.append(price)
                                
                    except ValueError:
                        continue
        
        # Also look for prices in meta tags or JSON-LD (common in Shopify)
        meta_price = soup.find('meta', {'property': 'product:price:amount'})
        if meta_price and meta_price.get('content'):
            try:
                price = float(meta_price.get('content'))
                if 100 <= price <= 2000:
                    current_prices.append(price)
            except ValueError:
                pass
        
        # Remove duplicates and select best prices
        current_prices = list(set(current_prices))
        original_prices = list(set(original_prices))
        
        # Select price logic
        current_price = max(current_prices) if current_prices else None
        original_price = max(original_prices) if original_prices else None
        
        # Calculate discount
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        if current_price:
            return current_price, discount_percent
        
        # Fallback: Look for any price in page text
        page_text = soup.get_text()
        all_prices = re.findall(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', page_text)
        
        valid_prices = []
        for price_str in all_prices:
            try:
                clean_price = float(price_str.replace(',', ''))
                if 100 <= clean_price <= 2000:  # Cigar box range
                    valid_prices.append(clean_price)
            except ValueError:
                continue
        
        if valid_prices:
            # For fallback, assume the highest price in range is the current price
            return max(valid_prices), None
        
        return None, None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock based on Pyramid Cigars patterns"""
        
        # Priority 1: Look for "Only X in stock" pattern (from screenshots)
        page_text = soup.get_text()
        
        # Check for "Only X in stock" pattern
        only_stock_match = re.search(r'only\s+\d+\s+in\s+stock', page_text, re.I)
        if only_stock_match:
            return True
        
        # Check for explicit "Out of stock"
        if re.search(r'out\s+of\s+stock', page_text, re.I):
            return False
        
        # Priority 2: Look for stock status elements with more specific selectors
        stock_selectors = [
            '.product__inventory',
            '.inventory',
            '.stock-level',
            '[class*="stock"]',
            '[class*="inventory"]'
        ]
        
        for selector in stock_selectors:
            stock_elem = soup.select_one(selector)
            if stock_elem:
                stock_text = stock_elem.get_text().strip().upper()
                
                # In stock indicators
                if re.search(r'only\s+\d+\s+in\s+stock', stock_text, re.I):
                    return True
                if any(phrase in stock_text for phrase in ['IN STOCK', 'AVAILABLE']):
                    return True
                
                # Out of stock indicators
                if 'OUT OF STOCK' in stock_text:
                    return False
        
        # Priority 3: Check button state and text
        add_button = soup.find(['button', 'input'], class_=re.compile(r'add.*cart|btn.*add|product.*add', re.I))
        
        if add_button:
            button_text = add_button.get_text().strip().upper()
            button_disabled = add_button.get('disabled') is not None
            
            # Strong in-stock indicators
            if 'ADD TO CART' in button_text and not button_disabled:
                return True
            
            # Strong out-of-stock indicators
            if any(phrase in button_text for phrase in ['SOLD OUT', 'NOTIFY ME', 'OUT OF STOCK']):
                return False
            
            if button_disabled:
                return False
        
        # Priority 4: Look for "Sold out" button specifically
        sold_out_button = soup.find(['button'], string=re.compile(r'sold\s+out', re.I))
        if sold_out_button:
            return False
        
        # Priority 5: Look for notify button (NOTIFY ME WHEN IN STOCK)
        notify_button = soup.find(['button', 'a'], string=re.compile(r'notify.*when.*stock', re.I))
        if notify_button:
            return False
        
        # Priority 6: Look for specific out-of-stock patterns in page text
        if 'SOLD OUT' in page_text.upper():
            return False
        
        # Priority 7: If we found a price and no clear out-of-stock indicators, assume in stock
        has_price = bool(re.search(r'\$\d+', page_text))
        return has_price


def extract_pyramid_cigars_data(url: str) -> Dict:
    """
    Main extraction function for Pyramid Cigars
    Compatible with CSV update workflow
    """
    extractor = PyramidCigarsExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to expected format (matching proven extractor output)
    return {
        'success': result['error'] is None,
        'price': result['box_price'], 
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'discount_percent': result['discount_percent'],
        'error': result['error']
    }


# Test function for development
def test_extractor():
    """Test the extractor with sample URLs"""
    
    # Test URLs from the screenshots
    test_urls = [
        'https://pyramidcigars.com/products/padron-1964-principe-maduro?_pos=2&_sid=0124eaec3&_ss=r',  # Box of 25, $344.99, in stock
        'https://pyramidcigars.com/products/cao-flathead-v660-carb?variant=45271346446617',            # Box of 24, $199.99 (was $239.99), in stock
        'https://pyramidcigars.com/products/my-father-judge-gran-robusto?variant=45232830939417',      # Box of 23, $219.99, out of stock
    ]
    
    print("Testing Pyramid Cigars extraction...")
    print("=" * 50)
    
    for i, url in enumerate(test_urls):
        print(f"\nTest {i+1}: {url.split('/')[-1].split('?')[0]}")
        print("-" * 40)
        result = extract_pyramid_cigars_data(url)
        
        if result['error']:
            print(f"ERROR: {result['error']}")
        else:
            print(f"SUCCESS!")
            print(f"  Price: ${result['price']}")
            print(f"  Box Qty: {result['box_quantity']}")
            print(f"  In Stock: {result['in_stock']}")
            if result['discount_percent']:
                print(f"  Discount: {result['discount_percent']:.1f}% off")

if __name__ == "__main__":
    test_extractor()
