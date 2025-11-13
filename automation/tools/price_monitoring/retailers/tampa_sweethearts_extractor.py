"""
Tampa Sweethearts Extractor
Extracts pricing from select option elements with packaging/price combinations
Platform: ASP.NET with server-side rendering

Key Features:
- Prices embedded directly in select option text (e.g., "Box of 25 / $273.95")
- Multiple packaging options available 
- Clean server-side HTML structure
- Targeting specific packaging combinations
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def extract_tampa_sweethearts_data(url: str, target_packaging: str = "Box of 25") -> Dict:
    """
    Extract data from Tampa Sweethearts with specific packaging targeting
    
    Args:
        url: Product page URL
        target_packaging: Packaging to target (e.g., "Box of 25", "Box of 10")
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract product title
        title_elem = soup.find('h1') or soup.find('h2') or soup.find(['span', 'div'], class_=re.compile(r'title|product', re.I))
        product_title = title_elem.get_text().strip() if title_elem else "Unknown Product"
        
        # Find packaging select element
        packaging_data = _extract_packaging_options(soup, target_packaging)
        
        if not packaging_data['success']:
            return {
                'success': False,
                'product_title': product_title,
                'price': None,
                'original_price': None,
                'discount_percent': None,
                'in_stock': False,
                'box_quantity': None,
                'target_found': False,
                'available_options': packaging_data.get('available_options', []),
                'error': packaging_data.get('error', 'Unknown error')
            }
        
        # Extract stock status (Tampa Sweethearts appears to show available items)
        stock_status = _extract_stock_status(soup)
        
        return {
            'success': True,
            'product_title': product_title,
            'price': packaging_data['price'],
            'original_price': packaging_data.get('original_price'),
            'discount_percent': packaging_data.get('discount_percent'),
            'in_stock': stock_status,
            'box_quantity': packaging_data['box_quantity'],
            'target_found': True,
            'available_options': packaging_data['available_options'],
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
            'available_options': [],
            'error': str(e)
        }


def _extract_packaging_options(soup: BeautifulSoup, target_packaging: str) -> Dict:
    """Extract pricing from packaging select options"""
    
    # Find select elements
    select_elements = soup.find_all('select')
    
    available_options = []
    target_data = None
    
    for select in select_elements:
        options = select.find_all('option')
        
        for option in options:
            option_text = option.get_text().strip()
            option_value = option.get('value', '')
            
            # Skip default/placeholder options
            if not option_text or 'select' in option_text.lower():
                continue
            
            # Look for packaging/price combinations like "Box of 25 / $273.95"
            packaging_match = re.search(r'(box\s*of\s*\d+|pack\s*of\s*\d+)\s*/\s*\$(\d+\.?\d*)', option_text, re.I)
            
            if packaging_match:
                packaging_type = packaging_match.group(1).strip()
                price = float(packaging_match.group(2))
                
                # Extract quantity
                qty_match = re.search(r'(\d+)', packaging_type)
                quantity = int(qty_match.group(1)) if qty_match else None
                
                option_info = {
                    'packaging': packaging_type,
                    'price': price,
                    'quantity': quantity,
                    'option_text': option_text,
                    'option_value': option_value
                }
                
                available_options.append(option_info)
                
                # Check if this matches our target
                if target_packaging.lower() in packaging_type.lower():
                    target_data = option_info
    
    if not available_options:
        return {
            'success': False,
            'error': 'No packaging options with pricing found',
            'available_options': []
        }
    
    if not target_data:
        return {
            'success': False,
            'error': f'Target packaging "{target_packaging}" not found',
            'available_options': available_options
        }
    
    return {
        'success': True,
        'price': target_data['price'],
        'box_quantity': target_data['quantity'],
        'packaging': target_data['packaging'],
        'available_options': available_options,
        'original_price': None,  # Tampa Sweethearts doesn't show MSRP
        'discount_percent': None
    }


def _extract_stock_status(soup: BeautifulSoup) -> bool:
    """Extract stock status from Tampa Sweethearts"""
    
    page_text = soup.get_text()
    
    # Look for out of stock indicators
    if re.search(r'out\s*of\s*stock|sold\s*out|unavailable|backorder', page_text, re.I):
        return False
    
    # Look for "Add to Cart" or similar buttons
    add_to_cart = soup.find(['button', 'input'], string=re.compile(r'add\s*to\s*cart|add\s*to\s*basket', re.I))
    if add_to_cart:
        return True
    
    # Look for quantity input (indicates item is available)
    qty_input = soup.find('input', attrs={'name': re.compile(r'quantity', re.I)})
    if qty_input:
        return True
    
    # Default to True (Tampa Sweethearts seems to show available items)
    return True


# Test function
if __name__ == "__main__":
    test_url = "https://www.tampasweethearts.com/hemingwayclassic.aspx"
    
    # Test different packaging options
    test_cases = [
        "Box of 25",
        "Box of 10", 
        "Pack of 10",
        "Pack of 5"
    ]
    
    print("=" * 70)
    print("TAMPA SWEETHEARTS EXTRACTOR TEST")
    print("=" * 70)
    
    for target in test_cases:
        print(f"\nTesting target: {target}")
        print("-" * 40)
        
        result = extract_tampa_sweethearts_data(test_url, target_packaging=target)
        
        print(f"Success: {result['success']}")
        print(f"Target Found: {result['target_found']}")
        print(f"Product: {result['product_title']}")
        print(f"Price: ${result['price']}" if result['price'] else "Price: None")
        print(f"Box Qty: {result['box_quantity']}")
        print(f"In Stock: {result['in_stock']}")
        
        if result['available_options']:
            print(f"Available options: {len(result['available_options'])}")
            for opt in result['available_options']:
                print(f"  - {opt['packaging']}: ${opt['price']}")
        
        if not result['success']:
            print(f"Error: {result['error']}")
        
        if result['price'] and result['box_quantity']:
            per_stick = result['price'] / result['box_quantity']
            print(f"Price per stick: ${per_stick:.2f}")
