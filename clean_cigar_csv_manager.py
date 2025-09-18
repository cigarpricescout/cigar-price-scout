#!/usr/bin/env python3
"""
Cigar CSV Data Manager
Handles creation and updating of cigar price tracking CSV files for cigarpricescout.com
"""

import csv
import os
from pathlib import Path
from typing import Dict, List, Optional

class CigarCSVManager:
    def __init__(self, data_directory: str = "static/data"):
        self.data_directory = Path(data_directory)
        self.data_directory.mkdir(parents=True, exist_ok=True)
        
        # Required CSV headers matching your system
        self.headers = [
            'title', 'url', 'brand', 'line', 'wrapper', 
            'vitola', 'size', 'box_qty', 'price', 'in_stock'
        ]
        
        # Retailer keys from your main.py RETAILERS list
        self.retailer_keys = [
            'abcfws', 'absolutecigars', 'atlantic', 'bestcigar', 'bighumidor',
            'bonitasmokeshop', 'buitragocigars', 'casademontecristo', 'cccrafter',
            'cdmcigars', 'cheaplittlecigars', 'ci', 'cigar', 'cigarboxpa',
            'cigarcellarofmiami', 'cigarcountry', 'cigarhustler', 'cigarking',
            'cigaroasis', 'cigarpage', 'cigarpairingparlor', 'cigarplace',
            'cigarsdirect', 'corona', 'cubancrafters', 'cuencacigars',
            'escobarcigars', 'famous', 'gothamcigars', 'hilands', 'holts',
            'jr', 'lmcigars', 'mikescigars', 'momscigars', 'neptune',
            'niceashcigars', 'nickscigarworld', 'oldhavana', 'pipesandcigars',
            'planetcigars', 'santamonicacigars', 'secretocigarbar',
            'smallbatchcigar', 'smokeinn', 'tampasweethearts', 'thecigarshop',
            'thecigarstore', 'thompson', 'tobaccolocker', 'twoguys',
            'watchcity', 'windycitycigars'
        ]
    
    def get_csv_path(self, retailer_key: str) -> Path:
        """Get the full path to a retailer's CSV file"""
        return self.data_directory / f"{retailer_key}.csv"
    
    def csv_exists(self, retailer_key: str) -> bool:
        """Check if CSV file exists for a retailer"""
        return self.get_csv_path(retailer_key).exists()
    
    def create_csv(self, retailer_key: str) -> bool:
        """Create a new CSV file with proper headers"""
        csv_path = self.get_csv_path(retailer_key)
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)
            print(f"+ Created new CSV: {csv_path}")
            return True
        except Exception as e:
            print(f"X Error creating {csv_path}: {e}")
            return False
    
    def add_cigar_data(self, retailer_key: str, cigar_data: Dict) -> bool:
        """Add cigar data to retailer CSV, creating file if needed"""
        
        # Validate retailer key
        if retailer_key not in self.retailer_keys:
            print(f"X Unknown retailer key: {retailer_key}")
            print(f"Available keys: {', '.join(self.retailer_keys)}")
            return False
        
        # Create CSV if it doesn't exist
        if not self.csv_exists(retailer_key):
            if not self.create_csv(retailer_key):
                return False
        
        csv_path = self.get_csv_path(retailer_key)
        
        # Validate required fields
        required_fields = ['title', 'url', 'brand', 'line', 'size', 'box_qty', 'price']
        missing_fields = [field for field in required_fields if field not in cigar_data]
        if missing_fields:
            print(f"X Missing required fields: {missing_fields}")
            return False
        
        # Set defaults for optional fields
        cigar_data.setdefault('wrapper', '')
        cigar_data.setdefault('vitola', '')
        cigar_data.setdefault('in_stock', True)
        
        try:
            # Read existing data to check for duplicates
            existing_data = []
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                existing_data = list(reader)
            
            # Check for duplicate
            for row in existing_data:
                if (row['brand'] == cigar_data['brand'] and 
                    row['line'] == cigar_data['line'] and
                    row['vitola'] == cigar_data['vitola'] and
                    row['size'] == cigar_data['size']):
                    print(f"WARNING: Duplicate found for {cigar_data['brand']} {cigar_data['line']} - updating price")
                    row['price'] = str(cigar_data['price'])
                    row['in_stock'] = str(cigar_data['in_stock'])
                    row['url'] = cigar_data['url']
                    
                    # Write updated data back
                    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=self.headers)
                        writer.writeheader()
                        writer.writerows(existing_data)
                    print(f"+ Updated existing entry in {retailer_key}.csv")
                    return True
            
            # Add new entry
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writerow(cigar_data)
            
            print(f"+ Added {cigar_data['brand']} {cigar_data['line']} to {retailer_key}.csv")
            return True
            
        except Exception as e:
            print(f"X Error adding data to {csv_path}: {e}")
            return False
    
    def list_existing_csvs(self) -> List[str]:
        """List all existing CSV files"""
        existing = []
        for key in self.retailer_keys:
            if self.csv_exists(key):
                existing.append(key)
        return existing

    def process_romeo_julieta_data(self) -> bool:
        """Process the Romeo y Julieta 1875 Churchill data you provided"""
        
        # Your actual CSV data - ALL retailers
        romeo_data = [
            {"retailer": "Cigar Country", "title": "Romeo y Julieta 1875 Churchill", "url": "https://cigarcountry.com/product/romeo-y-julieta-1875-churchill/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 184.01, "in_stock": False},
            {"retailer": "Holt's", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.holts.com/cigars/all-cigar-brands/romeo-y-julieta-1875.html", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 201.0, "in_stock": True},
            {"retailer": "Nick's Cigar World", "title": "Romeo y Julieta 1875 Churchill", "url": "https://nickscigarworld.com/shop/premium-cigars/romeo-y-julieta-1875/romeo-y-julieta-1875-churchill/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 168.95, "in_stock": True},
            {"retailer": "Cigars International", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.cigarsinternational.com/p/romeo-y-julieta-1875-cigars/1411962/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 201.99, "in_stock": True},
            {"retailer": "JR Cigars", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.jrcigars.com/cigars/handmade-cigars/romeo-y-julieta-cigars/romeo-y-julieta-1875/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 219.99, "in_stock": True},
            {"retailer": "Neptune Cigar", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.neptunecigar.com/cigars/romeo-y-julieta-1875-churchill", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 183.95, "in_stock": True},
            {"retailer": "Cigar King", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.cigarking.com/copy-of-romeo-y-julieta-1875-churchill-7x50-box-25-free-shipping/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 144.27, "in_stock": False},
            {"retailer": "Absolute Cigars", "title": "Romeo y Julieta 1875 Churchill", "url": "https://absolutecigars.com/product/romeo-y-julieta-churchill/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 234.0, "in_stock": True},
            {"retailer": "Mike's Cigars", "title": "Romeo y Julieta 1875 Churchill", "url": "https://mikescigars.com/romeo-y-julieta-1875-churchill", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 200.95, "in_stock": True},
            {"retailer": "Cigar.com", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.cigar.com/p/romeo-y-julieta-1875-cigars/1411962/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 201.99, "in_stock": True},
            {"retailer": "Atlantic Cigar Company", "title": "Romeo y Julieta 1875 Churchill", "url": "https://atlanticcigar.com/romeo-y-julieta-1875-churchill/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 240.98, "in_stock": True},
            {"retailer": "LM Cigars", "title": "Romeo y Julieta 1875 Churchill", "url": "https://lmcigars.com/product/romeo-y-julieta-1875-churchill/?srsltid=AfmBOoowNeLgRPOvAfmUEA3r32eZcaSeKPpYJxsu6kEcvYp4F9dqAWth", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 201.0, "in_stock": True},
            {"retailer": "Hiland's Cigars", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.hilandscigars.com/shop/cigars/romeo-y-julieta/romeo-y-julieta-1875/romeo-y-julieta-1875-churchill/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 201.0, "in_stock": True},
            {"retailer": "Gotham Cigars", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.gothamcigars.com/romeo-y-julieta-1875-churchill/", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 184.99, "in_stock": True},
            {"retailer": "Famous Smoke", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.famous-smoke.com/brand/romeo-y-julieta-1875-cigars", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 200.99, "in_stock": True},
            {"retailer": "Best Cigar Prices", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.bestcigarprices.com/cigar-directory/romeo-y-julieta-1875-cigars/romeo-y-julieta-1875-churchill-251958/?srsltid=AfmBOoq0pFPiJCQ0PmokPMsnoejXGR3gvDaHgHUq2MKCRFNxt8-FaxW-", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 201.99, "in_stock": True},
            {"retailer": "Cigar Place", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.cigarplace.biz/romeo-y-julieta-1875-churchill.html?152=4517", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 176.95, "in_stock": True},
            {"retailer": "Nice Ash Cigars", "title": "Romeo y Julieta 1875 Churchill", "url": "https://www.niceashcigars.com/product-p/rj7050.htm", "brand": "Romeo y Julieta", "line": "1875", "wrapper": "Indonesian Shade Grown TBN", "vitola": "Churchill", "size": "7 x 50", "box_qty": 25, "price": 223.86, "in_stock": True}
        ]
        
        # Map retailer names to your system's retailer keys
        retailer_key_mapping = {
            'cigar country': 'cigarcountry',
            'holt\'s': 'holts',
            'nick\'s cigar world': 'nickscigarworld',
            'cigars international': 'ci',
            'jr cigars': 'jr',
            'neptune cigar': 'neptune',
            'cigar king': 'cigarking',
            'absolute cigars': 'absolutecigars',
            'mike\'s cigars': 'mikescigars',
            'cigar.com': 'cigar',
            'atlantic cigar company': 'atlantic',
            'lm cigars': 'lmcigars',
            'hiland\'s cigars': 'hilands',
            'gotham cigars': 'gothamcigars',
            'famous smoke': 'famous',
            'best cigar prices': 'bestcigar',
            'cigar place': 'cigarplace',
            'nice ash cigars': 'niceashcigars'
        }
        
        processed_count = 0
        skipped_count = 0
        
        print("Processing ALL Romeo y Julieta 1875 Churchill data...")
        
        for row in romeo_data:
            retailer_name = row['retailer'].lower().strip()
            retailer_key = retailer_key_mapping.get(retailer_name)
            
            if not retailer_key:
                print(f"WARNING: Unknown retailer: '{row['retailer']}' - skipping")
                skipped_count += 1
                continue
            
            # Prepare cigar data for your system format
            cigar_data = {
                'title': row['title'],
                'url': row['url'],
                'brand': row['brand'],
                'line': row['line'],
                'wrapper': row['wrapper'],
                'vitola': row['vitola'],
                'size': row['size'],
                'box_qty': row['box_qty'],
                'price': row['price'],
                'in_stock': row['in_stock']
            }
            
            if self.add_cigar_data(retailer_key, cigar_data):
                processed_count += 1
            else:
                skipped_count += 1
        
        print(f"SUCCESS: Successfully processed {processed_count} Romeo y Julieta entries")
        if skipped_count > 0:
            print(f"WARNING: Skipped {skipped_count} entries")
        
        return processed_count > 0


def main():
    """Process your actual Romeo y Julieta data only"""
    manager = CigarCSVManager()
    
    print(">> Cigar Price Scout CSV Data Processor")
    print("=" * 50)
    
    # Process your actual Romeo y Julieta 1875 Churchill data
    print("\nProcessing your Romeo y Julieta 1875 Churchill data...")
    manager.process_romeo_julieta_data()
    
    # Show summary
    existing = manager.list_existing_csvs()
    print(f"\nSummary:")
    print(f"Total CSV files created/updated: {len(existing)}")
    print(f"Retailers with data: {', '.join(existing)}")
    print("\nData processing complete!")
    print("\nYour Romeo y Julieta 1875 Churchill data has been distributed to the appropriate retailer CSV files.")


if __name__ == "__main__":
    main()
