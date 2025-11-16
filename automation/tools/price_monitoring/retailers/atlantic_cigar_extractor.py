"""
Atlantic Cigar Extractor
Retailer-specific extraction rules for Atlantic Cigar (BigCommerce platform)
Handles variable box quantities, discounted pricing, stock detection
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class AtlanticCigarExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Atlantic Cigar URL
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
        
        # Look in product title
        title_elem = soup.find('h1', class_='productView-title')
        if title_elem:
            title = title_elem.get_text().strip()
            # Look for patterns like "Box of 25", "25ct", "(25)"
            qty_match = re.search(r'(?:box\s+of\s+|[\(\[]?)(\d+)(?:ct|[\)\]]?)', title, re.IGNORECASE)
            if qty_match:
                return int(qty_match.group(1))
        
        # Look in product description
        desc_elem = soup.find('div', class_='productView-info-value')
        if desc_elem:
            desc = desc_elem.get_text().strip()
            qty_match = re.search(r'(?:box\s+of\s+|quantity:\s*)(\d+)', desc, re.IGNORECASE)
            if qty_match:
                return int(qty_match.group(1))
        
        # Look for quantity selector options
        qty_options = soup.find_all('option', value=re.compile(r'\d+'))
        if qty_options:
            quantities = []
            for option in qty_options:
                try:
                    qty = int(option.get('value', '0'))
                    if qty > 5:  # Assume box quantities are > 5
                        quantities.append(qty)
                except ValueError:
                    continue
            if quantities:
                return max(quantities)  # Take the largest quantity as box size
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract box price and discount percentage"""
        
        # Look for price elements - BigCommerce typically uses these classes
        price_elements = soup.find_all(['span', 'div'], class_=re.compile(r'price'))
        
        prices = []
        for elem in price_elements:
            price_text = elem.get_text().strip()
            # Extract price numbers
            price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
            if price_match:
                try:
                    price = float(price_match.group(1))
                    if price > 10:  # Filter out obviously wrong prices
                        prices.append(price)
                except ValueError:
                    continue
        
        if not prices:
            return None, None
        
        # Look for crossed out or strikethrough prices (original price)
        original_price = None
        sale_price = None
        
        # Check for strikethrough or crossed out prices
        strikethrough_elems = soup.find_all(['del', 's']) + soup.find_all(attrs={'style': re.compile(r'text-decoration:\s*line-through', re.I)})
        for elem in strikethrough_elems:
            price_text = elem.get_text().strip()
            price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text.replace(',', ''))
            if price_match:
                try:
                    original_price = float(price_match.group(1))
                    break
                except ValueError:
                    continue
        
        # If we have multiple prices and one is crossed out, the other is the sale price
        if original_price and len(prices) >= 2:
            # Find the price that's not the original price
            for price in prices:
                if abs(price - original_price) > 0.01:  # Not the same as original
                    sale_price = price
                    break
        
        # Calculate discount percentage if we have both prices
        discount_percent = None
        if original_price and sale_price:
            discount_percent = ((original_price - sale_price) / original_price) * 100
            final_price = sale_price
        else:
            # Use the highest price as the box price (usually the most relevant)
            final_price = max(prices) if prices else None
        
        # Look for explicit "You Save" information
        save_elem = soup.find(text=re.compile(r'(?:you\s+save|save)\s*\$?(\d+(?:\.\d+)?)', re.I))
        if save_elem and not discount_percent:
            save_match = re.search(r'(?:you\s+save|save)\s*\$?([\d,]+\.?\d*)', save_elem, re.I)
            if save_match and final_price:
                save_amount = float(save_match.group(1))
                original_calc = final_price + save_amount
                discount_percent = (save_amount / original_calc) * 100
        
        return final_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock based on button text"""
        
        # Look for add to cart button
        add_to_cart = soup.find(['button', 'input'], attrs={
            'class': re.compile(r'add.*cart|cart.*add', re.I),
            'type': re.compile(r'submit|button', re.I)
        })
        
        if add_to_cart:
            button_text = add_to_cart.get_text().strip().upper()
            # In stock indicators
            if any(phrase in button_text for phrase in ['ADD TO CART', 'BUY NOW', 'PURCHASE']):
                return True
            # Out of stock indicators  
            if any(phrase in button_text for phrase in ['NOTIFY ME', 'SOLD OUT', 'OUT OF STOCK']):
                return False
        
        # Look for explicit stock status text
        stock_indicators = soup.find_all(text=re.compile(r'(?:in\s+stock|out\s+of\s+stock|sold\s+out|notify\s+me)', re.I))
        for indicator in stock_indicators:
            text = indicator.strip().upper()
            if 'IN STOCK' in text:
                return True
            if any(phrase in text for phrase in ['OUT OF STOCK', 'SOLD OUT', 'NOTIFY ME']):
                return False
        
        # Look for availability class names
        avail_elems = soup.find_all(attrs={'class': re.compile(r'(?:stock|availability)', re.I)})
        for elem in avail_elems:
            class_text = ' '.join(elem.get('class', [])).upper()
            text_content = elem.get_text().strip().upper()
            
            if any(phrase in class_text or phrase in text_content for phrase in ['INSTOCK', 'IN-STOCK', 'AVAILABLE']):
                return True
            if any(phrase in class_text or phrase in text_content for phrase in ['OUTOFSTOCK', 'OUT-OF-STOCK', 'UNAVAILABLE']):
                return False
        
        # Default to True if we can't determine (conservative approach)
        return True

# Test function for development
def test_extractor():
    """Test the extractor with sample URLs"""
    extractor = AtlanticCigarExtractor()
    
    # Test URLs - replace with actual Atlantic Cigar URLs
    test_urls = [
        # Add actual test URLs here
    ]
    
    for url in test_urls:
        print(f"\nTesting: {url}")
        result = extractor.extract_product_data(url)
        for key, value in result.items():
            print(f"  {key}: {value}")

if __name__ == "__main__":
    test_extractor()

def extract_atlantic_cigar_data(url: str) -> Dict:
    """Wrapper function for automation compatibility"""
    extractor = AtlanticCigarExtractor()
    return extractor.extract_product_data(url)
