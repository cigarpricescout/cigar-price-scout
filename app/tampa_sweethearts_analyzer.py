"""
Tampa Sweethearts Extractor - Analysis Version
Analyzes page structure to determine if dynamic pricing is extractable
URL: https://www.tampasweethearts.com/hemingwayclassic.aspx
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional

def analyze_tampa_sweethearts(url: str) -> Dict:
    """
    Analyze Tampa Sweethearts page structure to understand pricing mechanism
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
        
        print(f"DEBUG: Product title: {product_title}")
        
        # Get page text for analysis
        page_text = soup.get_text()
        print(f"DEBUG: Page contains {len(page_text)} characters")
        
        # Look for pricing patterns
        all_prices = re.findall(r'\$(\d+\.?\d*)', page_text)
        price_values = [float(p) for p in all_prices if 10 <= float(p) <= 2000]
        print(f"DEBUG: Found prices: {sorted(set(price_values))}")
        
        # Look for form elements that might control pricing
        select_elements = soup.find_all('select')
        print(f"DEBUG: Found {len(select_elements)} select elements")
        
        for i, select in enumerate(select_elements):
            select_name = select.get('name', 'unnamed')
            options = select.find_all('option')
            print(f"DEBUG: Select {i+1} (name='{select_name}'):")
            for option in options[:5]:  # Show first 5 options
                value = option.get('value', '')
                text = option.get_text().strip()
                print(f"  Option: value='{value}' text='{text}'")
        
        # Look for packaging-related text
        packaging_keywords = ['box of 25', 'box of', 'packaging', 'quantity', 'select']
        for keyword in packaging_keywords:
            if keyword.lower() in page_text.lower():
                keyword_pos = page_text.lower().find(keyword.lower())
                start = max(0, keyword_pos - 50)
                end = min(len(page_text), keyword_pos + 100)
                context = page_text[start:end]
                print(f"DEBUG: Context around '{keyword}': ...{context}...")
        
        # Look for JavaScript that might handle pricing
        script_tags = soup.find_all('script')
        print(f"DEBUG: Found {len(script_tags)} script tags")
        
        for script in script_tags:
            script_content = script.get_text() if script.string else ""
            if 'price' in script_content.lower() and len(script_content) > 100:
                print(f"DEBUG: Found price-related JavaScript (first 200 chars):")
                print(f"  {script_content[:200]}...")
                break
        
        # Look for data attributes that might contain pricing info
        price_data_attrs = soup.find_all(attrs=lambda x: x and any('price' in str(k).lower() for k in x.keys()))
        if price_data_attrs:
            print(f"DEBUG: Found {len(price_data_attrs)} elements with price-related data attributes")
            for elem in price_data_attrs[:3]:
                attrs = {k: v for k, v in elem.attrs.items() if 'price' in str(k).lower()}
                print(f"  Element with price attrs: {attrs}")
        
        # Look for input fields that might contain pricing
        input_elements = soup.find_all('input', type='hidden')
        print(f"DEBUG: Found {len(input_elements)} hidden input elements")
        for inp in input_elements[:5]:
            name = inp.get('name', '')
            value = inp.get('value', '')
            if 'price' in name.lower() or re.search(r'\d+\.?\d*', str(value)):
                print(f"  Hidden input: name='{name}' value='{value}'")
        
        return {
            'success': True,
            'product_title': product_title,
            'prices_found': sorted(set(price_values)),
            'select_elements_count': len(select_elements),
            'script_tags_count': len(script_tags),
            'analysis_complete': True
        }
        
    except Exception as e:
        print(f"DEBUG: Exception occurred: {e}")
        return {
            'success': False,
            'error': str(e)
        }

# Test function
if __name__ == "__main__":
    test_url = "https://www.tampasweethearts.com/hemingwayclassic.aspx"
    
    print("=" * 70)
    print("TAMPA SWEETHEARTS ANALYSIS")
    print("=" * 70)
    
    result = analyze_tampa_sweethearts(test_url)
    
    print("\n" + "=" * 50)
    print("ANALYSIS SUMMARY")
    print("=" * 50)
    print(f"Success: {result.get('success', False)}")
    print(f"Product: {result.get('product_title', 'Unknown')}")
    print(f"Prices found: {result.get('prices_found', [])}")
    print(f"Select elements: {result.get('select_elements_count', 0)}")
    print(f"Script tags: {result.get('script_tags_count', 0)}")
    
    if not result.get('success', False):
        print(f"Error: {result.get('error', 'Unknown error')}")
