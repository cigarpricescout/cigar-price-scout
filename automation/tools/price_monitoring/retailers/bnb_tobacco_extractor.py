"""
BnB Tobacco Extractor - FIXED VERSION
Handles dynamic product selection with vitola and packaging options
Platform appears to be Shopify-based with variant selection

FIXED: Stock status detection for "Out Of Stock - Notify Me!" pattern
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def extract_bnb_tobacco_data(url: str, target_vitola: str = None, target_packaging: str = "Box of 25") -> Dict:
    """
    Extract data from BnB Tobacco URL with specific product selection
    
    Args:
        url: Product page URL
        target_vitola: Specific vitola to target (e.g. "Churchill", "Robusto")
        target_packaging: Packaging type (default "Box of 25")
    """
    try:
        # Minimal headers following proven methodology
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Rate limiting
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract product title for context
        title_elem = soup.find(['h1', 'h2'], class_=re.compile(r'title|product', re.I))
        product_title = title_elem.get_text().strip() if title_elem else "Unknown Product"
        
        # Look for product variant selection (vitola options)
        vitola_options = _extract_vitola_options(soup)
        
        # Look for packaging options
        packaging_options = _extract_packaging_options(soup)
        
        # Extract pricing information
        pricing_data = _extract_pricing(soup, target_vitola, target_packaging, vitola_options)
        
        # Extract stock status
        stock_status = _extract_stock_status(soup)
        
        # Find the box quantities from packaging options
        box_qty = _extract_box_quantity(packaging_options, target_packaging, vitola_options)
        
        # Determine if we have the target configuration (BnB uses combined strings)
        has_target_vitola = not target_vitola or any(target_vitola.lower() in opt.lower() for opt in vitola_options)
        has_target_packaging = any(target_packaging.lower() in opt.lower() for opt in vitola_options + packaging_options)
        
        # For BnB, also check for combined format like "Churchill (7.0" x 50) / Box of 25 - $209.99"
        has_combined_target = False
        if target_vitola and target_packaging:
            for opt in vitola_options:
                if (target_vitola.lower() in opt.lower() and target_packaging.lower() in opt.lower()):
                    has_combined_target = True
                    break
        
        return {
            'success': True,
            'product_title': product_title,
            'price': pricing_data.get('current_price'),
            'original_price': pricing_data.get('original_price'),
            'discount_percent': pricing_data.get('discount_percent'),
            'in_stock': stock_status,
            'box_quantity': box_qty,
            'vitola_options': vitola_options,
            'packaging_options': packaging_options,
            'has_target_config': has_target_vitola and has_target_packaging or has_combined_target,
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
            'vitola_options': [],
            'packaging_options': [],
            'has_target_config': False,
            'error': str(e)
        }


def _extract_vitola_options(soup: BeautifulSoup) -> list:
    """Extract available vitola/size options"""
    options = []
    
    # Look for product variant buttons or selects
    # Common patterns: radio buttons, select options, variant buttons
    variant_elements = soup.find_all(['button', 'option', 'input', 'label'], 
                                    string=re.compile(r'\d+\.\d+"\s*x\s*\d+|churchill|robusto|toro|corona', re.I))
    
    for elem in variant_elements:
        text = elem.get_text().strip()
        if text and len(text) < 50:  # Reasonable length for vitola name
            options.append(text)
    
    # Also look for text patterns in product area
    product_area = soup.find(['div', 'section'], class_=re.compile(r'product', re.I))
    if product_area:
        text = product_area.get_text()
        # Look for size patterns like "Churchill (7.0" x 50)"
        size_matches = re.findall(r'[A-Za-z\s]+\s*\(\d+\.\d+"\s*x\s*\d+\)', text)
        for match in size_matches:
            if match not in options:
                options.append(match.strip())
    
    return list(set(options))  # Remove duplicates


def _extract_packaging_options(soup: BeautifulSoup) -> list:
    """Extract available packaging options"""
    options = []
    
    # Look for packaging-related elements
    packaging_elements = soup.find_all(['button', 'option', 'input', 'label'], 
                                     string=re.compile(r'box\s*of\s*\d+|\d+\s*pack|single', re.I))
    
    for elem in packaging_elements:
        text = elem.get_text().strip()
        if text and len(text) < 30:  # Reasonable length for packaging option
            options.append(text)
    
    # Look for packaging section specifically
    packaging_section = soup.find(string=re.compile(r'packaging', re.I))
    if packaging_section:
        parent = packaging_section.parent
        if parent:
            # Look for nearby options
            nearby_options = parent.find_all(['button', 'span'], 
                                           string=re.compile(r'box\s*of\s*\d+|\d+\s*pack', re.I))
            for opt in nearby_options:
                text = opt.get_text().strip()
                if text not in options:
                    options.append(text)
    
    return list(set(options))  # Remove duplicates


def _extract_pricing(soup: BeautifulSoup, target_vitola: str = None, target_packaging: str = None, vitola_options: list = None) -> dict:
    """Extract pricing information - improved to target specific vitola/packaging combo"""
    
    current_price = None
    original_price = None
    
    # BnB includes pricing in the vitola options strings like "Churchill (7.0" x 50) / Box of 25 - $209.99"
    # If we have target criteria, look for exact matches first
    if target_vitola and target_packaging and vitola_options:
        for option in vitola_options:
            # Check if this option matches both our target vitola AND packaging
            if (target_vitola.lower() in option.lower() and 
                target_packaging.lower() in option.lower()):
                
                # Extract price from this specific option
                price_match = re.search(r'\$(\d+\.?\d*)', option)
                if price_match:
                    try:
                        price_val = float(price_match.group(1))
                        if 50 <= price_val <= 2000:  # Reasonable box price range
                            current_price = price_val
                            break  # Found our target, stop looking
                    except ValueError:
                        continue
    
    # If we didn't find target-specific pricing, fall back to general price extraction
    if not current_price:
        # Look for price elements
        price_elements = soup.find_all(['span', 'div'], class_=re.compile(r'price', re.I))
        
        # Extract all prices found
        all_prices = []
        for elem in price_elements:
            text = elem.get_text().strip()
            price_match = re.search(r'\$(\d+\.?\d*)', text)
            if price_match:
                try:
                    price_val = float(price_match.group(1))
                    if 50 <= price_val <= 2000:  # Reasonable box price range
                        all_prices.append(price_val)
                except ValueError:
                    continue
        
        if all_prices:
            current_price = max(all_prices)  # Use highest price found
    
    # Look for strikethrough or crossed-out prices (original price)
    strikethrough_elems = soup.find_all(['del', 's']) + soup.find_all(attrs={'style': re.compile(r'line-through', re.I)})
    
    for elem in strikethrough_elems:
        text = elem.get_text().strip()
        price_match = re.search(r'\$(\d+\.?\d*)', text)
        if price_match:
            try:
                original_price = float(price_match.group(1))
                break
            except ValueError:
                continue
    
    # Look for "Save X%" indicators
    save_text = soup.find(string=re.compile(r'save\s*\d+%', re.I))
    discount_percent = None
    if save_text:
        save_match = re.search(r'save\s*(\d+)%', str(save_text), re.I)
        if save_match:
            discount_percent = float(save_match.group(1))
    
    # Calculate discount if not found directly
    if not discount_percent and original_price and current_price and original_price > current_price:
        discount_percent = ((original_price - current_price) / original_price) * 100
    
    return {
        'current_price': current_price,
        'original_price': original_price,
        'discount_percent': discount_percent
    }


def _extract_stock_status(soup: BeautifulSoup) -> bool:
    """Extract stock status - PRECISE version for BnB Tobacco"""
    
    # Strategy 1: Look for the specific "Add to Cart" button area
    add_to_cart_button = soup.find(['button', 'input'], string=re.compile(r'add\s*to\s*cart', re.I))
    
    if add_to_cart_button:
        # Check the immediate area around the Add to Cart button
        button_container = add_to_cart_button.find_parent(['div', 'form', 'section'])
        if button_container:
            container_text = button_container.get_text()
            
            # If we find "Out Of Stock" or "Notify Me" near the Add to Cart button, it's out of stock
            if re.search(r'out\s*of\s*stock.*notify\s*me|notify\s*me.*out\s*of\s*stock', container_text, re.I):
                return False
            
            # If button contains price and no out-of-stock indicators nearby, it's in stock
            if re.search(r'\$\d+', container_text):
                return True
    
    # Strategy 2: Look for explicit stock status indicators
    stock_indicators = soup.find_all(['span', 'div', 'p'], class_=re.compile(r'stock|inventory|availability', re.I))
    
    for indicator in stock_indicators:
        text = indicator.get_text().strip()
        if re.search(r'out\s*of\s*stock|sold\s*out', text, re.I):
            return False
        if re.search(r'in\s*stock|available|\d+\s*in\s*stock', text, re.I):
            return True
    
    # Strategy 3: Look at page text for clear indicators
    page_text = soup.get_text()
    
    # Check for the specific BnB out-of-stock pattern with button context
    if re.search(r'out\s*of\s*stock\s*-\s*notify\s*me', page_text, re.I):
        return False
    
    # Strategy 4: Default determination based on Add to Cart presence
    # If we have an Add to Cart button and no clear out-of-stock indicators, assume in stock
    if add_to_cart_button and not re.search(r'out\s*of\s*stock|sold\s*out|unavailable', page_text, re.I):
        return True
    
    # Conservative default for unclear cases
    return True


def _extract_box_quantity(packaging_options: list, target_packaging: str, vitola_options: list = None) -> Optional[int]:
    """Extract box quantity from packaging options or vitola options (BnB uses combined format)"""
    
    # BnB combines vitola and packaging in one string like "Churchill (7.0" x 50) / Box of 25 - $209.99"
    # Check vitola_options first since that's where BnB puts the data
    if vitola_options:
        for option in vitola_options:
            if target_packaging.lower() in option.lower():
                # Extract number from "Box of 25" format in combined string
                qty_match = re.search(r'box\s*of\s*(\d+)', option, re.IGNORECASE)
                if qty_match:
                    try:
                        qty = int(qty_match.group(1))
                        if qty >= 10:  # Box quantities only
                            return qty
                    except ValueError:
                        continue
    
    # Fallback to original packaging_options logic
    for option in packaging_options:
        if target_packaging.lower() in option.lower():
            qty_match = re.search(r'(\d+)', option)
            if qty_match:
                try:
                    qty = int(qty_match.group(1))
                    if qty >= 10:
                        return qty
                except ValueError:
                    continue
    
    return None


# Test function
if __name__ == "__main__":
    test_url = "https://www.bnbtobacco.com/products/my-father-le-bijou-1922?variant=33403225219"
    
    print(f"=== Testing BnB Stock Status Detection ===")
    print(f"URL: {test_url}")
    
    result = extract_bnb_tobacco_data(test_url, target_vitola="Toro", target_packaging="Box of 23")
    
    print(f"Price: ${result.get('price')}")
    print(f"Box Qty: {result.get('box_quantity')}")
    print(f"In Stock: {result.get('in_stock')} (Should be False for 'Out Of Stock - Notify Me!')")
    print(f"Success: {result.get('success')}")
    print(f"Error: {result.get('error')}")
