#!/usr/bin/env python3
"""
Enhanced batch updates script that integrates CJ API data with existing CSV management
"""

import os
import sys
from datetime import datetime
from cj_famous_integration import CJFamousSmokeIntegrator

# Add the app directory to the path so we can import from it
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

class EnhancedBatchUpdater:
    def __init__(self, cj_developer_key: str = None, website_id: str = None):
        """
        Initialize enhanced batch updater with optional CJ API integration
        """
        self.cj_integrator = None
        if cj_developer_key and website_id:
            self.cj_integrator = CJFamousSmokeIntegrator(cj_developer_key, website_id)
        
        # Your existing manual updates that need to be processed
        self.pending_manual_updates = [
            {
                'retailer': 'mikescigars',
                'identifier': 'excalibur-epicures-exep',
                'price': 152.50,
                'in_stock': True,
                'type': 'price_update'
            },
            {
                'retailer': 'famous',
                'identifier': 'excalibur-epicure-cigars-natural',
                'price': 152.99,
                'in_stock': True,
                'type': 'price_update'
            },
            {
                'retailer': 'ci',
                'identifier': 'excalibur-cigars/1411249',
                'price': 156.99,
                'in_stock': True,
                'type': 'price_update'
            },
            # Add more pending updates from your transition package
        ]
    
    def process_manual_updates(self):
        """
        Process the pending manual updates from your transition package
        """
        print("Processing pending manual updates...")
        
        for update in self.pending_manual_updates:
            try:
                self.apply_single_update(update)
                print(f"✓ Updated {update['retailer']}: {update['identifier']} - ${update['price']}")
            except Exception as e:
                print(f"✗ Failed to update {update['retailer']}: {update['identifier']} - {e}")
    
    def apply_single_update(self, update: dict):
        """
        Apply a single update to the appropriate CSV file
        """
        import csv
        
        retailer = update['retailer']
        csv_file = f"static/data/{retailer}.csv"
        
        if not os.path.exists(csv_file):
            print(f"Warning: CSV file {csv_file} does not exist")
            return
        
        # Read existing data
        rows = []
        updated = False
        
        with open(csv_file, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            
            for row in reader:
                # Check if this row matches our update criteria
                if self.row_matches_update(row, update):
                    # Apply updates
                    if 'price' in update:
                        row['price'] = str(update['price'])
                    if 'in_stock' in update:
                        row['in_stock'] = str(update['in_stock']).lower()
                    updated = True
                    print(f"  Found and updated: {row['title']}")
                
                rows.append(row)
        
        if updated:
            # Write back to file
            with open(csv_file, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        else:
            print(f"  No matching product found for {update['identifier']}")
    
    def row_matches_update(self, row: dict, update: dict) -> bool:
        """
        Check if a CSV row matches an update criteria
        """
        identifier = update['identifier']
        
        # Check if identifier appears in URL, title, or other identifying fields
        searchable_fields = [
            row.get('url', '').lower(),
            row.get('title', '').lower(),
            row.get('brand', '').lower(),
            row.get('line', '').lower()
        ]
        
        identifier_lower = identifier.lower()
        
        # Check for URL path matches
        if identifier_lower in ' '.join(searchable_fields):
            return True
        
        # Check for exact title matches (for more specific matching)
        if identifier_lower.replace('-', ' ') in row.get('title', '').lower():
            return True
        
        return False
    
    def update_famous_via_api(self):
        """
        Update Famous Smoke Shop data via CJ API
        """
        if not self.cj_integrator:
            print("CJ API integration not configured")
            return False
        
        print("Updating Famous Smoke Shop data via CJ API...")
        
        try:
            products = self.cj_integrator.update_famous_data()
            if products:
                print(f"✓ Successfully updated Famous Smoke data with {len(products)} products")
                return True
            else:
                print("✗ No products retrieved from CJ API")
                return False
        except Exception as e:
            print(f"✗ Error updating via CJ API: {e}")
            return False
    
    def backup_existing_data(self):
        """
        Create backups of existing CSV files before updates
        """
        import shutil
        
        backup_dir = f"backups/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(backup_dir, exist_ok=True)
        
        data_dir = "static/data"
        if os.path.exists(data_dir):
            for filename in os.listdir(data_dir):
                if filename.endswith('.csv'):
                    src = os.path.join(data_dir, filename)
                    dst = os.path.join(backup_dir, filename)
                    shutil.copy2(src, dst)
            
            print(f"✓ Backed up CSV files to {backup_dir}")
    
    def validate_csv_integrity(self, filename: str) -> bool:
        """
        Validate that a CSV file has the expected structure
        """
        expected_columns = ['title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
        
        try:
            import csv
            with open(filename, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                # Check if all expected columns are present
                missing_columns = set(expected_columns) - set(reader.fieldnames or [])
                if missing_columns:
                    print(f"✗ Missing columns in {filename}: {missing_columns}")
                    return False
                
                # Check if we can read at least one row
                try:
                    next(reader)
                    return True
                except StopIteration:
                    print(f"Warning: {filename} is empty")
                    return True
                    
        except Exception as e:
            print(f"✗ Error validating {filename}: {e}")
            return False
    
    def run_full_update(self):
        """
        Run the complete update process
        """
        print("=== Starting Enhanced Batch Update ===")
        print(f"Timestamp: {datetime.now()}")
        
        # Step 1: Backup existing data
        self.backup_existing_data()
        
        # Step 2: Process manual updates
        self.process_manual_updates()
        
        # Step 3: Update Famous Smoke via API (if configured)
        if self.cj_integrator:
            api_success = self.update_famous_via_api()
            if api_success:
                print("✓ CJ API update completed successfully")
            else:
                print("⚠ CJ API update failed, keeping existing data")
        
        # Step 4: Validate all CSV files
        print("\nValidating CSV files...")
        data_dir = "static/data"
        if os.path.exists(data_dir):
            for filename in os.listdir(data_dir):
                if filename.endswith('.csv'):
                    filepath = os.path.join(data_dir, filename)
                    if self.validate_csv_integrity(filepath):
                        print(f"✓ {filename} is valid")
                    else:
                        print(f"✗ {filename} has issues")
        
        print("\n=== Batch Update Complete ===")


def main():
    """
    Main execution function
    """
    # Configuration - Get Personal Access Token from environment variable
    PERSONAL_ACCESS_TOKEN = os.getenv('CJ_PERSONAL_ACCESS_TOKEN')
    WEBSITE_ID = "101532120"  # Your Publisher ID
    CID = "7711335"           # Your Company ID
    
    # Create updater
    updater = EnhancedBatchUpdater(PERSONAL_ACCESS_TOKEN, WEBSITE_ID, CID)
    
    # Run updates
    updater.run_full_update()


if __name__ == "__main__":
    main()