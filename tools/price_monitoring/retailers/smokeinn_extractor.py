"""
Smoke Inn Cigars Extractor
Single-product page extractor for Smoke Inn
Handles retail vs sale pricing, stock detection, and pack quantity extraction
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
from typing import Dict, Optional

class SmokeInnExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Polite rate limiting
        self.min_delay = 2
        self.max_delay = 4
    
    def _enforce_rate_limit(self):
        """Enforce polite delays between requests"""
        delay = random.uniform(self.min_delay, self.max_delay)
        print(f"[RATE LIMIT] Waiting {delay:.1f} seconds")
        time.sleep(delay)
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Smoke Inn URL
        Returns: {
            'price': float or None (sale price),
            'msrp_price': float or None (retail price),
            'in_stock': bool,
            'box_qty': int or None,
            'error': str or None
        }
        """
        try:
            # Rate limiting
            self._enforce_rate_limit()
            
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract pricing information
            sale_price, msrp_price = self._extract_pricing(soup)
            
            # Extract pack quantity
            box_qty = self._extract_pack_quantity(soup)
            
            # Check stock status
            in_stock = self._check_stock_status(soup)
            
            return {
                'price': sale_price,
                'msrp_price': msrp_price,
                'in_stock': in_stock,
                'box_qty': box_qty,
                'error': None
            }
            
        except Exception as e:
            return {
                'price': None,
                'msrp_price': None,
                'in_stock': False,
                'box_qty': None,
                'error': str(e)
            }
    
    def _extract_pricing(self, soup: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
        """Extract sale price and MSRP from Smoke Inn page"""
        
        sale_price = None
        msrp_price = None
        
        # Strategy 1: Look for "Our price" and "Retail price" text patterns
        page_text = soup.get_text()
        
        # Find "Our price" (sale price)
        our_price_match = re.search(r'our\s+price[:\s]*\$?(\d+(?:\.\d{2})?)', page_text, re.IGNORECASE)
        if our_price_match:
            try:
                sale_price = float(our_price_match.group(1))
            except ValueError:
                pass
        
        # Find "Retail price" (MSRP)
        retail_price_match = re.search(r'retail\s+price[:\s]*\$?(\d+(?:\.\d{2})?)', page_text, re.IGNORECASE)
        if retail_price_match:
            try:
                msrp_price = float(retail_price_match.group(1))
            except ValueError:
                pass
        
        # Strategy 2: Look for pricing in common CSS patterns
        if not sale_price or not msrp_price:
            # Find all elements with dollar signs
            price_elements = soup.find_all(text=re.compile(r'\$\d+'))
            
            for elem in price_elements:
                parent = elem.parent
                parent_text = parent.get_text().strip()
                
                # Check for sale price indicators
                if any(term in parent_text.lower() for term in ['our price', 'sale', 'special', 'now']):
                    price_match = re.search(r'\$(\d+(?:\.\d{2})?)', parent_text)
                    if price_match and not sale_price:
                        try:
                            sale_price = float(price_match.group(1))
                        except ValueError:
                            continue
                
                # Check for retail price indicators  
                elif any(term in parent_text.lower() for term in ['retail', 'msrp', 'list']):
                    price_match = re.search(r'\$(\d+(?:\.\d{2})?)', parent_text)
                    if price_match and not msrp_price:
                        try:
                            msrp_price = float(price_match.group(1))
                        except ValueError:
                            continue
        
        # Strategy 3: Look for crossed out prices (usually MSRP)
        if not msrp_price:
            strikethrough_elements = soup.find_all(['del', 's']) + soup.find_all(attrs={'style': re.compile(r'line-through', re.I)})
            
            for elem in strikethrough_elements:
                price_text = elem.get_text()
                price_match = re.search(r'\$(\d+(?:\.\d{2})?)', price_text)
                if price_match:
                    try:
                        msrp_price = float(price_match.group(1))
                        break
                    except ValueError:
                        continue
        
        # Strategy 4: If we only found one price, try to determine which type
        if sale_price and not msrp_price:
            # Look for any other prices on the page
            all_prices = re.findall(r'\$(\d+(?:\.\d{2})?)', page_text)
            unique_prices = list(set([float(p) for p in all_prices if p != str(sale_price)]))
            
            if unique_prices:
                # If there's a higher price, it's likely MSRP
                higher_prices = [p for p in unique_prices if p > sale_price]
                if higher_prices:
                    msrp_price = min(higher_prices)  # Take the lowest higher price
        
        return sale_price, msrp_price
    
    def _extract_pack_quantity(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract pack/box quantity from product page"""
        
        page_text = soup.get_text()
        
        # Look for "Pack: 25" pattern from the training data
        pack_match = re.search(r'pack\s*:?\s*(\d+)', page_text, re.IGNORECASE)
        if pack_match:
            qty = int(pack_match.group(1))
            if 1 <= qty <= 100:  # Reasonable range
                return qty
        
        # Look for other quantity patterns
        qty_patterns = [
            r'box\s+of\s+(\d+)',
            r'(\d+)\s*-?\s*pack',
            r'(\d+)\s*count',
            r'(\d+)\s*ct\b',
            r'quantity\s*:?\s*(\d+)'
        ]
        
        for pattern in qty_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                qty = int(match.group(1))
                if 1 <= qty <= 100:
                    return qty
        
        # Look in structured data elements
        pack_elements = soup.find_all(text=re.compile(r'pack', re.IGNORECASE))
        for elem in pack_elements:
            parent_text = elem.parent.get_text()
            qty_match = re.search(r'(\d+)', parent_text)
            if qty_match:
                qty = int(qty_match.group(1))
                if 1 <= qty <= 100:
                    return qty
        
        return None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock based on button text and indicators"""
        
        # Get all page text for comprehensive analysis
        page_text = soup.get_text().lower()
        
        # Priority check: Look for explicit "Out of Stock" text
        if 'out of stock' in page_text:
            return False
        
        # Priority check: Look for "Notify me" buttons (strong out-of-stock indicator)
        notify_buttons = soup.find_all(['button', 'input', 'a'], string=re.compile(r'notify\s+me', re.IGNORECASE))
        if notify_buttons:
            return False
        
        # Check for any element containing "notify me" text
        notify_elements = soup.find_all(text=re.compile(r'notify\s+me', re.IGNORECASE))
        if notify_elements:
            return False
        
        # Look for add to cart buttons (in-stock indicator)
        add_buttons = soup.find_all(['button', 'input', 'a'], string=re.compile(r'add\s+to\s+cart', re.IGNORECASE))
        if add_buttons:
            return True
        
        # Look for button with "Add to cart" in value or text content
        buttons = soup.find_all(['button', 'input'])
        for button in buttons:
            button_text = button.get_text().strip().lower()
            button_value = str(button.get('value', '')).lower()
            
            if 'notify' in button_text or 'notify' in button_value:
                return False
            elif 'add to cart' in button_text or 'add to cart' in button_value:
                return True
            elif any(term in button_text for term in ['out of stock', 'sold out', 'unavailable']):
                return False
        
        # Additional text-based checks
        if any(term in page_text for term in ['sold out', 'temporarily unavailable', 'unavailable']):
            return False
        elif any(term in page_text for term in ['in stock', 'available', 'add to cart']):
            return True
        
        # Look for stock indicators in common e-commerce elements
        stock_elements = soup.find_all(attrs={'class': re.compile(r'stock|availability', re.I)})
        for elem in stock_elements:
            text = elem.get_text().lower()
            if 'out of stock' in text or 'unavailable' in text or 'notify' in text:
                return False
            elif 'in stock' in text or 'available' in text:
                return True
        
        # Changed default to False (conservative approach)
        # Better to miss a stock item than show false availability
        return False

# Wrapper function for automation compatibility
def extract_smokeinn_cigar_data(url: str) -> Dict:
    """Wrapper function for automation compatibility"""
    extractor = SmokeInnExtractor()
    return extractor.extract_product_data(url)

# Test function
def test_extractor():
    """Test with known Smoke Inn URLs"""
    extractor = SmokeInnExtractor()
    
    test_cases = [
        {
            'url': 'https://www.smokeinn.com/arturo-fuente-cigars/fuente-hemingway-classics.html',
            'name': 'Hemingway Classic (Standard Discount)',
            'expected_sale': 273.95,
            'expected_msrp': 315.00,
            'expected_pack': 25,
            'expected_stock': True
        },
        {
            'url': 'https://www.smokeinn.com/diamond-crown-maximus/diamond-crown-maximus-no-1-double-corona.html',
            'name': 'Diamond Crown (Out of Stock)',
            'expected_sale': 416.95,
            'expected_msrp': 463.00,
            'expected_pack': 20,
            'expected_stock': False
        },
        {
            'url': 'https://www.smokeinn.com/davidoff-thousand-series/davidoff-1000.html',
            'name': 'Davidoff 1000 (Single Price)',
            'expected_sale': 385.00,
            'expected_msrp': None,  # No separate MSRP shown
            'expected_pack': 25,
            'expected_stock': True
        }
    ]
    
    print("=" * 70)
    print("SMOKE INN EXTRACTOR - COMPREHENSIVE TEST")
    print("=" * 70)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n[{i}/3] Testing: {test['name']}")
        print(f"URL: {test['url']}")
        
        result = extractor.extract_product_data(test['url'])
        
        print("\n--- RESULTS ---")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        print("\n--- EXPECTED ---")
        print(f"  Sale Price: ${test['expected_sale']}")
        print(f"  MSRP: ${test['expected_msrp']}" if test['expected_msrp'] else "  MSRP: None (single price)")
        print(f"  Pack: {test['expected_pack']}")
        print(f"  Stock: {test['expected_stock']}")
        
        # Validation
        success = True
        if result.get('price') != test['expected_sale']:
            print(f"  [ERROR] Sale price mismatch: got {result.get('price')}, expected {test['expected_sale']}")
            success = False
        if result.get('msrp_price') != test['expected_msrp']:
            print(f"  [ERROR] MSRP mismatch: got {result.get('msrp_price')}, expected {test['expected_msrp']}")
            success = False
        if result.get('in_stock') != test['expected_stock']:
            print(f"  [ERROR] Stock mismatch: got {result.get('in_stock')}, expected {test['expected_stock']}")
            success = False
            
        if success:
            print("  [OK] All extractions match expected values!")
        
        print("-" * 50)

if __name__ == "__main__":
    test_extractor()
