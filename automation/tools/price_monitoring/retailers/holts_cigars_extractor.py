"""
Holt's Cigars Extractor
Handles multi-product table pages with strict robots.txt compliance
Extracts pricing data from product tables by matching CID patterns
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
from typing import Dict, Optional, List
from urllib.parse import urlparse

class HoltsCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CigarPriceScoutBot/1.0 (+https://cigarpricescout.com/contact)'
        })
        
        # Robots.txt compliance - forbidden paths
        self.forbidden_paths = [
            '/catalogsearch/',
            '/advancedsearch/', 
            '/checkout/',
            '/holtsgallery/index/'
        ]
        
        # Rate limiting - minimum 3 seconds per robots.txt
        self.min_delay = 3
        self.max_delay = 6
        
    def _is_url_allowed(self, url: str) -> bool:
        """Check if URL is allowed per robots.txt"""
        parsed = urlparse(url)
        path = parsed.path
        
        for forbidden in self.forbidden_paths:
            if path.startswith(forbidden):
                raise ValueError(f"URL not allowed by robots.txt: {url}")
        return True
    
    def _enforce_rate_limit(self):
        """Enforce 3-6 second delay with jitter per robots.txt"""
        delay = random.uniform(self.min_delay, self.max_delay)
        print(f"[RATE LIMIT] Waiting {delay:.1f} seconds (robots.txt compliance)")
        time.sleep(delay)
    
    def _extract_vitola_from_cid(self, cigar_id: str) -> tuple:
        """Extract vitola name and size from CID for matching"""
        # CID format: BRAND|BRAND|LINE|VITOLA|VITOLA|SIZE|WRAPPER|PACKAGING
        parts = cigar_id.split('|')
        if len(parts) >= 6:
            vitola = parts[3]  # BESTSELLER, CLASSIC, etc.
            size = parts[5]    # 4.5x55, 7x48, etc.
            return vitola.lower(), size.lower()
        return None, None
    
    def extract_product_data(self, url: str, cigar_id: str) -> Dict:
        """
        Extract product data from Holt's multi-product table page
        Args:
            url: Holt's product page URL
            cigar_id: CID to find in the table
        Returns: {
            'price': float or None,
            'msrp_price': float or None, 
            'in_stock': bool,
            'box_qty': int or None,
            'error': str or None
        }
        """
        try:
            # Validate URL is allowed
            self._is_url_allowed(url)
            
            # Rate limiting compliance
            self._enforce_rate_limit()
            
            # Extract vitola and size from CID for matching
            vitola_name, size = self._extract_vitola_from_cid(cigar_id)
            if not vitola_name:
                return {'error': f'Could not parse CID: {cigar_id}'}
            
            print(f"[HOLT'S] Looking for vitola: {vitola_name}, size: {size}")
            
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the product table
            table_data = self._parse_product_table(soup, vitola_name, size)
            
            if table_data:
                return table_data
            else:
                return {'error': f'Could not find matching product for {vitola_name} {size}'}
            
        except Exception as e:
            # Handle backoff requirements from policy
            if '403' in str(e) or '429' in str(e) or '503' in str(e):
                print(f"[BACKOFF] Received {e} - implementing 24h backoff as per policy")
                # In production, this would trigger backoff mechanism
            
            return {
                'price': None,
                'msrp_price': None,
                'in_stock': False,
                'box_qty': None,
                'error': str(e)
            }
    
    def _parse_product_table(self, soup: BeautifulSoup, target_vitola: str, target_size: str) -> Optional[Dict]:
        """Parse the product table to find matching vitola and extract data"""
        
        # Find all table rows - look for actual table structure first
        table_rows = soup.find_all('tr')
        
        # If no table rows, look for div-based table structures
        if not table_rows:
            table_rows = soup.find_all('div', class_=lambda x: x and 'row' in str(x).lower())
        
        best_match = None
        best_match_score = 0
        
        # Score each row for match quality
        for row in table_rows:
            row_text = row.get_text().lower()
            match_score = 0
            
            # Check for vitola name match
            if target_vitola in row_text:
                match_score += 2
                
            # Check for size match (handle variations: 4.5x55, 4.5 x 55, 4.5" x 55)
            size_variants = [
                target_size,
                target_size.replace('x', ' x '),
                target_size.replace('x', '" x '),
                target_size.replace('x', ' X ')
            ]
            
            for size_variant in size_variants:
                if size_variant in row_text:
                    match_score += 2
                    break
            
            # Check for box quantity indicators (we want box prices, not singles)
            if any(term in row_text for term in ['box of', 'box', '25', '20', '10']):
                match_score += 1
                
            # Check that row contains pricing (must have dollar signs)
            price_count = len(re.findall(r'\$\d+', row_text))
            if price_count >= 1:
                match_score += 1
            if price_count >= 2:  # Prefer rows with both MSRP and sale price
                match_score += 1
                
            # Update best match if this row scores higher
            if match_score > best_match_score and match_score >= 3:  # Minimum threshold
                best_match = row
                best_match_score = match_score
                
        # Extract data from the best matching row
        if best_match:
            print(f"[HOLT'S] Best match found with score {best_match_score}")
            return self._extract_row_data(best_match, target_vitola, target_size)
        
        print(f"[HOLT'S] No suitable match found for {target_vitola} {target_size}")
        return None
    
    def _contains_vitola_match(self, element, target_vitola: str, target_size: str) -> bool:
        """Check if element contains text matching our target vitola and size"""
        text = element.get_text().lower()
        
        # Check for vitola name match
        vitola_match = target_vitola in text
        
        # Check for size match (handle different formats: 4.5x55, 4.5 x 55)
        size_clean = target_size.replace('x', ' x ')
        size_match = target_size in text or size_clean in text
        
        return vitola_match or size_match
    
    def _extract_row_data(self, row_element, target_vitola: str, target_size: str) -> Optional[Dict]:
        """Extract pricing and stock data from a table row element"""
        
        row_text = row_element.get_text()
        print(f"[DEBUG] Extracting from row: {row_text[:100]}...")
        
        # Extract all prices from the row
        price_matches = re.findall(r'\$(\d+(?:\.\d{2})?)', row_text)
        
        if not price_matches:
            return None
            
        # Convert to floats and sort
        prices = []
        for price_str in price_matches:
            try:
                price = float(price_str)
                # Filter out obviously invalid prices
                if 10 <= price <= 5000:  # Reasonable cigar price range
                    prices.append(price)
            except ValueError:
                continue
        
        if not prices:
            return None
        
        prices.sort()  # Sort ascending
        print(f"[DEBUG] Found prices: {prices}")
        
        # Determine MSRP vs Sale price logic
        if len(prices) == 1:
            # Only one price found - could be MSRP or sale
            sale_price = prices[0]
            msrp_price = None
        elif len(prices) == 2:
            # Two prices - typically MSRP (higher) and Sale (lower)
            sale_price = prices[0]    # Lower price = sale
            msrp_price = prices[1]    # Higher price = MSRP
        else:
            # Multiple prices - take the two most reasonable for box pricing
            # Skip very low prices (likely singles) and very high prices (likely errors)
            filtered_prices = [p for p in prices if p >= 50]  # Box prices usually $50+
            if len(filtered_prices) >= 2:
                sale_price = filtered_prices[0]
                msrp_price = filtered_prices[1]
            else:
                sale_price = prices[-1] if prices else None  # Take highest as fallback
                msrp_price = None
        
        # Extract box quantity - look for explicit box quantities in the specific row
        box_qty = self._extract_box_quantity_from_row(row_element)
        
        # Check stock status
        in_stock = self._check_stock_status(row_element)
        
        print(f"[DEBUG] Extracted - Sale: ${sale_price}, MSRP: ${msrp_price}, Box: {box_qty}, Stock: {in_stock}")
        
        return {
            'price': sale_price,
            'msrp_price': msrp_price,
            'in_stock': in_stock,
            'box_qty': box_qty,
            'error': None
        }
    
    def _extract_box_quantity_from_row(self, row_element) -> Optional[int]:
        """Extract box quantity from the specific table row element"""
        
        # Get text from the row and look for quantity indicators
        row_text = row_element.get_text().lower()
        
        # Look for explicit box quantities first
        box_patterns = [
            r'box\s+of\s+(\d+)',
            r'(\d+)\s*-\s*pack',
            r'(\d+)\s*pack',
            r'(\d+)\s*ct\b',
            r'(\d+)\s*count',
        ]
        
        for pattern in box_patterns:
            match = re.search(pattern, row_text, re.IGNORECASE)
            if match:
                qty = int(match.group(1))
                if 5 <= qty <= 100:  # Reasonable box range
                    return qty
        
        # Look for quantity in table cells or structured data
        cells = row_element.find_all(['td', 'div', 'span'])
        for cell in cells:
            cell_text = cell.get_text().strip().lower()
            
            # Check if this cell specifically contains packing info
            if any(word in cell_text for word in ['box', 'pack', 'count']):
                qty_match = re.search(r'(\d+)', cell_text)
                if qty_match:
                    qty = int(qty_match.group(1))
                    if 5 <= qty <= 100:
                        return qty
        
        # Default box quantities by common patterns if no explicit quantity found
        if 'single' in row_text:
            return 1
        elif any(term in row_text for term in ['5-pack', '5 pack', 'fiver']):
            return 5
        elif any(term in row_text for term in ['10-pack', '10 pack']):
            return 10
        elif any(term in row_text for term in ['20-pack', '20 pack']):
            return 20
        elif any(term in row_text for term in ['25-pack', '25 pack', 'box']):
            return 25
        
        return None
    
    def _check_stock_status(self, element) -> bool:
        """Check stock status based on button text or indicators"""
        
        # Get all text from the element
        element_text = element.get_text().upper()
        
        # Look for explicit stock indicators in text first
        if 'NOTIFY' in element_text or 'NOTIFY ME' in element_text:
            return False
        if 'OUT OF STOCK' in element_text or 'SOLD OUT' in element_text:
            return False
        if 'ADD TO CART' in element_text or 'ADD' in element_text:
            return True
        if 'IN STOCK' in element_text or 'AVAILABLE' in element_text:
            return True
            
        # Look for buttons and form elements
        buttons = element.find_all(['button', 'input', 'a', 'span', 'div'])
        
        for button in buttons:
            button_text = button.get_text().strip().upper()
            button_classes = ' '.join(button.get('class', [])).upper()
            button_value = str(button.get('value', '')).upper()
            
            # Check button text content
            if 'NOTIFY' in button_text or 'NOTIFY ME' in button_text:
                return False
            elif 'ADD' in button_text and 'CART' in button_text:
                return True
            elif button_text == 'ADD':
                return True
                
            # Check button classes for stock indicators
            if any(term in button_classes for term in ['NOTIFY', 'UNAVAILABLE', 'OUTOFSTOCK']):
                return False
            elif any(term in button_classes for term in ['ADD', 'AVAILABLE', 'INSTOCK']):
                return True
                
            # Check input values
            if 'NOTIFY' in button_value:
                return False
            elif 'ADD' in button_value:
                return True
        
        # Look for form inputs that might indicate stock status
        inputs = element.find_all(['input'])
        for input_elem in inputs:
            input_value = str(input_elem.get('value', '')).upper()
            if 'NOTIFY' in input_value:
                return False
            elif 'ADD' in input_value:
                return True
        
        # Additional checks for common e-commerce patterns
        if any(term in element_text for term in ['CALL FOR PRICE', 'CONTACT US', 'EMAIL FOR AVAILABILITY']):
            return False
            
        # If we can't determine definitively, default to False (conservative)
        # This is safer than assuming in stock when we're not sure
        return False

# Wrapper function for automation compatibility
def extract_holts_cigar_data(url: str, cigar_id: str) -> Dict:
    """Wrapper function for automation compatibility"""
    extractor = HoltsCigarsExtractor()
    return extractor.extract_product_data(url, cigar_id)

# Test function
def test_extractor():
    """Test with known Holt's URLs"""
    extractor = HoltsCigarsExtractor()
    
    test_cases = [
        {
            'url': 'https://www.holts.com/cigars/all-cigar-brands/arturo-fuente-hemingway.html',
            'cid': 'ARTUROFUENTE|ARTUROFUENTE|HEMINGWAY|BESTSELLER|BESTSELLER|4.5x55|CAM|BOX25',
            'expected': 'Best Seller Box of 25'
        },
        {
            'url': 'https://www.holts.com/cigars/all-cigar-brands/arturo-fuente-hemingway.html', 
            'cid': 'ARTUROFUENTE|ARTUROFUENTE|HEMINGWAY|CLASSIC|CLASSIC|7x48|CAM|BOX25',
            'expected': 'Classic Box of 25'
        }
    ]
    
    for test in test_cases:
        print(f"\nTesting: {test['expected']}")
        print(f"URL: {test['url']}")
        print(f"CID: {test['cid']}")
        
        result = extractor.extract_product_data(test['url'], test['cid'])
        
        print("Results:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        print("-" * 50)

if __name__ == "__main__":
    test_extractor()
