import requests
import json

def test_sovrn_cigars():
    """Simple test to extract cigar products from Sovrn API"""
    
    SECRET_KEY = "a8e2eb6acb128d673d1213efdb1a1c3c30c8a98c"
    SITE_API_KEY = "6ccb4c241e1761e7b22c9a71c341701b"
    
    base_url = "https://comparisons.sovrn.com/api/affiliate/v3.5"
    headers = {
        'Authorization': f'secret {SECRET_KEY}',
        'Accept': 'application/json'
    }
    
    # Test premium cigar brands you suggested
    search_terms = [
        "padron",
        "oliva", 
        "arturo fuente",
        "rocky patel",
        "ashton",
        "davidoff",
        "romeo y julieta",
        "hoyo de monterrey"
    ]
    
    found_cigars = []
    
    for term in search_terms:
        print(f"\nSearching for: {term}")
        
        endpoint = f"{base_url}/sites/{SITE_API_KEY}/compare/prices/usd_en/by/accuracy"
        params = {
            'search-keywords': term,
            'limit': 20
        }
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                products = response.json()
                print(f"Found {len(products)} products")
                
                # Extract cigar-related products
                for product in products:
                    if isinstance(product, dict):
                        name = product.get('name', '')
                        price = product.get('salePrice', product.get('retailPrice', 0))
                        url = product.get('deeplink', '')
                        merchant = product.get('merchant', {})
                        
                        # Check if it's actually a cigar
                        name_lower = name.lower()
                        if any(indicator in name_lower for indicator in ['cigar', 'robusto', 'churchill', 'toro', 'corona']):
                            # Exclude accessories
                            if not any(exclusion in name_lower for exclusion in ['lighter', 'cutter', 'humidor', 'ashtray']):
                                merchant_name = merchant.get('name', 'Unknown') if isinstance(merchant, dict) else str(merchant)
                                
                                cigar_info = {
                                    'search_term': term,
                                    'name': name,
                                    'price': price,
                                    'merchant': merchant_name,
                                    'url': url
                                }
                                found_cigars.append(cigar_info)
                                print(f"  CIGAR FOUND: {name} - ${price} from {merchant_name}")
                
            else:
                print(f"API Error: {response.status_code}")
                
        except Exception as e:
            print(f"Request failed: {e}")
    
    print(f"\n{'='*60}")
    print("CIGAR PRODUCTS FOUND IN SOVRN")
    print(f"{'='*60}")
    
    if found_cigars:
        print(f"Total cigar products found: {len(found_cigars)}")
        print("\nAll found cigars:")
        for i, cigar in enumerate(found_cigars, 1):
            print(f"{i}. {cigar['name']}")
            print(f"   Price: ${cigar['price']}")
            print(f"   Merchant: {cigar['merchant']}")
            print(f"   Search term: {cigar['search_term']}")
            print()
        
        print("CONCLUSION: Sovrn API has cigar products available!")
        print("Next step: Build full data collection system")
    else:
        print("No actual cigar products found")
        print("Sovrn may only have cigar accessories or filtered cigars")
        print("Consider focusing on web scraping approach")

if __name__ == "__main__":
    test_sovrn_cigars()
