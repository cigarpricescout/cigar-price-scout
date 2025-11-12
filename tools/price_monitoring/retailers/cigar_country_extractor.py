#!/usr/bin/env python3
"""
Cigar Country Extractor - Updated with Proven Hiland's Methodology
Retailer-specific extraction rules for Cigar Country (WooCommerce platform)
Dominican Republic jurisdiction - Tier 1 compliance

Updated to use the exact same successful approach as Hiland's Cigars:
- Simple headers (just User-Agent)
- 1 request/second rate limiting
- Price range filtering (50-2000)
- Main product area focus
- Conservative approach
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class CigarCountryExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Exact same headers as successful Hiland's extractor
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
            'error': str or None
        }
        """
        try:
            # Rate limiting - 1 request per second (same as Hiland's)
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from product title or options
            box_qty = self._extract_box_quantity(soup)
            
            # Extract pricing information using proven Hiland's approach
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
        
        # Look in product title (WooCommerce typically uses h1.product_title or similar)
        title_selectors = ['h1.product_title', 'h1', '.product_title', '.product-title']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()
                # Common patterns: "Brand Line Vitola (Size / Box of XX)"
                qty_match = re.search(r'(?:\(\s*[\d\.x]+\s*/\s*)?box\s+of\s+(\d+)\)?', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty > 5:  # Filter out single quantities
                        return qty
                
                # Alternative patterns
                qty_match = re.search(r'(?:[\(\[]?)(\d+)(?:ct|[\)\]]?)', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty > 5:
                        return qty
        
        # Look in product description for "Packing" section (Cigar Country specific)
        packing_section = soup.find(string=re.compile(r'packing', re.I))
        if packing_section:
            parent = packing_section.find_parent()
            if parent:
                packing_text = parent.get_text()
                qty_match = re.search(r'box\s+of\s+(\d+)', packing_text, re.I)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty > 5:
                        return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract box price and discount percentage using proven Hiland's approach"""
        
        # Look for the main product price in the primary product information area
        main_product_area = soup.find(['div'], class_=re.compile(r'product-summary|summary|product-info|single-product', re.I))
        
        if main_product_area:
            # Look for price elements within the main product area only
            price_elements = main_product_area.find_all(['span', 'div'], class_=re.compile(r'woocommerce-Price-amount|amount|price'))
            
            current_prices = []
            original_prices = []
            
            for elem in price_elements:
                price_text = elem.get_text().strip()
                price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
                
                if price_match:
                    try:
                        price = float(price_match.group(1))
                        # Filter for box-level pricing (same as Hiland's: $50-$2000)
                        if 50 <= price <= 2000:
                            # Check if this is a strikethrough price
                            is_strikethrough = (
                                elem.find_parent(['del', 's']) or
                                (elem.has_attr('style') and 'line-through' in str(elem.get('style', '')))
                            )
                            
                            if is_strikethrough:
                                original_prices.append(price)
                            else:
                                current_prices.append(price)
                                
                    except ValueError:
                        continue
            
            # Select the best prices (same logic as Hiland's)
            current_price = max(current_prices) if current_prices else None
            original_price = max(original_prices) if original_prices else None
            
            # Calculate discount
            discount_percent = None
            if original_price and current_price and original_price > current_price:
                discount_percent = ((original_price - current_price) / original_price) * 100
            
            if current_price:
                return current_price, discount_percent
        
        # Fallback: Look for prices anywhere but be selective (same as Hiland's)
        all_price_elements = soup.find_all(['span', 'div'], class_=re.compile(r'woocommerce-Price-amount'))
        
        valid_prices = []
        for elem in all_price_elements:
            # Skip if in obviously unrelated sections
            parent_classes = []
            parent = elem.find_parent(['div', 'section'])
            if parent:
                parent_classes = ' '.join(parent.get('class', [])).lower()
                
            if any(skip in parent_classes for skip in ['related', 'upsell', 'cross-sell', 'widget', 'sidebar']):
                continue
                
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
            
            if price_match:
                try:
                    price = float(price_match.group(1))
                    # Only consider box-level prices (same range as Hiland's)
                    if 50 <= price <= 2000:
                        valid_prices.append(price)
                except ValueError:
                    continue
        
        if valid_prices:
            # Take the highest valid price as it's most likely the box price
            current_price = max(valid_prices)
            
            # Look for strikethrough prices for discount calculation
            original_price = None
            strikethrough_elems = soup.find_all(['del', 's'])
            for elem in strikethrough_elems:
                price_text = elem.get_text().strip()
                price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
                if price_match:
                    try:
                        price = float(price_match.group(1))
                        if 50 <= price <= 2000 and price > current_price:
                            original_price = price
                            break
                    except ValueError:
                        continue
            
            discount_percent = None
            if original_price and original_price > current_price:
                discount_percent = ((original_price - current_price) / original_price) * 100
            
            return current_price, discount_percent
        
        return None, None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock based on button text and stock indicators"""
        
        # Look for add to cart button (WooCommerce patterns)
        add_to_cart = soup.find(['button', 'input'], attrs={
            'class': re.compile(r'add.*cart|cart.*add|single_add_to_cart_button', re.I),
            'type': re.compile(r'submit|button', re.I)
        })
        
        if add_to_cart:
            button_text = add_to_cart.get_text().strip().upper()
            # In stock indicators
            if any(phrase in button_text for phrase in ['ADD TO CART', 'BUY NOW', 'PURCHASE']):
                return True
            # Out of stock indicators
            if any(phrase in button_text for phrase in ['NOTIFY ME', 'SOLD OUT', 'OUT OF STOCK']):
                return False
        
        # Look for explicit stock status text
        stock_indicators = soup.find_all(string=re.compile(r'(?:only\s+\d+\s+left|in\s+stock|out\s+of\s+stock|sold\s+out)', re.I))
        for indicator in stock_indicators:
            text = indicator.strip().upper()
            if any(phrase in text for phrase in ['IN STOCK', 'LEFT IN STOCK']):
                return True
            if any(phrase in text for phrase in ['OUT OF STOCK', 'SOLD OUT']):
                return False
        
        # Default to True if we can't determine (conservative approach, same as Hiland's)
        return True


def extract_cigar_country_data(url: str) -> Dict:
    """
    Main extraction function for Cigar Country
    Compatible with CSV update workflow - same format as Hiland's
    """
    extractor = CigarCountryExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to the expected format (matching other extractors)
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
    """Test the extractor with sample Cigar Country URLs"""
    
    # Test URLs - Cigar Country product for testing
    test_urls = [
        'https://cigarcountry.com/product/perdomo-reserve-10th-anniversary-champagne-connecticut-epicure/',
    ]
    
    if not test_urls or not any(test_urls):
        print("No test URLs provided. Add actual Cigar Country product URLs to test.")
        return
    
    print("Testing Cigar Country extraction...")
    print("=" * 50)
    
    for i, url in enumerate(test_urls):
        if url:  # Only test non-empty URLs
            print(f"\nTest {i+1}: {url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]}")
            print("-" * 40)
            result = extract_cigar_country_data(url)
            
            if result['error']:
                print(f"ERROR: {result['error']}")
                if '403' in str(result['error']):
                    print("  This suggests bot detection - may work better in production environment")
            else:
                print(f"SUCCESS!")
                print(f"  Price: ${result['price']}")
                print(f"  Box Qty: {result['box_quantity']}")
                print(f"  In Stock: {result['in_stock']}")
                if result['discount_percent']:
                    print(f"  Discount: {result['discount_percent']:.1f}% off")

if __name__ == "__main__":
    test_extractor()
