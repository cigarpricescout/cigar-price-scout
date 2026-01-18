#!/usr/bin/env python3
"""
Thompson Cigars Working Extractor
Following the proven pattern from Hiland's extractor - actual data extraction
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class ThompsonCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Thompson Cigars URL
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
        
        # Look in product title
        title_selectors = ['h1', '.product-title', '.product_title', 'h1.product-title']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()
                
                # Thompson's pattern: "Box of 25" or similar
                qty_match = re.search(r'box\s+of\s+(\d+)', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty > 5:
                        return qty
                
                # Alternative patterns
                qty_match = re.search(r'(\d+)\s*pack', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty > 5:
                        return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract box price and discount percentage"""
        
        # Look for current price (sale price from screenshot: $169.43)
        current_prices = []
        original_prices = []
        
        # Thompson's pricing structure - look for main price elements
        price_selectors = ['.price', '.product-price', '.current-price', '.sale-price']
        
        for selector in price_selectors:
            price_elements = soup.select(selector)
            for elem in price_elements:
                price_text = elem.get_text().strip()
                price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
                
                if price_match:
                    try:
                        price = float(price_match.group(1))
                        if 50 <= price <= 2000:  # Box price range
                            # Check if this is strikethrough/original price
                            is_strikethrough = (
                                elem.find_parent(['del', 's']) or
                                'line-through' in str(elem.get('style', '')) or
                                'strikethrough' in ' '.join(elem.get('class', []))
                            )
                            
                            if is_strikethrough:
                                original_prices.append(price)
                            else:
                                current_prices.append(price)
                    except ValueError:
                        continue
        
        # Get the best prices
        current_price = min(current_prices) if current_prices else None
        original_price = max(original_prices) if original_prices else None
        
        # Calculate discount
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock based on button text and indicators"""
        
        # Look for add to cart button
        add_to_cart = soup.find(['button', 'input'], string=re.compile(r'add.*cart', re.I))
        if add_to_cart:
            return True
        
        # Look for stock status text
        stock_indicators = soup.find_all(string=re.compile(r'(?:in\s+stock|out\s+of\s+stock|sold\s+out)', re.I))
        for indicator in stock_indicators:
            text = indicator.strip().upper()
            if 'IN STOCK' in text:
                return True
            if any(phrase in text for phrase in ['OUT OF STOCK', 'SOLD OUT']):
                return False
        
        # Default to True if unclear
        return True


def extract_thompson_cigars_data(url: str) -> Dict:
    """
    Main extraction function for Thompson Cigars
    Compatible with CSV update workflow
    """
    extractor = ThompsonCigarsExtractor()
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
    """Test the extractor with the provided URL"""
    
    test_url = "https://www.thompsoncigar.com/p/arturo-fuente-hemingway-short-story-perfecto-cameroon/73670/#p-143939"
    
    print("Testing Thompson Cigars extraction...")
    print("=" * 50)
    print(f"URL: {test_url}")
    print("Expected: Box of 25, $169.43, In Stock")
    print("-" * 40)
    
    result = extract_thompson_cigars_data(test_url)
    
    if result['error']:
        print(f"ERROR: {result['error']}")
    else:
        print("SUCCESS!")
        print(f"  Price: ${result['price']}")
        print(f"  Box Qty: {result['box_quantity']}")
        print(f"  In Stock: {result['in_stock']}")
        if result['discount_percent']:
            print(f"  Discount: {result['discount_percent']:.1f}% off")


if __name__ == "__main__":
    test_extractor()
