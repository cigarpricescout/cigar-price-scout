#!/usr/bin/env python3
"""
Debug script to test the import path for Hiland's extractor
"""
import sys
import os

# Add the tools directory to path (same as in updater)
sys.path.append(os.path.join(os.path.dirname(__file__), 'tools', 'price_monitoring'))

print("Python path:")
for p in sys.path:
    print(f"  {p}")

print("\nTrying to import...")

try:
    from retailers.hilands_cigars import extract_hilands_cigars_data
    print("✅ SUCCESS: Import worked!")
    
    # Test the function
    print("\nTesting function...")
    result = extract_hilands_cigars_data('https://www.hilandscigars.com/shop/cigars/arturo-fuente/a-fuente-don-carlos/don-carlos-robusto/')
    print(f"✅ Function test result: {result.get('success', False)}")
    
except ImportError as e:
    print(f"❌ IMPORT ERROR: {e}")
    
    # Check if the file exists
    expected_path = os.path.join('tools', 'price_monitoring', 'retailers', 'hilands_cigars.py')
    print(f"\nChecking if file exists at: {expected_path}")
    print(f"File exists: {os.path.exists(expected_path)}")
    
    # List what's actually in the retailers directory
    retailers_dir = os.path.join('tools', 'price_monitoring', 'retailers')
    if os.path.exists(retailers_dir):
        print(f"\nContents of {retailers_dir}:")
        for item in os.listdir(retailers_dir):
            print(f"  {item}")
    else:
        print(f"\n❌ Directory doesn't exist: {retailers_dir}")

except Exception as e:
    print(f"❌ OTHER ERROR: {e}")
