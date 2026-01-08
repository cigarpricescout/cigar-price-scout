#!/usr/bin/env python3
"""
CigarBoxPA Extractor
Clean e-commerce site with explicit stock indicators and clear pricing structure
Based on screenshots showing very straightforward data presentation
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class CigarBoxPAExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Minimal headers - proven approach
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from CigarBoxPA URL
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
        """Extract box quantity from product title and description"""
        
        # Priority 1: Look in main product title (very explicit in screenshots)
        title_selectors = ['h1', '.product-title', '.page-title', 'h2']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title_text = title_elem.get_text().strip()
                
                # CigarBoxPA specific patterns from screenshots
                qty_patterns = [
                    r'box\s+of\s+(\d+)',           # "Box of 25"
                    r'pack\s+of\s+(\d+)',          # "Pack of 2 Cigars"
                    r'(\d+)\s+cigars?',            # "25 Cigars"
                    r'(\d+)ct',                    # "25ct"
                    r'(\d+)-pack',                 # "25-pack"
                ]
                
                for pattern in qty_patterns:
                    qty_match = re.search(pattern, title_text, re.I)
                    if qty_match:
                        qty = int(qty_match.group(1))
                        if qty >= 2:  # Allow packs of 2 or more
                            return qty
        
        # Priority 2: Look in breadcrumbs or page text
        page_text = soup.get_text()
        for pattern in [r'box\s+of\s+(\d+)', r'pack\s+of\s+(\d+)']:
            qty_match = re.search(pattern, page_text, re.I)
            if qty_match:
                qty = int(qty_match.group(1))
                if qty >= 2:
                    return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract current price - simplified approach focused on main display price"""
        
        current_price = None
        original_price = None
        
        # Priority 1: Look for data-price attributes first (most reliable)
        data_price_elems = soup.find_all(attrs={'data-price': True})
        for elem in data_price_elems:
            data_price = elem.get('data-price')
            if data_price:
                try:
                    price = float(data_price)
                    if 20 <= price <= 1000:
                        current_price = price
                        break  # Use first valid data-price found
                except ValueError:
                    continue
        
        # Priority 2: If no data-price, look for main price elements
        if not current_price:
            main_price_selectors = [
                'span.price.bold',      # From HTML: span class="price bold fz-120"
                '.price:not(del):not(s)',
                '.product-price:not(del):not(s)', 
                '.current-price',
                '.sale-price'
            ]
            
            for selector in main_price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem and not price_elem.find_parent(['del', 's']):
                    price_text = price_elem.get_text().strip()
                    price_match = re.search(r'\$?(\d{1,4}(?:\.\d{2})?)', price_text)
                    
                    if price_match:
                        try:
                            price = float(price_match.group(1))
                            if 20 <= price <= 1000:
                                current_price = price
                                break
                        except ValueError:
                            continue
        
        # Priority 3: Look for strikethrough prices (originals)
        strikethrough_elems = soup.select('del, s')
        for elem in strikethrough_elems:
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$(\d{1,4}(?:\.\d{2})?)', price_text)
            
            if price_match:
                try:
                    price = float(price_match.group(1))
                    if 20 <= price <= 1000:
                        original_price = price
                        break  # Use first valid strikethrough price
                except ValueError:
                    continue
        
        # Priority 4: Final fallback - find highest reasonable price on page
        if not current_price:
            page_text = soup.get_text()
            all_prices = re.findall(r'\$(\d{1,4}(?:\.\d{2})?)', page_text)
            
            valid_prices = []
            for price_str in all_prices:
                try:
                    price = float(price_str)
                    if 100 <= price <= 500:  # Focus on main product range
                        valid_prices.append(price)
                except ValueError:
                    continue
            
            if valid_prices:
                # Take the highest price as it's likely the main product price
                current_price = max(valid_prices)
        
        # Calculate discount if we have both prices
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        return current_price, discount_percent
    
    def _extract_all_prices(self, soup: BeautifulSoup) -> list:
        """Extract all prices from page text as fallback"""
        page_text = soup.get_text()
        all_prices = re.findall(r'\$(\d{1,4}(?:\.\d{2})?)', page_text)
        
        valid_prices = []
        for price_str in all_prices[:5]:  # Only check first few
            try:
                price = float(price_str)
                if 40 <= price <= 500:
                    valid_prices.append(price)
            except ValueError:
                continue
        
        return sorted(list(set(valid_prices)))
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check stock status - be more precise about out of stock detection"""
        
        page_text = soup.get_text().lower()
        
        # Priority 1: Explicit out of stock first (most definitive)
        out_of_stock_phrases = ['out of stock', 'sold out', 'unavailable', 'temporarily unavailable']
        for phrase in out_of_stock_phrases:
            if phrase in page_text:
                return False
        
        # Priority 2: In stock indicators
        # Check for in stock with quantity: "In stock (11)"
        in_stock_match = re.search(r'in\s+stock\s*\((\d+)\)', page_text)
        if in_stock_match:
            return True
        
        # Check for general in stock text
        if 'in stock' in page_text:
            return True
        
        # Priority 3: Check for add to cart button functionality
        add_button = soup.find(['button', 'input'], string=re.compile(r'add.*cart', re.I))
        if add_button:
            is_disabled = add_button.get('disabled') is not None
            button_text = add_button.get_text().strip().lower()
            
            # If button is disabled or says out of stock, it's out of stock
            if is_disabled or 'out of stock' in button_text:
                return False
            
            # If button is enabled and doesn't mention stock issues, it's in stock
            return True
        
        # Priority 4: Default logic - if we have a price but no explicit indicators
        # Be more conservative - assume out of stock unless explicitly stated otherwise
        return False


def extract_cigarboxpa_data(url: str) -> Dict:
    """
    Main extraction function for CigarBoxPA
    Compatible with CSV update workflow
    """
    extractor = CigarBoxPAExtractor()
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
    """Test the extractor with the provided CigarBoxPA URLs"""
    
    test_urls = [
        'https://www.cigarboxpa.com/af-short-story-box.html',                           # $189.99, Box of 25, in stock
        'https://www.cigarboxpa.com/arturo-fuente-toast-across-america-2025-pack-of-2.html',  # $54.99, Pack of 2, out of stock
        'https://www.cigarboxpa.com/arturo-fuente-2024-rare-holiday-collection.html',  # $189.99 (was $199.99), in stock
    ]
    
    print("Testing CigarBoxPA extraction...")
    print("=" * 60)
    
    for i, url in enumerate(test_urls):
        product_name = url.split('/')[-1].replace('-', ' ').title().replace('.Html', '')
        print(f"\nTest {i+1}: {product_name}")
        print("-" * 40)
        result = extract_cigarboxpa_data(url)
        
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
