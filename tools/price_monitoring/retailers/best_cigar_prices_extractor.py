"""
Best Cigar Prices Extractor
Retailer-specific extraction rules for bestcigarprices.com (Custom platform)
Handles box quantities, MSRP vs sale pricing, backorder detection

Based on proven Atlantic Cigar extractor methodology with BCP-specific adaptations:
- Simple headers only (no bot detection triggers)
- 1-second rate limiting
- Box quantity filtering (>=10)
- Advanced stock detection (handles misleading "Add to Cart" buttons)
- MSRP vs Sale price extraction
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class BestCigarPricesExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Best Cigar Prices URL
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
            
            # Extract box quantity from quantity options
            box_qty = self._extract_box_quantity(soup)
            
            # Extract pricing information (MSRP vs Sale)
            box_price, discount_percent = self._extract_pricing(soup)
            
            # Check stock status (critical - handles backorder detection)
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
        Extract box quantity from quantity selection options
        BCP uses format: "Box - 25 Total Cigars", "Box - 20 Total Cigars"
        Filter out non-box quantities like "5 Cigars", "Sealed Pack - 5 Total Cigars"
        """
        
        # Look for quantity option buttons/text patterns
        # Pattern 1: "Box - XX Total Cigars" (primary target)
        box_patterns = [
            r'box\s*-\s*(\d+)\s*total\s*cigars',
            r'box\s*of\s*(\d+)',
            r'(\d+)\s*total\s*cigars.*box'
        ]
        
        # Search in all text content for quantity patterns
        page_text = soup.get_text()
        for pattern in box_patterns:
            matches = re.finditer(pattern, page_text, re.IGNORECASE)
            for match in matches:
                try:
                    qty = int(match.group(1))
                    # Filter for box quantities only (>=10, following BCP box standards)
                    if qty >= 10:
                        return qty
                except (ValueError, IndexError):
                    continue
        
        # Look in specific quantity selection elements
        qty_elements = soup.find_all(['div', 'span', 'button', 'option'], 
                                    string=re.compile(r'box.*\d+.*total.*cigars|box.*of.*\d+', re.IGNORECASE))
        
        for elem in qty_elements:
            text = elem.get_text().strip()
            # Extract number from "Box - 25 Total Cigars" format
            qty_match = re.search(r'box\s*-\s*(\d+)', text, re.IGNORECASE)
            if qty_match:
                try:
                    qty = int(qty_match.group(1))
                    if qty >= 10:  # Box quantities only
                        return qty
                except ValueError:
                    continue
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract pricing from BCP's MSRP vs Sale price structure
        BCP shows: MSRP crossed out, Sale price prominent
        Format: "$267.75 MSRP" crossed out, "$201.99" as sale price
        """
        
        sale_price = None
        msrp_price = None
        
        # Look for sale price (prominent price display)
        sale_price_patterns = [
            r'\$(\d+\.?\d*)',  # Generic dollar pattern
        ]
        
        # Find the main price display area
        price_elements = soup.find_all(['span', 'div', 'h1', 'h2'], 
                                      string=re.compile(r'\$\d+', re.IGNORECASE))
        
        prices_found = []
        
        for elem in price_elements:
            text = elem.get_text().strip()
            # Extract all prices from text
            price_matches = re.findall(r'\$(\d+\.?\d*)', text)
            for price_text in price_matches:
                try:
                    price = float(price_text)
                    # Filter reasonable box prices (50-2000 range)
                    if 50 <= price <= 2000:
                        prices_found.append((price, text, elem))
                except ValueError:
                    continue
        
        # Look specifically for MSRP (usually crossed out or labeled)
        msrp_elements = soup.find_all(text=re.compile(r'msrp|retail', re.IGNORECASE))
        for msrp_text in msrp_elements:
            msrp_match = re.search(r'\$(\d+\.?\d*)', str(msrp_text))
            if msrp_match:
                try:
                    msrp_price = float(msrp_match.group(1))
                    break
                except ValueError:
                    continue
        
        # If we didn't find MSRP in text, look for crossed out prices
        if not msrp_price:
            strikethrough_elems = (soup.find_all(['del', 's']) + 
                                 soup.find_all(attrs={'style': re.compile(r'text-decoration:\s*line-through', re.I)}))
            
            for elem in strikethrough_elems:
                msrp_text = elem.get_text().strip()
                msrp_match = re.search(r'\$(\d+\.?\d*)', msrp_text)
                if msrp_match:
                    try:
                        msrp_price = float(msrp_match.group(1))
                        break
                    except ValueError:
                        continue
        
        # Determine sale price (should be lower than MSRP if both exist)
        if prices_found:
            if msrp_price:
                # Find price lower than MSRP
                for price, text, elem in prices_found:
                    if price < msrp_price:
                        sale_price = price
                        break
                
                # If no price lower than MSRP found, use the most prominent one
                if not sale_price:
                    sale_price = max(prices_found, key=lambda x: x[0])[0]
            else:
                # No MSRP, use the highest price found (assuming it's the box price)
                sale_price = max(prices_found, key=lambda x: x[0])[0]
        
        # Calculate discount percentage
        discount_percent = None
        if msrp_price and sale_price and msrp_price > sale_price:
            discount_percent = ((msrp_price - sale_price) / msrp_price) * 100
        
        final_price = sale_price if sale_price else msrp_price
        
        return final_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """
        Advanced stock detection for BCP - handles misleading "Add to Cart" buttons
        
        Stock Detection Hierarchy:
        1. True Out of Stock: "Notify Me" button + out-of-stock message
        2. Backordered: "Add to Cart" button BUT "Backordered" text in options
        3. In Stock: "Add to Cart" button with NO backorder indicators
        """
        
        # Priority 1: Look for "Notify Me" button (definitely out of stock)
        notify_buttons = soup.find_all(['button', 'input'], 
                                      string=re.compile(r'notify\s*me', re.I))
        if notify_buttons:
            return False
        
        # Priority 2: Look for explicit out-of-stock messages
        out_of_stock_messages = [
            r"out\s*of\s*stock",
            r"we're\s*sorry.*out\s*of\s*stock",
            r"item.*out\s*of\s*stock",
            r"temporarily\s*unavailable"
        ]
        
        page_text = soup.get_text()
        for pattern in out_of_stock_messages:
            if re.search(pattern, page_text, re.IGNORECASE):
                return False
        
        # Priority 3: Check for backorder indicators (critical for BCP)
        backorder_indicators = [
            r"backordered",
            r"\d+\s*week.*backordered",
            r"back.*ordered",
            r"expected.*\d+.*week"
        ]
        
        for pattern in backorder_indicators:
            if re.search(pattern, page_text, re.IGNORECASE):
                return False
        
        # Priority 4: Look for "Add to Cart" button (but verify no backorder)
        add_to_cart = soup.find_all(['button', 'input'], 
                                   string=re.compile(r'add\s*to\s*cart', re.I))
        
        if add_to_cart:
            # Double-check: if "Add to Cart" exists, make sure no backorder text nearby
            for button in add_to_cart:
                # Check parent elements and siblings for backorder text
                context_text = ""
                parent = button.parent
                if parent:
                    context_text += parent.get_text()
                
                for pattern in backorder_indicators:
                    if re.search(pattern, context_text, re.IGNORECASE):
                        return False
            
            # "Add to Cart" found and no backorder indicators
            return True
        
        # Priority 5: Look for general stock indicators
        in_stock_indicators = [
            r"in\s*stock",
            r"available",
            r"ready\s*to\s*ship"
        ]
        
        for pattern in in_stock_indicators:
            if re.search(pattern, page_text, re.IGNORECASE):
                return True
        
        # Default: if we can't determine, assume out of stock (conservative approach)
        return False


# Standalone function for integration with existing updater scripts
def extract_best_cigar_prices_data(url: str) -> Dict:
    """
    Standalone function to extract data from Best Cigar Prices URL
    Returns standardized result format for integration with CSV updaters
    """
    extractor = BestCigarPricesExtractor()
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
    extractor = BestCigarPricesExtractor()
    
    # Test URLs from provided examples
    test_urls = [
        # In stock with discount
        "https://www.bestcigarprices.com/cigar-directory/romeo-y-julieta-1875-cigars/romeo-y-julieta-1875-churchill-5395/",
        
        # Backordered (misleading "Add to Cart")
        "https://www.bestcigarprices.com/cigar-directory/m-by-macanudo-cigars/m-by-macanudo-espresso-with-cream-belicoso-245029/",
        
        # Out of stock ("Notify Me")
        "https://www.bestcigarprices.com/cigar-directory/la-gloria-cubana-cigars/la-gloria-cubana-wavell-maduro-252013/"
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
