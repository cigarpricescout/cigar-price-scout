#!/usr/bin/env python3
"""
Cigar Prime Store Extractor - Production Ready
WooCommerce platform with clean product display
Based on successful Cigar Depot/Cigar Hustler patterns

Platform: WooCommerce
Compliance: Tier 1 (stable URLs, 1 req/sec)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional
from datetime import datetime

class CigarPrimeStoreExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Cigar Prime Store URL
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
            
            # Extract box quantity
            box_qty = self._extract_box_quantity(soup)
            
            # Extract price (WooCommerce specific logic)
            box_price = self._extract_price(soup)
            
            # Check stock status
            in_stock = self._check_stock_status(soup)
            
            # Calculate discount if available
            discount_percent = self._calculate_discount(soup, box_price)
            
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
        """Extract box quantity from product page"""
        # Look in the product details table
        # Based on web search: "PACKING | 29"
        
        # Method 1: Look for "PACKING" in table rows
        for row in soup.find_all('tr'):
            row_text = row.get_text()
            if 'PACKING' in row_text.upper():
                # Extract number from the row
                qty_match = re.search(r'(\d+)', row_text)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if 5 <= qty <= 100:
                        return qty
        
        # Method 2: Standard patterns in page text
        page_text = soup.get_text()
        
        qty_patterns = [
            r'[Bb]ox [Oo]f (\d+)',
            r'\(Box of (\d+)\)',
            r'(\d+) [Pp]ack',
            r'(\d+)-[Pp]ack',
            r'[Pp]acking[:\s]+(\d+)',
            r'(\d+) [Cc]ount',
            r'(\d+)[Cc]t',
        ]
        
        for pattern in qty_patterns:
            match = re.search(pattern, page_text)
            if match:
                qty = int(match.group(1))
                if 5 <= qty <= 100:
                    return qty
        
        return None
    
    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        """
        Extract current price from WooCommerce product page
        Strategy: Look for main product price element, avoid cart/navigation prices
        """
        # Method 1: Look in product title/info section
        product_title = soup.find('h1')
        if product_title:
            # Get the section containing the title
            main_section = product_title.find_parent(['div', 'section', 'article'])
            if main_section:
                # Look for price elements in product section
                price_elems = main_section.find_all('span', class_='woocommerce-Price-amount')
                
                for elem in price_elems:
                    price_text = elem.get_text().strip()
                    price_match = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text.replace(',', ''))
                    if price_match:
                        try:
                            price = float(price_match.group(1))
                            # Skip invalid prices like $0.00 and ensure reasonable range
                            if 50 <= price <= 5000:
                                return price
                        except ValueError:
                            continue
        
        # Method 2: Look for WooCommerce price amounts, but filter carefully
        price_elements = soup.find_all('span', class_='woocommerce-Price-amount')
        
        valid_prices = []
        for elem in price_elements:
            price_text = elem.get_text().strip()
            # Extract numeric value
            price_match = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text.replace(',', ''))
            if price_match:
                try:
                    price = float(price_match.group(1))
                    # Skip cart totals ($0.00) and ensure reasonable range
                    if 50 <= price <= 5000:
                        valid_prices.append(price)
                except ValueError:
                    continue
        
        if valid_prices:
            # Return first valid price (most likely the product price)
            return valid_prices[0]
        
        # Method 3: Look for any price pattern in product summary
        summary = soup.find(['div', 'section'], class_=lambda x: x and 'summary' in str(x).lower())
        if summary:
            price_text = summary.get_text()
            price_matches = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text.replace(',', ''))
            
            for price_str in price_matches:
                try:
                    price = float(price_str.replace(',', ''))
                    if 50 <= price <= 5000:
                        return price
                except ValueError:
                    continue
        
        return None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock"""
        page_text = soup.get_text().lower()
        
        # Priority 1: Check for "Out of Stock" or "Sold Out"
        if 'out of stock' in page_text or 'sold out' in page_text:
            return False
        
        # Priority 2: Check for "Add to Cart" button (indicates in stock)
        if 'add to cart' in page_text:
            return True
        
        # Priority 3: Check for button elements
        add_to_cart_btn = soup.find(['button', 'input', 'a'], string=re.compile(r'[Aa]dd [Tt]o [Cc]art', re.I))
        if add_to_cart_btn:
            is_disabled = add_to_cart_btn.get('disabled') is not None
            return not is_disabled
        
        # Priority 4: Check for "In Stock" text
        if 'in stock' in page_text:
            return True
        
        # Default: assume out of stock if unclear
        return False
    
    def _calculate_discount(self, soup: BeautifulSoup, current_price: Optional[float]) -> Optional[float]:
        """Calculate discount percentage if original price is available"""
        if not current_price:
            return None
        
        # Look for strikethrough/del prices (original prices)
        del_prices = []
        
        for elem in soup.find_all(['del', 's']):
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text.replace(',', ''))
            if price_match:
                try:
                    price = float(price_match.group(1).replace(',', ''))
                    if price > current_price and 50 <= price <= 5000:
                        del_prices.append(price)
                except ValueError:
                    continue
        
        if del_prices:
            original_price = max(del_prices)
            discount_percent = ((original_price - current_price) / original_price) * 100
            return round(discount_percent, 1)
        
        return None


