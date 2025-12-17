import requests
import csv
import json
import time
from typing import List, Dict, Optional
import re
import xml.etree.ElementTree as ET

class CJFamousSmokeIntegrator:
    def __init__(self, personal_access_token: str, website_id: str = "101532120", cid: str = "7711335"):
        """
        Initialize CJ API integration for Famous Smoke Shop
        """
        self.personal_access_token = personal_access_token
        self.website_id = website_id
        self.cid = cid
        self.link_search_url = "https://link-search.api.cj.com/v2/link-search"
        self.famous_advertiser_id = None
        
    def get_headers(self) -> Dict[str, str]:
        """Get API request headers with Personal Access Token"""
        return {
            'Authorization': f'Bearer {self.personal_access_token}',
            'User-Agent': 'CigarPriceScout/1.0'
        }
    
    def discover_famous_advertiser_id(self) -> Optional[str]:
        """
        Search for Famous Smoke Shop using the Link Search API
        """
        print("Searching for Famous Smoke Shop via CJ Link Search API...")
        
        # Search for Famous Smoke Shop links - using only valid parameters
        params = {
            'website-id': self.website_id,
            'advertiser-ids': '6240744',
            'records-per-page': 50
        }
        
        try:
            response = requests.get(
                self.link_search_url,
                params=params,
                headers=self.get_headers(),
                timeout=30
            )
            
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                content = response.text
                print(f"Response sample: {content[:300]}...")
                
                try:
                    root = ET.fromstring(content)
                    
                    # Look for Famous Smoke Shop in the results
                    found_advertisers = []
                    
                    for link in root.findall('.//link'):
                        advertiser_id_elem = link.find('advertiser-id')
                        advertiser_name_elem = link.find('advertiser-name')
                        
                        if advertiser_id_elem is not None and advertiser_name_elem is not None:
                            advertiser_id = advertiser_id_elem.text
                            advertiser_name = advertiser_name_elem.text
                            
                            found_advertisers.append(f"{advertiser_name} (ID: {advertiser_id})")
                            
                            if 'famous' in advertiser_name.lower() and 'smoke' in advertiser_name.lower():
                                self.famous_advertiser_id = advertiser_id
                                print(f"SUCCESS: Found Famous Smoke Shop! Advertiser ID: {advertiser_id}")
                                return advertiser_id
                    
                    print(f"Found {len(found_advertisers)} advertisers total:")
                    for adv in found_advertisers[:10]:  # Show first 10
                        print(f"  - {adv}")
                    
                    if not self.famous_advertiser_id:
                        print("\nFamous Smoke Shop not found with 'famous smoke' keywords.")
                        print("Let's try a broader search...")
                        return self.search_all_advertisers()
                                
                except ET.ParseError as e:
                    print(f"XML parsing error: {e}")
                    print(f"Raw response: {content}")
                    
            elif response.status_code == 401:
                print("ERROR: Unauthorized - check your Personal Access Token")
            elif response.status_code == 403:
                print("ERROR: Forbidden - check your API permissions")
            else:
                print(f"API Error: {response.status_code}")
                print(f"Response: {response.text}")
                
        except requests.RequestException as e:
            print(f"Request error: {e}")
            
        return None
    
    def search_all_advertisers(self) -> Optional[str]:
        """
        Search through all available advertisers to find Famous Smoke Shop
        """
        print("Searching all advertisers for Famous Smoke Shop...")
        
        # Try different keyword combinations
        keywords_to_try = ['cigars', 'smoke', 'tobacco', 'famous']
        
        for keyword in keywords_to_try:
            print(f"Trying keyword: '{keyword}'")
            
            params = {
                'website-id': self.website_id,
                'keywords': keyword,
                'records-per-page': 100
            }
            
            try:
                response = requests.get(
                    self.link_search_url,
                    params=params,
                    headers=self.get_headers(),
                    timeout=30
                )
                
                if response.status_code == 200:
                    root = ET.fromstring(response.text)
                    
                    for link in root.findall('.//link'):
                        advertiser_name_elem = link.find('advertiser-name')
                        advertiser_id_elem = link.find('advertiser-id')
                        
                        if advertiser_name_elem is not None and advertiser_id_elem is not None:
                            advertiser_name = advertiser_name_elem.text
                            advertiser_id = advertiser_id_elem.text
                            
                            # Check for Famous Smoke Shop variations
                            name_lower = advertiser_name.lower()
                            if any(term in name_lower for term in ['famous', 'smoke']):
                                print(f"POSSIBLE MATCH: {advertiser_name} (ID: {advertiser_id})")
                                
                                if 'famous' in name_lower and 'smoke' in name_lower:
                                    self.famous_advertiser_id = advertiser_id
                                    print(f"SUCCESS: Found Famous Smoke Shop! Advertiser ID: {advertiser_id}")
                                    return advertiser_id
                
            except Exception as e:
                print(f"Error searching with keyword '{keyword}': {e}")
                continue
        
        return None
    
    def test_connection(self) -> bool:
        """
        Test API connection and search for Famous Smoke Shop
        """
        print("Testing CJ API connection...")
        result = self.discover_famous_advertiser_id()
        
        if result:
            print("SUCCESS: Connected to CJ API and found Famous Smoke Shop!")
            print(f"Advertiser ID: {result}")
            self.check_for_product_data()
            return True
        else:
            print("Could not find Famous Smoke Shop.")
            print("\nThis could mean:")
            print("1. You're not yet approved for Famous Smoke Shop's program")
            print("2. Famous Smoke Shop doesn't have active links in CJ right now") 
            print("3. They might be listed under a different name")
            print("4. You might need to apply to their program first")
            return False
     
    def check_for_product_data(self):
        """Check if Famous Smoke Shop has detailed product data available"""
        # Try GraphQL Product Search API
        graphql_url = "https://commissions.api.cj.com/query"
        
        query = {
        "query": """
        {
        productFeed(advertiserId: "6240744") {
            products {
            name
            url
            price
            currency
            imageUrl
            inStock
            }
        }
        }
        """
    }
        
        headers = self.get_headers()
        headers['Content-Type'] = 'application/json'
        
        response = requests.post(graphql_url, json=query, headers=headers)
        print(f"GraphQL Response: {response.status_code}")
        print(response.text[:500])
    
    def get_famous_products(self, advertiser_id: str = None, search_keywords: List[str] = None, max_results: int = 1000) -> List[Dict]:
        """
        Fetch products from Famous Smoke Shop using CJ Product Catalog API
        Returns list of product dictionaries with affiliate links
        """
        if not advertiser_id:
            advertiser_id = self.famous_advertiser_id or '6240744'
        
        print(f"Attempting to fetch product catalog for advertiser {advertiser_id}")
        
        # Try REST API Product Catalog endpoint
        product_url = f"https://product-search.api.cj.com/v2/product-search"
        
        params = {
            'website-id': self.website_id,
            'advertiser-ids': advertiser_id,
            'keywords': 'cigar cigars',
            'records-per-page': min(max_results, 1000)
        }
        
        try:
            response = requests.get(
                product_url,
                params=params,
                headers=self.get_headers(),
                timeout=30
            )
            
            print(f"Product API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                # Parse XML response
                root = ET.fromstring(response.text)
                products_elem = root.findall('.//product')
                
                print(f"Found {len(products_elem)} products in catalog")
                
                if len(products_elem) == 0:
                    print("No products in catalog - Famous Smoke may not provide product feed")
                    print("Response sample:", response.text[:500])
                    return []
                
                products = []
                for product_elem in products_elem:
                    # Extract product data
                    name = self._get_xml_text(product_elem, 'name')
                    price = self._get_xml_text(product_elem, 'price')
                    buy_url = self._get_xml_text(product_elem, 'buy-url')
                    in_stock = self._get_xml_text(product_elem, 'in-stock', 'true')
                    
                    if name and buy_url:
                        product = {
                            'name': name,
                            'link': buy_url,  # Already an affiliate link!
                            'brand': self._extract_brand(name),
                            'line': self._extract_line(name),
                            'price': float(price) if price else 0.0,
                            'in_stock': in_stock.lower() == 'true',
                            'retailer': 'famous',
                            'source': 'cj_product_catalog'
                        }
                        products.append(product)
                
                print(f"Extracted {len(products)} valid products")
                return products[:max_results]
                
            elif response.status_code == 404:
                print("Product Catalog API not available for this advertiser")
                print("Famous Smoke may not provide a product feed through CJ")
                return []
            else:
                print(f"API Error: {response.status_code}")
                print(f"Response: {response.text[:500]}")
                return []
                
        except Exception as e:
            print(f"Error fetching product catalog: {e}")
            return []
    
    def _get_xml_text(self, element, tag: str, default: str = '') -> str:
        """Safely extract text from XML element"""
        child = element.find(tag)
        return child.text if child is not None and child.text else default
    
    def _extract_url_from_html(self, html_code: str) -> str:
        """Extract URL from HTML anchor tag"""
        if not html_code:
            return ''
        
        # Look for href in the HTML
        import re
        match = re.search(r'href=["\']([^"\']+)["\']', html_code)
        if match:
            return match.group(1)
        return ''
    
    def _extract_brand(self, product_name: str) -> str:
        """Extract brand from product name"""
        # Common cigar brands
        brands = ['Arturo Fuente', 'Padron', 'Oliva', 'Cohiba', 'Romeo y Julieta', 
                  'Montecristo', 'Ashton', 'Drew Estate', 'Liga Privada', 'Acid']
        
        name_lower = product_name.lower()
        for brand in brands:
            if brand.lower() in name_lower:
                return brand
        
        # Default: first word is brand
        return product_name.split()[0] if product_name else ''
    
    def _extract_line(self, product_name: str) -> str:
        """Extract line from product name"""
        # Skip common words
        skip_words = ['cigars', 'cigar', 'box', 'pack', 'single']
        
        words = product_name.split()
        if len(words) > 1:
            # Return second word if first is brand
            return ' '.join([w for w in words[1:3] if w.lower() not in skip_words])
        
        return product_name

def main():
    """
    Test the integration
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    personal_access_token = os.getenv('CJ_PERSONAL_ACCESS_TOKEN')
    
    if not personal_access_token:
        print("ERROR: CJ_PERSONAL_ACCESS_TOKEN not found in environment")
        return
    
    # Create integrator and test
    integrator = CJFamousSmokeIntegrator(personal_access_token)
    integrator.test_connection()

if __name__ == "__main__":
    main()