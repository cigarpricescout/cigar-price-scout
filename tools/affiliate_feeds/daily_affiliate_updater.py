#!/usr/bin/env python3
"""
Daily Affiliate Feed Updater
Fetches product data from affiliate networks and updates pricing CSV files

Run this alongside your existing scrapers for complete coverage:
- CJ Affiliate: Famous Smoke, Gotham, etc.
- Sovrn Commerce: Various retailers
- AWIN: (future)

Usage:
    python daily_affiliate_updater.py --retailers all
    python daily_affiliate_updater.py --retailers famous,gotham
"""

import os
import sys
import csv
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Add parent directories to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'tools' / 'affiliate'))

class AffiliateDataMerger:
    """Merge affiliate feed data with existing scraped data"""
    
    def __init__(self):
        self.project_root = project_root
        self.static_data = self.project_root / 'static' / 'data'
        self.data_dir = self.project_root / 'data'
        
        # Load environment variables
        load_dotenv(self.project_root / '.env')
        
        self.cj_token = os.getenv('CJ_PERSONAL_ACCESS_TOKEN')
        self.cj_website_id = os.getenv('CJ_WEBSITE_ID', '101532120')
        self.cj_company_id = os.getenv('CJ_COMPANY_ID', '7711335')
        
    def update_famous_smoke(self) -> Dict:
        """Update Famous Smoke prices from CJ Affiliate feed"""
        print("=" * 60)
        print("Updating Famous Smoke from CJ Affiliate...")
        print("=" * 60)
        
        if not self.cj_token or self.cj_token == 'your_token_here':
            return {
                'success': False,
                'error': 'CJ_PERSONAL_ACCESS_TOKEN not configured',
                'message': 'Add your CJ token to .env file'
            }
        
        try:
            # Import CJ integration
            from cj_famous_integration import CJFamousSmokeIntegrator
            
            integrator = CJFamousSmokeIntegrator(
                personal_access_token=self.cj_token,
                website_id=self.cj_website_id,
                cid=self.cj_company_id
            )
            
            # Discover advertiser ID
            print("Finding Famous Smoke advertiser...")
            advertiser_id = integrator.discover_famous_advertiser_id()
            
            if not advertiser_id:
                return {
                    'success': False,
                    'error': 'Could not find Famous Smoke in CJ network',
                    'message': 'Verify you are approved for Famous Smoke affiliate program'
                }
            
            print(f"Found advertiser ID: {advertiser_id}")
            
            # Get products (limit to cigars)
            print("Fetching cigar products...")
            products = integrator.get_famous_products(
                advertiser_id=advertiser_id,
                search_keywords=['cigar'],
                max_results=1000
            )
            
            if not products:
                return {
                    'success': False,
                    'error': 'No products returned from CJ feed',
                    'products_found': 0
                }
            
            print(f"Retrieved {len(products)} products from CJ feed")
            
            # Check if we have existing Famous data to merge with
            famous_csv = self.static_data / 'famous.csv'
            existing_data = []
            
            if famous_csv.exists():
                with open(famous_csv, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    existing_data = list(reader)
                print(f"Found {len(existing_data)} existing Famous Smoke entries")
            
            # Merge: Use CJ data for prices, keep existing metadata
            merged_data = self._merge_famous_data(products, existing_data)
            
            # Write updated CSV
            self._write_csv(famous_csv, merged_data)
            
            return {
                'success': True,
                'retailer': 'famous',
                'products_updated': len(merged_data),
                'source': 'cj_affiliate',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'retailer': 'famous'
            }
    
    def _merge_famous_data(self, cj_products: List[Dict], existing_data: List[Dict]) -> List[Dict]:
        """Merge CJ affiliate data with existing scraped data"""
        
        # Create lookup by product name
        existing_map = {row.get('name', '').lower(): row for row in existing_data}
        merged = []
        
        for product in cj_products:
            name = product.get('name', '').lower()
            
            # If we have existing data, merge
            if name in existing_map:
                existing = existing_map[name]
                merged_row = {**existing}  # Start with existing
                
                # Update with fresh CJ data
                merged_row['price'] = product.get('price', existing.get('price'))
                merged_row['url'] = product.get('link', existing.get('url'))  # Use affiliate link!
                merged_row['oos'] = product.get('in_stock', 'true') == 'false'
                merged_row['source'] = 'cj_affiliate'
                merged_row['last_updated'] = datetime.now().strftime('%Y-%m-%d')
                
                merged.append(merged_row)
            else:
                # New product from CJ feed
                merged.append({
                    'brand': product.get('brand', ''),
                    'line': product.get('line', ''),
                    'name': product.get('name', ''),
                    'price': product.get('price', ''),
                    'url': product.get('link', ''),
                    'oos': product.get('in_stock', 'true') == 'false',
                    'source': 'cj_affiliate',
                    'last_updated': datetime.now().strftime('%Y-%m-%d')
                })
        
        return merged
    
    def _write_csv(self, filepath: Path, data: List[Dict]):
        """Write data to CSV file"""
        if not data:
            print(f"Warning: No data to write to {filepath}")
            return
        
        fieldnames = data[0].keys()
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        print(f"[OK] Wrote {len(data)} rows to {filepath}")
    
    def update_all_affiliates(self) -> Dict:
        """Update all affiliate retailers"""
        results = {
            'famous': self.update_famous_smoke(),
            # Add more retailers here as you integrate them:
            # 'gotham': self.update_gotham(),
            # 'ci': self.update_cigars_international(),
        }
        
        return results


def main():
    print("Starting Affiliate Feed Update")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    updater = AffiliateDataMerger()
    
    # Check credentials
    if not updater.cj_token or updater.cj_token == 'your_token_here':
        print("ERROR: CJ_PERSONAL_ACCESS_TOKEN not configured")
        print()
        print("Setup Instructions:")
        print("1. Go to: https://developers.cj.com/")
        print("2. Create a Personal Access Token")
        print("3. Add to .env file:")
        print("   CJ_PERSONAL_ACCESS_TOKEN=your_token_here")
        print()
        print("For now, create .env file from .env.example:")
        print("   cp .env.example .env")
        sys.exit(1)
    
    # Run updates
    results = updater.update_all_affiliates()
    
    # Summary
    print()
    print("=" * 60)
    print("AFFILIATE UPDATE SUMMARY")
    print("=" * 60)
    
    success_count = sum(1 for r in results.values() if r.get('success'))
    total_count = len(results)
    
    for retailer, result in results.items():
        status = "[OK]" if result.get('success') else "[FAIL]"
        products = result.get('products_updated', 0)
        error = result.get('error', '')
        
        print(f"{status} {retailer.upper()}: {products} products" + (f" - {error}" if error else ""))
    
    print()
    print(f"Success Rate: {success_count}/{total_count} retailers")
    print(f"Completed: {datetime.now().strftime('%H:%M:%S')}")
    
    return success_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
