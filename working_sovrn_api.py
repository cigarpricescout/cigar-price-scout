import requests
import json
import csv
import time
from datetime import datetime
from pathlib import Path

class SovrnPriceComparisonAPI:
    def __init__(self, secret_key, site_api_key):
        self.secret_key = secret_key
        self.site_api_key = site_api_key
        self.base_url = "https://comparisons.sovrn.com/api/affiliate/v3.5"
        self.headers = {
            'Authorization': f'secret {secret_key}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def search_products(self, search_keywords, market="usd_en", limit=100):
        """Search for products using keywords"""
        print(f"Searching for: '{search_keywords}' in market: {market}")
        
        endpoint = f"{self.base_url}/sites/{self.site_api_key}/compare/prices/{market}/by/accuracy"
        
        params = {
            'search-keywords': search_keywords,
            'limit': limit
        }
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)
            
            print(f"API Response Status: {response.status_code}")
            print(f"Request URL: {response.url}")
            
            if response.status_code == 200:
                data = response.json()
                return self.analyze_product_data(data, search_keywords)
            else:
                print(f"Error Response ({response.status_code}): {response.text}")
                return None
                
        except Exception as e:
            print(f"Request failed: {e}")
            return None
    
    def search_by_retailer_url(self, product_url, market="usd_en"):
        """Search for product alternatives using a retailer's product URL"""
        print(f"Searching by product URL: {product_url}")
        
        endpoint = f"{self.base_url}/sites/{self.site_api_key}/compare/prices/{market}/by/accuracy"
        
        params = {
            'plainlink': product_url
        }
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)
            
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                return self.analyze_product_data(data, f"URL: {product_url}")
            else:
                print(f"Error Response ({response.status_code}): {response.text}")
                return None
                
        except Exception as e:
            print(f"Request failed: {e}")
            return None
    
    def analyze_product_data(self, data, search_term):
        """Analyze the API response and extract cigar-relevant information"""
        print(f"\n=== SOVRN API RESPONSE ANALYSIS ===")
        print(f"Search term: {search_term}")
        
        if not data:
            print("Empty response")
            return None
        
        print(f"Response type: {type(data)}")
        if isinstance(data, dict):
            print(f"Top-level keys: {list(data.keys())}")
        
        # Look for products in response
        products = []
        if isinstance(data, dict):
            # Common locations for products in API responses
            for key in ['products', 'results', 'items', 'data', 'offers']:
                if key in data:
                    products = data[key] if isinstance(data[key], list) else [data[key]]
                    break
            
            # If no products found, the whole response might be a product list
            if not products and isinstance(data, list):
                products = data
        elif isinstance(data, list):
            products = data
        
        print(f"Found {len(products)} products")
        
        if not products:
            print("No products found in response")
            print(f"Full response structure: {json.dumps(data, indent=2)[:1000]}...")
            return None
        
        # Analyze first product for structure
        sample = products[0] if products else {}
        print(f"\n=== SAMPLE PRODUCT STRUCTURE ===")
        if isinstance(sample, dict):
            print(f"Product fields: {list(sample.keys())}")
            
            # Extract key information based on actual API response structure
            product_info = {}
            field_mappings = {
                'title': ['name', 'title', 'product_name', 'productName'],
                'price': ['salePrice', 'retailPrice', 'price', 'cost', 'amount'],
                'description': ['description', 'desc', 'productDescription'],
                'url': ['deeplink', 'url', 'link', 'productUrl', 'affiliateUrl'],
                'merchant': ['merchant', 'retailer', 'store', 'merchantName'],
                'brand': ['brand', 'manufacturer', 'brandName'],
                'image': ['image', 'imageUrl', 'thumbnail'],
                'availability': ['availability', 'inStock', 'stock', 'affiliatable']
            }
            
            for field_name, possible_keys in field_mappings.items():
                for key in possible_keys:
                    if key in sample:
                        product_info[field_name] = sample[key]
                        break
                if field_name not in product_info:
                    product_info[field_name] = 'N/A'
            
            print(f"\n=== EXTRACTED PRODUCT INFORMATION ===")
            for field, value in product_info.items():
                display_value = str(value)
                if len(display_value) > 100:
                    display_value = display_value[:100] + "..."
                print(f"{field}: {display_value}")
            
            # Check for cigar-specific content
            title_desc = f"{product_info.get('title', '')} {product_info.get('description', '')}".lower()
            
            cigar_indicators = {
                'has_cigar_keyword': 'cigar' in title_desc,
                'has_wrapper_info': any(w in title_desc for w in ['maduro', 'connecticut', 'habano', 'natural']),
                'has_vitola_info': any(v in title_desc for v in ['robusto', 'churchill', 'toro', 'corona']),
                'has_size_info': any(s in title_desc for s in ['x 50', 'x 52', ' x ', 'ring gauge']),
                'likely_cigar_retailer': any(r in product_info.get('merchant', '').lower() for r in ['cigar', 'smoke', 'tobacco'])
            }
            
            print(f"\n=== CIGAR RELEVANCE ANALYSIS ===")
            for indicator, found in cigar_indicators.items():
                print(f"{indicator}: {'YES' if found else 'NO'}")
            
            return {
                'total_products': len(products),
                'sample_product': product_info,
                'cigar_analysis': cigar_indicators,
                'all_products': products,
                'raw_response': data
            }
        else:
            print(f"Unexpected product structure: {sample}")
            return None
    
    def test_cigar_searches(self):
        """Test various search terms starting broad, then cigar-specific"""
        search_terms = [
            # First test broad terms to confirm API works
            "shoes",
            "laptop", 
            "coffee",
            # Then test tobacco-adjacent terms
            "tobacco",
            "smoking",
            # Finally test cigar terms
            "cigars",
            "cigar",
            "robusto",
            "montecristo"
        ]
        
        results = {}
        
        for term in search_terms:
            print(f"\n{'='*60}")
            print(f"Testing search term: '{term}'")
            print(f"{'='*60}")
            
            result = self.search_products(term, limit=20)
            results[term] = result
            
            if result and result.get('total_products', 0) > 0:
                print(f"SUCCESS: Found {result['total_products']} products")
                
                # Check if any products are from known cigar retailers
                cigar_retailers = []
                for product in result['all_products'][:5]:  # Check first 5
                    if isinstance(product, dict):
                        merchant = product.get('merchant', product.get('retailer', ''))
                        # Handle merchant as dict or string
                        if isinstance(merchant, dict):
                            merchant_name = merchant.get('name', str(merchant))
                        else:
                            merchant_name = str(merchant)
                        
                        if any(keyword in merchant_name.lower() for keyword in ['cigar', 'smoke', 'tobacco']):
                            cigar_retailers.append(merchant_name)
                
                if cigar_retailers:
                    print(f"Found cigar retailers: {list(set(cigar_retailers))}")
            else:
                print("No products found or API error")
            
            # Rate limiting
            time.sleep(1)
        
        return results
    
    def extract_cigar_products(self, api_response):
        """Extract and format cigar products from API response"""
        if not api_response or not api_response.get('all_products'):
            return []
        
        cigar_products = []
        
        for product in api_response['all_products']:
            if not isinstance(product, dict):
                continue
            
            # Extract basic fields
            title = product.get('title', product.get('name', ''))
            description = product.get('description', '')
            
            # Check if it's actually a cigar
            if not self.is_cigar_product(title, description):
                continue
            
            # Parse cigar attributes
            brand, line, wrapper, vitola, size = self.parse_cigar_attributes(title, description)
            
            # Extract other fields
            price_str = str(product.get('price', product.get('salePrice', '0')))
            price = self.extract_price(price_str)
            
            url = product.get('url', product.get('link', ''))
            merchant = product.get('merchant', product.get('retailer', ''))
            availability = product.get('availability', product.get('inStock', True))
            
            cigar_product = {
                'title': title,
                'url': url,
                'brand': brand,
                'line': line,
                'wrapper': wrapper,
                'vitola': vitola,
                'size': size,
                'box_qty': self.extract_box_qty(title),
                'price': price,
                'in_stock': availability if isinstance(availability, bool) else str(availability).lower() not in ['false', 'out of stock', 'unavailable']
            }
            
            cigar_products.append(cigar_product)
        
        return cigar_products
    
    def is_cigar_product(self, title, description):
        """Check if product is actually a cigar"""
        text = f"{title} {description}".lower()
        
        cigar_indicators = ['cigar', 'robusto', 'churchill', 'toro', 'corona', 'torpedo', 'belicoso']
        exclusions = ['lighter', 'cutter', 'humidor', 'ashtray', 'case']
        
        has_cigar = any(indicator in text for indicator in cigar_indicators)
        has_exclusion = any(exclusion in text for exclusion in exclusions)
        
        return has_cigar and not has_exclusion
    
    def parse_cigar_attributes(self, title, description):
        """Parse cigar-specific attributes from text"""
        text = f"{title} {description}"
        
        # Extract size
        size_match = re.search(r'(\d+\.?\d*\s*x\s*\d+)', text, re.IGNORECASE)
        size = size_match.group(1).strip() if size_match else ""
        
        # Extract wrapper
        wrapper_patterns = ['Connecticut', 'Maduro', 'Habano', 'Natural', 'Cameroon', 'Corojo', 'Sumatra']
        wrapper = ""
        for pattern in wrapper_patterns:
            if pattern.lower() in text.lower():
                wrapper = pattern
                break
        
        # Extract vitola
        vitola_patterns = ['Robusto', 'Churchill', 'Toro', 'Corona', 'Torpedo', 'Belicoso', 'Gordo']
        vitola = ""
        for pattern in vitola_patterns:
            if pattern.lower() in text.lower():
                vitola = pattern
                break
        
        # Extract brand and line
        words = title.split()
        brand = words[0] if words else ""
        line = words[1] if len(words) > 1 else ""
        
        return brand, line, wrapper, vitola, size
    
    def extract_price(self, price_str):
        """Extract numeric price from price string"""
        import re
        price_match = re.search(r'[\d,]+\.?\d*', str(price_str).replace('$', '').replace(',', ''))
        return float(price_match.group()) if price_match else 0.0
    
    def extract_box_qty(self, title):
        """Extract box quantity from title"""
        import re
        box_patterns = [r'box of (\d+)', r'(\d+) count', r'(\d+)ct']
        for pattern in box_patterns:
            match = re.search(pattern, title.lower())
            if match:
                return int(match.group(1))
        return 25  # Default

