#!/usr/bin/env python3
"""
Big Humidor Extractor
Extracts pricing data from bighumidor.com product pages
Based on tested patterns that successfully extract price and stock status

Compliance: Tier 1 (1 req/sec, minimal headers)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

class BigHumidorExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.request_delay = 1  # 1 second between requests for Tier 1 compliance
        self.timeout = 15

    def extract_product_data(self, url: str) -> Dict:
        """Extract product data from Big Humidor URL"""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract data using proven patterns
            title = self._extract_title(soup)
            price = self._extract_price(soup)
            in_stock = self._extract_stock_status(soup)
            box_qty = self._extract_box_quantity(soup)
            
            return {
                'price': price,
                'in_stock': in_stock,
                'box_qty': box_qty,
                'title': title
            }
            
        except requests.exceptions.RequestException as e:
            return None
        except Exception as e:
            return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title using proven header pattern"""
        # Look for product title in headers
        content_headers = soup.find_all(['h1', 'h2', 'h3'])
        
        for header in content_headers:
            title_text = header.get_text().strip()
            # Filter for actual product titles with brand names
            if (len(title_text) > 5 and 
                title_text not in ['Big Humidor', 'Buy Online'] and
                not title_text.startswith('Cigars') and
                any(brand in title_text.lower() for brand in 
                    ['arturo', 'fuente', 'padron', 'romeo', 'julieta', 'perdomo', 
                     'my father', 'tabak', 'ashton', 'drew estate', 'montecristo', 
                     'oliva', 'rocky patel', 'macanudo', 'cao'])):
                return title_text
        
        # Fallback to page title
        page_title_elem = soup.find('title')
        if page_title_elem:
            page_title = page_title_elem.get_text().strip()
            if ' - ' in page_title and 'Big Humidor' in page_title:
                product_part = page_title.split(' - ')[0].strip()
                if len(product_part) > 5 and product_part != 'Big Humidor':
                    return product_part
        
        return "Product Title Not Found"

    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract price using Big Humidor's actual format - two prices separated by spaces"""
        page_text = soup.get_text()
        
        # Strategy 1: Look for Big Humidor's actual format: "Price: $X.XX  $Y.YY"
        dual_price_pattern = r'price:\s*\$(\d+(?:\.\d{2})?)\s+\$(\d+(?:\.\d{2})?)'
        dual_match = re.search(dual_price_pattern, page_text, re.I)
        
        if dual_match:
            regular_price = float(dual_match.group(1))
            sale_price = float(dual_match.group(2))
            
            if (self._is_valid_box_price(sale_price) and 
                self._is_valid_box_price(regular_price) and
                sale_price < regular_price):
                print(f"[DEBUG] Found dual price format: Regular ${regular_price} -> Sale ${sale_price}")
                return sale_price
            elif self._is_valid_box_price(regular_price):
                print(f"[DEBUG] Found dual prices but second not valid sale, using regular: ${regular_price}")
                return regular_price
        
        # Strategy 2: Find main "Price: $X.XX" pattern (single price)
        price_pattern = r'price:\s*\$(\d+(?:,\d{3})*(?:\.\d{2})?)'
        price_match = re.search(price_pattern, page_text, re.I)
        
        if price_match:
            regular_price = float(price_match.group(1).replace(',', ''))
            if self._is_valid_box_price(regular_price):
                
                # Look for context around this price
                match_start = max(0, price_match.start() - 50)
                match_end = price_match.end()
                context_text = page_text[match_start:match_end + 150]
                
                print(f"[DEBUG] Price context: '{context_text.strip()[:100]}...'")
                
                # Look for traditional sale patterns in context
                sale_format_patterns = [
                    r'\$\d+\s+on\s+sale!\s*\$(\d+\.?\d*)',        # "$5 On Sale! $147.95"
                    r'\$\d+\s+On\s+Sale!\s*\$(\d+\.?\d*)',        # "$5 On Sale! $147.95"
                    r'on\s+sale!\s*\$(\d+\.?\d*)',                # "On Sale! $147.95"
                    r'On\s+Sale!\s*\$(\d+\.?\d*)',                # "On Sale! $147.95"
                    r'\$\d+\s+off!\s*\$(\d+\.?\d*)',              # "$30 off! $249.95"
                    r'\$\d+\s+OFF!\s*\$(\d+\.?\d*)',              # "$30 OFF! $249.95"
                ]
                
                for pattern in sale_format_patterns:
                    sale_format_match = re.search(pattern, context_text, re.I)
                    if sale_format_match:
                        sale_price = float(sale_format_match.group(1))
                        if (self._is_valid_box_price(sale_price) and 
                            sale_price < regular_price and
                            self._prices_make_sense_as_pair(sale_price, regular_price)):
                            print(f"[DEBUG] Found traditional sale format: ${sale_price}")
                            return sale_price
                
                print(f"[DEBUG] Using regular price (no sale found): ${regular_price}")
                return regular_price
        
        # Strategy 3: Final fallback - any valid box price
        all_price_matches = re.findall(r'\$(\d+\.?\d*)', page_text)
        valid_box_prices = []
        
        for price_str in all_price_matches:
            try:
                price_val = float(price_str)
                if self._is_valid_box_price(price_val):
                    valid_box_prices.append(price_val)
            except ValueError:
                continue
        
        if valid_box_prices:
            fallback_price = min(valid_box_prices)
            print(f"[DEBUG] Using fallback box price: ${fallback_price}")
            return fallback_price
        
        print("[DEBUG] No valid price found")
        return None
    
    def _is_valid_box_price(self, price: float) -> bool:
        """Check if price is reasonable for a box of cigars"""
        # Box prices should be between $50-$3000
        # This filters out single cigar prices ($5-$50) and navigation noise
        return 50.0 <= price <= 3000.0
    
    def _prices_make_sense_as_pair(self, lower: float, higher: float) -> bool:
        """Check if two prices make sense as regular/sale price pair"""
        # Both should be valid box prices
        if not (self._is_valid_box_price(lower) and self._is_valid_box_price(higher)):
            return False
        
        # Discount should be reasonable (5%-50%)
        discount_percent = (higher - lower) / higher * 100
        if not (5 <= discount_percent <= 50):
            return False
        
        # Price difference should be reasonable ($5-$500)
        price_diff = higher - lower
        if not (5 <= price_diff <= 500):
            return False
            
        return True

    def _extract_stock_status(self, soup: BeautifulSoup) -> bool:
        """Extract stock status with precise product-specific detection"""
        page_text = soup.get_text().lower()
        
        # Find the main product area by looking for price context
        price_match = re.search(r'price:\s*\$[\d.,]+', page_text, re.I)
        if price_match:
            # Look for stock status within 300 chars before and after the price
            price_start = max(0, price_match.start() - 300)
            price_end = min(len(page_text), price_match.end() + 300)
            product_context = page_text[price_start:price_end]
            
            print(f"[DEBUG] Stock context: '{product_context[:150]}...'")
            
            # Check for definitive out-of-stock indicators in product context
            product_out_patterns = [
                'this item is currently out of stock',
                'item is currently out of stock',
                'currently out of stock',
                'out of stock',
                'sold out',
                'gone!!',
                'discontinued',  # Only if it's about THIS product
                'unavailable',
                'temporarily unavailable'
            ]
            
            for pattern in product_out_patterns:
                if pattern in product_context:
                    print(f"[DEBUG] Found product-specific out-of-stock: '{pattern}'")
                    return False
            
            # Check for definitive in-stock indicators in product context
            product_in_patterns = [
                'add to cart',
                'purchase',
                'buy now',
                'order now',
                'in stock',
                'available',
                'ready to ship'
            ]
            
            for pattern in product_in_patterns:
                if pattern in product_context:
                    print(f"[DEBUG] Found product-specific in-stock: '{pattern}'")
                    return True
        
        # Fallback: Look for strong indicators anywhere on page
        # But be more selective about out-of-stock patterns
        
        # Very specific out-of-stock text that's usually product-specific
        strong_out_patterns = [
            'this item is currently out of stock',
            'item is currently out of stock'
        ]
        
        for pattern in strong_out_patterns:
            if pattern in page_text:
                print(f"[DEBUG] Found strong out-of-stock indicator: '{pattern}'")
                return False
        
        # Look for Add to Cart button (strong in-stock indicator)
        if 'add to cart' in page_text:
            print(f"[DEBUG] Found 'add to cart' button - In Stock")
            return True
        
        # Look for purchase/buy indicators
        if any(indicator in page_text for indicator in ['purchase', 'buy now', 'order now']):
            print(f"[DEBUG] Found purchase indicator - In Stock")
            return True
        
        # Default to in stock if no clear indicators (avoid false negatives)
        print(f"[DEBUG] No clear stock indicators found - defaulting to In Stock")
        return True

    def _extract_box_quantity(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract box quantity using proven patterns with ring gauge filtering"""
        page_text = soup.get_text()
        
        # Primary pattern: "Box of X Cigars"
        box_cigars_match = re.search(r'box\s+of\s+(\d+)\s+cigars', page_text, re.I)
        if box_cigars_match:
            qty = int(box_cigars_match.group(1))
            if self._is_valid_box_quantity(qty):
                return qty
        
        # Secondary pattern: "Box of X"
        box_match = re.search(r'box\s+of\s+(\d+)', page_text, re.I)
        if box_match:
            qty = int(box_match.group(1))
            if self._is_valid_box_quantity(qty):
                return qty
        
        # Check all "box of X" patterns and filter for valid quantities
        all_box_matches = re.findall(r'box\s+of\s+(\d+)', page_text, re.I)
        for qty_str in all_box_matches:
            qty = int(qty_str)
            if self._is_valid_box_quantity(qty):
                return qty
        
        # Additional patterns for edge cases
        quantity_patterns = [
            r'(\d+)\s+cigars?\s+per\s+box',
            r'(\d+)\s*ct\s+box',
            r'(\d+)\s*count\s+box'
        ]
        
        for pattern in quantity_patterns:
            qty_match = re.search(pattern, page_text, re.I)
            if qty_match:
                qty = int(qty_match.group(1))
                if self._is_valid_box_quantity(qty):
                    return qty
        
        return None

    def _is_valid_box_quantity(self, qty: int) -> bool:
        """Check if quantity is valid box size (not ring gauge)"""
        # Filter out common ring gauges and unreasonable quantities
        ring_gauges = [46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 70]
        return (5 <= qty <= 100 and qty not in ring_gauges)

# For backward compatibility and testing
def extract_big_humidor_data(url: str) -> Dict:
    """Standalone extraction function for compatibility"""
    extractor = BigHumidorExtractor()
    result = extractor.extract_product_data(url)
    
    if result:
        return {
            'success': True,
            'price': result['price'],
            'original_price': None,
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

# Test with a few sample URLs to verify the logic works
def test_extractor_sample():
    """Test extractor with a few sample cases"""
    extractor = BigHumidorExtractor()
    
    # Test URLs from your CSV
    sample_urls = [
        "https://www.bighumidor.com/index.cfm?ref=80200&ref2=363",  # Romeo y Julieta Churchill
        "https://www.bighumidor.com/index.cfm?ref=80200&ref2=246",  # Padron 1964 Exclusivo Natural
        "https://www.bighumidor.com/index.cfm?ref=80200&ref2=662",  # Arturo Fuente Hemingway Short Story
    ]
    
    print("Testing Big Humidor Extractor on sample URLs...")
    print("=" * 60)
    
    for i, url in enumerate(sample_urls, 1):
        print(f"\n[TEST {i}] {url}")
        
        start_time = time.time()
        data = extractor.extract_product_data(url)
        end_time = time.time()
        
        if data:
            print(f"Title: {data['title']}")
            print(f"Price: ${data['price']}")
            print(f"Stock: {'In Stock' if data['in_stock'] else 'Out of Stock'}")
            print(f"Box Qty: {data['box_qty']}")
        else:
            print("Extraction failed")
        
        print(f"Time: {end_time - start_time:.2f}s")
        
        # Rate limiting
        if i < len(sample_urls):
            time.sleep(1)
    
    print("\n" + "=" * 60)
    print("Sample test completed")

if __name__ == "__main__":
    test_extractor_sample()