def extract_cigarprimestore_data(url: str) -> Dict:
    """
    Main extraction function for Cigar Prime Store
    Compatible with CSV update workflow
    """
    extractor = CigarPrimeStoreExtractor()
    result = extractor.extract_product_data(url)
    
    return {
        'success': result['error'] is None,
        'price': result['box_price'], 
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'discount_percent': result['discount_percent'],
        'error': result['error']
    }


# Cigar Prime Store Retailer Configuration
CIGAR_PRIME_STORE_CONFIG = {
    "retailer_info": {
        "name": "Cigar Prime Store",
        "domain": "cigarprimestore.com",
        "platform": "WooCommerce",
        "compliance_tier": 1,
        "trained_date": "2026-01-19",
        "training_examples": 1
    },
    
    "extraction_patterns": {
        "pricing_method": "WooCommerce standard price display",
        "price_location": "Main product price element",
        "box_quantities_seen": [29],
        "price_range": "$1000+ for premium boxes",
        
        "stock_indicators": {
            "in_stock": ["Add to cart"],
            "out_of_stock": ["Out of stock", "Sold out"]
        }
    },
    
    "automation_ready": True,
    "confidence_level": "high",
    "notes": [
        "WooCommerce platform with clean product pages",
        "Product details in table format (PACKING row)",
        "Standard WooCommerce price/stock indicators",
        "Premium cigar retailer with higher price points"
    ]
}


# Test function
def test_cigarprimestore_extraction():
    """Test the extraction on training URL"""
    
    test_url = "http://cigarprimestore.com/en/product/arturo-fuente-opus-x-super-belicoso/"
    
    print("Testing Cigar Prime Store extraction...")
    print("=" * 70)
    print(f"\nTest URL: {test_url}")
    print("Expected: $1,016.95, In Stock, Box of 29\n")
    
    result = extract_cigarprimestore_data(test_url)
    
    if result['success']:
        print(f"Price: ${result['price']}")
        print(f"Box Quantity: {result['box_quantity']}")
        print(f"In Stock: {result['in_stock']}")
        if result['discount_percent']:
            print(f"Discount: {result['discount_percent']:.1f}% off")
        
        # Validation
        price_ok = abs(result['price'] - 1016.95) < 0.01 if result['price'] else False
        stock_ok = result['in_stock'] == True
        qty_ok = result['box_quantity'] == 29 if result['box_quantity'] else False
        
        print("\n" + "="*70)
        if price_ok and stock_ok and qty_ok:
            print("[SUCCESS] All checks passed! Ready for production.")
        else:
            print("[PARTIAL] Some values may need adjustment:")
            if not price_ok:
                print(f"  - Price: expected $1016.95, got ${result['price']}")
            if not stock_ok:
                print(f"  - Stock: expected True, got {result['in_stock']}")
            if not qty_ok:
                print(f"  - Quantity: expected 29, got {result['box_quantity']}")
    else:
        print(f"[ERROR] {result.get('error', 'Unknown error')}")
        print("\n" + "="*70)
        print("[FAILED] Extraction encountered an error")


if __name__ == "__main__":
    test_cigarprimestore_extraction()
