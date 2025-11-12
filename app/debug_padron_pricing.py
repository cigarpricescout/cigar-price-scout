#!/usr/bin/env python3
"""
Debug script for Hiland's pricing extraction
Tests the specific Padron URL to see what's happening
"""

import sys
import os

# Add retailers directory to path
retailers_dir = os.path.join(os.path.dirname(__file__), '..', 'tools', 'price_monitoring', 'retailers')
sys.path.append(retailers_dir)

import hilands_cigars
import requests
from bs4 import BeautifulSoup

def debug_padron_pricing():
    """Debug the Padron pricing extraction specifically"""
    
    url = "https://www.hilandscigars.com/shop/cigars/ashton/ashton-vsg-virgin-sun-grown/ashton-vsg-robusto-5-5x50-box-of-24-free-shipping/"
    
    print("=" * 60)
    print(f"DEBUGGING ASHTON VSG PRICING")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Expected Price: $421.98")
    print()
    
    # Test the full extractor
    print("1. FULL EXTRACTOR TEST:")
    print("-" * 30)
    result = hilands_cigars.extract_hilands_cigars_data(url)
    print(f"   Extracted Price: ${result.get('price', 'N/A')}")
    print(f"   Box Quantity: {result.get('box_quantity', 'N/A')}")
    print(f"   In Stock: {result.get('in_stock', 'N/A')}")
    print(f"   Success: {result.get('success', 'N/A')}")
    if result.get('error'):
        print(f"   Error: {result['error']}")
    print()
    
    # Manual debugging
    print("2. MANUAL PRICE ELEMENT ANALYSIS:")
    print("-" * 35)
    
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        response = session.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find ALL price elements
        price_elements = soup.find_all(['span', 'div'], class_=lambda x: x and ('price' in str(x).lower() or 'amount' in str(x).lower() or 'cost' in str(x).lower()))
        
        print(f"   Found {len(price_elements)} price-related elements:")
        
        for i, elem in enumerate(price_elements):
            price_text = elem.get_text().strip()
            elem_classes = elem.get('class', [])
            print(f"   [{i+1}] Text: '{price_text}' | Classes: {elem_classes}")
        
        print()
        
        # Look for specific price patterns
        print("3. PRICE PATTERN ANALYSIS:")
        print("-" * 30)
        
        import re
        all_text = soup.get_text()
        price_matches = re.findall(r'\$[\d,]+\.?\d*', all_text)
        unique_prices = list(set(price_matches))
        
        print(f"   All price patterns found: {unique_prices}")
        
        # Check for strikethrough prices
        strikethrough_elems = soup.find_all(['del', 's']) + soup.find_all(attrs={'style': re.compile(r'text-decoration:\s*line-through', re.I)})
        if strikethrough_elems:
            print(f"   Strikethrough elements found: {len(strikethrough_elems)}")
            for elem in strikethrough_elems:
                print(f"     - '{elem.get_text().strip()}'")
        else:
            print("   No strikethrough elements found")
            
    except Exception as e:
        print(f"   Error during manual analysis: {e}")
    
    print()
    print("=" * 60)

if __name__ == "__main__":
    debug_padron_pricing()
