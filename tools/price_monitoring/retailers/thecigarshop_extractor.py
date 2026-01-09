#!/usr/bin/env python3
"""
TheCigarShop Extractor
Clean e-commerce site with clear pricing and explicit stock indicators
Based on screenshots showing straightforward data presentation
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class TheCigarShopExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Minimal headers - proven approach
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from TheCigarShop URL
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
        """Extract box quantity from product title and page content"""
        
        # Priority 1: Look in main product title (very clear in screenshots)
        title_selectors = ['h1', '.product-title', '.page-title', 'h2']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title_text = title_elem.get_text().strip()
                
                # TheCigarShop specific patterns from screenshots
                qty_patterns = [
                    r'box\s+of\s+(\d+)',           # "Box Of 25", "Box Of 20"
                    r'(\d+)\s+count',              # "25 Count"
                    r'(\d+)ct',                    # "25ct"
                    r'(\d+)-pack',                 # "25-pack"
                    r'(\d+)\s+cigars?',            # "25 Cigars"
                ]
                
                for pattern in qty_patterns:
                    qty_match = re.search(pattern, title_text, re.I)
                    if qty_match:
                        qty = int(qty_match.group(1))
                        if qty >= 2:  # Allow any reasonable quantity
                            return qty
        
        # Priority 2: Look in page text or breadcrumbs
        page_text = soup.get_text()
        for pattern in [r'box\s+of\s+(\d+)', r'(\d+)\s+count']:
            qty_match = re.search(pattern, page_text, re.I)
            if qty_match:
                qty = int(qty_match.group(1))
                if qty >= 2:
                    return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract current price and calculate discount - prioritize structured data"""
        
        current_price = None
        original_price = None
        
        # Priority 1: Look for JSON-LD structured data (most reliable)
        json_scripts = soup.find_all('script', {'type': 'application/ld+json'})
        for script in json_scripts:
            try:
                import json
                data = json.loads(script.string)
                
                # Handle both single objects and arrays
                if isinstance(data, list):
                    data = data[0] if data else {}
                
                # Look for offers data
                offers = data.get('offers', {})
                if offers and isinstance(offers, dict):
                    price_str = offers.get('price', '')
                    if price_str:
                        try:
                            price = float(price_str)
                            if 50 <= price <= 1500:
                                current_price = price
                                print(f"  Found JSON-LD price: ${price}")
                                break
                        except ValueError:
                            continue
                            
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        
        # Priority 2: Check if we have a clear sale scenario (strikethrough present)
        strikethrough_prices = []
        
        # Check <del> and <s> tags
        for elem in soup.select('del, s'):
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$(\d{1,4}(?:\.\d{2})?)', price_text)
            
            if price_match:
                try:
                    price = float(price_match.group(1))
                    if 50 <= price <= 1500:
                        strikethrough_prices.append(price)
                except ValueError:
                    continue
        
        # Also check for elements with strikethrough styling
        for elem in soup.find_all(style=re.compile(r'text-decoration:\s*line-through', re.I)):
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$(\d{1,4}(?:\.\d{2})?)', price_text)
            
            if price_match:
                try:
                    price = float(price_match.group(1))
                    if 50 <= price <= 1500:
                        strikethrough_prices.append(price)
                except ValueError:
                    continue
        
        if strikethrough_prices:
            original_price = max(strikethrough_prices)
            
            # If we already have current price from JSON-LD, use it
            if current_price and current_price < original_price:
                pass  # We have both prices, good to go
            else:
                # SALE SCENARIO - Use enhanced logic for HTML parsing
                page_text = soup.get_text()
                all_price_matches = re.findall(r'\$(\d{1,4}(?:\.\d{2})?)', page_text)
                
                all_prices = []
                for price_str in all_price_matches:
                    try:
                        price = float(price_str)
                        if 50 <= price <= 1500:
                            all_prices.append(price)
                    except ValueError:
                        continue
                
                unique_prices = sorted(list(set(all_prices)), reverse=True)
                
                # Find current price - should be different from original and lower
                potential_current = [p for p in unique_prices if p != original_price and p < original_price]
                if potential_current:
                    current_price = max(potential_current)
        
        elif not current_price:
            # REGULAR PRICING - Use traditional CSS selector approach
            main_price_selectors = [
                '.price',
                '.product-price', 
                '.current-price',
                '.sale-price',
                'span[class*="price"]',
                'div[class*="price"]'
            ]
            
            for selector in main_price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem and not price_elem.find_parent(['del', 's']):
                    price_text = price_elem.get_text().strip()
                    price_match = re.search(r'\$(\d{1,4}(?:\.\d{2})?)', price_text)
                    
                    if price_match:
                        try:
                            price = float(price_match.group(1))
                            if 100 <= price <= 1500:  # Reasonable range for main products
                                current_price = price
                                break
                        except ValueError:
                            continue
            
            # Fallback for regular pricing - highest reasonable price from page
            if not current_price:
                page_text = soup.get_text()
                all_prices = re.findall(r'\$(\d{1,4}(?:\.\d{2})?)', page_text)
                
                valid_prices = []
                for price_str in all_prices:
                    try:
                        price = float(price_str)
                        if 200 <= price <= 1000:  # Focus on main product range
                            valid_prices.append(price)
                    except ValueError:
                        continue
                
                if valid_prices:
                    current_price = max(valid_prices)  # Take highest as main price
        
        # Calculate discount percentage
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check stock status - TheCigarShop has very explicit indicators"""
        
        # Priority 1: Check for explicit "Out Of Stock" button (very clear indicator)
        out_of_stock_button = soup.find(['button', 'input'], string=re.compile(r'out\s+of\s+stock', re.I))
        if out_of_stock_button:
            return False
        
        # Priority 2: Check for "SOLD OUT" overlay or text
        page_text = soup.get_text().lower()
        if 'sold out' in page_text:
            return False
        
        # Priority 3: Check for other out of stock indicators
        out_of_stock_phrases = ['out of stock', 'unavailable', 'temporarily unavailable']
        for phrase in out_of_stock_phrases:
            if phrase in page_text:
                return False
        
        # Priority 4: Check for "Add To Cart" button (positive indicator)
        add_cart_button = soup.find(['button', 'input'], string=re.compile(r'add\s+to\s+cart', re.I))
        if add_cart_button:
            is_disabled = add_cart_button.get('disabled') is not None
            if not is_disabled:
                return True
        
        # Priority 5: Look for other purchase indicators
        purchase_buttons = soup.find_all(['button', 'input'], string=re.compile(r'buy|purchase|order', re.I))
        for button in purchase_buttons:
            is_disabled = button.get('disabled') is not None
            if not is_disabled:
                return True
        
        # Priority 6: Check for quantity selector (usually means purchaseable)
        quantity_input = soup.find(['input', 'select'], {'name': re.compile(r'quantity', re.I)})
        if quantity_input:
            return True
        
        # Default: If we have a price and no explicit out-of-stock indicators, assume in stock
        has_price = bool(re.search(r'\$\d+', page_text))
        return has_price


def extract_thecigarshop_data(url: str) -> Dict:
    """
    Main extraction function for TheCigarShop
    Compatible with CSV update workflow
    """
    extractor = TheCigarShopExtractor()
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
    """Test the extractor with the provided TheCigarShop URLs"""
    
    test_urls = [
        'https://www.thecigarshop.com/arturo-fuente-hemingway-signature-natural-box-of-2.html',  # $289.97, Box of 25, in stock
        'https://www.thecigarshop.com/copy-of-20-acre-farm-by-drew-estate-robus-45431665.html',  # $213.48 (was $304.97), Box of 20, in stock
        'https://www.thecigarshop.com/fuente-fuente-opusx-templo-de-oro-8-box-of-20.html',       # $799.97, Box of 20, out of stock
    ]
    
    print("Testing TheCigarShop extraction...")
    print("=" * 60)
    
    for i, url in enumerate(test_urls):
        product_name = url.split('/')[-1].replace('-', ' ').title().replace('.Html', '')
        print(f"\nTest {i+1}: {product_name}")
        print("-" * 40)
        result = extract_thecigarshop_data(url)
        
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
