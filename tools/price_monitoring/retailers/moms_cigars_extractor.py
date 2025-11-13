"""
Mom's Cigars Extractor
Handles table-based multi-product pages where one URL contains multiple cigars
Platform: Custom e-commerce with product tables

Key Features:
- Single URL contains multiple products in table format
- Targets specific vitola + packaging combinations 
- Extracts from table rows based on product matching
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def extract_moms_cigars_data(url: str, target_vitola: str = None, target_packaging: str = None) -> Dict:
    """
    Extract data from Mom's Cigars table-based product pages
    
    Args:
        url: Product page URL (contains multiple products in table)
        target_vitola: Specific vitola to target (e.g. "Classic", "Signature", "Short Story") 
        target_packaging: Packaging type (e.g. "Box of 25", "5 Pack")
    """
    try:
        # Conservative headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Rate limiting
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract product title for context
        title_elem = soup.find(['h1', 'h2'], string=re.compile(r'hemingway|arturo', re.I))
        if not title_elem:
            title_elem = soup.find(['h1', 'h2'])
        product_title = title_elem.get_text().strip() if title_elem else "Unknown Product"
        
        # Find the product table
        table_data = _extract_from_product_table(soup, target_vitola, target_packaging)
        
        if not table_data['success']:
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
                'error': table_data['error']
            }
        
        return {
            'success': True,
            'product_title': product_title,
            'price': table_data['price'],
            'original_price': table_data['original_price'],
            'discount_percent': table_data['discount_percent'],
            'in_stock': table_data['in_stock'],
            'box_quantity': table_data['box_quantity'],
            'target_found': table_data['target_found'],
            'available_products': table_data['available_products'],
            'error': None
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


def _extract_from_product_table(soup: BeautifulSoup, target_vitola: str = None, target_packaging: str = None) -> Dict:
    """Extract data from Mom's Cigars product layout - focus on HTML table"""
    
    # Strategy 1: Find the actual HTML table first (Mom's uses real tables!)
    table = soup.find('table')
    if table:
        return _parse_html_table(table, target_vitola, target_packaging)
    
    # Strategy 2: If no table found, fall back to div-based approach
    return _parse_div_layout(soup, target_vitola, target_packaging)


