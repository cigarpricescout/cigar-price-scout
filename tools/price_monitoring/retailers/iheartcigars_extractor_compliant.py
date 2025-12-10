"""
iHeartCigars Extractor - COMPLIANT VERSION
Following exact specifications:

COMPLIANCE RULES:
- Rate: 1 request/second
- Timeout: 10 seconds  
- Compliance: Tier 1 ("No scraping clause; stable URLs")
- Platform: WooCommerce (easier than BigCommerce)
- Headers: Minimal (just User-Agent)

EXPECTED RESULTS (from screenshots):
- Privada No.9: $375 sale from $414 retail, Box of 24, IN STOCK
- Belicosos XXX: $1,250 no sale, Box of 42, IN STOCK  
- Dubai Exclusivo: $850 no sale, Box of 15, OUT OF STOCK
"""

import requests
from bs4 import BeautifulSoup
import time
import re

def extract_iheartcigars_data(url):
    """
    COMPLIANT iHeartCigars extractor
    
    Follows all compliance rules for stable, respectful scraping
    """
    
    # Minimal headers - just User-Agent as specified
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        print(f"    [EXTRACT] Fetching iHeartCigars page...")
        
        # Rate limiting: 1 request/second
        time.sleep(1.0)
        
        # Timeout: 10 seconds as specified
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract all product data
        price_info = _extract_price(soup)
        stock_info = _extract_stock(soup)
        box_qty = _extract_box_quantity(soup)
        
        return {
            'price': price_info['current_price'],
            'retail_price': price_info.get('retail_price'),
            'box_qty': box_qty,
            'in_stock': stock_info
        }
        
    except Exception as e:
        print(f"    [ERROR] Extraction failed: {e}")
        return None


def _extract_price(soup):
    """Extract current price and retail price (if on sale)"""
    
    print(f"    [PRICE] Analyzing pricing...")
    
    current_price = None
    retail_price = None
    
    # WooCommerce typically uses these price classes
    price_selectors = [
        '.price .amount',
        '.price .woocommerce-Price-amount',
        '.product-price .amount',
        '[class*="price"]',
        'span', 'div'
    ]
    
    found_prices = []
    
    for selector in price_selectors:
        elements = soup.select(selector)
        for element in elements:
            text = element.get_text().strip()
            
            # Extract dollar amounts
            price_matches = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', text)
            for match in price_matches:
                price_value = float(match.replace(',', ''))
                found_prices.append(price_value)
    
    # Remove duplicates and sort
    unique_prices = sorted(list(set(found_prices)))
    
    print(f"    [PRICE] Found prices: {unique_prices}")
    
    if len(unique_prices) == 1:
        current_price = unique_prices[0]
        print(f"    [PRICE] Single price: ${current_price}")
        
    elif len(unique_prices) >= 2:
        # Multiple prices - lower is typically sale price
        current_price = min(unique_prices)
        potential_retail = max(unique_prices)
        
        # Only treat as sale if retail is significantly higher
        if potential_retail > current_price * 1.05:  # At least 5% difference
            retail_price = potential_retail
            print(f"    [PRICE] Sale: ${current_price}, Retail: ${retail_price}")
        else:
            print(f"    [PRICE] Current: ${current_price}")
    
    # Fallback: any price in page text
    if current_price is None:
        page_text = soup.get_text()
        all_prices = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', page_text)
        if all_prices:
            current_price = float(all_prices[0].replace(',', ''))
            print(f"    [PRICE] Fallback: ${current_price}")
    
    return {
        'current_price': current_price,
        'retail_price': retail_price
    }


