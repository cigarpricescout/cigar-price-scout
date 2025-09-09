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
            # Add more mappings as needed
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
                            row[field] = str(value)
                            print(f"Updated {retailer_key}: {field} {old_value} -> {value}")
                            self.updates_log.append({
                                'retailer': retailer_key,
                                'url': url,
                                'field': field,
                                'old_value': old_value,
                                'new_value': value
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
    
    def log_promotion(self, retailer, promotion_details):
        """Log promotion for future use"""
        self.promotions_log.append({
            'retailer': retailer,
            'details': promotion_details,
            'logged_at': str(Path.cwd())  # You could use datetime here
        })
        print(f"Logged promotion for {retailer}: {promotion_details}")
    
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
    
    def show_promotions_log(self):
        """Display all logged promotions"""
        print("\n=== Promotions Log ===")
        for promo in self.promotions_log:
            print(f"{promo['retailer']}: {promo['details']}")

# Usage examples
if __name__ == "__main__":
    updater = CigarDataUpdater()
    
    # Single update example
    updater.update_product(
        "https://mikescigars.com/excalibur-epicures-exep", 
        price=152.50
    )
    
    # Batch updates example
    updates = [
        {
            'url': 'https://mikescigars.com/excalibur-epicures-exep',
            'price': 152.50,
            'in_stock': True
        },
        # Add more updates here
    ]
    # updater.batch_update(updates)
    
    # Log a promotion
    updater.log_promotion("mikescigars", "Free shipping over $99")
    
    # Show logs
    updater.show_update_log()
    updater.show_promotions_log()
