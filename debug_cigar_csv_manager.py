#!/usr/bin/env python3
"""
Debug version of Cigar CSV Data Manager
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
    
    def add_cigar_data(self, retailer_key: str, cigar_data: Dict) -> bool:
        """Add cigar data to retailer CSV, creating file if needed"""
        
        print(f"DEBUG: Processing retailer_key: '{retailer_key}'")
        print(f"DEBUG: Cigar data: {cigar_data}")
        
        # Validate retailer key
        if retailer_key not in self.retailer_keys:
            print(f"X Unknown retailer key: {retailer_key}")
            print(f"Available keys: {', '.join(self.retailer_keys)}")
            return False
        
        csv_path = self.get_csv_path(retailer_key)
        print(f"DEBUG: CSV path: {csv_path}")
        print(f"DEBUG: CSV exists: {csv_path.exists()}")
        
        # Set defaults for optional fields
        cigar_data.setdefault('wrapper', '')
        cigar_data.setdefault('vitola', '')
        cigar_data.setdefault('in_stock', True)
        
        try:
            # Read existing data to check for duplicates
            existing_data = []
            if csv_path.exists():
                with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    existing_data = list(reader)
                print(f"DEBUG: Found {len(existing_data)} existing entries")
            else:
                print("DEBUG: CSV file doesn't exist, will create it")
                # Create CSV with headers
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.headers)
                print(f"+ Created new CSV: {csv_path}")
            
            # Check for duplicate
            for i, row in enumerate(existing_data):
                print(f"DEBUG: Checking row {i}: brand='{row.get('brand')}', line='{row.get('line')}', vitola='{row.get('vitola')}', size='{row.get('size')}'")
                if (row.get('brand') == cigar_data['brand'] and 
                    row.get('line') == cigar_data['line'] and
                    row.get('vitola') == cigar_data['vitola'] and
                    row.get('size') == cigar_data['size']):
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
            print(f"DEBUG: No duplicate found, adding new entry")
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.headers)
                writer.writerow(cigar_data)
            
            print(f"+ Added {cigar_data['brand']} {cigar_data['line']} to {retailer_key}.csv")
            return True
            
        except Exception as e:
            print(f"X Error adding data to {csv_path}: {e}")
            return False

    def process_romeo_julieta_data(self) -> bool:
        """Process just one Romeo y Julieta entry for debugging"""
        
        # Just process one entry for debugging
        test_entry = {
            "retailer": "Cigar Country", 
            "title": "Romeo y Julieta 1875 Churchill", 
            "url": "https://cigarcountry.com/product/romeo-y-julieta-1875-churchill/", 
            "brand": "Romeo y Julieta", 
            "line": "1875", 
            "wrapper": "Indonesian Shade Grown TBN", 
            "vitola": "Churchill", 
            "size": "7 x 50", 
            "box_qty": 25, 
            "price": 184.01, 
            "in_stock": False
        }
        
        retailer_key_mapping = {
            'cigar country': 'cigarcountry',
        }
        
        print("DEBUG: Processing single Romeo y Julieta entry...")
        
        retailer_name = test_entry['retailer'].lower().strip()
        print(f"DEBUG: Retailer name after lowercase/strip: '{retailer_name}'")
        
        retailer_key = retailer_key_mapping.get(retailer_name)
        print(f"DEBUG: Mapped retailer key: '{retailer_key}'")
        
        if not retailer_key:
            print(f"WARNING: Unknown retailer: '{test_entry['retailer']}' - skipping")
            return False
        
        # Prepare cigar data for your system format
        cigar_data = {
            'title': test_entry['title'],
            'url': test_entry['url'],
            'brand': test_entry['brand'],
            'line': test_entry['line'],
            'wrapper': test_entry['wrapper'],
            'vitola': test_entry['vitola'],
            'size': test_entry['size'],
            'box_qty': test_entry['box_qty'],
            'price': test_entry['price'],
            'in_stock': test_entry['in_stock']
        }
        
        return self.add_cigar_data(retailer_key, cigar_data)


def main():
    """Debug version - process just one entry"""
    manager = CigarCSVManager()
    
    print(">> DEBUG Cigar CSV Manager")
    print("=" * 50)
    
    print("\nProcessing single Romeo y Julieta entry for debugging...")
    success = manager.process_romeo_julieta_data()
    
    if success:
        print("\nDEBUG: Processing completed successfully")
    else:
        print("\nDEBUG: Processing failed")


if __name__ == "__main__":
    main()
