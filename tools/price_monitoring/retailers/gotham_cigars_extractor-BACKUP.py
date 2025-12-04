#!/usr/bin/env python3
"""
Gotham Cigars Extractor - BigCommerce Platform
Using proven methodology from successful Hiland's extractor
Adapted for BigCommerce dynamic pricing and product options structure
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class GothamCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Exact same headers as successful Hiland's extractor
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Gotham Cigars URL"""
        try:
            # Rate limiting - 1 request per second (same as Hiland's)
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from product options
            box_qty = self._extract_box_quantity(soup)
            
            # Extract pricing information (adapted for BigCommerce)
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
        """Extract box quantity from BigCommerce product options table"""
        
        # Look for product options table with quantity information
        quantity_cells = soup.find_all(['td', 'th'], string=re.compile(r'box\s+of\s+\d+|pack\s+of\s+\d+|\d+\s*ct', re.I))
        
        box_quantities = []
        for cell in quantity_cells:
            qty_text = cell.get_text().strip()
            qty_match = re.search(r'box\s+of\s+(\d+)|(\d+)\s*ct', qty_text, re.I)
            if qty_match:
                qty = int(qty_match.group(1) if qty_match.group(1) else qty_match.group(2))
                if qty > 5:  # Filter for box quantities
                    box_quantities.append(qty)
        
        # Return the largest box quantity (prefer boxes over smaller packs)
        if box_quantities:
            return max(box_quantities)
        
        # Look for radio button labels or option text
        option_labels = soup.find_all(['label', 'span'], string=re.compile(r'box\s+of\s+\d+', re.I))
        for label in option_labels:
            label_text = label.get_text().strip()
            qty_match = re.search(r'box\s+of\s+(\d+)', label_text, re.I)
            if qty_match:
                qty = int(qty_match.group(1))
                if qty > 5:
                    return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract pricing from BigCommerce structure with dynamic pricing"""
        
        current_prices = []
        original_prices = []
        priority_current_prices = []  # Prices with sale context
        
        # Look for price elements with BigCommerce patterns
        price_selectors = ['.price', '.product-price', '.price-section']
        
        for selector in price_selectors:
            price_elements = soup.select(selector)
            
            for elem in price_elements:
                price_text = elem.get_text().strip()
                elem_classes = elem.get('class', [])
                
                # Skip empty elements
                if not price_text:
                    continue
                
                # Check if this price has sale context
                has_sale_context = (
                    'now:' in price_text.lower() or
                    'sale' in ' '.join(elem_classes).lower() or
                    'main' in ' '.join(elem_classes).lower()
                )
                
                # Extract price ranges (like "$40.99 - $184.99")
                price_range_match = re.search(r'\$?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*-\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
                if price_range_match:
                    min_price = float(price_range_match.group(1).replace(',', ''))
                    max_price = float(price_range_match.group(2).replace(',', ''))
                    # Use max price for box pricing
                    if 50 <= max_price <= 2000:
                        if has_sale_context:
                            priority_current_prices.append(max_price)
                        else:
                            current_prices.append(max_price)
                    continue
                
                # Extract single prices
                single_price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
                if single_price_match:
                    try:
                        price = float(single_price_match.group(1))
                        if 50 <= price <= 2000:
                            # Check if this is a strikethrough/MSRP price
                            is_original_price = (
                                elem.find_parent(['del', 's']) or
                                'msrp' in ' '.join(elem_classes).lower() or
                                'rrp' in ' '.join(elem_classes).lower() or
                                'was' in price_text.lower() or
                                (elem.has_attr('style') and 'line-through' in str(elem.get('style', '')))
                            )
                            
                            if is_original_price:
                                original_prices.append(price)
                            elif has_sale_context:
                                priority_current_prices.append(price)
                            else:
                                current_prices.append(price)
                                
                    except ValueError:
                        continue
        
        # Select best prices - prioritize sale context prices
        current_price = None
        if priority_current_prices:
            # Use the highest priority price (from sale context)
            current_price = max(priority_current_prices)
        elif current_prices:
            # Fallback to regular prices, but use minimum to avoid related products
            current_price = min(current_prices)
        
        original_price = max(original_prices) if original_prices else None
        
        # Calculate discount
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock based on BigCommerce indicators"""
        
        # Method 1: Look for actual buttons with specific text (most reliable)
        all_buttons = soup.find_all(['button', 'input'])
        
        for button in all_buttons:
            button_text = button.get_text().strip().upper()
            
            # In stock indicators (prioritize these)
            if any(phrase in button_text for phrase in ['ADD TO CART', 'BUY NOW', 'PURCHASE']):
                return True
                
            # Out of stock indicators
            if any(phrase in button_text for phrase in ['NOTIFY ME', 'NOTIFY WHEN AVAILABLE', 'EMAIL ME', 'SOLD OUT', 'OUT OF STOCK', 'UNAVAILABLE']):
                return False
        
        # Method 2: Look for add to cart button by regex (backup)
        cart_buttons = soup.find_all(['button', 'input'], string=re.compile(r'add\s+to\s+cart', re.I))
        if cart_buttons:
            return True
        
        # Method 3: Look for notify buttons by regex (backup)
        notify_buttons = soup.find_all(['button', 'input'], string=re.compile(r'notify\s+me|email\s+me', re.I))
        if notify_buttons:
            return False
        
        # Method 4: Look for out-of-stock text only in visible page content (exclude scripts)
        # Remove script and style tags to avoid false positives
        for script in soup(["script", "style"]):
            script.extract()
            
        visible_text = soup.get_text()
        if re.search(r'this\s+item\s+is\s+currently\s+out\s+of\s+stock', visible_text, re.I):
            return False
            
        # Default to True (conservative - assume in stock if unclear)
        return True


def extract_gotham_cigars_data(url: str) -> Dict:
    """
    Main extraction function for Gotham Cigars
    Compatible with CSV update workflow - same format as other extractors
    """
    extractor = GothamCigarsExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to the expected format (matching other extractors)
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
    """Test the extractor with the Romeo y Julieta URL"""
    
    test_url = 'https://www.gothamcigars.com/padron-5000-maduro/'
    
    print("Testing Gotham Cigars extraction...")
    print("=" * 50)
    print(f"URL: {test_url}")
    print("-" * 50)
    
    result = extract_gotham_cigars_data(test_url)
    
    if result['error']:
        print(f"ERROR: {result['error']}")
        if '403' in str(result['error']):
            print("  403 Forbidden - Bot detection active")
        elif '404' in str(result['error']):
            print("  404 Not Found - URL may be incorrect")
        else:
            print("  Network or parsing error")
    else:
        print(f"SUCCESS!")
        print(f"  Price: ${result['price']}")
        print(f"  Box Quantity: {result['box_quantity']}")
        print(f"  In Stock: {result['in_stock']}")
        if result['discount_percent']:
            print(f"  Discount: {result['discount_percent']:.1f}% off")
    
    print("=" * 50)

if __name__ == "__main__":
    test_extractor()
