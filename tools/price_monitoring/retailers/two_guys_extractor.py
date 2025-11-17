"""
Two Guys Cigars Extractor
Retailer-specific extraction rules for Two Guys Cigars
Handles standard e-commerce pricing, stock detection, and product metadata
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

class TwoGuysCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Two Guys Cigars URL
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
            
            # Extract pricing information
            box_price, discount_percent = self._extract_pricing(soup)
            
            # Extract box quantity
            box_qty = self._extract_box_quantity(soup)
            
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
    
    def _extract_pricing(self, soup: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
        """Extract price and discount information"""
        
        # Look for price elements - try multiple common patterns
        price_selectors = [
            '.price',
            '.product-price', 
            '.price-current',
            '[class*="price"]',
            '.money',
            '.amount'
        ]
        
        price = None
        
        # Try each selector
        for selector in price_selectors:
            price_elements = soup.select(selector)
            for elem in price_elements:
                price_text = elem.get_text().strip()
                # Extract price from text like "$454.99"
                price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
                if price_match:
                    try:
                        price_value = float(price_match.group(1))
                        if price_value > 10:  # Reasonable price filter
                            price = price_value
                            break
                    except ValueError:
                        continue
            if price:
                break
        
        # If specific selectors don't work, try broad search
        if not price:
            # Look for any element containing price-like pattern
            all_text = soup.get_text()
            price_matches = re.findall(r'\$(\d+\.?\d*)', all_text)
            for match in price_matches:
                try:
                    price_value = float(match)
                    if 50 <= price_value <= 2000:  # Reasonable cigar box price range
                        price = price_value
                        break
                except ValueError:
                    continue
        
        # Look for discount/sale information
        discount_percent = None
        
        # Check for strikethrough/original prices
        strikethrough_selectors = [
            'del', 's', '.line-through', '.strikethrough',
            '[style*="line-through"]', '.was-price', '.original-price'
        ]
        
        original_price = None
        for selector in strikethrough_selectors:
            elems = soup.select(selector)
            for elem in elems:
                price_text = elem.get_text().strip()
                price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
                if price_match:
                    try:
                        original_price = float(price_match.group(1))
                        break
                    except ValueError:
                        continue
            if original_price:
                break
        
        # Calculate discount if we have both prices
        if price and original_price and original_price > price:
            discount_percent = ((original_price - price) / original_price) * 100
        
        # Look for explicit "Save X%" or discount text
        if not discount_percent:
            discount_text = soup.get_text()
            save_match = re.search(r'save\s+(\d+)%', discount_text, re.IGNORECASE)
            if save_match:
                discount_percent = float(save_match.group(1))
        
        return price, discount_percent
    
    def _extract_box_quantity(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract box quantity from product information"""
        
        # Look in common places for box quantity information
        text_sources = []
        
        # Product title/name
        title_elems = soup.select('h1, .product-title, .product-name, .title')
        for elem in title_elems:
            text_sources.append(elem.get_text().strip())
        
        # Product description areas
        desc_selectors = [
            '.description', '.product-description', '.product-info',
            '.details', '.product-details', '.specs', '.specifications'
        ]
        
        for selector in desc_selectors:
            elems = soup.select(selector)
            for elem in elems:
                text_sources.append(elem.get_text().strip())
        
        # Look for box quantity patterns in all text sources
        for text in text_sources:
            # Pattern: "Box of XX", "XX ct", "(XX)", "Count: XX"
            qty_patterns = [
                r'box\s+of\s+(\d+)',
                r'(\d+)\s*ct\b',
                r'\((\d+)\)',
                r'count:?\s*(\d+)',
                r'quantity:?\s*(\d+)',
                r'(\d+)\s*count\b'
            ]
            
            for pattern in qty_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    try:
                        qty = int(match)
                        if 5 <= qty <= 50:  # Reasonable box quantity range
                            return qty
                    except ValueError:
                        continue
        
        # Default fallback - look in any text for reasonable numbers
        all_text = soup.get_text()
        numbers = re.findall(r'\b(\d+)\b', all_text)
        for num in numbers:
            try:
                qty = int(num)
                if 10 <= qty <= 30:  # Most common box sizes
                    return qty
            except ValueError:
                continue
        
        return None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Determine if product is in stock"""
        
        # Look for explicit stock status text first
        stock_text_patterns = [
            'out of stock', 'out-of-stock', 'sold out', 'unavailable',
            'in stock', 'in-stock', 'available'
        ]
        
        page_text = soup.get_text().lower()
        
        # Check for explicit out-of-stock indicators
        for pattern in ['out of stock', 'out-of-stock', 'sold out']:
            if pattern in page_text:
                return False
        
        # Check for explicit in-stock indicators  
        if 'in stock' in page_text or 'in-stock' in page_text:
            return True
        
        # Look for stock status in specific elements
        stock_indicators = [
            '.stock-status', '.availability', '.stock', '.in-stock', 
            '.out-of-stock', '.product-availability', '[class*="stock"]'
        ]
        
        for selector in stock_indicators:
            elems = soup.select(selector)
            for elem in elems:
                text = elem.get_text().strip().lower()
                if any(pattern in text for pattern in ['out of stock', 'sold out', 'unavailable']):
                    return False
                if any(pattern in text for pattern in ['in stock', 'available']):
                    return True
        
        # Check button text - "Notify Me" vs "Add to Cart"
        button_selectors = [
            'button', 'input[type="submit"]', '.btn', '.button',
            '.add-to-cart', '.notify-me', '.btn-cart', '.purchase-btn'
        ]
        
        for selector in button_selectors:
            buttons = soup.select(selector)
            for button in buttons:
                button_text = button.get_text().strip().lower()
                
                # Out of stock button indicators
                if any(phrase in button_text for phrase in [
                    'notify me', 'email me', 'back in stock', 'restock',
                    'out of stock', 'sold out', 'unavailable'
                ]):
                    return False
                
                # In stock button indicators
                if any(phrase in button_text for phrase in [
                    'add to cart', 'add to bag', 'buy now', 'purchase',
                    'add', 'cart'
                ]) and button_text not in ['notify me when back in stock']:
                    # Double check button isn't disabled
                    if not (button.get('disabled') or 'disabled' in str(button.get('class', []))):
                        return True
        
        # Check quantity selector for "0" or disabled state
        qty_selectors = soup.select('select option[selected], select option[value="0"]')
        for option in qty_selectors:
            if option.get('value') == '0' or option.get_text().strip() == '0':
                return False
        
        # Check for disabled quantity inputs
        qty_inputs = soup.select('input[type="number"], select')
        for input_elem in qty_inputs:
            if input_elem.get('disabled') or 'disabled' in str(input_elem.get('class', [])):
                return False
        
        # Look for specific Two Guys Cigars patterns
        # Check for "Notify Me" specifically
        if 'notify me' in page_text:
            return False
        
        # Default to in stock if no clear indication (conservative approach)
        # But if we found price but no clear stock indicators, lean towards in-stock
        return True

# Test function for development
def test_extractor():
    """Test the extractor with both in-stock and out-of-stock URLs"""
    extractor = TwoGuysCigarsExtractor()
    
    test_cases = [
        {
            'name': 'In-Stock Product',
            'url': 'https://www.2guyscigars.com/padron-ani-diplomatico-mad-160135/',
            'expected': {
                'price': 454.99,
                'stock': True,
                'box_qty': 25
            }
        },
        {
            'name': 'Out-of-Stock Product', 
            'url': 'https://www.2guyscigars.com/af-hemingway-best-seller-010112/',
            'expected': {
                'price': 243.99,
                'stock': False,
                'box_qty': 25
            }
        }
    ]
    
    print(f"Testing Two Guys Cigars Extractor")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"URL: {test_case['url']}")
        print("-" * 50)
        
        result = extractor.extract_product_data(test_case['url'])
        
        print("Results:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        print("\nValidation:")
        expected = test_case['expected']
        
        # Check price
        price_match = abs((result.get('box_price', 0) or 0) - expected['price']) < 1
        print(f"  Price: Expected ~${expected['price']}, Got ${result.get('box_price', 'N/A')} - {'PASS' if price_match else 'FAIL'}")
        
        # Check stock
        stock_match = result.get('in_stock') == expected['stock']
        print(f"  Stock: Expected {expected['stock']}, Got {result.get('in_stock')} - {'PASS' if stock_match else 'FAIL'}")
        
        # Check box qty
        qty_match = result.get('box_qty') == expected['box_qty']
        print(f"  Box Qty: Expected {expected['box_qty']}, Got {result.get('box_qty', 'N/A')} - {'PASS' if qty_match else 'FAIL'}")
        
        # Check for errors
        if result.get('error'):
            print(f"  ERROR: {result.get('error')}")
        else:
            print(f"  Status: No extraction errors")
        
        print()
    
    print("Test completed!")
    print("If all tests show PASS, the extractor is working correctly.")

if __name__ == "__main__":
    test_extractor()

def extract_two_guys_cigars_data(url: str) -> Dict:
    """Wrapper function for automation compatibility"""
    extractor = TwoGuysCigarsExtractor()
    return extractor.extract_product_data(url)