def _parse_html_table(table, target_vitola: str = None, target_packaging: str = None) -> Dict:
    """Parse actual HTML table structure"""
    
    try:
        rows = table.find_all('tr')
        if len(rows) < 2:
            return {'success': False, 'error': 'Product table has insufficient rows'}
        
        # Parse header to understand column structure  
        header_row = rows[0]
        header_cells = header_row.find_all(['th', 'td'])
        
        if not header_cells:
            return {'success': False, 'error': 'No header cells found in table'}
        
        headers = [cell.get_text().strip().lower() for cell in header_cells]
        
        # Debug: print headers
        print(f"DEBUG: Table headers: {headers}")
        
        # Find column indices
        product_col = None
        packaging_col = None
        stock_col = None
        price_col = None
        msrp_col = None
        
        for i, header in enumerate(headers):
            if 'product' in header:
                product_col = i
            elif 'packaging' in header:
                packaging_col = i
            elif 'stock' in header:
                stock_col = i
            elif 'price' in header and 'msrp' not in header:
                price_col = i
            elif 'msrp' in header:
                msrp_col = i
        
        print(f"DEBUG: Column indices - Product: {product_col}, Packaging: {packaging_col}, Price: {price_col}, MSRP: {msrp_col}, Stock: {stock_col}")
        
        if product_col is None:
            return {'success': False, 'error': 'Product column not found in table headers'}
        
        available_products = []
        target_data = None
        
        # Process each data row
        for row_idx, row in enumerate(rows[1:], 1):  # Skip header
            try:
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < len(headers):
                    print(f"DEBUG: Row {row_idx} has {len(cells)} cells but expected {len(headers)}")
                    continue  # Skip incomplete rows
                
                # Extract product info safely
                product_name = cells[product_col].get_text().strip() if product_col < len(cells) else ""
                packaging = cells[packaging_col].get_text().strip() if packaging_col is not None and packaging_col < len(cells) else ""
                
                print(f"DEBUG: Row {row_idx} - Product: '{product_name}', Packaging: '{packaging}'")
                
                if not product_name:
                    continue  # Skip rows without product name
                
                # Extract vitola from product name
                vitola_patterns = [
                    (r'classic\s*\(7\.0.*x.*48\)', 'classic'),
                    (r'signature\s*\(6\.0.*x.*47\)', 'signature'),
                    (r'short\s*story\s*\(4\.0.*x.*42.*49\)', 'short story'),
                    (r'masterpiece\s*\(9\.0.*x.*52\)', 'masterpiece'), 
                    (r'work\s*of\s*art\s*\(4\.875.*x.*60\)', 'work of art'),
                    # Flexible patterns
                    (r'signature\s*\(6.*x.*4[67]\)', 'signature'),
                    (r'short\s*story\s*\(4.*x.*4[23]\)', 'short story'),
                    (r'masterpiece\s*\(9.*x.*5[12]\)', 'masterpiece'),
                    (r'work\s*of\s*art\s*\(4\.8.*x.*6[01]\)', 'work of art'),
                    (r'classic\s*\(', 'classic')
                ]
                
                found_vitola = None
                for pattern, vitola_name in vitola_patterns:
                    if re.search(pattern, product_name, re.I):
                        found_vitola = vitola_name
                        break
                
                if not found_vitola:
                    print(f"DEBUG: No vitola found in '{product_name}'")
                    continue  # Skip rows without recognized vitolas
                
                print(f"DEBUG: Found vitola '{found_vitola}' in '{product_name}'")
                
                # Extract pricing safely
                price = None
                original_price = None
                
                if price_col is not None and price_col < len(cells):
                    price_text = cells[price_col].get_text().strip()
                    price_match = re.search(r'\$(\d+\.?\d*)', price_text)
                    if price_match:
                        price = float(price_match.group(1))
                
                if msrp_col is not None and msrp_col < len(cells):
                    msrp_text = cells[msrp_col].get_text().strip()
                    msrp_match = re.search(r'\$(\d+\.?\d*)', msrp_text)
                    if msrp_match:
                        original_price = float(msrp_match.group(1))
                
                # Extract stock status safely
                in_stock = True
                if stock_col is not None and stock_col < len(cells):
                    stock_text = cells[stock_col].get_text().strip().lower()
                    if any(indicator in stock_text for indicator in ['out', 'sold', 'unavailable']):
                        in_stock = False
                    elif '✓' in stock_text or 'in stock' in stock_text:
                        in_stock = True
                
                # Extract box quantity
                box_quantity = None
                if packaging:
                    qty_match = re.search(r'box\s*of\s*(\d+)', packaging, re.I)
                    if qty_match:
                        box_quantity = int(qty_match.group(1))
                
                # Create product entry
                product_info = {
                    'product': found_vitola,
                    'packaging': packaging,
                    'full_row': row.get_text().strip(),
                    'price': price,
                    'msrp': original_price,
                    'in_stock': in_stock,
                    'box_quantity': box_quantity
                }
                
                available_products.append(product_info)
                
                # Check if this matches our target
                if target_vitola and target_packaging:
                    vitola_match = target_vitola.lower() in found_vitola.lower()
                    packaging_match = target_packaging.lower() in packaging.lower() if packaging else False
                    
                    if vitola_match and packaging_match and not target_data:
                        target_data = product_info
                        
            except Exception as row_error:
                print(f"DEBUG: Error processing row {row_idx}: {row_error}")
                continue
        
        print(f"DEBUG: Found {len(available_products)} products total")
        
        if not target_data and target_vitola and target_packaging:
            return {
                'success': False,
                'error': f'Target not found: {target_vitola} + {target_packaging}. Found {len(available_products)} products.',
                'available_products': available_products
            }
        elif not available_products:
            return {
                'success': False,
                'error': 'No product data found in table.',
                'available_products': []
            }
        elif target_data:
            # Calculate discount
            discount_percent = None
            if target_data['msrp'] and target_data['price'] and target_data['msrp'] > target_data['price']:
                discount_percent = ((target_data['msrp'] - target_data['price']) / target_data['msrp']) * 100
            
            return {
                'success': True,
                'price': target_data['price'],
                'original_price': target_data['msrp'],
                'discount_percent': discount_percent,
                'in_stock': target_data['in_stock'],
                'box_quantity': target_data['box_quantity'],
                'target_found': True,
                'available_products': available_products
            }
        
        return {'success': False, 'error': 'No target specified for extraction'}
        
    except Exception as e:
        return {'success': False, 'error': f'Table parsing error: {str(e)}'}



def _parse_div_layout(soup: BeautifulSoup, target_vitola: str = None, target_packaging: str = None) -> Dict:
    """Fallback: Parse div-based layout if no HTML table found"""


def _calculate_discount(msrp, price):
    """Calculate discount percentage"""
    if msrp and price and msrp > price:
        return ((msrp - price) / msrp) * 100
    return None


def _extract_quantity_from_text(text):
    """Extract box quantity from text"""
    if not text:
        return None
    
    qty_match = re.search(r'(\d+)', text)
    if qty_match:
        qty = int(qty_match.group(1))
        if qty >= 5:
            return qty
    return None


# Test function
if __name__ == "__main__":
    test_url = "https://www.momscigars.com/products/arturo-fuente-hemingway"
    
    # Test multiple targets from the same URL
    test_cases = [
        ("Classic", "Box of 25"),
        ("Signature", "Box of 25"), 
        ("Short Story", "Box of 25"),
        ("Masterpiece", "Box of 10"),
        ("Work of Art", "Box of 25")
    ]
    
    print("=" * 60)
    print("MOM'S CIGARS EXTRACTOR TEST")
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
            raw_text = prod.get('full_row', 'No raw text')[:80] + "..." if len(prod.get('full_row', '')) > 80 else prod.get('full_row', '')
            print(f"{i:2d}. '{product_name}' | '{packaging}' | ${price}")
            print(f"    Raw: {raw_text}")
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
            if result['available_products']:
                print("Available products found:")
                for prod in result['available_products'][:3]:  # Show first 3
                    print(f"  - {prod['product']} | {prod['packaging']}")
