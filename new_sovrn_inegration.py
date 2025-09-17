import requests
import csv
from typing import List, Dict

class SovrnCommerceIntegrator:
    def __init__(self, site_api_key: str, secret_key: str):
        self.site_api_key = site_api_key
        self.secret_key = secret_key
        self.base_url = "https://comparisons.sovrn.com/api/affiliate/v3.5"
    
    def search_cigar(self, search_terms: str) -> List[Dict]:
        """Search for cigars across all merchants"""
        url = f"{self.base_url}/sites/{self.site_api_key}/compare/prices/usd_en/by/accuracy"
        
        headers = {
            "authorization": f"secret {self.secret_key}",
            "accept": "application/json"
        }
        
        params = {
            "search-keywords": search_terms,
            "limit": 50
        }
        
        response = requests.get(url, headers=headers, params=params)

        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return []

def main():
    # Your Sovrn credentials
    SITE_API_KEY = "6ccb4c241e1761e7b22c9a71c341701b"
    SECRET_KEY = "a8e2eb6acb128d673d1213efdb1a1c3c30c8a98c"  # You still need this from Sovrn dashboard
    
    integrator = SovrnCommerceIntegrator(SITE_API_KEY, SECRET_KEY)
    results = integrator.search_cigar("montecristo cigars")
    print(f"Found {len(results)} results")
    
    # Print first result for testing
    if results:
        print("Sample result:")
        print(results[0])

if __name__ == "__main__":
    main()