def _extract_stock(soup):
    """Extract stock status from buttons and text"""
    
    print(f"    [STOCK] Analyzing stock status...")
    
    # Method 1: Button analysis (most reliable)
    buttons = soup.find_all(['button', 'input', 'a'])
    
    for button in buttons:
        button_text = button.get_text().strip().lower()
        
        # Clear indicators from screenshots
        if 'add to cart' in button_text:
            print(f"    [STOCK] ADD TO CART button -> IN STOCK")
            return True
        
        if 'sold out' in button_text:
            print(f"    [STOCK] SOLD OUT button -> OUT OF STOCK")
            return False
    
    # Method 2: Page text analysis
    page_text = soup.get_text().lower()
    
    # Out of stock indicators
    oos_patterns = [
        'sold out',
        'out of stock',
        'currently unavailable'
    ]
    
    for pattern in oos_patterns:
        if pattern in page_text:
            print(f"    [STOCK] '{pattern}' found -> OUT OF STOCK")
            return False
    
    # In stock indicators
    in_stock_patterns = [
        'add to cart',
        'in stock',
        'available now'
    ]
    
    for pattern in in_stock_patterns:
        if pattern in page_text:
            print(f"    [STOCK] '{pattern}' found -> IN STOCK")
            return True
    
    # Default to in stock if no clear indicators
    print(f"    [STOCK] No clear indicators -> IN STOCK (default)")
    return True


def _extract_box_quantity(soup):
    """Extract box quantity from product options"""
    
    print(f"    [QTY] Analyzing box quantity...")
    
    # Method 1: "Box of X" pattern in text
    page_text = soup.get_text()
    box_matches = re.findall(r'box of (\d+)', page_text, re.I)
    
    if box_matches:
        # Use first match (typically the selected/main option)
        box_qty = int(box_matches[0])
        print(f"    [QTY] Found 'Box of {box_qty}'")
        return box_qty
    
    # Method 2: Select dropdown options
    selects = soup.find_all('select')
    for select in selects:
        for option in select.find_all('option'):
            option_text = option.get_text()
            
            # Look for box quantity
            box_match = re.search(r'box of (\d+)', option_text, re.I)
            if box_match:
                box_qty = int(box_match.group(1))
                print(f"    [QTY] Found in dropdown: Box of {box_qty}")
                return box_qty
    
    # Method 3: Radio button or checkbox options
    inputs = soup.find_all('input', {'type': ['radio', 'checkbox']})
    for input_elem in inputs:
        # Check associated label
        label = soup.find('label', {'for': input_elem.get('id')})
        if label:
            label_text = label.get_text()
            box_match = re.search(r'box of (\d+)', label_text, re.I)
            if box_match:
                box_qty = int(box_match.group(1))
                print(f"    [QTY] Found in label: Box of {box_qty}")
                return box_qty
    
    # Method 4: Data attributes (WooCommerce sometimes uses these)
    elements_with_data = soup.find_all(attrs={"data-quantity": True})
    for element in elements_with_data:
        qty_attr = element.get('data-quantity')
        if qty_attr and qty_attr.isdigit():
            qty = int(qty_attr)
            if 5 <= qty <= 100:  # Reasonable box range
                print(f"    [QTY] Found in data attribute: {qty}")
                return qty
    
    # Default box quantity
    print(f"    [QTY] No quantity found, defaulting to 25")
    return 25


def test_iheartcigars_urls():
    """Test the extractor with provided URLs"""
    
    test_urls = [
        'https://iheartcigars.com/products/no-9-robusto?_pos=2&_sid=5b548dd97&_ss=r',
        'https://iheartcigars.com/products/opusx-belicosos-xxx?variant=45748064649393',
        'https://iheartcigars.com/products/opus-x-dubai-exclusivo-black-52?_pos=5&_sid=97b460cbf&_ss=r'
    ]
    
    print("IHEARTCIGARS EXTRACTOR TEST")
    print("=" * 50)
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n[{i}/3] Testing: {url}")
        print("-" * 50)
        
        result = extract_iheartcigars_data(url)
        
        if result:
            print(f"\nEXTRACTED DATA:")
            print(f"  Current Price: ${result['price']}")
            print(f"  Retail Price: ${result['retail_price']}" if result['retail_price'] else "  Retail Price: None")
            print(f"  Box Quantity: {result['box_qty']}")
            print(f"  In Stock: {result['in_stock']}")
        else:
            print("EXTRACTION FAILED")
        
        print("=" * 50)


if __name__ == "__main__":
    test_iheartcigars_urls()
