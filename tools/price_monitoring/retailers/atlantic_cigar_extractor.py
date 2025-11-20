"""
Atlantic Cigar Extractor - Fixed Version
Based on actual HTML structure analysis
Targets specific elements: price-value, price-rrp, BCData JavaScript
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import json
from typing import Dict

class AtlanticCigarExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Atlantic Cigar URL"""
        try:
            time.sleep(1)  # Rate limiting
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract sale price using specific Atlantic Cigar structure
            sale_price = self._extract_sale_price(soup)
            
            # Extract box quantity from package options
            box_qty = self._extract_box_quantity(soup)
            
            # Check stock status using BCData JavaScript
            in_stock = self._check_stock_status(soup)
            
            # Calculate discount if there's an MSRP
            discount_percent = self._calculate_discount(soup, sale_price)
            
            return {
                'box_price': sale_price,
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
    
    def _extract_sale_price(self, soup: BeautifulSoup) -> float:
        """Extract the main sale price (not MSRP) - targets price-value class"""
        
        # Priority 1: Look for the specific sale price element (price-value class)
        sale_price_elem = soup.find('span', class_='price-value')
        if sale_price_elem:
            price_text = sale_price_elem.get_text().strip()
            price_match = re.search(r'\$?(\d+(?:\.\d{2})?)', price_text)
            if price_match:
                try:
                    return float(price_match.group(1))
                except ValueError:
                    pass
        
        # Priority 2: Look in JavaScript BCData for sale price
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.get_text()
            if 'BCData' in script_text and 'sale_price_without_tax' in script_text:
                # Extract sale price from JavaScript BCData
                match = re.search(r'"sale_price_without_tax":\s*{\s*"formatted":\s*"\$(\d+\.\d+)"', script_text)
                if match:
                    try:
                        return float(match.group(1))
                    except ValueError:
                        continue
        
        # Priority 3: Look for any price-value elements
        price_value_elems = soup.find_all('span', class_=re.compile(r'price-value'))
        for elem in price_value_elems:
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$?(\d+(?:\.\d{2})?)', price_text)
            if price_match:
                try:
                    price = float(price_match.group(1))
                    if 50 <= price <= 2000:
                        return price
                except ValueError:
                    continue
        
        return None
    
    def _extract_box_quantity(self, soup: BeautifulSoup) -> int:
        """Extract box quantity from package options"""
        
        # Look for "Box of X" options from the examples
        package_options = soup.find_all(['button', 'option', 'span'], string=re.compile(r'Box of \d+', re.I))
        
        for option in package_options:
            text = option.get_text().strip()
            qty_match = re.search(r'Box of (\d+)', text, re.I)
            if qty_match:
                return int(qty_match.group(1))
        
        # Alternative: look in product title
        title_elem = soup.find('h1')
        if title_elem:
            title_text = title_elem.get_text().strip()
            qty_match = re.search(r'Box of (\d+)', title_text, re.I)
            if qty_match:
                return int(qty_match.group(1))
        
        # Default fallback
        return 25
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check stock status using BCData JavaScript object"""
        
        # Priority 1: Look in BCData JavaScript object for stock info
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.get_text()
            if 'BCData' in script_text and 'instock' in script_text:
                # Extract stock status from BCData
                instock_match = re.search(r'"instock":\s*(true|false)', script_text)
                if instock_match:
                    return instock_match.group(1) == 'true'
                
                # Also check stock number
                stock_match = re.search(r'"stock":\s*(\d+)', script_text)
                if stock_match:
                    stock_num = int(stock_match.group(1))
                    return stock_num > 0
        
        # Priority 2: Look for explicit unavailable messages
        unavailable_indicators = [
            'currently unavailable',
            'sold out', 
            'out of stock',
            'notify when available'
        ]
        
        page_text = soup.get_text().lower()
        for indicator in unavailable_indicators:
            if indicator in page_text:
                return False
        
        # Priority 3: Look for "ADD TO CART" button
        add_to_cart_button = soup.find(['button', 'input'], string=re.compile(r'add to cart', re.I))
        if add_to_cart_button and not add_to_cart_button.get('disabled'):
            return True
        
        # Priority 4: Look for red warning banners about unavailability
        warning_banners = soup.find_all(['div', 'span'], class_=re.compile(r'alert|warning|unavailable', re.I))
        for banner in warning_banners:
            banner_text = banner.get_text().lower()
            if any(indicator in banner_text for indicator in unavailable_indicators):
                return False
        
        # Default to in stock if no clear indicators
        return True
    
    def _calculate_discount(self, soup: BeautifulSoup, sale_price: float) -> float:
        """Calculate discount percentage using MSRP from price-rrp class"""
        
        if not sale_price:
            return None
        
        # Priority 1: Look for MSRP in price-rrp class
        msrp_elem = soup.find('span', class_='price-rrp')
        if msrp_elem:
            price_text = msrp_elem.get_text().strip()
            price_match = re.search(r'\$?(\d+(?:\.\d{2})?)', price_text)
            if price_match:
                try:
                    msrp = float(price_match.group(1))
                    if msrp > sale_price:  # Valid MSRP should be higher
                        discount_percent = ((msrp - sale_price) / msrp) * 100
                        return round(discount_percent, 1)
                except ValueError:
                    pass
        
        # Priority 2: Look in BCData JavaScript for RRP
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.get_text()
            if 'BCData' in script_text and 'rrp_without_tax' in script_text:
                # Extract RRP from JavaScript BCData
                match = re.search(r'"rrp_without_tax":\s*{\s*"formatted":\s*"\$(\d+\.\d+)"', script_text)
                if match:
                    try:
                        msrp = float(match.group(1))
                        if msrp > sale_price:
                            discount_percent = ((msrp - sale_price) / msrp) * 100
                            return round(discount_percent, 1)
                    except ValueError:
                        continue
        
        return None


def extract_atlantic_cigar_data(url: str) -> Dict:
    """Main extraction function for automation compatibility"""
    extractor = AtlanticCigarExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to automation format
    return {
        'success': result['error'] is None,
        'price': result['box_price'],
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'discount_percent': result['discount_percent'],
        'error': result['error']
    }


# Test function
def test_extractor():
    """Test with the three example URLs"""
    test_cases = [
        {
            'url': 'https://atlanticcigar.com/arturo-fuente-hemingway-classic-natural/',
            'expected_price': 272.95,
            'expected_stock': True,
            'expected_qty': 25,
            'name': 'Hemingway Classic (Sale Price)'
        },
        {
            'url': 'https://atlanticcigar.com/padron-1964-anniversary-diplomatico-maduro/',
            'expected_price': 455.00,
            'expected_stock': True,
            'expected_qty': 25,
            'name': 'Padron Diplomatico (No Discount)'
        },
        {
            'url': 'https://atlanticcigar.com/dapper-el-borracho-maduro-edmundo-bp-5-1-2x52/',
            'expected_price': 106.80,
            'expected_stock': False,
            'expected_qty': 16,
            'name': 'Dapper El Borracho (Out of Stock)'
        }
    ]
    
    print("Testing Atlantic Cigar Extractor - Fixed Version")
    print("=" * 50)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['name']}")
        print(f"URL: {test['url']}")
        print("-" * 40)
        
        result = extract_atlantic_cigar_data(test['url'])
        
        print("Results:")
        print(f"  Price: ${result.get('price', 'N/A')} (Expected: ${test['expected_price']})")
        print(f"  Stock: {result.get('in_stock', 'N/A')} (Expected: {test['expected_stock']})")
        print(f"  Box Qty: {result.get('box_quantity', 'N/A')} (Expected: {test['expected_qty']})")
        print(f"  Discount: {result.get('discount_percent', 'N/A')}%")
        print(f"  Success: {result.get('success', 'N/A')}")
        
        if result.get('error'):
            print(f"  ERROR: {result['error']}")


if __name__ == "__main__":
    test_extractor()
