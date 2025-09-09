import csv
import os
from pathlib import Path
from urllib.parse import urlparse

class CigarDataUpdater:
    def __init__(self, data_directory="../static/data"):
        self.data_directory = Path(data_directory)
        self.updates_log = []
        self.promotions_log = []
    
    def find_retailer_from_url(self, url):
        """Extract retailer key from URL"""
        domain = urlparse(url).netloc.lower()
        
        # Map domains to retailer keys
        domain_mapping = {
            'mikescigars.com': 'mikescigars',
            'atlanticcigar.com': 'atlantic',
            'bestcigarprices.com': 'bestcigar',
            'gothamcigars.com': 'gothamcigars',
            'famous-smoke.com': 'famous',
            'thompsoncigar.com': 'thompson',
            'cigarsinternational.com': 'ci',
            'jrcigars.com': 'jr',
            'cigar.com': 'cigar',
            'cigarsintl.com': 'ci',
            'nickscigarworld.com': 'nickscigarworld',
            'cigarplace.biz': 'cigarplace',
            'abcfws.com': 'abcfws',
            'cccrafter.com': 'cccrafter',
            'cigarcountry.com': 'cigarcountry',
            'cuencacigars.com': 'cuencacigars',
            'cigarhustler.com': 'cigarhustler',
            'oldhavanacigarco.com': 'oldhavana',
            'momscigars.com': 'momscigars',
            'watchcitycigar.com': 'watchcity'
        }
        
        for domain_key, retailer_key in domain_mapping.items():
            if domain_key in domain:
                return retailer_key
        
        return None
    
    def update_product(self, url, **updates):
        """
        Update a product based on its URL
        
        Args:
            url: Product URL to identify the item
            **updates: Dictionary of fields to update (price, in_stock, etc.)
        """
        retailer_key = self.find_retailer_from_url(url)
        if not retailer_key:
            print(f"Could not identify retailer from URL: {url}")
            return False
        
        csv_file = self.data_directory / f"{retailer_key}.csv"
        if not csv_file.exists():
            print(f"CSV file not found: {csv_file}")
            return False
        
        # Read current data
        rows = []
        found = False
        
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            for row in reader:
                if row['url'] == url:
                    # Update specified fields
                    for field, value in updates.items():
                        if field in row:
                            old_value = row[field]
                            # Convert boolean values for in_stock field
                            if field == 'in_stock':
                                row[field] = 'true' if value else 'false'
                            else:
                                row[field] = str(value)
                            print(f"Updated {retailer_key}: {field} {old_value} -> {row[field]}")
                            self.updates_log.append({
                                'retailer': retailer_key,
                                'url': url,
                                'field': field,
                                'old_value': old_value,
                                'new_value': row[field]
                            })
                        else:
                            print(f"Warning: Field '{field}' not found in CSV")
                    found = True
                rows.append(row)
        
        if not found:
            print(f"Product not found with URL: {url}")
            return False
        
        # Write updated data back
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        return True
    
    def batch_update(self, updates_list):
        """
        Process multiple updates at once
        
        Args:
            updates_list: List of dictionaries with 'url' and update fields
        """
        for update in updates_list:
            url = update.pop('url')  # Remove URL from updates dict
            self.update_product(url, **update)
    
    def show_update_log(self):
        """Display all updates made"""
        print("\n=== Update Log ===")
        for update in self.updates_log:
            print(f"{update['retailer']}: {update['field']} changed from {update['old_value']} to {update['new_value']}")

# Run all the batch updates
if __name__ == "__main__":
    # Initialize the updater
    updater = CigarDataUpdater()
    
    # All your updates in batch
    updates = [
        {'url': 'https://mikescigars.com/excalibur-epicures-exep', 'price': 152.50},
        {'url': 'https://www.famous-smoke.com/excalibur-epicure-cigars-natural', 'price': 152.99},
        {'url': 'https://www.cigarsinternational.com/p/excalibur-cigars/1411249/', 'price': 156.99},
        {'url': 'https://cigarcountry.com/product/arturo-fuente-hemingway-natural-classic/', 'price': 273.94, 'in_stock': False},
        {'url': 'https://www.cuencacigars.com/arturo-fuente-hemingway-v-classic-cigars-box-of-25/', 'in_stock': False},
        {'url': 'https://www.bestcigarprices.com/cigar-directory/arturo-fuente-hemingway-cigars/arturo-fuente-hemingway-classic-13923/', 'in_stock': False},
        {'url': 'https://cigarhustler.com/arturo-fuente-hemingway-c-1_178/arturo-fuente-hemingway-classic-v-natural-cigar-box-p-4927.html', 'in_stock': False},
        {'url': 'https://www.cigarsinternational.com/p/arturo-fuente-hemingway-cigars/1410664/', 'price': 274.05},
        {'url': 'https://www.oldhavanacigarco.com/product/fuente-af-hemingway-natural-classic-box/1587', 'in_stock': False},
        {'url': 'https://www.momscigars.com/products/herrera-esteli-norteno', 'in_stock': False},
        {'url': 'https://www.cigar.com/p/drew-estate-herrera-esteli-norteno-ii-cigars/2013657/', 'in_stock': False},
        {'url': 'https://watchcitycigar.com/padron-1964-anniversary-series-diplomatico-maduro-50-x-7/', 'in_stock': False},
        {'url': 'https://cigarcountry.com/product/padron-1964-anniversary-series-diplomatico-maduro/', 'in_stock': False}
    ]
    
    print("Starting batch update process...")
    print(f"Processing {len(updates)} updates...")
    
    # Process all updates
    updater.batch_update(updates)
    
    # Show what was updated
    updater.show_update_log()
    print(f"\nBatch update complete! Processed {len(updater.updates_log)} changes.")