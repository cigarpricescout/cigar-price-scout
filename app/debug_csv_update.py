#!/usr/bin/env python3
"""
Debug script to trace the CSV update process
Tests why the Ashton VSG price isn't updating in the CSV
"""

import sys
import os
import csv

# Add retailers directory to path
retailers_dir = os.path.join(os.path.dirname(__file__), '..', 'tools', 'price_monitoring', 'retailers')
sys.path.append(retailers_dir)

import hilands_cigars

def debug_csv_update():
    """Debug the CSV update process step by step"""
    
    ashton_url = "https://www.hilandscigars.com/shop/cigars/ashton/ashton-vsg-virgin-sun-grown/ashton-vsg-robusto-5-5x50-box-of-24-free-shipping/"
    
    print("=" * 70)
    print("DEBUGGING CSV UPDATE PROCESS")
    print("=" * 70)
    
    # Step 1: Test extraction
    print("1. TESTING EXTRACTION:")
    print("-" * 30)
    result = hilands_cigars.extract_hilands_cigars_data(ashton_url)
    print(f"   Extracted Price: ${result.get('price', 'N/A')}")
    print(f"   Success: {result.get('success', False)}")
    if result.get('error'):
        print(f"   Error: {result['error']}")
    
    # Step 2: Read current CSV
    print("\n2. READING CURRENT CSV:")
    print("-" * 30)
    csv_path = os.path.join('..', 'static', 'data', 'hilands.csv')
    
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
        
        # Find the Ashton row
        ashton_row = None
        for i, row in enumerate(data):
            if ashton_url in row.get('url', ''):
                ashton_row = row
                print(f"   Found Ashton row at index {i}:")
                print(f"   Current Price: {row.get('price', 'N/A')}")
                print(f"   URL: {row.get('url', 'N/A')}")
                break
        
        if not ashton_row:
            print("   ERROR: Ashton row NOT FOUND in CSV!")
            print("   Available URLs in CSV:")
            for row in data:
                print(f"     - {row.get('url', 'N/A')}")
        
    except Exception as e:
        print(f"   ERROR: Error reading CSV: {e}")
        return
    
    # Step 3: Simulate update process
    print("\n3. SIMULATING UPDATE:")
    print("-" * 30)
    
    if ashton_row and result.get('success') and result.get('price'):
        old_price = ashton_row.get('price', 'N/A')
        new_price = result.get('price')
        
        print(f"   Old Price: ${old_price}")
        print(f"   New Price: ${new_price}")
        
        if str(old_price) == str(new_price):
            print("   WARNING: Prices are the same - no update needed")
        else:
            print("   SUCCESS: Prices differ - should update")
            
            # Simulate the update
            ashton_row['price'] = new_price
            print(f"   Updated row price to: ${ashton_row['price']}")
    
    # Step 4: Check data types
    print("\n4. DATA TYPE ANALYSIS:")
    print("-" * 30)
    if ashton_row:
        print(f"   CSV price type: {type(ashton_row.get('price'))} = '{ashton_row.get('price')}'")
        print(f"   Extracted price type: {type(result.get('price'))} = '{result.get('price')}'")
        
        # Check if they're equal as strings
        csv_price_str = str(ashton_row.get('price', '')).strip()
        extracted_price_str = str(result.get('price', '')).strip()
        
        print(f"   CSV price (string): '{csv_price_str}'")
        print(f"   Extracted price (string): '{extracted_price_str}'")
        print(f"   String comparison equal: {csv_price_str == extracted_price_str}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    debug_csv_update()
