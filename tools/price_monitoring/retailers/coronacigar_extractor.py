#!/usr/bin/env python3
"""
Corona Cigar Co. Extractor - Production Ready
E-commerce platform with clean product display and stock notifications
Based on successful Cigar Hustler/Prime Store patterns

Platform: Custom E-commerce
Compliance: Tier 1 (stable URLs, 1 req/sec)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional
from datetime import datetime

class CoronaCigarExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Corona Cigar URL
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
            
            # Extract price
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
        page_text = soup.get_text()
        
        # Method 1: Look for "Box of X" in Option label
        # Pattern from web search: "Option: Box of 25" or "Option: Box of 10"
        box_match = re.search(r'[Bb]ox [Oo]f (\d+)', page_text)
        if box_match:
            qty = int(box_match.group(1))
            if 5 <= qty <= 100:
                return qty
        
        # Method 2: Look for other quantity patterns
        qty_patterns = [
            r'\(Box of (\d+)\)',
            r'(\d+) [Pp]ack',
            r'(\d+)-[Pp]ack',
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
        Extract current price from Corona Cigar product page
        Strategy: The sale price appears AFTER MSRP and before "Save X%"
        """
        page_text = soup.get_text()
        
        # Method 1: Look for price pattern between MSRP and "Save X%"
        # Pattern: MSRP: $227.90 ... $198.95 ... Save 13%
        msrp_to_save_match = re.search(r'MSRP[:\s]+\$(\d+(?:\.\d{2})?)\s+\$(\d+(?:\.\d{2})?)\s+[Ss]ave', page_text)
        if msrp_to_save_match:
            # The second price is the sale price
            sale_price = float(msrp_to_save_match.group(2))
            if 50 <= sale_price <= 5000:
                return sale_price
        
        # Method 2: If no MSRP, look for price just before "Save X%"
        save_match = re.search(r'\$(\d+(?:\.\d{2})?)\s+[Ss]ave\s+\d+%', page_text)
        if save_match:
            price = float(save_match.group(1))
            if 50 <= price <= 5000:
                return price
        
        # Method 3: Look for the main product price section
        product_title = soup.find('h1')
        if product_title:
            main_section = product_title.find_parent(['div', 'section', 'article'])
            
            if main_section:
                price_text = main_section.get_text()
                price_matches = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
                
                # Skip navigation prices ($50, $100, etc.) and get product prices
                # Navigation prices are typically in increments of 50
                for price_str in price_matches:
                    try:
                        price = float(price_str.replace(',', ''))
                        # Skip common navigation/filter prices
                        if price in [50, 100, 150, 250, 500]:
                            continue
                        if 50 <= price <= 5000:
                            return price
                    except ValueError:
                        continue
        
        # Fallback: Get all prices and skip navigation ones
        price_matches = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', page_text)
        
        for price_str in price_matches:
            try:
                price = float(price_str.replace(',', ''))
                # Skip navigation prices
                if price in [50, 100, 150, 250, 500]:
                    continue
                if 50 <= price <= 5000:
                    return price
            except ValueError:
                continue
        
        return None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock"""
        # Priority 1: Check for stock status class elements
        # Corona Cigar uses: <p class="stock in_stock">in stock</p> or <p class="stock out_of_stock">
        in_stock_elem = soup.find(['p', 'span', 'div'], class_=lambda x: x and 'in_stock' in str(x))
        if in_stock_elem:
            # Check if it's visible (not display:none)
            style = in_stock_elem.get('style', '')
            if 'display' not in style.lower() or 'none' not in style.lower():
                return True
        
        out_of_stock_elem = soup.find(['p', 'span', 'div'], class_=lambda x: x and 'out_of_stock' in str(x))
        if out_of_stock_elem:
            # Check if it's visible (not display:none)
            style = out_of_stock_elem.get('style', '')
            if 'display' not in style.lower() or 'none' not in style.lower():
                return False
        
        page_text = soup.get_text().lower()
        
        # Priority 2: Check for "notify me" or email notification text (specific to out of stock)
        if 'notify me' in page_text or 'enter your email address to be notified' in page_text:
            return False
        
        # Priority 3: Generic out of stock indicators
        if 'sold out' in page_text:
            return False
        
        # Priority 4: Check for positive stock indicators in text
        if 'adding to cart' in page_text:
            return True
        
        if 'add to cart' in page_text:
            return True
        
        # Default: If unclear, assume out of stock for safety
        return False
    
    def _calculate_discount(self, soup: BeautifulSoup, current_price: Optional[float]) -> Optional[float]:
        """Calculate discount percentage from MSRP"""
        if not current_price:
            return None
        
        page_text = soup.get_text()
        
        # Look for "Save X%" text first (most direct)
        save_match = re.search(r'[Ss]ave\s+(\d+(?:\.\d+)?)%', page_text)
        if save_match:
            return float(save_match.group(1))
        
        # Look for MSRP price
        msrp_match = re.search(r'MSRP[:\s]+\$(\d+(?:,\d{3})*(?:\.\d{2})?)', page_text)
        if msrp_match:
            try:
                msrp = float(msrp_match.group(1).replace(',', ''))
                if msrp > current_price:
                    discount = ((msrp - current_price) / msrp) * 100
                    return round(discount, 1)
            except ValueError:
                pass
        
        return None


def extract_coronacigar_data(url: str) -> Dict:
    """
    Main extraction function for Corona Cigar Co.
    Compatible with CSV update workflow
    """
    extractor = CoronaCigarExtractor()
    result = extractor.extract_product_data(url)
    
    return {
        'success': result['error'] is None,
        'price': result['box_price'], 
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'discount_percent': result['discount_percent'],
        'error': result['error']
    }


# Corona Cigar Retailer Configuration
CORONA_CIGAR_CONFIG = {
    "retailer_info": {
        "name": "Corona Cigar Co.",
        "domain": "coronacigar.com",
        "platform": "Custom E-commerce",
        "compliance_tier": 1,
        "trained_date": "2026-01-19",
        "training_examples": 3
    },
    
    "extraction_patterns": {
        "pricing_method": "Sale price with MSRP strikethrough",
        "price_location": "Main product section with 'Save X%' indicator",
        "box_quantities_seen": [10, 25],
        "price_range": "$100-$500 typical",
        
        "stock_indicators": {
            "in_stock": ["Adding to cart", "Add to cart"],
            "out_of_stock": ["Enter your email address to be notified", "Out of stock"]
        }
    },
    
    "automation_ready": True,
    "confidence_level": "high",
    "notes": [
        "E-commerce platform with clear stock notifications",
        "Box quantity in 'Option: Box of X' text",
        "Sale prices shown with 'Save X%' badge",
        "Out of stock items prompt email notification"
    ]
}


# Test function
def test_coronacigar_extraction():
    """Test the extraction on all training URLs"""
    
    test_cases = [
        {
            "name": "Arturo Fuente Hemingway Sun Grown Classic",
            "url": "https://www.coronacigar.com/arturo-fuente-hemingway-sun-grown-classic/",
            "expected": {
                "price": 323.00,
                "box_qty": 25,
                "in_stock": False
            }
        },
        {
            "name": "Arturo Fuente Hemingway Cameroon Best Seller",
            "url": "https://www.coronacigar.com/arturo-fuente-hemingway-cameroon-best-seller/",
            "expected": {
                "price": 198.95,
                "box_qty": 25,
                "in_stock": True
            }
        },
        {
            "name": "FSG By Drew Estate Toro Limited Edition",
            "url": "https://www.coronacigar.com/fsg-by-drew-estate-toro-limited-edition/",
            "expected": {
                "price": 124.95,
                "box_qty": 10,
                "in_stock": False
            }
        }
    ]
    
    print("Testing Corona Cigar extraction...")
    print("=" * 70)
    
    all_passed = True
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n[Test {i}] {test['name']}")
        print(f"URL: {test['url']}")
        print(f"Expected: ${test['expected']['price']}, Box of {test['expected']['box_qty']}, " +
              f"{'In Stock' if test['expected']['in_stock'] else 'Out of Stock'}\n")
        
        result = extract_coronacigar_data(test['url'])
        
        if result['success']:
            print(f"  Price: ${result['price']}")
            print(f"  Box Quantity: {result['box_quantity']}")
            print(f"  In Stock: {result['in_stock']}")
            if result['discount_percent']:
                print(f"  Discount: {result['discount_percent']:.1f}% off")
            
            # Validation
            price_ok = abs(result['price'] - test['expected']['price']) < 0.01 if result['price'] else False
            qty_ok = result['box_quantity'] == test['expected']['box_qty'] if result['box_quantity'] else False
            stock_ok = result['in_stock'] == test['expected']['in_stock']
            
            if price_ok and qty_ok and stock_ok:
                print(f"  Status: PASSED")
            else:
                print(f"  Status: FAILED")
                if not price_ok:
                    print(f"    - Price: expected ${test['expected']['price']}, got ${result['price']}")
                if not qty_ok:
                    print(f"    - Quantity: expected {test['expected']['box_qty']}, got {result['box_quantity']}")
                if not stock_ok:
                    print(f"    - Stock: expected {test['expected']['in_stock']}, got {result['in_stock']}")
                all_passed = False
        else:
            print(f"  [ERROR] {result.get('error', 'Unknown error')}")
            print(f"  Status: FAILED")
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("[SUCCESS] All tests passed! Ready for production.")
    else:
        print("[FAILED] Some tests failed - needs adjustment")


if __name__ == "__main__":
    test_coronacigar_extraction()
