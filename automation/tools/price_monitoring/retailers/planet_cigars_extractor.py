#!/usr/bin/env python3
"""
Planet Cigars Extractor
Custom Platform - Dual Pricing Structure (MSRP/Sale vs Single Price)
Retailer #13 in proven automation framework
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class PlanetCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Proven conservative headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Planet Cigars URL
        Handles both MSRP/Sale pricing and single pricing
        """
        try:
            # Rate limiting - 1 request per second
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from title or product details
            box_qty = self._extract_box_quantity(soup)
            
            # Extract pricing (handles both MSRP/Sale and single price)
            box_price, msrp_price, discount_percent = self._extract_pricing(soup)
            
            # Check stock status
            in_stock = self._check_stock_status(soup)
            
            return {
                'box_price': box_price,
                'box_qty': box_qty,
                'in_stock': in_stock,
                'msrp_price': msrp_price,
                'discount_percent': discount_percent,
                'error': None
            }
            
        except Exception as e:
            return {
                'box_price': None,
                'box_qty': None,
                'in_stock': False,
                'msrp_price': None,
                'discount_percent': None,
                'error': str(e)
            }
    
    def _extract_box_quantity(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract box quantity from product title or details"""
        
        # Check product title
        title_elem = soup.find('h1')
        if title_elem:
            title = title_elem.get_text().strip()
            
            # Look for box patterns
            qty_match = re.search(r'box\s+of\s+(\d+)', title, re.I)
            if qty_match:
                qty = int(qty_match.group(1))
                if qty >= 5:
                    return qty
        
        # Look specifically for "Packed" field in specifications table
        packed_elements = soup.find_all(['span'], class_='propery-title', string=re.compile(r'packed', re.I))
        
        for packed_elem in packed_elements:
            # Find the corresponding value element (propery-des class)
            parent_li = packed_elem.find_parent(['li'])
            if parent_li:
                value_elem = parent_li.find(['span'], class_='propery-des')
                if value_elem:
                    qty_text = value_elem.get_text().strip()
                    qty_match = re.search(r'(\d+)', qty_text)
                    if qty_match:
                        qty = int(qty_match.group(1))
                        if 5 <= qty <= 100:
                            return qty
        
        # Fallback: Look for "Packed" anywhere in the specifications
        spec_text = soup.get_text()
        packed_patterns = re.findall(r'packed\s*:?\s*(\d+)', spec_text, re.I)
        for qty_str in packed_patterns:
            try:
                qty = int(qty_str)
                if 5 <= qty <= 100:
                    return qty
            except ValueError:
                continue
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Extract pricing - handles both MSRP/Sale and single price formats"""
        
        page_text = soup.get_text()
        
        # Strategy 1: Look for MSRP and Sale price structure
        # MSRP appears as strikethrough, Sale price in red
        
        # Find MSRP (price-old class)
        msrp_price = None
        msrp_elements = soup.find_all(['span'], class_='price-old')
        
        for elem in msrp_elements:
            price_text = elem.get_text()
            msrp_match = re.search(r'\$(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)', price_text)
            if msrp_match:
                try:
                    clean_price = float(msrp_match.group(1).replace(',', ''))
                    if 50 <= clean_price <= 2000:
                        msrp_price = clean_price
                        break
                except ValueError:
                    continue
        
        # Find Sale price (price-new class)
        sale_price = None
        sale_elements = soup.find_all(['span'], class_='price-new')
        
        for elem in sale_elements:
            price_text = elem.get_text()
            sale_match = re.search(r'\$(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)', price_text)
            if sale_match:
                try:
                    clean_price = float(sale_match.group(1).replace(',', ''))
                    if 50 <= clean_price <= 2000:
                        sale_price = clean_price
                        break
                except ValueError:
                    continue
        
        # Strategy 2: If no sale price found, look for pricing logic 
        if not sale_price:
            # Look for all prices on page and filter
            page_text = soup.get_text()
            all_prices = re.findall(r'\$(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)', page_text)
            
            valid_prices = []
            for price_str in all_prices:
                try:
                    clean_price = float(price_str.replace(',', ''))
                    if 50 <= clean_price <= 2000:  # Cigar price range
                        valid_prices.append(clean_price)
                except ValueError:
                    continue
            
            # Filter out navigation noise (cart total $0.00)
            navigation_prices = {0.0}
            product_prices = [p for p in valid_prices if p not in navigation_prices]
            
            if msrp_price and product_prices:
                # If we have MSRP, find the sale price (lower than MSRP)
                sale_candidates = [p for p in product_prices if p < msrp_price]
                if sale_candidates:
                    sale_price = max(sale_candidates)  # Highest price below MSRP
                else:
                    # No sale price found, use MSRP as sale price
                    sale_price = msrp_price
                    msrp_price = None
            elif product_prices:
                # No MSRP, take highest price
                sale_price = max(product_prices)
        
        # Calculate discount percentage
        discount_percent = None
        if msrp_price and sale_price and msrp_price > sale_price:
            discount_percent = ((msrp_price - sale_price) / msrp_price) * 100
        
        return sale_price, msrp_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check stock status based on Planet Cigars patterns"""
        
        # Look for availability field (from screenshots)
        availability_elements = soup.find_all(['span', 'div'], string=re.compile(r'availability', re.I))
        
        for elem in availability_elements:
            parent = elem.find_parent(['div', 'tr'])
            if parent:
                availability_text = parent.get_text().lower()
                
                # Strong out-of-stock indicators
                if any(indicator in availability_text for indicator in [
                    'out of stock', 'sold out', 'pre-order', 'backorder', 'unavailable'
                ]):
                    return False
                
                # Strong in-stock indicators  
                if 'in stock' in availability_text:
                    return True
        
        # Fallback: Look for stock indicators in page text
        page_text = soup.get_text().lower()
        
        # Check for explicit availability statements
        if any(indicator in page_text for indicator in [
            'out of stock', 'sold out', 'pre-order', 'backorder'
        ]):
            return False
        
        if 'in stock' in page_text:
            return True
        
        # Check for ADD TO CART button presence
        add_to_cart_btn = soup.find(['button', 'input'], string=re.compile(r'add\s+to\s+cart', re.I))
        
        # If we found a price and ADD TO CART button, likely in stock
        page_text = soup.get_text()
        has_price = bool(re.search(r'\$\d+', page_text))
        
        if has_price and add_to_cart_btn:
            return True
        
        # Conservative default
        return False


def extract_planet_cigars_data(url: str) -> Dict:
    """
    Main extraction function for Planet Cigars
    Compatible with CSV update workflow
    """
    extractor = PlanetCigarsExtractor()
    result = extractor.extract_product_data(url)
    
    return {
        'success': result['error'] is None,
        'price': result['box_price'], 
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'msrp_price': result['msrp_price'],
        'discount_percent': result['discount_percent'],
        'error': result['error']
    }


# Test function for development
def test_extractor():
    """Test the extractor with sample URLs from screenshots"""
    
    test_urls = [
        'https://www.planetcigars.com/excalibur/excalibur-epicures-natural',  # Sale: $132.97, MSRP: $183.80, In Stock
        'https://www.planetcigars.com/romeo-y-julieta-1875-churchill-tubos-cigars',  # Sale: $83.97, MSRP: $112.50, Out of Stock
        'https://www.planetcigars.com/arturo-fuente-opus-x-double-corona-cigars',  # Single: $1,250.00, Pre-Order
    ]
    
    print("Testing Planet Cigars extraction...")
    print("=" * 50)
    
    for i, url in enumerate(test_urls):
        print(f"\nTest {i+1}: {url.split('/')[-1]}")
        print("-" * 40)
        result = extract_planet_cigars_data(url)
        
        if result['error']:
            print(f"ERROR: {result['error']}")
        else:
            print(f"SUCCESS!")
            print(f"  Price: ${result['price']}")
            print(f"  MSRP: ${result['msrp_price']}")
            print(f"  Box Qty: {result['box_quantity']}")
            print(f"  In Stock: {result['in_stock']}")
            if result['discount_percent']:
                print(f"  Discount: {result['discount_percent']:.1f}% off")

if __name__ == "__main__":
    test_extractor()
