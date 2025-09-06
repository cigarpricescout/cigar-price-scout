import requests
import json
from datetime import datetime

# Replace with your actual CJ Developer Key
CJ_API_KEY = "YOUR_DEVELOPER_KEY_HERE"

def test_cj_connection():
    """Test basic connection to CJ API"""
    url = "https://product-search.api.cj.com/v2/product-search"
    
    headers = {
        'Authorization': f'Bearer {CJ_API_KEY}',
        'Accept': 'application/json'
    }
    
    # Test search for cigars from Famous Smoke Shop (advertiser-ids: 1357)
    params = {
        'website-id': 'YOUR_WEBSITE_ID',  # Get this from CJ dashboard
        'advertiser-ids': '1357',  # Famous Smoke Shop
        'keywords': 'cigar',
        'records-per-page': 10
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ API Connection Successful!")
            print(f"Found {len(data.get('products', []))} products")
            
            # Print first product as example
            if data.get('products'):
                product = data['products'][0]
                print(f"\nExample Product:")
                print(f"Name: {product.get('name', 'N/A')}")
                print(f"Price: ${product.get('price', 'N/A')}")
                print(f"Brand: {product.get('manufacturer', 'N/A')}")
        else:
            print(f"❌ API Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    print("Testing CJ API Connection...")
    test_cj_connection()
