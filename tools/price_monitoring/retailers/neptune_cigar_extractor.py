"""
Neptune Cigar Extractor
Retailer-specific extraction rules for neptunecigar.com (Custom platform)
Handles table-based pricing structure, variable box quantities, backorder detection

Platform Analysis: Custom e-commerce with clean table structure
- MSRP vs OUR PRICE with YOU SAVE calculation
- Clear stock status (IN STOCK vs BACKORDER)
- Variable box quantities (23, 25, 29, etc.)
- Button-based stock confirmation (Add to Cart vs Email Me When Available)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class NeptuneCigarExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Neptune Cigar URL
        Returns: {
            'box_price': float or None,
            'box_qty': int or None,
            'in_stock': bool,
            'discount_percent': float or None,
            'error': str or None
        }
        """
        try:
            # Rate limiting - 1 request per second (CRITICAL for bot detection avoidance)
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity from table structure
            box_qty = self._extract_box_quantity(soup)
            
            # Extract pricing information from table
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
        """
        Extract box quantity from Neptune's table structure
        Neptune uses format: "BOX OF 25", "BOX OF 23", "BOX OF 29"
        """
        
        # Look for "BOX OF XX" text in table cells
        box_patterns = [
            r'box\s+of\s+(\d+)',
            r'box\s*-\s*(\d+)',
            r'(\d+)\s*count\s*box'
        ]
        
        # Search in table cells and other elements
        text_elements = soup.find_all(['td', 'th', 'span', 'div'])
        
        for elem in text_elements:
            text = elem.get_text().strip()
            for pattern in box_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        qty = int(match.group(1))
                        # Filter for reasonable box quantities (>=10)
                        if qty >= 10:
                            return qty
                    except (ValueError, IndexError):
                        continue
        
        # Fallback: search entire page text
        page_text = soup.get_text()
        for pattern in box_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                try:
                    qty = int(match.group(1))
                    if qty >= 10:
                        return qty
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract box pricing from Neptune's table structure
        Neptune shows: MSRP | OUR PRICE | YOU SAVE | AVAILABILITY
        Target box row (not single row)
        """
        
        current_price = None
        msrp_price = None
        discount_percent = None
        
        # Look for table rows - Neptune uses table structure
        table_rows = soup.find_all('tr')
        
        for row in table_rows:
            row_text = row.get_text().strip()
            
            # Skip single cigar rows, target box rows
            if 'single' in row_text.lower():
                continue
            
            # Look for box rows
            if 'box' in row_text.lower():
                # Extract all prices from this row
                price_cells = row.find_all(['td', 'th'])
                row_prices = []
                
                for cell in price_cells:
                    cell_text = cell.get_text().strip()
                    # Find dollar amounts
                    price_matches = re.findall(r'\$(\d+\.?\d*)', cell_text)
                    for price_text in price_matches:
                        try:
                            price_val = float(price_text)
                            # Filter reasonable box prices (50-2000 range)
                            if 50 <= price_val <= 2000:
                                row_prices.append(price_val)
                        except ValueError:
                            continue
                
                # Neptune typically shows: [MSRP, OUR_PRICE, YOU_SAVE]
                if len(row_prices) >= 2:
                    # First price is usually MSRP, second is sale price
                    msrp_price = max(row_prices)  # Higher price = MSRP
                    current_price = min(row_prices)  # Lower price = sale price
                    
                    # Make sure we have the right order
                    if msrp_price > current_price:
                        break  # Found valid pricing pair
                elif len(row_prices) == 1:
                    # Only one price found
                    current_price = row_prices[0]
                    break
        
        # If no box pricing found in table, look for general price elements
        if not current_price:
            price_elements = soup.find_all(['span', 'div'], class_=re.compile(r'price', re.I))
            
            all_prices = []
            for elem in price_elements:
                text = elem.get_text().strip()
                price_match = re.search(r'\$(\d+\.?\d*)', text)
                if price_match:
                    try:
                        price_val = float(price_match.group(1))
                        if 50 <= price_val <= 2000:
                            all_prices.append(price_val)
                    except ValueError:
                        continue
            
            if all_prices:
                # Use highest price as likely box price
                current_price = max(all_prices)
        
        # Calculate discount percentage
        if msrp_price and current_price and msrp_price > current_price:
            discount_percent = ((msrp_price - current_price) / msrp_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """
        Check stock status using Neptune's availability indicators
        
        Stock Detection Hierarchy:
        1. "BACKORDER" text → Out of stock (check this FIRST)
        2. "IN STOCK" text → In stock
        3. "Email Me When Available" button → Out of stock
        4. "Add to Cart" button → In stock
        """
        
        page_text = soup.get_text()
        
        # Priority 1: Look for BACKORDER first (most important for Neptune)
        if re.search(r'backorder', page_text, re.IGNORECASE):
            return False
        
        # Priority 2: Look for explicit IN STOCK text
        if re.search(r'in\s*stock', page_text, re.IGNORECASE):
            return True
        
        # Priority 3: Check button text
        # Neptune uses "Add to Cart" for in-stock, "Email Me When Available" for out-of-stock
        
        # Look for "Email Me When Available" (out of stock indicator)
        email_buttons = soup.find_all(['button', 'input', 'a'], 
                                     string=re.compile(r'email\s*me\s*when\s*available', re.I))
        if email_buttons:
            return False
        
        # Look for "Add to Cart" (in stock indicator) 
        cart_buttons = soup.find_all(['button', 'input', 'a'], 
                                    string=re.compile(r'add\s*to\s*cart', re.I))
        if cart_buttons:
            # Double-check: if we have Add to Cart but also backorder text, it's out of stock
            if re.search(r'backorder', page_text, re.IGNORECASE):
                return False
            return True
        
        # Priority 4: Look for other stock indicators
        out_of_stock_patterns = [
            r'out\s*of\s*stock',
            r'sold\s*out',
            r'unavailable',
            r'temporarily\s*unavailable'
        ]
        
        for pattern in out_of_stock_patterns:
            if re.search(pattern, page_text, re.IGNORECASE):
                return False
        
        # Priority 5: Look for availability in table structure specifically
        availability_elements = soup.find_all(text=re.compile(r'availability', re.I))
        for elem in availability_elements:
            parent = elem.parent
            if parent:
                # Look for backorder or in stock in nearby text
                context = parent.get_text()
                if 'backorder' in context.lower():
                    return False
                if 'in stock' in context.lower():
                    return True
        
        # Default to True if we can't determine (conservative approach for Neptune)
        return True


# Standalone function for integration with existing updater scripts
def extract_neptune_cigar_data(url: str) -> Dict:
    """
    Standalone function to extract data from Neptune Cigar URL
    Returns standardized result format for integration with CSV updaters
    """
    extractor = NeptuneCigarExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to standard format expected by updater scripts
    if result.get('error'):
        return {
            'success': False,
            'error': result['error'],
            'price': None,
            'in_stock': False,
            'box_quantity': None,
            'discount_percent': None
        }
    else:
        return {
            'success': True,
            'error': None,
            'price': result.get('box_price'),
            'in_stock': result.get('in_stock'),
            'box_quantity': result.get('box_qty'),
            'discount_percent': result.get('discount_percent')
        }


# Test function for development
def test_extractor():
    """Test the extractor with the provided sample URLs"""
    extractor = NeptuneCigarExtractor()
    
    # Test URLs from provided examples
    test_urls = [
        # In stock with discount - Box of 25
        "https://www.neptunecigar.com/cigars/arturo-fuente-hemingway-classic",
        
        # Backorder - Box of 29
        "https://www.neptunecigar.com/cigars/arturo-fuente-opus-x-robusto",
        
        # In stock - Box of 23
        "https://www.neptunecigar.com/cigars/my-father-the-judge-grand-robusto"
    ]
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n=== Test {i}: {url} ===")
        result = extractor.extract_product_data(url)
        
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        # Additional analysis
        if result.get('box_price') and result.get('box_qty'):
            per_stick = result['box_price'] / result['box_qty']
            print(f"  price_per_stick: ${per_stick:.2f}")


if __name__ == "__main__":
    test_extractor()
