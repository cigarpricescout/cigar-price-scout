"""
CigarsDirect Price Extractor - Production Version
Extracts product data from CigarsDirect URLs
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
        
        # Extract pricing
        sale_price, msrp_price, discount_percent = _extract_pricing(soup)
        
        # Extract stock status
        in_stock = _extract_stock(soup)
        
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

def _extract_pricing(soup: BeautifulSoup) -> tuple:
    """Extract sale price and MSRP using comprehensive price detection"""
    sale_price = None
    msrp_price = None
    discount_percent = None
    
    # Get all text and extract prices with multiple patterns
    page_text = soup.get_text()
    
    # Pattern 1: Standard prices with dollar signs
    prices_1 = re.findall(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', page_text)
    
    # Pattern 2: Look specifically in crossed-out/strikethrough elements for MSRP
    crossed_out_prices = []
    strikethrough_elements = soup.find_all(['s', 'del', 'strike'])
    
    # Also look for elements with strikethrough styling
    style_elements = soup.find_all(['span', 'div'], style=re.compile(r'text-decoration.*line-through', re.I))
    strikethrough_elements.extend(style_elements)
    
    for element in strikethrough_elements:
        element_text = element.get_text(strip=True)
        # Look for prices in strikethrough elements
        strike_prices = re.findall(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', element_text)
        crossed_out_prices.extend(strike_prices)
    
    # Pattern 3: Numbers that might be prices (in reasonable ranges)
    potential_prices = re.findall(r'\b(\d{2,4}\.\d{2})\b', page_text)
    
    # Combine all patterns
    all_prices = prices_1 + crossed_out_prices + potential_prices
    
    # Convert all prices and track them
    all_converted_prices = []
    for price_str in all_prices:
        try:
            clean_price_str = price_str.replace(',', '')
            price_val = float(clean_price_str)
            all_converted_prices.append(price_val)
        except ValueError:
            continue
    
    # Remove duplicates for analysis
    unique_all_prices = sorted(list(set(all_converted_prices)))
    
    # Comprehensive navigation price filter (all known CigarsDirect navigation prices)
    navigation_prices = {
        100.0, 200.0, 206.0,  # Low navigation prices
        656.0,                # Mid-range navigation 
        1330.0, 1340.0, 1378.0, 1415.0  # High navigation prices
    }
    
    # Filter out navigation noise
    product_prices = []
    for price in unique_all_prices:
        if 150 <= price <= 2000 and price not in navigation_prices:
            product_prices.append(price)
    
    if len(product_prices) >= 2:
        # Check if we have a premium single price that should take priority
        premium_prices = [p for p in product_prices if p >= 1500]
        
        if premium_prices:
            # Premium product - use highest premium price as single price
            sale_price = max(premium_prices)
        else:
            # Look for discount patterns in regular price range
            found_pair = False
            for i in range(len(product_prices)):
                for j in range(i+1, len(product_prices)):
                    lower = product_prices[i]
                    higher = product_prices[j]
                    
                    discount = (higher - lower) / higher * 100
                    
                    # Look for reasonable discount range
                    if 5 <= discount <= 25:
                        sale_price = lower
                        msrp_price = higher
                        found_pair = True
                        break
                if found_pair:
                    break
            
            # If no discount pattern, use highest product price
            if not found_pair:
                sale_price = max(product_prices)
    
    elif len(product_prices) == 1:
        # Single product price
        sale_price = product_prices[0]
    
    else:
        # No product prices found after filtering
        # Fallback: look for the most reasonable prices, even if near navigation range
        reasonable_prices = [p for p in unique_all_prices if 160 <= p <= 2000]
        
        if reasonable_prices:
            # Try to find pairs that aren't navigation prices
            non_nav_prices = [p for p in reasonable_prices if p not in navigation_prices]
            
            if len(non_nav_prices) >= 2:
                # Try discount pattern on non-navigation prices
                for i in range(len(non_nav_prices)):
                    for j in range(i+1, len(non_nav_prices)):
                        lower = non_nav_prices[i]
                        higher = non_nav_prices[j]
                        
                        discount = (higher - lower) / higher * 100
                        
                        if 5 <= discount <= 30:
                            sale_price = lower
                            msrp_price = higher
                            break
                    if sale_price:
                        break
            
            # Final fallback: use highest non-navigation price
            if not sale_price and non_nav_prices:
                sale_price = max(non_nav_prices)
    
    # Calculate discount
    if msrp_price and sale_price and msrp_price > sale_price:
        discount_percent = ((msrp_price - sale_price) / msrp_price) * 100
    
    return sale_price, msrp_price, discount_percent

def _extract_stock(soup: BeautifulSoup) -> bool:
    """Extract stock status"""
    page_text = soup.get_text().lower()
    
    # Check for explicit out-of-stock indicators
    out_of_stock_indicators = [
        'sold out',
        'out of stock',
        'notify me on restock',
        'temporarily unavailable',
        'currently unavailable'
    ]
    
    in_stock_indicators = [
        'in stock',
        'ready to ship', 
        'add to cart'
    ]
    
    # Strong out-of-stock indicators take priority
    for indicator in ['sold out', 'out of stock']:
        if indicator in page_text:
            return False
    
    # Strong in-stock indicators
    for indicator in in_stock_indicators:
        if indicator in page_text:
            return True
    
    # Weak out-of-stock indicators
    for indicator in ['notify me on restock']:
        if indicator in page_text:
            return False
    
    # Default to out of stock if unclear
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
