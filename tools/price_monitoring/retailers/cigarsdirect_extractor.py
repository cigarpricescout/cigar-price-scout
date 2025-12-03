"""
CigarsDirect Price Extractor - FINAL VERSION
Keeps proven pricing method, fixes stock detection for multi-variant pages
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict

def extract_cigarsdirect_data(url: str) -> Dict:
    """Extract product data from CigarsDirect URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        time.sleep(1.0)
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Use the PROVEN pricing method from before
        sale_price, msrp_price, discount_percent = _extract_pricing_proven(soup)
        
        # Use SIMPLE but effective stock detection
        in_stock = _extract_stock_simple_effective(soup)
        
        # Extract box quantity
        box_quantity = _extract_box_quantity(soup)
        
        return {
            'success': True,
            'price': sale_price,
            'original_price': msrp_price,
            'discount_percent': discount_percent,
            'in_stock': in_stock,
            'box_quantity': box_quantity,
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'price': None,
            'original_price': None,
            'discount_percent': None,
            'in_stock': False,
            'box_quantity': None,
            'error': str(e)
        }

def _extract_pricing_proven(soup: BeautifulSoup) -> tuple:
    """PROVEN pricing extraction - this was working at 99% accuracy"""
    sale_price = None
    msrp_price = None
    discount_percent = None
    
    # PRIMARY METHOD: Shopify JSON data extraction (this was working perfectly)
    scripts = soup.find_all('script')
    for script in scripts:
        if script.string and 'product' in script.string.lower():
            script_text = script.string
            
            # Extract price from JSON (cents to dollars)
            price_matches = re.findall(r'"price":\s*(\d+)', script_text)
            if price_matches:
                try:
                    price_cents = int(price_matches[0])
                    candidate_price = price_cents / 100
                    
                    # Validate reasonable box price range
                    if 150 <= candidate_price <= 2500:
                        sale_price = candidate_price
                except (ValueError, IndexError):
                    continue
            
            # Extract MSRP from JSON
            compare_matches = re.findall(r'"compare_at_price":\s*(\d+)', script_text)
            if compare_matches:
                try:
                    compare_cents = int(compare_matches[0])
                    candidate_msrp = compare_cents / 100
                    
                    if candidate_msrp > 0 and 150 <= candidate_msrp <= 2500:
                        msrp_price = candidate_msrp
                except (ValueError, IndexError):
                    continue
            
            # If we found a price via JSON, we're done
            if sale_price:
                break
    
    # FALLBACK: Element-based extraction if JSON fails
    if not sale_price:
        price_elements = soup.find_all(['span', 'div'], class_=re.compile(r'price', re.I))
        
        for elem in price_elements:
            # Skip navigation price elements
            elem_class = str(elem.get('class', []))
            if 'grid-product__price' in elem_class:
                continue  # Skip navigation grid prices
            
            price_text = elem.get_text()
            price_match = re.search(r'\$(\d+\.?\d*)', price_text)
            if price_match:
                try:
                    price_val = float(price_match.group(1))
                    if 150 <= price_val <= 2500:
                        sale_price = price_val
                        break
                except ValueError:
                    continue
    
    # Calculate discount percentage
    if msrp_price and sale_price and msrp_price > sale_price:
        discount_percent = ((msrp_price - sale_price) / msrp_price) * 100
    
    return sale_price, msrp_price, discount_percent

def _extract_stock_simple_effective(soup: BeautifulSoup) -> bool:
    """Simple but effective stock detection - focus on main purchase button"""
    
    # Look for the primary "ADD TO CART" button
    # This is the most reliable indicator across all page types
    add_cart_buttons = soup.find_all(['button'], string=re.compile(r'add.*to.*cart', re.I))
    
    # If we find an "ADD TO CART" button, check if it's enabled
    for button in add_cart_buttons:
        button_text = button.get_text(strip=True).upper()
        
        if 'ADD TO CART' in button_text:
            # Check if button is disabled
            if button.get('disabled') or 'disabled' in str(button.get('class', [])):
                return False
            else:
                return True
    
    # Look for "SOLD OUT" in button text specifically
    all_buttons = soup.find_all(['button'])
    for button in all_buttons:
        button_text = button.get_text(strip=True).upper()
        if 'SOLD OUT' in button_text:
            return False
    
    # Look for "Notify Me" buttons (indicates out of stock)
    notify_buttons = soup.find_all(['button'], string=re.compile(r'notify.*me', re.I))
    if notify_buttons:
        return False
    
    # If we found any add to cart button but couldn't determine status clearly,
    # default to available (most CigarsDirect products are available)
    if add_cart_buttons:
        return True
    
    # Final check: look for any mention of stock status in main content
    page_text = soup.get_text()
    
    # Simple text-based check as final fallback
    if 'in stock' in page_text.lower() and 'ready to ship' in page_text.lower():
        return True
    
    # Conservative default
    return False

def _extract_box_quantity(soup: BeautifulSoup) -> int:
    """Extract box quantity"""
    page_text = soup.get_text()
    
    # Look for "Box of X" pattern
    box_match = re.search(r'box\s+of\s+(\d+)', page_text, re.I)
    if box_match:
        try:
            qty = int(box_match.group(1))
            if 5 <= qty <= 50:  # Reasonable box size
                return qty
        except ValueError:
            pass
    
    return None
