#!/usr/bin/env python3
"""
Cigar King Extractor
Extracts pricing data from cigarking.com product pages
Based on BigCommerce platform structure

Compliance: Tier 1 (1 req/sec, minimal headers)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

class CigarKingExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.request_delay = 1  # 1 second between requests for Tier 1 compliance
        self.timeout = 15

    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Cigar King URL"""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract data using proven patterns
            title = self._extract_title(soup)
            price = self._extract_price(soup)
            original_price = self._extract_original_price(soup)
            in_stock = self._extract_stock_status(soup)
            box_qty = self._extract_box_quantity(soup, title)
            
            return {
                'price': price,
                'original_price': original_price,
                'in_stock': in_stock,
                'box_qty': box_qty,
                'title': title
            }
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Request failed for {url}: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Extraction failed for {url}: {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from Cigar King page"""
        # Try the main product title heading
        title_elem = soup.find('h1', class_='productView-title')
        if title_elem:
            return title_elem.get_text().strip()
        
        # Fallback to any h1
        h1_elem = soup.find('h1')
        if h1_elem:
            title_text = h1_elem.get_text().strip()
            if len(title_text) > 5 and 'cigar king' not in title_text.lower():
                return title_text
        
        # Last resort: page title
        page_title_elem = soup.find('title')
        if page_title_elem:
            page_title = page_title_elem.get_text().strip()
            if ' - ' in page_title:
                product_part = page_title.split(' - ')[0].strip()
                if len(product_part) > 5:
                    return product_part
        
        return "Product Title Not Found"

    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract sale/current price from Cigar King page"""
        
        # Strategy 1: Look for BigCommerce price divs
        # Sale price is usually in a specific class - find ALL prices in section
        sale_price_elem = soup.find('div', class_='price-section')
        if sale_price_elem:
            price_text = sale_price_elem.get_text()
            # Find all prices in the price section
            all_prices = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
            valid_prices = []
            for price_str in all_prices:
                price = float(price_str.replace(',', ''))
                if self._is_valid_box_price(price):
                    valid_prices.append(price)
            
            # If we have multiple prices, the lowest is usually the sale price
            if len(valid_prices) >= 2:
                sale_price = min(valid_prices)
                print(f"[DEBUG] Found sale price in price-section: ${sale_price} (from {valid_prices})")
                return sale_price
            elif len(valid_prices) == 1:
                print(f"[DEBUG] Found single price in price-section: ${valid_prices[0]}")
                return valid_prices[0]
        
        # Strategy 2: Look for price patterns in page text
        page_text = soup.get_text()
        
        # Look for common price labels
        price_patterns = [
            r'price[:\s]*\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'sale price[:\s]*\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'current price[:\s]*\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
        ]
        
        for pattern in price_patterns:
            price_match = re.search(pattern, page_text, re.I)
            if price_match:
                price = float(price_match.group(1).replace(',', ''))
                if self._is_valid_box_price(price):
                    print(f"[DEBUG] Found price with pattern: ${price}")
                    return price
        
        # Strategy 3: Find all prices and pick the most likely one
        all_price_matches = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', page_text)
        valid_box_prices = []
        
        for price_str in all_price_matches:
            try:
                price_val = float(price_str.replace(',', ''))
                if self._is_valid_box_price(price_val):
                    valid_box_prices.append(price_val)
            except ValueError:
                continue
        
        if valid_box_prices:
            # Return the lowest valid price (likely the sale price)
            fallback_price = min(valid_box_prices)
            print(f"[DEBUG] Using fallback box price: ${fallback_price}")
            return fallback_price
        
        print("[DEBUG] No valid price found")
        return None
    
    def _extract_original_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract original/MSRP price if product is on sale"""
        page_text = soup.get_text()
        
        # Look for strikethrough or "was" prices
        original_price_patterns = [
            r'was[:\s]*\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'msrp[:\s]*\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'retail[:\s]*\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'regular price[:\s]*\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
        ]
        
        for pattern in original_price_patterns:
            price_match = re.search(pattern, page_text, re.I)
            if price_match:
                price = float(price_match.group(1).replace(',', ''))
                if self._is_valid_box_price(price):
                    print(f"[DEBUG] Found original price: ${price}")
                    return price
        
        # Look for strikethrough elements
        strikethrough_elems = soup.find_all(['del', 's', 'strike'])
        for elem in strikethrough_elems:
            price_text = elem.get_text()
            price_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
            if price_match:
                price = float(price_match.group(1).replace(',', ''))
                if self._is_valid_box_price(price):
                    print(f"[DEBUG] Found strikethrough price: ${price}")
                    return price
        
        return None
    
    def _is_valid_box_price(self, price: float) -> bool:
        """Check if price is reasonable for a box of cigars"""
        # Box prices should be between $50-$3000
        # This filters out single cigar prices ($5-$50) and navigation noise
        return 50.0 <= price <= 3000.0

    def _extract_stock_status(self, soup: BeautifulSoup) -> bool:
        """Extract stock status from Cigar King page"""
        
        # Strategy 1: Check for specific out-of-stock HTML elements
        # Cigar King uses these specific classes and IDs for out-of-stock products
        
        # Check for out-of-stock button
        out_of_stock_button = soup.find('span', class_='button--out-of-stock')
        if out_of_stock_button:
            print(f"[DEBUG] Found out-of-stock button element")
            return False
        
        # Check for alert box with "Out of stock" message
        alert_box = soup.find('span', id='alertBox-message-text')
        if alert_box:
            alert_text = alert_box.get_text().strip().lower()
            if 'out of stock' in alert_text:
                print(f"[DEBUG] Found out-of-stock alert: '{alert_text}'")
                return False
        
        # Check for alertBox class with out-of-stock message
        alert_box_div = soup.find('div', class_='alertBox')
        if alert_box_div:
            alert_text = alert_box_div.get_text().strip().lower()
            if 'out of stock' in alert_text:
                print(f"[DEBUG] Found out-of-stock in alertBox: '{alert_text}'")
                return False
        
        # Strategy 2: Check page text for out-of-stock patterns
        page_text = soup.get_text().lower()
        
        # More specific out-of-stock patterns
        out_of_stock_patterns = [
            'item is currently out of stock',
            'this item is currently out of stock',
            'currently unavailable',
            'notify me',  # Cigar King shows "NOTIFY ME" button when out of stock
        ]
        
        for pattern in out_of_stock_patterns:
            if pattern in page_text:
                print(f"[DEBUG] Found out-of-stock text pattern: '{pattern}'")
                return False
        
        # Strategy 3: Check for in-stock indicators (must be in product form area)
        # Look for the product form specifically
        product_form = soup.find('form', class_='form')
        if product_form:
            form_text = product_form.get_text().lower()
            
            # Check if "add to cart" button exists in the form
            if 'add to cart' in form_text:
                print(f"[DEBUG] Found 'add to cart' in product form - In Stock")
                return True
            
            # If no add to cart but has form, check for other indicators
            if 'buy now' in form_text:
                print(f"[DEBUG] Found 'buy now' in product form - In Stock")
                return True
        
        # Strategy 4: Look for "Add to Cart" button element specifically
        add_to_cart_button = soup.find('button', {'data-wait-message': True})
        if add_to_cart_button:
            button_text = add_to_cart_button.get_text().strip().lower()
            if 'add' in button_text:
                print(f"[DEBUG] Found add to cart button element - In Stock")
                return True
        
        # Default to True if no clear indicators (avoid false negatives)
        print(f"[DEBUG] No clear stock indicators - defaulting to In Stock")
        return True

    def _extract_box_quantity(self, soup: BeautifulSoup, title: str = "") -> Optional[int]:
        """Extract box quantity from Cigar King page"""
        # Check title first
        if title:
            qty_from_title = self._extract_qty_from_text(title)
            if qty_from_title:
                return qty_from_title
        
        # Check page text
        page_text = soup.get_text()
        qty_from_page = self._extract_qty_from_text(page_text)
        if qty_from_page:
            return qty_from_page
        
        return None
    
    def _extract_qty_from_text(self, text: str) -> Optional[int]:
        """Extract quantity from text using common patterns"""
        # Pattern 1: "Box 25", "Box of 25", "/Box 25"
        box_patterns = [
            r'box\s+of\s+(\d+)',
            r'/\s*box\s+(\d+)',
            r'\(\s*\d+x\d+\s*/\s*box\s+(\d+)\s*\)',  # (4x48 / Box 25)
        ]
        
        for pattern in box_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                qty = int(match.group(1))
                if self._is_valid_box_quantity(qty):
                    print(f"[DEBUG] Found box quantity: {qty}")
                    return qty
        
        # Pattern 2: "Pack 20", "Pack of 20"
        pack_patterns = [
            r'pack\s+of\s+(\d+)',
            r'/\s*pack\s+(\d+)',
            r'\(\s*\d+x\d+\s*/\s*pack\s+(\d+)\s*\)',
        ]
        
        for pattern in pack_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                qty = int(match.group(1))
                if self._is_valid_box_quantity(qty):
                    print(f"[DEBUG] Found pack quantity: {qty}")
                    return qty
        
        return None
    
    def _is_valid_box_quantity(self, qty: int) -> bool:
        """Check if quantity is valid box size (not ring gauge)"""
        # Filter out common ring gauges and unreasonable quantities
        ring_gauges = [46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 70]
        return (5 <= qty <= 100 and qty not in ring_gauges)


# For backward compatibility and testing
def extract_cigar_king_data(url: str) -> Dict:
    """Standalone extraction function for compatibility"""
    extractor = CigarKingExtractor()
    result = extractor.extract_product_data(url)
    
    if result:
        return {
            'success': True,
            'price': result['price'],
            'original_price': result['original_price'],
            'discount_percent': None,
            'in_stock': result['in_stock'],
            'box_quantity': result['box_qty'],
            'title': result['title'],
            'error': None
        }
    else:
        return {
            'success': False,
            'price': None,
            'original_price': None,
            'discount_percent': None,
            'in_stock': False,
            'box_quantity': None,
            'title': None,
            'error': "Extraction failed"
        }


# Test with the sample URLs provided
def test_extractor_sample():
    """Test extractor with Cigar King sample URLs"""
    extractor = CigarKingExtractor()
    
    # Test URLs from user's request
    sample_urls = [
        "https://www.cigarking.com/arturo-fuente-hemingway-short-story-4x48-box-25/",
        "https://www.cigarking.com/my-father-le-bijou-1922-toro/?searchid=4192410&search_query=my+father",
        "https://www.cigarking.com/romeo-y-julieta-reserva-real-robusto-5x52-pack-20/?searchid=4192411&search_query=out+of+stock",
    ]
    
    expected_results = [
        {"price": 169.45, "in_stock": True, "box_qty": 25},
        {"price": 254.70, "in_stock": True, "box_qty": 23},
        {"price": 89.95, "in_stock": False, "box_qty": 20},
    ]
    
    print("Testing Cigar King Extractor on sample URLs...")
    print("=" * 80)
    
    for i, (url, expected) in enumerate(zip(sample_urls, expected_results), 1):
        print(f"\n[TEST {i}] {url}")
        print(f"Expected: Price=${expected['price']}, Stock={expected['in_stock']}, Qty={expected['box_qty']}")
        
        start_time = time.time()
        data = extractor.extract_product_data(url)
        end_time = time.time()
        
        if data:
            print(f"Extracted:")
            print(f"  Title: {data['title']}")
            print(f"  Price: ${data['price']}")
            print(f"  Original Price: ${data['original_price']}" if data['original_price'] else "  Original Price: None")
            print(f"  Stock: {'In Stock' if data['in_stock'] else 'Out of Stock'}")
            print(f"  Box Qty: {data['box_qty']}")
            
            # Validate results
            matches = []
            if data['price'] == expected['price']:
                matches.append("[OK] Price matches")
            else:
                matches.append(f"[MISMATCH] Price (expected {expected['price']}, got {data['price']})")
            
            if data['in_stock'] == expected['in_stock']:
                matches.append("[OK] Stock status matches")
            else:
                matches.append(f"[MISMATCH] Stock (expected {expected['in_stock']}, got {data['in_stock']})")
            
            if data['box_qty'] == expected['box_qty']:
                matches.append("[OK] Box quantity matches")
            else:
                matches.append(f"[MISMATCH] Box qty (expected {expected['box_qty']}, got {data['box_qty']})")
            
            print("\n  " + "\n  ".join(matches))
        else:
            print("[FAILED] Extraction failed")
        
        print(f"Time: {end_time - start_time:.2f}s")
        
        # Rate limiting
        if i < len(sample_urls):
            time.sleep(1)
    
    print("\n" + "=" * 80)
    print("Sample test completed")


if __name__ == "__main__":
    test_extractor_sample()