def main():
    print("SOVRN PRICE COMPARISON API TESTING")
    print("=" * 50)
    print(f"Timestamp: {datetime.now()}")
    
    # You need to provide these values
    SECRET_KEY = "a8e2eb6acb128d673d1213efdb1a1c3c30c8a98c"  # From Sovrn dashboard
    SITE_API_KEY = "6ccb4c241e1761e7b22c9a71c341701b"  # Your site API key
    
    if SECRET_KEY == "YOUR_SECRET_KEY_HERE" or SITE_API_KEY == "YOUR_SITE_API_KEY_HERE":
        print("Please update the script with your actual Sovrn credentials:")
        print("1. SECRET_KEY: Get from Account > Settings > Generate Secret Key")
        print("2. SITE_API_KEY: Your site's API key from the same settings page")
        return
    
    api = SovrnPriceComparisonAPI(SECRET_KEY, SITE_API_KEY)
    
    print("Testing Sovrn Price Comparison API...")
    
    # Test cigar searches
    results = api.test_cigar_searches()
    
    print(f"\n{'='*60}")
    print("SUMMARY OF SEARCH RESULTS")
    print(f"{'='*60}")
    
    total_found = 0
    for term, result in results.items():
        if result and result.get('total_products', 0) > 0:
            count = result['total_products']
            total_found += count
            print(f"SUCCESS '{term}': {count} products")
        else:
            print(f"NO RESULTS '{term}': No products found")
    
    print(f"\nTotal products found across all searches: {total_found}")
    
    if total_found > 0:
        print("\n=== NEXT STEPS ===")
        print("1. API is working! You can access product data")
        print("2. Build collection script to gather data from all search terms")
        print("3. Filter and process cigar products into CSV format")
        print("4. Set up automated daily updates")
    else:
        print("\n=== TROUBLESHOOTING ===")
        print("1. Check your SECRET_KEY and SITE_API_KEY are correct")
        print("2. Verify your site is approved in Sovrn dashboard")
        print("3. Try different search terms or check API documentation")

if __name__ == "__main__":
    main()
