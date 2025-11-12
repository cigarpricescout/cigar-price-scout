#!/usr/bin/env python3
"""
Hiland's Cigars Extractor
Following the exact same pattern as the working Atlantic Cigar extractor
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class HilandsCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Exact same headers as Atlantic extractor
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Hiland's Cigars URL
        Returns: {
            'box_price': float or None,
            'box_qty': int or None,
            'in_stock': bool,
            'discount_percent': float or None,
            'error': str or None
        }
        """
        try:
            # Rate limiting - 1 request per second (same as Atlantic)
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from product title or options
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
        
        # Look in product title (WooCommerce typically uses h1.product_title or similar)
        title_selectors = ['h1.product_title', 'h1', '.product_title', '.product-title']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()
                # Hiland's specific pattern: "Brand Line Vitola (Size / Box of XX)"
                qty_match = re.search(r'(?:\(\s*[\d\.x]+\s*/\s*)?box\s+of\s+(\d+)\)?', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty > 5:  # Filter out single quantities
                        return qty
                
                # Cube pattern (for Cubanitos)
                qty_match = re.search(r'(?:\(\s*[\d\.x]+\s*/\s*)?cube\s+of\s+(\d+)\)?', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty > 5:
                        return qty
                
                # Fallback patterns
                qty_match = re.search(r'(?:[\(\[]?)(\d+)(?:ct|[\)\]]?)', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty > 5:
                        return qty
        
        # Check URL for quantity patterns (like cube-of-100)
        # Get current URL from the page if possible
        canonical_link = soup.find('link', rel='canonical')
        current_url = canonical_link['href'] if canonical_link else ''
        
        url_patterns = [
            r'cube-of-(\d+)',
            r'box-of-(\d+)', 
            r'pack-of-(\d+)'
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, current_url, re.I)
            if match:
                qty = int(match.group(1))
                if qty > 5:
                    return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract box price and discount percentage"""
        
        # Look for the main product price in the primary product information area
        # This is usually in a div with the product summary/details
        
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
                        # Filter for box-level pricing (typically $50-$2000 range)
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
            
            # Select the best prices
            current_price = max(current_prices) if current_prices else None
            original_price = max(original_prices) if original_prices else None
            
            # Calculate discount
            discount_percent = None
            if original_price and current_price and original_price > current_price:
                discount_percent = ((original_price - current_price) / original_price) * 100
            
            if current_price:
                return current_price, discount_percent
        
        # Fallback: Look for prices anywhere but be more selective
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
                    # Only consider box-level prices
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
        """Check if product is in stock based on button text"""
        
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
            # Out of stock indicators (Hiland's specific)  
            if any(phrase in button_text for phrase in ['EMAIL WHEN STOCK AVAILABLE', 'NOTIFY ME', 'SOLD OUT', 'OUT OF STOCK', 'SUBSCRIBE NOW']):
                return False
        
        # Look for explicit stock status text (Hiland's pattern: "Out of stock")
        stock_indicators = soup.find_all(string=re.compile(r'(?:in\s+stock|out\s+of\s+stock|sold\s+out|notify\s+me)', re.I))
        for indicator in stock_indicators:
            text = indicator.strip().upper()
            if 'IN STOCK' in text:
                return True
            if any(phrase in text for phrase in ['OUT OF STOCK', 'SOLD OUT', 'NOTIFY ME']):
                return False
        
        # Look for availability class names or explicit "Out of stock" text
        avail_elems = soup.find_all(['span', 'div', 'p'], string=re.compile(r'out\s+of\s+stock', re.I))
        if avail_elems:
            return False
        
        # Default to True if we can't determine (conservative approach)
        return True


def extract_hilands_cigars_data(url: str) -> Dict:
    """
    Main extraction function for Hiland's Cigars
    Compatible with your CSV update workflow
    """
    extractor = HilandsCigarsExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to the expected format (matching Atlantic extractor output)
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
    
    # Test URLs based on the search results we found
    test_urls = [
        'https://www.hilandscigars.com/shop/cigars/arturo-fuente/a-fuente-don-carlos/don-carlos-robusto/',
        'https://www.hilandscigars.com/shop/cigars/arturo-fuente/fuente-y-padron-legends-collaboration-7x50-box-of-40/',
        'https://www.hilandscigars.com/shop/cigars/arturo-fuente/a-fuente-gran-reserva/arturo-fuente-cubanitos/',
    ]
    
    print("Testing Hiland's Cigars extraction...")
    print("=" * 50)
    
    for i, url in enumerate(test_urls):
        print(f"\nTest {i+1}: {url.split('/')[-2]}")
        print("-" * 40)
        result = extract_hilands_cigars_data(url)
        
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
