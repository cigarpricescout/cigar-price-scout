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
     
    def check_for_product_data(self):  # <-- ADD THIS NEW METHOD HERE
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