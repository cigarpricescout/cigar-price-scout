"""
Neptune Cigar Extractor - DEBUG VERSION
Debug the Romeo y Julieta 1875 Churchill pricing extraction

Expected: $183.95 for Box of 25
Getting: $68.55 (incorrect)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class NeptuneCigarExtractorDebug:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data_debug(self, url: str) -> Dict:
        """Debug version with extensive logging"""
        try:
            print(f"[DEBUG] Fetching: {url}")
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            print("\n=== DEBUGGING TABLE STRUCTURE ===")
            
            # Find all tables and analyze them
            tables = soup.find_all('table')
            print(f"Found {len(tables)} tables on page")
            
            for i, table in enumerate(tables):
                print(f"\n--- Table {i+1} ---")
                rows = table.find_all('tr')
                print(f"Table has {len(rows)} rows")
                
                for j, row in enumerate(rows):
                    cells = row.find_all(['td', 'th'])
                    row_text = row.get_text().strip()
                    print(f"  Row {j+1}: {row_text}")
                    
                    # Extract all prices from this row
                    price_matches = re.findall(r'\$(\d+\.?\d*)', row_text)
                    if price_matches:
                        prices = [float(p) for p in price_matches]
                        print(f"    Prices found: {prices}")
                        
                        # Check if this looks like a box row
                        if any(term in row_text.lower() for term in ['box', '25', '20', '23', '29']):
                            print(f"    *** POTENTIAL BOX ROW ***")
            
            print("\n=== CURRENT EXTRACTOR RESULTS ===")
            
            # Run the original extraction methods
            box_qty = self._extract_box_quantity_debug(soup)
            box_price, discount_percent = self._extract_pricing_debug(soup)
            in_stock = self._check_stock_status_debug(soup)
            
            print(f"Final Results:")
            print(f"  Box Quantity: {box_qty}")
            print(f"  Box Price: ${box_price}")
            print(f"  In Stock: {in_stock}")
            print(f"  Discount: {discount_percent}%")
            
            return {
                'box_price': box_price,
                'box_qty': box_qty,
                'in_stock': in_stock,
                'discount_percent': discount_percent,
                'error': None
            }
            
        except Exception as e:
            print(f"[ERROR] {str(e)}")
            return {
                'box_price': None,
                'box_qty': None,
                'in_stock': False,
                'discount_percent': None,
                'error': str(e)
            }
    
    def _extract_box_quantity_debug(self, soup: BeautifulSoup) -> Optional[int]:
        """Debug version of box quantity extraction"""
        print("\n=== BOX QUANTITY EXTRACTION ===")
        
        box_patterns = [
            r'box\s+of\s+(\d+)',
            r'box\s*-\s*(\d+)',
            r'(\d+)\s*count\s*box'
        ]
        
        text_elements = soup.find_all(['td', 'th', 'span', 'div'])
        
        for elem in text_elements:
            text = elem.get_text().strip()
            for pattern in box_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        qty = int(match.group(1))
                        if qty >= 10:
                            print(f"Found box quantity: {qty} from text: {text}")
                            return qty
                    except (ValueError, IndexError):
                        continue
        
        print("No box quantity found in specific elements, checking page text...")
        
        page_text = soup.get_text()
        for pattern in box_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                try:
                    qty = int(match.group(1))
                    if qty >= 10:
                        print(f"Found box quantity from page text: {qty}")
                        return qty
                except (ValueError, IndexError):
                    continue
        
        print("No box quantity found")
        return None
    
    def _extract_pricing_debug(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Debug version of pricing extraction"""
        print("\n=== PRICING EXTRACTION ===")
        
        current_price = None
        msrp_price = None
        discount_percent = None
        
        table_rows = soup.find_all('tr')
        print(f"Analyzing {len(table_rows)} table rows for pricing...")
        
        for i, row in enumerate(table_rows):
            row_text = row.get_text().strip()
            print(f"\nRow {i+1}: {row_text}")
            
            # Skip single cigar rows
            if 'single' in row_text.lower():
                print("  -> Skipping single cigar row")
                continue
            
            # Look for box rows
            if 'box' in row_text.lower():
                print("  -> Found BOX row!")
                
                price_cells = row.find_all(['td', 'th'])
                row_prices = []
                
                for j, cell in enumerate(price_cells):
                    cell_text = cell.get_text().strip()
                    price_matches = re.findall(r'\$(\d+\.?\d*)', cell_text)
                    print(f"    Cell {j+1}: '{cell_text}' -> Prices: {price_matches}")
                    
                    for price_text in price_matches:
                        try:
                            price_val = float(price_text)
                            if 50 <= price_val <= 2000:
                                row_prices.append(price_val)
                                print(f"      Valid price: ${price_val}")
                        except ValueError:
                            continue
                
                print(f"  -> Row prices found: {row_prices}")
                
                if len(row_prices) >= 2:
                    msrp_price = max(row_prices)
                    current_price = min(row_prices)
                    print(f"  -> Selected MSRP: ${msrp_price}, Sale Price: ${current_price}")
                    
                    if msrp_price > current_price:
                        print("  -> Valid pricing pair found, using these prices")
                        break
                elif len(row_prices) == 1:
                    current_price = row_prices[0]
                    print(f"  -> Single price found: ${current_price}")
                    break
        
        if not current_price:
            print("\nNo box pricing found in table, looking for general price elements...")
            
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
                            print(f"Found general price: ${price_val} from: {text}")
                    except ValueError:
                        continue
            
            if all_prices:
                current_price = max(all_prices)
                print(f"Using highest general price as box price: ${current_price}")
        
        # Calculate discount
        if msrp_price and current_price and msrp_price > current_price:
            discount_percent = ((msrp_price - current_price) / msrp_price) * 100
            print(f"Calculated discount: {discount_percent:.1f}%")
        
        return current_price, discount_percent
    
    def _check_stock_status_debug(self, soup: BeautifulSoup) -> bool:
        """Debug version of stock status check"""
        print("\n=== STOCK STATUS CHECK ===")
        
        page_text = soup.get_text()
        
        if re.search(r'backorder', page_text, re.IGNORECASE):
            print("Found 'backorder' text -> OUT OF STOCK")
            return False
        
        if re.search(r'in\s*stock', page_text, re.IGNORECASE):
            print("Found 'in stock' text -> IN STOCK")
            return True
        
        email_buttons = soup.find_all(['button', 'input', 'a'], 
                                     string=re.compile(r'email\s*me\s*when\s*available', re.I))
        if email_buttons:
            print("Found 'Email Me When Available' button -> OUT OF STOCK")
            return False
        
        cart_buttons = soup.find_all(['button', 'input', 'a'], 
                                    string=re.compile(r'add\s*to\s*cart', re.I))
        if cart_buttons:
            print("Found 'Add to Cart' button -> IN STOCK")
            return True
        
        print("No clear stock indicators found, defaulting to IN STOCK")
        return True


def test_romeo_debug():
    """Test specifically with Romeo y Julieta 1875 Churchill"""
    extractor = NeptuneCigarExtractorDebug()
    
    # The problematic URL
    url = "https://www.neptunecigar.com/cigars/romeo-y-julieta-1875-churchill"
    
    print("=== DEBUGGING ROMEO Y JULIETA 1875 CHURCHILL ===")
    print(f"Expected: $183.95 for Box of 25")
    print(f"Current result: $68.55 (incorrect)")
    print(f"URL: {url}")
    print("=" * 60)
    
    result = extractor.extract_product_data_debug(url)
    
    print("\n" + "=" * 60)
    print("DEBUGGING COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_romeo_debug()
