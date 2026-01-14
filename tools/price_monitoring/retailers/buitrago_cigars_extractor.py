#!/usr/bin/env python3
"""
Buitrago Cigars Extractor
Following the proven pattern for accessible WooCommerce sites
Based on screenshots showing clear pricing structure and stock indicators
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional, Tuple

class BuitragoCigarsExtractor:
    def __init__(self):
        self.session = requests.Session()
        # Minimal headers - your proven approach
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Buitrago Cigars URL
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
            
            # Extract box quantity from product title/description
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
        """Extract box quantity from product title or URL"""
        
        # Priority 1: Extract from URL pattern (from screenshots)
        # URLs contain patterns like "25ct-box" and "20ct-box"
        url_patterns = [
            r'(\d+)ct-box',
            r'(\d+)-ct-box', 
            r'box-(\d+)ct',
            r'(\d+)-count'
        ]
        
        page_url = soup.find('link', rel='canonical')
        if page_url:
            url = page_url.get('href', '')
        else:
            url = ''
        
        for pattern in url_patterns:
            match = re.search(pattern, url, re.I)
            if match:
                qty = int(match.group(1))
                if qty >= 5:  # Filter out single quantities
                    return qty
        
        # Priority 2: Look in product title (from screenshots: "25 Ct. Box", "20Ct. Box")
        title_selectors = ['h1.product_title', 'h1', '.product-title', '.product_title']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text().strip()
                
                # Buitrago specific patterns from screenshots
                qty_patterns = [
                    r'(\d+)\s*ct\.?\s*box',  # "25 Ct. Box"
                    r'(\d+)ct\s*box',        # "20Ct Box"
                    r'(\d+)\s*count',        # "25 count"
                    r'box\s+of\s+(\d+)',     # "Box of 25"
                ]
                
                for pattern in qty_patterns:
                    qty_match = re.search(pattern, title, re.I)
                    if qty_match:
                        qty = int(qty_match.group(1))
                        if qty >= 5:
                            return qty
        
        # Priority 3: Look in breadcrumb or product description
        breadcrumb_text = soup.get_text()
        qty_match = re.search(r'(\d+)ct\.?\s*box', breadcrumb_text, re.I)
        if qty_match:
            qty = int(qty_match.group(1))
            if qty >= 5:
                return qty
        
        return None
    
    def _extract_pricing(self, soup: BeautifulSoup) -> Tuple[Optional[float], Optional[float]]:
        """Extract pricing information focusing on primary display prices"""
        
        current_price = None
        original_price = None
        
        # Priority 1: Look for main WooCommerce price structure
        main_price_selectors = [
            '.price .woocommerce-Price-amount',
            '.woocommerce-Price-amount.amount',
            'p.price .amount',
            'span.price .amount'
        ]
        
        found_prices = []
        msrp_prices = []
        
        # Extract all prices from main price areas
        for selector in main_price_selectors:
            price_elems = soup.select(selector)
            for elem in price_elems:
                price_text = elem.get_text().strip()
                price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', price_text)
                
                if price_match:
                    try:
                        price_str = price_match.group(1).replace(',', '')
                        price = float(price_str)
                        if 50 <= price <= 2000:
                            # Check if this is a strikethrough (original) price
                            is_strikethrough = elem.find_parent(['del', 's']) is not None
                            
                            if is_strikethrough:
                                msrp_prices.append(price)
                            else:
                                found_prices.append(price)
                                
                    except ValueError:
                        continue
        
        # Priority 2: Look for explicit MSRP text patterns
        page_text = soup.get_text()
        msrp_matches = re.finditer(r'msrp[:\s]+\$(\d+\.?\d*)', page_text, re.I)
        for match in msrp_matches:
            try:
                msrp_price = float(match.group(1))
                if 50 <= msrp_price <= 2000:
                    msrp_prices.append(msrp_price)
            except ValueError:
                pass
        
        # Priority 3: Select the appropriate current price
        if found_prices:
            # Remove duplicates and sort
            unique_prices = sorted(list(set(found_prices)))
            
            # Logic: If we have MSRP context, find the price that makes sense as current
            if msrp_prices:
                max_msrp = max(msrp_prices)
                # Look for a current price that's significantly lower than MSRP
                valid_current = [p for p in unique_prices if p < max_msrp * 0.9]  # At least 10% off
                if valid_current:
                    current_price = max(valid_current)  # Take highest valid current price
                else:
                    current_price = max(unique_prices)  # Fallback to highest found
                original_price = max_msrp
            else:
                # No MSRP context - take the highest price as the main price
                current_price = max(unique_prices)
        
        # Priority 4: Fallback to text extraction if no structured prices
        if not current_price:
            # Look for prominent price patterns in text
            text_prices = re.findall(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', page_text)
            valid_text_prices = []
            
            for price_str in text_prices:
                try:
                    price = float(price_str.replace(',', ''))
                    if 150 <= price <= 800:  # Focus on realistic main cigar box prices
                        valid_text_prices.append(price)
                except ValueError:
                    continue
            
            if valid_text_prices:
                # Take the most common price in the expected range
                price_counts = {}
                for price in valid_text_prices:
                    price_counts[price] = price_counts.get(price, 0) + 1
                
                # Get the price that appears most frequently
                most_common_price = max(price_counts, key=price_counts.get)
                current_price = most_common_price
        
        # Calculate discount percentage
        discount_percent = None
        if original_price and current_price and original_price > current_price:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        return current_price, discount_percent
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock - final optimized version"""
        
        # Priority 1: Check for explicit out-of-stock indicators FIRST
        page_text = soup.get_text().lower()
        explicit_oos = ['out of stock', 'sold out', 'unavailable', 'temporarily unavailable', 'not available']
        for phrase in explicit_oos:
            if phrase in page_text:
                return False
        
        # Priority 2: If we have a price and NO explicit out-of-stock text, assume in stock
        # This is the most reliable pattern for e-commerce sites
        has_price = bool(re.search(r'\$\d{2,4}\.?\d{0,2}', page_text))
        
        if has_price:
            # Additional check: look for any form of purchase mechanism
            purchase_indicators = [
                # Look for any button or form element
                soup.find('button'),
                soup.find('input', {'type': 'submit'}),
                soup.find('form'),
                # Look for cart-related elements
                soup.find(class_=re.compile(r'cart', re.I)),
                soup.find(class_=re.compile(r'add', re.I)),
                # Look for payment elements
                soup.find(class_=re.compile(r'buy|purchase|order', re.I))
            ]
            
            # If we have a price AND any purchase mechanism, assume in stock
            if any(indicator for indicator in purchase_indicators):
                return True
            
            # Even if no clear purchase mechanism, if we have price and no explicit OOS, assume in stock
            return True
        
        # Priority 3: No price found - likely out of stock or invalid page
        return False


