#!/usr/bin/env python3
"""
Small Batch Cigar Extractor
Shopify Platform - Dual Pricing Options (Pack vs Box)
Retailer #12 in proven automation framework
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class SmallBatchCigarExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Proven conservative headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Small Batch Cigar URL
        Focus on Box pricing (ignore Pack pricing)
        """
        try:
            # Rate limiting - 1 request per second
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity and pricing (targeting Box options only)
            box_qty, box_price, discount_percent = self._extract_box_pricing(soup)
            
            # Check stock status for box option
            in_stock = self._check_box_stock_status(soup)
            
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
    
    def _extract_box_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[int], Optional[float], Optional[float]]:
        """Extract box quantity and pricing, ignoring pack options"""
        
        # Look for product variants/options sections
        # Small Batch uses sections for Pack vs Box options
        
        box_qty = None
        box_price = None
        discount_percent = None
        
        # Strategy 1: Find "Box of X" sections specifically
        box_sections = soup.find_all(['div', 'section'], string=re.compile(r'box\s+of\s+\d+', re.I))
        
        if not box_sections:
            # Strategy 2: Look for elements containing "Box of" text
            all_elements = soup.find_all(string=re.compile(r'box\s+of\s+\d+', re.I))
            box_sections = [elem.find_parent(['div', 'section', 'p', 'span']) for elem in all_elements if elem.find_parent()]
            box_sections = [elem for elem in box_sections if elem]
        
        for section in box_sections:
            if not section:
                continue
                
            section_text = section.get_text()
            
            # Extract box quantity
            qty_match = re.search(r'box\s+of\s+(\d+)', section_text, re.I)
            if qty_match:
                box_qty = int(qty_match.group(1))
            
            # Find price in this section or nearby
            # Look for price patterns around the box section
            price_container = section.find_parent(['div']) or section
            
            # Expand search area for price
            for _ in range(3):  # Look up to 3 parent levels
                if price_container:
                    price_text = price_container.get_text()
                    # Look for $ amounts in reasonable cigar box range
                    price_matches = re.findall(r'\$(\d{2,4}(?:\.\d{2})?)', price_text)
                    
                    for price_str in price_matches:
                        try:
                            price = float(price_str)
                            if 150 <= price <= 2000:  # Box price range - lowered to catch Box of 12
                                box_price = price
                                break
                        except ValueError:
                            continue
                    
                    if box_price:
                        break
                    
                    price_container = price_container.find_parent(['div'])
                else:
                    break
            
            # If we found a box price, we're done
            if box_price and box_qty:
                break
        
        # Fallback: If no specific box section found, look for general pricing
        if not box_price:
            # Look for all prices on the page
            page_text = soup.get_text()
            all_prices = re.findall(r'\$(\d{2,4}(?:\.\d{2})?)', page_text)
            
            valid_box_prices = []
            for price_str in all_prices:
                try:
                    price = float(price_str)
                    # Filter for box-level pricing (exclude pack prices like $64, include Box of 12 ~$194)
                    if 150 <= price <= 2000:
                        valid_box_prices.append(price)
                except ValueError:
                    continue
            
            # Take the highest valid price (most likely the box price)
            if valid_box_prices:
                box_price = max(valid_box_prices)
        
        # Extract box quantity from page title if not found in sections
        if not box_qty:
            title_elem = soup.find('h1')
            if title_elem:
                title = title_elem.get_text().strip()
                qty_match = re.search(r'box\s+of\s+(\d+)', title, re.I)
                if qty_match:
                    box_qty = int(qty_match.group(1))
        
        return box_qty, box_price, discount_percent
    
    def _check_box_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check stock status specifically for box option"""
        
        # Strategy: Find box sections and check their stock status
        box_sections = soup.find_all(['div', 'section'], string=re.compile(r'box\s+of\s+\d+', re.I))
        
        if not box_sections:
            # Fallback: look for elements with "Box of" text
            all_elements = soup.find_all(string=re.compile(r'box\s+of\s+\d+', re.I))
            box_sections = [elem.find_parent(['div', 'section', 'p']) for elem in all_elements if elem.find_parent()]
            box_sections = [elem for elem in box_sections if elem]
        
        for section in box_sections:
            if not section:
                continue
            
            # Look for stock indicators in this section
            section_container = section.find_parent(['div']) or section
            
            # Expand search for stock indicators
            for _ in range(3):  # Look up parent levels
                if section_container:
                    container_text = section_container.get_text().lower()
                    
                    # Check for out of stock indicators
                    if any(indicator in container_text for indicator in ['out of stock', 'notify me when available']):
                        return False
                    
                    # Check for in stock indicators (ADD TO CART button)
                    add_to_cart_btn = section_container.find(['button', 'input'], string=re.compile(r'add\s+to\s+cart', re.I))
                    if add_to_cart_btn:
                        return True
                    
                    section_container = section_container.find_parent(['div'])
                else:
                    break
        
        # Fallback: General stock detection
        # Look for "ADD TO CART" buttons vs "Notify me" buttons
        add_to_cart = soup.find(['button'], string=re.compile(r'add\s+to\s+cart', re.I))
        notify_me = soup.find(['button'], string=re.compile(r'notify\s+me', re.I))
        
        # If we see "Notify me" button, it's likely out of stock
        if notify_me and not add_to_cart:
            return False
        
        # Look for explicit "Out of stock" text
        out_of_stock_text = soup.find_all(string=re.compile(r'out\s+of\s+stock', re.I))
        if out_of_stock_text:
            return False
        
        # If we found a price and no clear out-of-stock indicators, assume in stock
        page_text = soup.get_text()
        has_box_price = bool(re.search(r'\$[23]\d{2}', page_text))  # $200-$399 range
        
        return has_box_price


def extract_smallbatch_cigar_data(url: str) -> Dict:
    """
    Main extraction function for Small Batch Cigar
    Compatible with CSV update workflow
    """
    extractor = SmallBatchCigarExtractor()
    result = extractor.extract_product_data(url)
    
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
    """Test the extractor with sample URLs from screenshots"""
    
    test_urls = [
        'https://www.smallbatchcigar.com/hemingway-best-seller',    # In stock - $243
        'https://www.smallbatchcigar.com/anejo-reserva-46',        # Out of stock - $420  
        'https://www.smallbatchcigar.com/romeo-y-julieta-1875-churchill',  # Mixed stock - $321
    ]
    
    print("Testing Small Batch Cigar extraction...")
    print("=" * 50)
    
    for i, url in enumerate(test_urls):
        print(f"\nTest {i+1}: {url.split('/')[-1]}")
        print("-" * 40)
        result = extract_smallbatch_cigar_data(url)
        
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
