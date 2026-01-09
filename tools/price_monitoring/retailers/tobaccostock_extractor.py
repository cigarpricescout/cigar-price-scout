#!/usr/bin/env python3
"""
TobaccoStock Extractor
Clean e-commerce site with clear pricing and explicit stock indicators
Based on screenshots showing straightforward data presentation and structured data
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class TobaccoStockExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Minimal headers - proven approach
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from TobaccoStock URL
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
                
                # TobaccoStock specific patterns from screenshots
                qty_patterns = [
                    r'box\s+of\s+(\d+)',           # "Box of 24", "Box of 25"  
                    r'(\d+)\s+pack\s+of\s+\d+',    # "8 pack of 5" -> extract 8
                    r'(\d+)\s+count',              # "24 Count"
                    r'(\d+)ct',                    # "24ct"
                    r'(\d+)-pack',                 # "24-pack"
                    r'(\d+)\s+cigars?',            # "24 Cigars"
                ]
                
                for pattern in qty_patterns:
                    qty_match = re.search(pattern, title_text, re.I)
                    if qty_match:
                        qty = int(qty_match.group(1))
                        if qty >= 2:  # Allow any reasonable quantity
                            return qty
        
        # Priority 2: Look in page text or product description
        page_text = soup.get_text()
        for pattern in [r'box\s+of\s+(\d+)', r'(\d+)\s+count', r'(\d+)\s+pack']:
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
        
        # Priority 1: Look for Open Graph price data (most reliable)
        og_price_elem = soup.find('meta', {'property': 'og:price:amount'})
        if og_price_elem:
            price_content = og_price_elem.get('content', '').strip()
            if price_content:
                try:
                    price = float(price_content)
                    if 1 <= price <= 2000:  # Reasonable range for TobaccoStock
                        current_price = price
                        print(f"  Found OG price: ${price}")
                except ValueError:
                    pass
        
        # Priority 2: Look for JSON-LD structured data as backup
        if not current_price:
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
                                if 1 <= price <= 2000:
                                    current_price = price
                                    print(f"  Found JSON-LD price: ${price}")
                                    break
                            except ValueError:
                                continue
                                
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        
        # Priority 3: Look for strikethrough prices (original/MSRP)
        strikethrough_prices = []
        
        # Check <del> and <s> tags
        for elem in soup.select('del, s'):
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$(\d{1,4}(?:\.\d{2})?)', price_text)
            
            if price_match:
                try:
                    price = float(price_match.group(1))
                    if 1 <= price <= 2000:
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
                    if 1 <= price <= 2000:
                        strikethrough_prices.append(price)
                except ValueError:
                    continue
        
        if strikethrough_prices:
            original_price = max(strikethrough_prices)
            
            # If we don't have current price from structured data, find it from HTML
            if not current_price:
                page_text = soup.get_text()
                all_price_matches = re.findall(r'\$(\d{1,4}(?:\.\d{2})?)', page_text)
                
                all_prices = []
                for price_str in all_price_matches:
                    try:
                        price = float(price_str)
                        if 1 <= price <= 2000:
                            all_prices.append(price)
                    except ValueError:
                        continue
                
                unique_prices = sorted(list(set(all_prices)), reverse=True)
                
                # Find current price - should be different from original and lower
                potential_current = [p for p in unique_prices if p != original_price and p < original_price]
                if potential_current:
                    current_price = max(potential_current)
        
        # Priority 4: HTML price selectors as final fallback
        if not current_price:
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
                            if 5 <= price <= 1000:  # Focus on main product range
                                current_price = price
                                break
                        except ValueError:
                            continue
        
        # Final fallback - highest reasonable price from page
        if not current_price:
            page_text = soup.get_text()
            all_prices = re.findall(r'\$(\d{1,4}(?:\.\d{2})?)', page_text)
            
            valid_prices = []
            for price_str in all_prices:
                try:
                    price = float(price_str)
                    if 10 <= price <= 500:  # Focus on main product range
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
        """Check stock status - TobaccoStock uses specific button text patterns"""
        
        page_text = soup.get_text().lower()
        
        # Priority 1: Check for "Sold out" button (definitive out of stock)
        sold_out_button = soup.find(['button', 'input'], string=re.compile(r'sold\s+out', re.I))
        if sold_out_button:
            return False
        
        # Priority 2: Check for "Add to Cart" button (definitive in stock)
        add_cart_button = soup.find(['button', 'input'], string=re.compile(r'add\s+to\s+cart', re.I))
        if add_cart_button:
            return True
        
        # Priority 3: Check for "NOTIFY ME" button (out of stock indicator)
        notify_button = soup.find(['button', 'input'], string=re.compile(r'notify\s+me', re.I))
        if notify_button:
            return False
        
        # Priority 4: Check for explicit text patterns in page content
        if 'sold out' in page_text:
            return False
        
        if 'add to cart' in page_text:
            return True
        
        # Priority 5: Check other explicit out of stock indicators
        out_of_stock_patterns = [
            r'low\s+stock\s+only\s+0\s+left',
            r'low\s+stock\s+only\s+-\d+\s+left',
            r'out\s+of\s+stock',
            r'unavailable'
        ]
        
        for pattern in out_of_stock_patterns:
            if re.search(pattern, page_text):
                return False
        
        # Priority 6: Check for positive stock indicators
        if 'in stock' in page_text:
            return True
        
        # "Low Stock only X Left" where X > 0
        low_stock_match = re.search(r'low\s+stock\s+only\s+(\d+)\s+left', page_text)
        if low_stock_match:
            stock_qty = int(low_stock_match.group(1))
            return stock_qty > 0
        
        # Priority 7: Look for other purchase indicators
        purchase_buttons = soup.find_all(['button', 'input'], string=re.compile(r'buy|purchase|order', re.I))
        for button in purchase_buttons:
            is_disabled = button.get('disabled') is not None
            if not is_disabled:
                return True
        
        # Priority 8: Check for quantity selector (indicates purchaseable)
        quantity_input = soup.find(['input', 'select'], {'name': re.compile(r'quantity', re.I)})
        if quantity_input and not quantity_input.get('disabled'):
            return True
        
        # Default: Conservative approach - assume out of stock unless we found positive indicators
        return False


def extract_tobaccostock_data(url: str) -> Dict:
    """
    Main extraction function for TobaccoStock
    Compatible with CSV update workflow
    """
    extractor = TobaccoStockExtractor()
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
    """Test the extractor with the provided TobaccoStock URLs"""
    
    test_urls = [
        'https://www.tobaccostock.com/products/ashton-vsg-virgin-sun-grown-robusto-cigars-box-of-24',  # $289.99, Box of 24, in stock
        'https://www.tobaccostock.com/products/arturo-fuente-hemingway-short-story-cigars-box-of-25',  # $149.15, Box of 25, out of stock
        'https://www.tobaccostock.com/products/game-leaf-cigarillos-5-for-2-99-sweet-aroma-8-pack-of-5',  # $13.20 (was $21.99), 8 pack, out of stock
    ]
    
    print("Testing TobaccoStock extraction...")
    print("=" * 60)
    
    for i, url in enumerate(test_urls):
        product_name = url.split('/')[-1].replace('-', ' ').title()
        print(f"\nTest {i+1}: {product_name}")
        print("-" * 40)
        result = extract_tobaccostock_data(url)
        
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
