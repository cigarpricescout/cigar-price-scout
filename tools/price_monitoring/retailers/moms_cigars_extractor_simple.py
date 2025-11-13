"""
Mom's Cigars Extractor - SIMPLIFIED VERSION
Handles cases where no HTML table is found on the page
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def extract_moms_cigars_data(url: str, target_vitola: str = None, target_packaging: str = None) -> Dict:
    """
    Extract data from Mom's Cigars pages with simplified approach
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get page title
        title_elem = soup.find(['h1', 'h2'])
        product_title = title_elem.get_text().strip() if title_elem else "Unknown Product"
        
        # Get all text content
        page_text = soup.get_text()
        
        print(f"DEBUG: Page contains {len(page_text)} characters")
        print(f"DEBUG: Looking for table element: {soup.find('table') is not None}")
        
        # Look for product data in the page text
        available_products = []
        
        # Search for Hemingway vitola patterns
        vitola_patterns = [
            (r'classic\s*\(7\.0[^)]*\)', 'classic'),
            (r'signature\s*\(6\.0[^)]*\)', 'signature'),
            (r'short\s*story\s*\(4\.0[^)]*\)', 'short story'),
            (r'masterpiece\s*\(9\.0[^)]*\)', 'masterpiece'),
            (r'work\s*of\s*art\s*\(4\.8[^)]*\)', 'work of art'),
        ]
        
        for pattern, vitola_name in vitola_patterns:
            matches = re.finditer(pattern, page_text, re.I)
            
            for match in matches:
                # Get text around this match to find associated pricing - expand context
                start = max(0, match.start() - 500)  # Increased from 200
                end = min(len(page_text), match.end() + 500)  # Increased from 200
                context = page_text[start:end]
                
                print(f"DEBUG: Found {vitola_name} at position {match.start()}")
                print(f"DEBUG: Context: {context[:100]}...")
                
                # Look for prices in the context - only accept box prices
                prices = re.findall(r'\$(\d+\.?\d*)', context)
                box_prices = [float(p) for p in prices if 99 <= float(p) <= 2000]  # Box price range
                
                # Look for packaging info - prioritize box quantities
                packaging = 'Unknown'
                box_quantity = None
                
                # Look for "Box of X" patterns first
                box_match = re.search(r'box\s*of\s*(\d+)', context, re.I)
                if box_match:
                    qty = int(box_match.group(1))
                    if qty >= 10:  # Valid box quantity
                        packaging = f"Box of {qty}"
                        box_quantity = qty
                
                # If we found box prices and box packaging, this is valid
                if box_prices and box_quantity:
                    product_info = {
                        'product': vitola_name,
                        'packaging': packaging,
                        'full_row': context[:100] + "...",
                        'price': min(box_prices) if len(box_prices) > 1 else box_prices[0],
                        'msrp': max(box_prices) if len(box_prices) > 1 else None,
                        'in_stock': 'out of stock' not in context.lower(),
                        'box_quantity': box_quantity
                    }
                    
                    available_products.append(product_info)
                    print(f"DEBUG: Added valid box product: {vitola_name} - ${product_info['price']} for Box of {box_quantity}")
                    break  # Only take first valid match for each vitola
                else:
                    print(f"DEBUG: Skipping {vitola_name} - no valid box pricing found (prices: {box_prices}, box_qty: {box_quantity})")
        
        print(f"DEBUG: Found {len(available_products)} products total")
        
        # Find target if specified
        target_data = None
        if target_vitola and target_packaging and available_products:
            for product in available_products:
                vitola_match = target_vitola.lower() in product['product'].lower()
                packaging_match = target_packaging.lower() in product['packaging'].lower()
                
                if vitola_match and packaging_match:
                    target_data = product
                    break
        
        if target_vitola and target_packaging:
            if target_data:
                discount_percent = None
                if target_data['msrp'] and target_data['price'] and target_data['msrp'] > target_data['price']:
                    discount_percent = ((target_data['msrp'] - target_data['price']) / target_data['msrp']) * 100
                
                return {
                    'success': True,
                    'product_title': product_title,
                    'price': target_data['price'],
                    'original_price': target_data['msrp'],
                    'discount_percent': discount_percent,
                    'in_stock': target_data['in_stock'],
                    'box_quantity': target_data['box_quantity'],
                    'target_found': True,
                    'available_products': available_products,
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'product_title': product_title,
                    'price': None,
                    'original_price': None,
                    'discount_percent': None,
                    'in_stock': False,
                    'box_quantity': None,
                    'target_found': False,
                    'available_products': available_products,
                    'error': f'Target not found: {target_vitola} + {target_packaging}'
                }
        else:
            # Return first product if no target specified
            if available_products:
                first_product = available_products[0]
                return {
                    'success': True,
                    'product_title': product_title,
                    'price': first_product['price'],
                    'original_price': first_product['msrp'],
                    'discount_percent': None,
                    'in_stock': first_product['in_stock'],
                    'box_quantity': first_product['box_quantity'],
                    'target_found': False,
                    'available_products': available_products,
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'product_title': product_title,
                    'price': None,
                    'original_price': None,
                    'discount_percent': None,
                    'in_stock': False,
                    'box_quantity': None,
                    'target_found': False,
                    'available_products': [],
                    'error': 'No products found on page'
                }
        
    except Exception as e:
        return {
            'success': False,
            'product_title': None,
            'price': None,
            'original_price': None,
            'discount_percent': None,
            'in_stock': False,
            'box_quantity': None,
            'target_found': False,
            'available_products': [],
            'error': str(e)
        }


