#!/usr/bin/env python3
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

# Load token
project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(project_root / '.env')

token = os.getenv('CJ_PERSONAL_ACCESS_TOKEN')
headers = {'Authorization': f'Bearer {token}'}

retailers = {
    'Cigars International': '5359174',
    'Gotham Cigars': '3982297',
    'Thompson Cigar': '2965991',
    'Cigora': '5815943',
    'Famous Smoke Shop': '6240744'
}

print("=" * 60)
print("Testing CJ Product Catalogs for All Approved Retailers")
print("=" * 60)

for name, advertiser_id in retailers.items():
    print(f"\n{name} (ID: {advertiser_id})")
    print("-" * 40)
    
    url = "https://product-search.api.cj.com/v2/product-search"
    params = {
        'website-id': '101532120',
        'advertiser-ids': advertiser_id,
        'keywords': 'cigar',
        'records-per-page': 10
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            # Check if products exist
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.text)
            products = root.findall('.//product')
            print(f"[SUCCESS] Found {len(products)} products!")
            
            if products:
                # Show first product sample
                first = products[0]
                name_elem = first.find('name')
                price_elem = first.find('price')
                if name_elem is not None:
                    print(f"Sample: {name_elem.text[:50]}...")
                    print(f"Price: ${price_elem.text if price_elem is not None else 'N/A'}")
        elif response.status_code == 404:
            print("[NO CATALOG] Retailer doesn't provide product feed")
        else:
            print(f"[ERROR] API returned {response.status_code}")
            
    except Exception as e:
        print(f"[ERROR] {str(e)}")

print("\n" + "=" * 60)
print("Summary: Retailers with product catalogs can be integrated")
print("=" * 60)
