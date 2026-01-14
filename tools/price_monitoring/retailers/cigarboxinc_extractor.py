#!/usr/bin/env python3
"""
CigarBoxInc Extractor
Clean, modern e-commerce site with clear pricing and stock indicators
Based on screenshots showing straightforward product structure
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class CigarBoxIncExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Minimal headers - proven approach
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from CigarBoxInc URL
        Returns: {
            'box_price': float or None,
            'box_qty': int or None,
            'in_stock': bool,
            'discount_percent': float or None,
            'error': str or None
        }
        """
        try:
            # Conservative rate limiting - 1 request per second
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from product description
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
        """Extract box quantity from product description or specs"""
        
        # Priority 1: Look for "Box of XX Cigars" in product specs (from screenshots)
        specs_text = soup.get_text()
        
        # CigarBoxInc specific patterns from screenshots
        qty_patterns = [
            r'box\s+of\s+(\d+)\s+cigars?',  # "Box of 25 Cigars"
            r'box\s+of\s+(\d+)',            # "Box of 20"
            r'(\d+)\s+cigars?\s+per\s+box', # "25 cigars per box"
            r'(\d+)ct\s+box',               # "25ct box"
        ]
        
        for pattern in qty_patterns:
            qty_match = re.search(pattern, specs_text, re.I)
            if qty_match:
                qty = int(qty_match.group(1))
                if qty >= 5:  # Filter out single quantities
                    return qty
        
        # Priority 2: Look in product title or breadcrumbs
        title_selectors = ['h1', '.product-title', '.page-title']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()
                for pattern in qty_patterns:
                    qty_match = re.search(pattern, title, re.I)
                    if qty_match:
                        qty = int(qty_match.group(1))
                        if qty >= 5:
                            return qty
        
        # Priority 3: Check URL for quantity indicators
        url_patterns = [r'(\d+)-pack', r'box-(\d+)', r'(\d+)ct']
        for pattern in url_patterns:
            match = re.search(pattern, url, re.I)
            if match:
                qty = int(match.group(1))
                if qty >= 5:
                    return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract current price - final optimized version focusing on main product price"""
        
        current_price = None
        original_price = None
        
        # Priority 1: Look for main product price in primary price containers
        main_price_selectors = [
            '.product-price',
            '.price',
            '.current-price',
            '.sale-price',
            'h2 + .price',  # Price immediately after product title
            '[class*="product"] .price'
        ]
        
        primary_prices = []
        for selector in main_price_selectors:
            price_elems = soup.select(selector)
            for elem in price_elems[:2]:  # Only check first 2 matches to avoid related products
                # Skip if inside navigation or sidebar
                if elem.find_parent(['nav', 'aside', '.sidebar', '.related', '.recommended']):
                    continue
                    
                price_text = elem.get_text().strip()
                price_match = re.search(r'\$(\d{1,4}(?:\.\d{2})?)', price_text)
                
                if price_match:
                    try:
                        price = float(price_match.group(1))
                        if 100 <= price <= 2000:  # Focus on main product price range
                            primary_prices.append(price)
                    except ValueError:
                        continue
        
        # Priority 2: Look for strikethrough prices (original/MSRP)
        strikethrough_prices = []
        for elem in soup.select('del, s, .original-price, .regular-price'):
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$(\d{1,4}(?:\.\d{2})?)', price_text)
            
            if price_match:
                try:
                    price = float(price_match.group(1))
                    if 100 <= price <= 2000:
                        strikethrough_prices.append(price)
                except ValueError:
                    continue
        
        # Priority 3: Logic to select correct prices
        if primary_prices:
            unique_primary = sorted(list(set(primary_prices)))
            
            if strikethrough_prices:
                # We have both current and original
                original_price = max(strikethrough_prices)
                current_candidates = [p for p in unique_primary if p < original_price]
                current_price = min(current_candidates) if current_candidates else max(unique_primary)
            else:
                # Only primary prices - select the most prominent one
                if len(unique_primary) == 1:
                    current_price = unique_primary[0]
                else:
                    # Multiple prices - use the highest as it's likely the main product price
                    # (Lower prices might be related products or smaller quantities)
                    current_price = max(unique_primary)
        
        # Priority 4: Fallback to text extraction but be more selective
        if not current_price:
            # Look for prices in the main content area only
            main_content = soup.find(['main', '.main', '#main', '.content', '.product-details'])
            if main_content:
                content_text = main_content.get_text()
            else:
                content_text = soup.get_text()
            
            all_prices = re.findall(r'\$(\d{1,4}(?:\.\d{2})?)', content_text)
            valid_prices = []
            
            for price_str in all_prices[:5]:  # Only check first 5 prices found
                try:
                    price = float(price_str)
                    if 200 <= price <= 2000:  # Higher threshold to avoid small prices
                        valid_prices.append(price)
                except ValueError:
                    continue
            
            if valid_prices:
                # Take the highest price as it's likely the main product
                current_price = max(valid_prices)
        
        # Calculate discount percentage
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock - look for explicit text first"""
        
        page_text = soup.get_text().lower()
        
        # Priority 1: Look for explicit stock text (as you mentioned: "pages literally say in stock or out of stock")
        if 'in stock' in page_text:
            return True
        
        if 'out of stock' in page_text:
            return False
        
        # Priority 2: Look for stock quantity indicators  
        stock_qty_match = re.search(r'(\d+)\s+in\s+stock', page_text)
        if stock_qty_match:
            return True
        
        # Priority 3: Other out of stock indicators
        out_of_stock_phrases = ['sold out', 'unavailable', 'temporarily unavailable']
        for phrase in out_of_stock_phrases:
            if phrase in page_text:
                return False
        
        # Priority 4: Check for add to cart functionality as backup
        add_to_cart_button = soup.find(['button', 'input'], string=re.compile(r'add.*cart', re.I))
        if add_to_cart_button:
            is_disabled = add_to_cart_button.get('disabled') is not None
            if not is_disabled:
                return True
        
        # Default: if we have a price but no explicit indicators, assume in stock
        has_price = bool(re.search(r'\$\d+', page_text))
        return has_price


def extract_cigarboxinc_data(url: str) -> Dict:
    """
    Main extraction function for CigarBoxInc
    Compatible with CSV update workflow
    """
    extractor = CigarBoxIncExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to expected format
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
    """Test the extractor with the provided URLs"""
    
    test_urls = [
        'https://www.cigarboxinc.com/product/arturo-fuente-hemingway-short-story-4-x-42-49-natural/',  # $160, Box of 25, in stock
        'https://www.cigarboxinc.com/product/arturo-fuente-opus-x-double-corona-758-49/',             # $1000, out of stock  
        'https://www.cigarboxinc.com/product/arturo-fuente-double-chateau-6-34-50-natural/',          # $121 (was $141), Box of 20, in stock
    ]
    
    print("Testing CigarBoxInc extraction...")
    print("=" * 60)
    
    for i, url in enumerate(test_urls):
        product_name = url.split('/')[-2].replace('-', ' ').title()
        print(f"\nTest {i+1}: {product_name}")
        print("-" * 40)
        result = extract_cigarboxinc_data(url)
        
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