# Test function
if __name__ == "__main__":
    test_url = "https://www.momscigars.com/products/arturo-fuente-hemingway"
    
    test_cases = [
        ("Classic", "Box of 25"),
        ("Signature", "Box of 25"), 
        ("Short Story", "Box of 25"),
        ("Masterpiece", "Box of 10"),
        ("Work of Art", "Box of 25")
    ]
    
    print("=" * 60)
    print("MOM'S CIGARS EXTRACTOR TEST - SIMPLIFIED")
    print("=" * 60)
    
    # First, let's see what products are available on the page
    print("\nFirst, checking what products are available...")
    
    # Use the Classic test to get the available products list
    debug_result = extract_moms_cigars_data(test_url, target_vitola="Classic", target_packaging="Box of 25")
    if debug_result.get('available_products'):
        print(f"\nFound {len(debug_result['available_products'])} products on page:")
        for i, prod in enumerate(debug_result['available_products'][:10], 1):  # Show first 10
            product_name = prod.get('product', 'Unknown')
            packaging = prod.get('packaging', 'Unknown pkg')
            price = prod.get('price', 'N/A')
            print(f"{i:2d}. '{product_name}' | '{packaging}' | ${price}")
    else:
        print("No products found in debug extraction")
    
    print("\n" + "=" * 60)
    print("TARGETED EXTRACTION TESTS")
    print("=" * 60)
    
    for vitola, packaging in test_cases:
        print(f"\nTesting: {vitola} + {packaging}")
        print("-" * 30)
        
        result = extract_moms_cigars_data(test_url, target_vitola=vitola, target_packaging=packaging)
        
        print(f"Success: {result['success']}")
        print(f"Target Found: {result['target_found']}")
        print(f"Price: ${result['price']}" if result['price'] else "Price: None")
        print(f"MSRP: ${result['original_price']}" if result['original_price'] else "MSRP: None")
        print(f"Box Qty: {result['box_quantity']}")
        print(f"In Stock: {result['in_stock']}")
        
        if result['discount_percent']:
            print(f"Discount: {result['discount_percent']:.1f}%")
        
        if not result['success']:
            print(f"Error: {result['error']}")