def extract_buitrago_cigars_data(url: str) -> Dict:
    """
    Main extraction function for Buitrago Cigars
    Compatible with CSV update workflow
    """
    extractor = BuitragoCigarsExtractor()
    result = extractor.extract_product_data(url)
    
    # Convert to expected format (matching proven extractor output)
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
    """Test the extractor with the provided URLs"""
    
    test_urls = [
        'https://www.buitragocigars.com/padron-1964-anniversary-series-principe-natural-cigars-25ct-box/?searchid=1037915&search_query=1964',  # $326.90, 25ct, in stock
        'https://www.buitragocigars.com/arturo-fuente-cigars-hemingway-work-of-art-natural-25-ct-box/?searchid=1037919&search_query=hemingway',  # $293.90 (was $577.10), 25ct, in stock
        'https://www.buitragocigars.com/aj-fernandez-san-lotano-oval-connecticut-gordo-cigars-20ct-box/',  # $177.90, 20ct, out of stock
    ]
    
    print("Testing Buitrago Cigars extraction...")
    print("=" * 60)
    
    for i, url in enumerate(test_urls):
        product_name = url.split('/')[-2].split('?')[0].replace('-', ' ').title()
        print(f"\nTest {i+1}: {product_name}")
        print("-" * 40)
        result = extract_buitrago_cigars_data(url)
        
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
