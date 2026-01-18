#!/usr/bin/env python3
"""
Debug script to inspect Mom's Cigars HTML structure
"""

import requests
from bs4 import BeautifulSoup
import time

def inspect_page(url):
    print(f"\n{'='*60}")
    print(f"Inspecting: {url}")
    print('='*60)
    
    try:
        time.sleep(1)
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check for tables
        tables = soup.find_all('table')
        print(f"\nTables found: {len(tables)}")
        
        if tables:
            for i, table in enumerate(tables):
                print(f"\nTable {i+1}:")
                rows = table.find_all('tr')
                print(f"  Rows: {len(rows)}")
                if rows:
                    print(f"  First row content: {rows[0].get_text().strip()[:200]}")
        
        # Check for common product containers
        print("\n--- Checking for product containers ---")
        
        # Look for product-related divs
        product_divs = soup.find_all('div', class_=lambda x: x and 'product' in str(x).lower())
        print(f"Divs with 'product' in class: {len(product_divs)}")
        if product_divs:
            print(f"  First div classes: {product_divs[0].get('class')}")
        
        # Look for price elements
        print("\n--- Looking for prices ---")
        price_patterns = ['$163.99', '$169.99', '163', '169']
        for pattern in price_patterns:
            if pattern in response.text:
                print(f"  Found '{pattern}' in page text")
        
        # Look for specific text
        print("\n--- Looking for key text ---")
        key_texts = ['Short Story', 'Box of 25', 'Lonsdale Deluxe', 'Stock']
        for text in key_texts:
            count = response.text.lower().count(text.lower())
            print(f"  '{text}': {count} occurrences")
        
        # Check for JSON-LD data
        json_scripts = soup.find_all('script', type='application/ld+json')
        print(f"\nJSON-LD scripts found: {len(json_scripts)}")
        
        # Look for any elements with stock/availability info
        print("\n--- Stock indicators ---")
        stock_elements = soup.find_all(string=lambda text: text and ('stock' in text.lower() or 'available' in text.lower()))
        print(f"Elements with 'stock'/'available': {len(stock_elements)}")
        for elem in stock_elements[:5]:
            print(f"  > {elem.strip()[:100]}")
        
        # Check page title
        title = soup.find('title')
        if title:
            print(f"\nPage Title: {title.get_text().strip()}")
        
        # Check if content is mostly JavaScript-generated
        body_text = soup.find('body')
        if body_text:
            text_length = len(body_text.get_text())
            print(f"\nBody text length: {text_length} characters")
            if text_length < 1000:
                print("  WARNING: Very little text content - likely JavaScript-rendered")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    urls = [
        "https://www.momscigars.com/products/arturo-fuente-hemingway",
        "https://www.momscigars.com/products/herrera-esteli-norteno"
    ]
    
    for url in urls:
        inspect_page(url)
