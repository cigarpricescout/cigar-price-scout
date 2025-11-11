import requests
import json

def test_sovrn_product_recommendations():
    """Test Sovrn Product Recommendation API for cigar content"""
    
    api_key = "6ccb4c241e1761e7b22c9a71c341701b"
    base_url = "https://shopping-gallery.prd-commerce.sovrnservices.com/ai-orchestration/products"
    
    headers = {
        "accept": "application/json",
        "content-type": "application/json"
    }
    
    # Test different cigar-related content to see what products are recommended
    test_cases = [
        {
            "title": "Premium Cigars Review",
            "content": "Looking for the best premium cigars including Padron, Arturo Fuente, Oliva, and Rocky Patel. Interested in robusto and churchill vitolas with Connecticut and Maduro wrappers.",
            "description": "General premium cigar content"
        },
        {
            "title": "Cigar Shopping Guide",
            "content": "Best places to buy cigars online. Thompson Cigar, JR Cigars, Famous Smoke Shop, and Cigars International have great selections of handmade premium cigars.",
            "description": "Content mentioning known cigar retailers"
        },
        {
            "title": "Cohiba Cigar Review",
            "content": "Cohiba cigars are among the most prestigious. The Cohiba Robusto and Churchill are excellent choices for special occasions. Dominican and Cuban tobacco blends.",
            "description": "Specific brand content"
        },
        {
            "title": "Cigar Accessories",
            "content": "Essential cigar accessories include humidors, cutters, lighters, and ashtrays. Proper storage and cutting tools enhance the smoking experience.",
            "description": "Cigar accessories to test broader product range"
        }
    ]
    
    found_products = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"TEST {i}: {test_case['description']}")
        print(f"{'='*60}")
        print(f"Content: {test_case['content'][:100]}...")
        
        params = {
            'apiKey': api_key,
            'market': 'usd_en',
            'numProducts': 20,  # Get more products to analyze
            'pageUrl': f'https://cigarpricescout.com/test/{i}'
        }
        
        payload = {
            'title': test_case['title'],
            'content': test_case['content']
        }
        
        try:
            response = requests.post(base_url, headers=headers, params=params, json=payload, timeout=30)
            
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                products = response.json()
                print(f"Found {len(products)} recommended products")
                
                # Analyze products for cigar relevance
                cigar_products = []
                accessory_products = []
                other_products = []
                
                for product in products:
                    if isinstance(product, dict):
                        name = product.get('name', '').lower()
                        price = product.get('salePrice', product.get('retailPrice', 0))
                        merchant = product.get('merchant', {})
                        url = product.get('deeplink', '')
                        
                        # Extract merchant info
                        if isinstance(merchant, dict):
                            merchant_name = merchant.get('name', 'Unknown')
                            merchant_id = merchant.get('id', 'Unknown')
                        else:
                            merchant_name = str(merchant)
                            merchant_id = 'Unknown'
                        
                        product_info = {
                            'name': product.get('name', ''),
                            'price': price,
                            'merchant': merchant_name,
                            'merchant_id': merchant_id,
                            'url': url
                        }
                        
                        # Categorize products
                        if any(indicator in name for indicator in ['cigar', 'robusto', 'churchill', 'toro', 'corona']):
                            if not any(exclusion in name for exclusion in ['lighter', 'cutter', 'humidor', 'ashtray']):
                                cigar_products.append(product_info)
                            else:
                                accessory_products.append(product_info)
                        else:
                            other_products.append(product_info)
                
                # Report findings
                print(f"\nCATEGORIZATION RESULTS:")
                print(f"  Actual cigars: {len(cigar_products)}")
                print(f"  Cigar accessories: {len(accessory_products)}")
                print(f"  Other products: {len(other_products)}")
                
                # Show cigar products if found
                if cigar_products:
                    print(f"\nCIGAR PRODUCTS FOUND:")
                    for product in cigar_products:
                        print(f"  - {product['name']} (${product['price']}) from {product['merchant']}")
                        found_products.append(product)
                
                # Show merchants represented
                all_merchants = set()
                for product in products:
                    if isinstance(product, dict):
                        merchant = product.get('merchant', {})
                        if isinstance(merchant, dict):
                            merchant_name = merchant.get('name', 'Unknown')
                            all_merchants.add(merchant_name)
                
                print(f"\nMERCHANTS REPRESENTED:")
                for merchant in sorted(all_merchants):
                    print(f"  - {merchant}")
                
            else:
                print(f"API Error: {response.status_code}")
                print(f"Response: {response.text}")
                
        except Exception as e:
            print(f"Request failed: {e}")
    
    # Final summary
    print(f"\n{'='*60}")
    print("OVERALL RESULTS")
    print(f"{'='*60}")
    
    if found_products:
        print(f"SUCCESS: Found {len(found_products)} actual cigar products!")
        print("\nAll cigar products discovered:")
        for i, product in enumerate(found_products, 1):
            print(f"{i}. {product['name']}")
            print(f"   Price: ${product['price']}")
            print(f"   Merchant: {product['merchant']} (ID: {product['merchant_id']})")
            print()
        
        print("CONCLUSION: Product Recommendation API can access cigar products!")
        print("Next step: Build data collection system using this API")
        
        # Check for known cigar retailers
        cigar_retailer_names = ['thompson', 'jr', 'famous', 'cigars international', 'cigar', 'tobacco']
        found_retailers = []
        for product in found_products:
            merchant_lower = product['merchant'].lower()
            if any(retailer in merchant_lower for retailer in cigar_retailer_names):
                found_retailers.append(product['merchant'])
        
        if found_retailers:
            print(f"\nKNOWN CIGAR RETAILERS FOUND: {list(set(found_retailers))}")
        
    else:
        print("No actual cigar products found through Product Recommendation API")
        print("This API may also focus on general retail rather than specialty tobacco")
        print("Recommendation: Proceed with web scraping approach")

if __name__ == "__main__":
    test_sovrn_product_recommendations()
