"""
Neptune Cigar Extractor - FIXED VERSION
Addresses the Romeo y Julieta 1875 Churchill pricing issue ($68.55 -> $183.95)

Key fixes:
1. More specific box row identification 
2. Better price cell prioritization
3. Enhanced table structure parsing
4. Fallback mechanisms for edge cases
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
            # Rate limiting - 1 request per second
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity first (helps identify correct pricing row)
            box_qty = self._extract_box_quantity(soup)
            
            # Extract pricing using improved logic
            box_price, discount_percent = self._extract_pricing_improved(soup, box_qty)
            
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
        """Extract box quantity - unchanged from original"""
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
    
    def _extract_pricing_improved(self, soup: BeautifulSoup, box_qty: Optional[int] = None) -> Tuple[Optional[float], Optional[float]]:
        """
        IMPROVED pricing extraction with better box row targeting
        
        Strategy:
        1. Find rows that explicitly mention box quantities
        2. Prioritize rows with higher price values (box prices > single prices)
        3. Use quantity information to validate correct row
        4. Better price cell selection logic
        """
        
        current_price = None
        msrp_price = None
        discount_percent = None
        
        # Find all table rows
        table_rows = soup.find_all('tr')
        
        # Strategy 1: Look for rows with explicit box quantities
        box_price_candidates = []
        
        for row in table_rows:
            row_text = row.get_text().strip().lower()
            
            # Skip obvious single cigar rows
            if any(term in row_text for term in ['single', '1 cigar', 'each']):
                continue
            
            # Target box rows more specifically
            box_indicators = [
                'box',
                f'{box_qty}' if box_qty else None,
                '20', '23', '25', '29'  # Common box quantities
            ]
            
            # Check if this row contains box indicators
            has_box_indicator = any(indicator and indicator in row_text 
                                  for indicator in box_indicators)
            
            if has_box_indicator:
                # Extract all prices from this row
                price_cells = row.find_all(['td', 'th'])
                row_prices = []
                
                for cell in price_cells:
                    cell_text = cell.get_text().strip()
                    price_matches = re.findall(r'\$(\d+\.?\d*)', cell_text)
                    
                    for price_text in price_matches:
                        try:
                            price_val = float(price_text)
                            # Box prices should be substantial (typically $80+)
                            if 80 <= price_val <= 2000:
                                row_prices.append(price_val)
                        except ValueError:
                            continue
                
                if row_prices:
                    # Store candidate with priority score
                    priority = 0
                    
                    # Higher priority for explicit "box" mentions
                    if 'box' in row_text:
                        priority += 10
                    
                    # Higher priority for matching quantity
                    if box_qty and str(box_qty) in row_text:
                        priority += 20
                    
                    # Higher priority for higher price values (box vs single)
                    priority += max(row_prices) / 10  # Price-based priority
                    
                    box_price_candidates.append({
                        'prices': row_prices,
                        'priority': priority,
                        'row_text': row_text
                    })
        
        # Select best candidate
        if box_price_candidates:
            # Sort by priority (highest first)
            box_price_candidates.sort(key=lambda x: x['priority'], reverse=True)
            best_candidate = box_price_candidates[0]
            
            prices = best_candidate['prices']
            
            if len(prices) >= 2:
                # Multiple prices: likely MSRP and sale price
                msrp_price = max(prices)
                current_price = min(prices)
                
                # Validate that MSRP > sale price
                if msrp_price <= current_price:
                    current_price = max(prices)  # Use highest as current price
            else:
                # Single price found
                current_price = prices[0]
        
        # Strategy 2: Fallback to general price elements if no box pricing found
        if not current_price:
            price_elements = soup.find_all(['span', 'div'], class_=re.compile(r'price', re.I))
            all_prices = []
            
            for elem in price_elements:
                text = elem.get_text().strip()
                price_match = re.search(r'\$(\d+\.?\d*)', text)
                if price_match:
                    try:
                        price_val = float(price_match.group(1))
                        # Filter for box-range prices
                        if 80 <= price_val <= 2000:
                            all_prices.append(price_val)
                    except ValueError:
                        continue
            
            if all_prices:
                # Use highest price as likely box price
                current_price = max(all_prices)
        
        # Strategy 3: Last resort - look for any substantial prices
        if not current_price:
            all_text_prices = re.findall(r'\$(\d+\.?\d*)', soup.get_text())
            substantial_prices = []
            
            for price_text in all_text_prices:
                try:
                    price_val = float(price_text)
                    if 100 <= price_val <= 2000:  # Very conservative for box prices
                        substantial_prices.append(price_val)
                except ValueError:
                    continue
            
            if substantial_prices:
                # Use most common substantial price or highest
                from collections import Counter
                price_counts = Counter(substantial_prices)
                if price_counts:
                    current_price = price_counts.most_common(1)[0][0]
        
        # Calculate discount percentage
        if msrp_price and current_price and msrp_price > current_price:
            discount_percent = ((msrp_price - current_price) / msrp_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Stock status check - unchanged from original"""
        page_text = soup.get_text()
        
        # Priority 1: Look for BACKORDER first
        if re.search(r'backorder', page_text, re.IGNORECASE):
            return False
        
        # Priority 2: Look for explicit IN STOCK text
        if re.search(r'in\s*stock', page_text, re.IGNORECASE):
            return True
        
        # Priority 3: Check button text
        email_buttons = soup.find_all(['button', 'input', 'a'], 
                                     string=re.compile(r'email\s*me\s*when\s*available', re.I))
        if email_buttons:
            return False
        
        cart_buttons = soup.find_all(['button', 'input', 'a'], 
                                    string=re.compile(r'add\s*to\s*cart', re.I))
        if cart_buttons:
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
        
        # Default to True
        return True


# Standalone function for integration with existing updater scripts
def extract_neptune_cigar_data(url: str) -> Dict:
    """
    FIXED standalone function to extract data from Neptune Cigar URL
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


# Test function
def test_extractor_fixed():
    """Test the fixed extractor"""
    extractor = NeptuneCigarExtractor()
    
    # Test with problematic URL
    test_url = "https://www.neptunecigar.com/cigars/romeo-y-julieta-1875-churchill"
    
    print("=== TESTING FIXED NEPTUNE EXTRACTOR ===")
    print(f"URL: {test_url}")
    print(f"Expected: $183.95 for Box of 25")
    print("=" * 50)
    
    result = extractor.extract_product_data(test_url)
    
    print("Results:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    
    if result.get('box_price') and result.get('box_qty'):
        per_stick = result['box_price'] / result['box_qty']
        print(f"  price_per_stick: ${per_stick:.2f}")


if __name__ == "__main__":
    test_extractor_fixed()
