#!/usr/bin/env python3
"""
Bayside Cigars Extractor
Following the exact same pattern as the working Absolute Cigars extractor
Rate: 1 request/second, Timeout: 10 seconds, Compliance: Tier 1
Platform: WooCommerce, Headers: Minimal (just User-Agent)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class BaysideCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Minimal headers - just User-Agent (proven effective)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Bayside Cigars URL"""
        try:
            # Rate limiting - 1 request per second (compliance requirement)
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            box_qty = self._extract_box_quantity(soup)
            box_price, discount_percent = self._extract_pricing(soup)
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
        """Extract box quantity from product title"""
        title_selectors = ['h1.product_title', 'h1', '.product_title', '.product-title']
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()
                
                # Bayside patterns: "BOX OF 25", "BOX OF 29"
                qty_match = re.search(r'box\s+of\s+(\d+)', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 5:
                        return qty
        
        # Check product info area
        product_info = soup.find('div', class_=re.compile(r'product-summary|summary', re.I))
        if product_info:
            info_text = product_info.get_text()
            qty_match = re.search(r'box\s+of\s+(\d+)', info_text, re.IGNORECASE)
            if qty_match:
                return int(qty_match.group(1))
            
            # Single cigar indicator
            if re.search(r'price\s+for\s+single', info_text, re.IGNORECASE):
                return 1
        
        return 25  # Default fallback
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract price and discount percentage"""
        product_summary = soup.find('div', class_=re.compile(r'product-summary|summary', re.I))
        
        if product_summary:
            price_elements = product_summary.find_all(['span', 'div'], class_=re.compile(r'price|amount'))
            
            current_prices = []
            original_prices = []
            
            for elem in price_elements:
                price_text = elem.get_text().strip()
                price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', price_text)
                
                if price_match:
                    try:
                        price = float(price_match.group(1).replace(',', ''))
                        if 50 <= price <= 2000:  # Valid cigar price range
                            # Check for strikethrough (original price)
                            is_strikethrough = (
                                elem.find_parent(['del', 's']) or
                                'line-through' in str(elem.get('style', ''))
                            )
                            
                            if is_strikethrough:
                                original_prices.append(price)
                            else:
                                current_prices.append(price)
                    except ValueError:
                        continue
            
            current_price = max(current_prices) if current_prices else None
            original_price = max(original_prices) if original_prices else None
            
            discount_percent = None
            if original_price and current_price and original_price > current_price:
                discount_percent = ((original_price - current_price) / original_price) * 100
            
            if current_price:
                return current_price, discount_percent
        
        return None, None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock"""
        # Look for "Out of stock" text
        stock_indicators = soup.find_all(string=re.compile(r'out\s+of\s+stock|sold\s+out', re.I))
        if stock_indicators:
            return False
        
        # Look for "ADD TO CART" button
        buy_button = soup.find(['button', 'input'], class_=re.compile(r'add.*cart|cart.*add', re.I))
        if buy_button:
            button_text = buy_button.get_text().strip().upper()
            if 'ADD TO CART' in button_text:
                return True
        
        # Check for "SOLD OUT" badges
        badge_elems = soup.find_all(['span', 'div'], string=re.compile(r'sold\s+out', re.I))
        if badge_elems:
            return False
        
        return True  # Default to in stock if no clear indicators


def extract_bayside_cigars_data(url: str) -> Dict:
    """Main extraction function for Bayside Cigars"""
    extractor = BaysideCigarsExtractor()
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
    """Test the extractor with sample URLs"""
    test_urls = [
        'https://baysidecigars.com/product/arturo-fuente-hemingway-best-seller-natural-box/',
        'https://baysidecigars.com/product/arturo-fuente-opusx-robusto/',
        'https://baysidecigars.com/product/cohiba-spectre-2021-1-cigar/'
    ]
    
    print("Testing Bayside Cigars extraction...")
    print("=" * 50)
    
    for i, url in enumerate(test_urls):
        print(f"\nTest {i+1}: {url.split('/')[-2]}")
        print("-" * 40)
        result = extract_bayside_cigars_data(url)
        
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
