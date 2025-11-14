#!/usr/bin/env python3
"""
Absolute Cigars Extractor
Following the exact same pattern as the working Hiland's Cigars extractor
Retailer #11 - WooCommerce Platform
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class AbsoluteCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Exact same headers as proven extractors
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Absolute Cigars URL
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
        
        # Look in product title - Absolute Cigars pattern: "Brand Name - Box of XX"
        title_selectors = ['h1.product_title', 'h1', '.product_title', '.product-title', 'h1.entry-title']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()
                
                # Absolute Cigars specific patterns from screenshots
                qty_match = re.search(r'box\s+of\s+(\d+)', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 5:  # Filter out single quantities
                        return qty
                
                # Additional patterns
                qty_match = re.search(r'(\d+)\s*ct\b', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 5:
                        return qty
                
                qty_match = re.search(r'(\d+)\s*count', title, re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if qty >= 5:
                        return qty
        
        # Check URL patterns
        url_patterns = [
            r'box-of-(\d+)',
            r'pack-of-(\d+)',
            r'bundle-of-(\d+)'
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, url, re.I)
            if match:
                qty = int(match.group(1))
                if qty >= 5:
                    return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract box price and discount percentage"""
        
        # Look for main product pricing area
        product_summary = soup.find(['div'], class_=re.compile(r'product-summary|summary|product-info|single-product|entry-summary', re.I))
        
        if product_summary:
            # Look for price in WooCommerce standard format
            price_elements = product_summary.find_all(['span'], class_=re.compile(r'woocommerce-Price-amount|amount|price'))
            
            current_prices = []
            original_prices = []
            
            for elem in price_elements:
                price_text = elem.get_text().strip()
                # Handle comma-separated prices like $1,649.99 
                price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', price_text)
                
                if price_match:
                    try:
                        price_str = price_match.group(1).replace(',', '')
                        price = float(price_str)
                        # Filter for cigar box pricing range
                        if 150 <= price <= 2000:
                            # Check for strikethrough (sale pricing)
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
            
            # Remove navigation noise - cart total is $0.00 on Absolute Cigars
            navigation_prices = {0.0}
            current_prices = [p for p in current_prices if p not in navigation_prices]
            
            # Select best prices
            current_price = max(current_prices) if current_prices else None
            original_price = max(original_prices) if original_prices else None
            
            # Calculate discount
            discount_percent = None
            if original_price and current_price and original_price > current_price:
                discount_percent = ((original_price - current_price) / original_price) * 100
            
            if current_price:
                return current_price, discount_percent
        
        # Fallback: Look for prices in page text but be more selective
        page_text = soup.get_text()
        all_prices = re.findall(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', page_text)
        
        valid_prices = []
        for price_str in all_prices:
            try:
                clean_price = float(price_str.replace(',', ''))
                if 150 <= clean_price <= 2000:  # Cigar box range
                    valid_prices.append(clean_price)
            except ValueError:
                continue
        
        # Filter out navigation noise (Absolute Cigars specific)
        navigation_prices = {0.0}  # Cart total
        product_prices = [p for p in valid_prices if p not in navigation_prices]
        
        if product_prices:
            # Logic for single vs discount pricing
            if len(product_prices) == 1:
                return product_prices[0], None
            else:
                # Multiple prices - assume sale pricing
                current_price = min(product_prices)
                original_price = max(product_prices) 
                discount_percent = ((original_price - current_price) / original_price) * 100
                return current_price, discount_percent
        
        return None, None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock based on Absolute Cigars patterns"""
        
        # Priority 1: Look for buy button (from screenshots: "Buy Now")
        buy_button = soup.find(['button', 'input'], class_=re.compile(r'add.*cart|cart.*add|single_add_to_cart_button|buy.*now', re.I))
        
        if buy_button:
            button_text = buy_button.get_text().strip().upper()
            # Strong in-stock indicators from Absolute Cigars
            if any(phrase in button_text for phrase in ['BUY NOW', 'ADD TO CART', 'PURCHASE']):
                return True
            # Strong out-of-stock indicators  
            if any(phrase in button_text for phrase in ['OUT OF STOCK', 'NOTIFY ME', 'SOLD OUT']):
                return False
        
        # Priority 2: Look for explicit stock status text (from screenshot: "Out of stock")
        stock_indicators = soup.find_all(string=re.compile(r'(?:in\s+stock|out\s+of\s+stock|sold\s+out|availability)', re.I))
        for indicator in stock_indicators:
            text = indicator.strip().upper()
            if 'IN STOCK' in text:
                return True
            if any(phrase in text for phrase in ['OUT OF STOCK', 'SOLD OUT']):
                return False
        
        # Priority 3: Look for stock status elements
        availability_elem = soup.find(['span', 'div', 'p'], class_=re.compile(r'stock|availability', re.I))
        if availability_elem:
            avail_text = availability_elem.get_text().strip().upper()
            if 'OUT OF STOCK' in avail_text:
                return False
            if 'IN STOCK' in avail_text:
                return True
        
        # Look for red "Out of stock" indicator from screenshot
        out_of_stock_elems = soup.find_all(['span', 'div', 'p'], string=re.compile(r'out\s+of\s+stock', re.I))
        if out_of_stock_elems:
            return False
        
        # If we found a price but no stock indicators, assume in stock
        page_text = soup.get_text()
        has_price = bool(re.search(r'\$\d+', page_text))
        
        if has_price:
            return True
        else:
            # No price found - likely out of stock (matches screenshot pattern)
            return False


def extract_absolute_cigars_data(url: str) -> Dict:
    """
    Main extraction function for Absolute Cigars
    Compatible with CSV update workflow
    """
    extractor = AbsoluteCigarsExtractor()
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
        'https://absolutecigars.com/product/hemingway-signature/',  # In stock, $290
        'https://absolutecigars.com/product/bestseller-cigars/',    # Out of stock, no price
    ]
    
    print("Testing Absolute Cigars extraction...")
    print("=" * 50)
    
    for i, url in enumerate(test_urls):
        print(f"\nTest {i+1}: {url.split('/')[-2]}")
        print("-" * 40)
        result = extract_absolute_cigars_data(url)
        
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