"""
Two Guys Cigars Enhanced CSV Updater with Master-Driven Metadata Sync
ALWAYS syncs ALL metadata from master_cigars.db (master is authority source)
Enhanced version: metadata changes in master file auto-propagate to retailer CSV
Following the proven master-sync pattern for true data consistency
"""

import csv
import os
import sys
import shutil
import pandas as pd
import sqlite3
from datetime import datetime
from typing import List, Dict

# Add the retailers directory to path  
retailers_dir = os.path.join(os.path.dirname(__file__), '..', 'tools', 'price_monitoring', 'retailers')
sys.path.append(retailers_dir)

try:
    from two_guys_extractor import extract_two_guys_cigars_data
except ImportError as e:
    print(f"[ERROR] Could not import extract_two_guys_cigars_data. Make sure the extractor is in tools/price_monitoring/retailers/two_guys_extractor.py")
    print(f"[ERROR] Import error details: {e}")
    sys.exit(1)


class TwoGuysCSVUpdaterWithMaster:
    def __init__(self, csv_path: str = None, master_path: str = None, dry_run: bool = False):
        if csv_path is None:
            self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'twoguys.csv')
        else:
            self.csv_path = csv_path
            
        if master_path is None:
            self.master_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'master_cigars.db')  # CORRECT
        else:
            self.master_path = master_path
            
        self.backup_path = None
        self.master_df = None
        self.dry_run = dry_run
        
    def load_master_file(self) -> bool:
        """Load the master cigars file"""
        try:
            conn = sqlite3.connect(self.master_path)
            self.master_df = pd.read_sql_query("SELECT * FROM cigars", conn)
            conn.close()
            
            # Convert Box Quantity to numeric
            self.master_df['Box Quantity'] = pd.to_numeric(self.master_df['Box Quantity'], errors='coerce').fillna(0)
            
            # Filter to box quantities (10+)
            box_skus = self.master_df[self.master_df['Box Quantity'] >= 10]
            
            print(f"[INFO] Loaded master file with {len(self.master_df)} total cigars")
            print(f"[INFO] Found {len(box_skus)} box SKUs for retail comparison")
            return True
            
        except FileNotFoundError:
            print(f"[ERROR] Master file not found at: {self.master_path}")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to load master file: {e}")
            return False
    
    def get_cigar_metadata(self, cigar_id: str) -> Dict:
        """Get metadata for a cigar from the master file"""
        if self.master_df is None:
            return {}
        
        matching_rows = self.master_df[self.master_df['cigar_id'] == cigar_id]
        
        if len(matching_rows) == 0:
            print(f"[WARNING] No metadata found for cigar_id: {cigar_id}")
            return {}
        
        if len(matching_rows) > 1:
            print(f"[WARNING] Multiple matches found for cigar_id: {cigar_id}, using first match")
        
        row = matching_rows.iloc[0]
        
        # Build size string from Length x Ring Gauge
        size = ''
        if pd.notna(row.get('Length')) and pd.notna(row.get('Ring Gauge')):
            size = f"{row.get('Length')}x{row.get('Ring Gauge')}"
        
        # Get box quantity
        box_qty = 0
        if pd.notna(row.get('Box Quantity')):
            try:
                box_qty = int(row.get('Box Quantity', 0))
            except (ValueError, TypeError):
                pass
        
        return {
            'title': row.get('product_name', ''),
            'brand': row.get('Brand', ''), 
            'line': row.get('Line', ''),
            'wrapper': row.get('Wrapper', ''),
            'vitola': row.get('Vitola', ''),
            'size': size,
            'box_qty': box_qty
        }
    
    def auto_populate_metadata(self, row: Dict) -> Dict:
        """ALWAYS sync metadata from master file (master is authority source)"""
        cigar_id = row.get('cigar_id', '')
        if not cigar_id:
            return row
        
        metadata = self.get_cigar_metadata(cigar_id)
        
        # ALWAYS override with master data - master file is authority source
        metadata_changes = []
        for field in ['title', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty']:
            if field in metadata and metadata[field]:
                old_value = row.get(field, '')
                new_value = metadata[field]
                
                # Track changes for logging
                if old_value != new_value:
                    metadata_changes.append(f"{field}: '{old_value}' -> '{new_value}'")
                
                # Always update from master
                row[field] = new_value
        
        # Log metadata sync changes
        if metadata_changes:
            print(f"  [MASTER SYNC] Updated metadata: {', '.join(metadata_changes)}")
        
        return row
    
    def create_backup(self) -> bool:
        """Create a backup of the current CSV file"""
        try:
            if not os.path.exists(self.csv_path):
                print(f"[INFO] CSV file doesn't exist yet, will create new one: {self.csv_path}")
                return True
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_path = self.csv_path.replace('.csv', f'_backup_{timestamp}.csv')
            shutil.copy2(self.csv_path, self.backup_path)
            print(f"[INFO] Backup created: {self.backup_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create backup: {e}")
            return False
    
    def load_csv(self) -> List[Dict]:
        """Load the CSV file or return empty list if doesn't exist"""
        try:
            if not os.path.exists(self.csv_path):
                print(f"[INFO] Two Guys CSV not found, will create new one: {self.csv_path}")
                return []
            
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                data = list(reader)
            
            print(f"[INFO] Loaded {len(data)} products from Two Guys CSV")
            return data
        except Exception as e:
            print(f"[ERROR] Failed to load CSV: {e}")
            return []
    
    def save_csv(self, data: List[Dict]) -> bool:
        """Save the updated data back to CSV (respects dry_run mode)"""
        if not data:
            print("[ERROR] No data to save")
            return False
        
        if self.dry_run:
            print(f"[DRY RUN] Would save {len(data)} updated products to {self.csv_path}")
            return True
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            
            fieldnames = list(data[0].keys()) if data else ['cigar_id', 'title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
            
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            
            print(f"[INFO] Updated data saved to {self.csv_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save CSV: {e}")
            return False
    
    def update_pricing_data(self, url: str) -> Dict:
        """Extract live pricing data from Two Guys Cigars"""
        try:
            result = extract_two_guys_cigars_data(url)
            
            if result.get('error'):
                print(f"[WARNING] Extraction error: {result.get('error')}")
                return {'error': result.get('error')}
            
            return {
                'price': result.get('box_price'),
                'in_stock': result.get('in_stock', False),
                'box_quantity': result.get('box_qty'),
                'discount_percent': result.get('discount_percent')
            }
                
        except Exception as e:
            print(f"[ERROR] Price extraction failed: {e}")
            return {'error': str(e)}
    
    def add_new_product(self, cigar_id: str, url: str) -> Dict:
        """Add a new product to track"""
        print(f"[NEW] Adding new product: {cigar_id}")
        
        # Get metadata from master file
        metadata = self.get_cigar_metadata(cigar_id)
        
        if not metadata.get('title'):
            print(f"[WARNING] No metadata found in master file for: {cigar_id}")
        
        # Create base product entry
        new_product = {
            'cigar_id': cigar_id,
            'url': url,
            'price': None,
            'in_stock': False,
            # Metadata from master file
            'title': metadata.get('title', ''),
            'brand': metadata.get('brand', ''),
            'line': metadata.get('line', ''),
            'wrapper': metadata.get('wrapper', ''),
            'vitola': metadata.get('vitola', ''),
            'size': metadata.get('size', ''),
            'box_qty': metadata.get('box_qty', 0)
        }
        
        return new_product
    
    def run_update(self, new_products: List[Dict] = None) -> bool:
        """Run the complete update process"""
        mode_str = "[DRY RUN] " if self.dry_run else ""
        print("=" * 70)
        print(f"{mode_str}TWO GUYS CIGARS ENHANCED PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("MASTER-DRIVEN METADATA SYNC: All metadata always synced from master file")
        print("=" * 70)
        
        # Load master file
        if not self.load_master_file():
            return False
        
        # Load existing CSV data
        data = self.load_csv()
        
        # Add new products if provided
        if new_products:
            print(f"[INFO] Adding {len(new_products)} new products")
            for new_product in new_products:
                cigar_id = new_product.get('cigar_id')
                url = new_product.get('url')
                
                if not cigar_id or not url:
                    print(f"[ERROR] Invalid new product data: {new_product}")
                    continue
                
                # Check if already exists
                if any(row.get('cigar_id') == cigar_id for row in data):
                    print(f"[SKIP] Product already exists: {cigar_id}")
                    continue
                
                new_entry = self.add_new_product(cigar_id, url)
                data.append(new_entry)
        
        if not data:
            print("[WARNING] No products to update")
            return True
        
        # Backup disabled - historical prices tracked in historical_prices.db
        
        # Update each product
        successful_updates = 0
        failed_updates = 0
        metadata_sync_count = 0
        
        for i, row in enumerate(data):
            cigar_id = row.get('cigar_id', 'Unknown')
            url = row.get('url', '')
            
            print(f"\n[{i+1}/{len(data)}] Processing: {cigar_id}")
            
            # ALWAYS sync metadata from master file
            original_row = row.copy()
            row = self.auto_populate_metadata(row)
            
            # Check if metadata was updated
            metadata_updated = any(original_row.get(field) != row.get(field) 
                                 for field in ['title', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty'])
            if metadata_updated:
                metadata_sync_count += 1
            
            # Skip pricing extraction in dry run mode
            if self.dry_run:
                print("  [DRY RUN] Skipping price extraction")
                successful_updates += 1
                data[i] = row  # Update the data with metadata changes
                continue
            
            # Skip if no URL
            if not url:
                print("  [SKIP] No URL provided")
                failed_updates += 1
                data[i] = row  # Update the data with metadata changes
                continue
            
            # Extract live pricing
            pricing_data = self.update_pricing_data(url)
            
            if 'error' in pricing_data:
                print(f"  [FAIL] {pricing_data['error']}")
                failed_updates += 1
                data[i] = row  # Update the data with metadata changes
                continue
            
            # Update the row with new pricing data
            if pricing_data.get('price') is not None:
                row['price'] = pricing_data['price']
            if pricing_data.get('in_stock') is not None:
                row['in_stock'] = pricing_data['in_stock']
            
            # Show results
            price_str = f"${pricing_data.get('price', 'N/A')}"
            stock_str = "In Stock" if pricing_data.get('in_stock') else "Out of Stock"
            discount_str = f" ({pricing_data['discount_percent']:.1f}% off)" if pricing_data.get('discount_percent') else ""
            
            print(f"  [OK] {price_str} | {stock_str}{discount_str}")
            successful_updates += 1
            data[i] = row  # Update the data with all changes
        
        # Save updated data
        if self.save_csv(data):
            print("\n" + "=" * 70)
            print(f"{mode_str}UPDATE COMPLETE")
            print(f"Successful updates: {successful_updates}")
            print(f"Failed updates: {failed_updates}")
            print(f"Metadata synced: {metadata_sync_count} products")
            print(f"Total processed: {len(data)}")
            print(f"Updated file: {self.csv_path}")
            if self.backup_path:
                print(f"Backup file: {self.backup_path}")
            print("=" * 70)
            return True
        else:
            return False


def main():
    """Main function for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Two Guys Cigars price updater with master-driven metadata sync')
    parser.add_argument('--csv', help='Path to Two Guys CSV file')
    parser.add_argument('--master', help='Path to master cigars CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Show what metadata would be updated without making changes')
    parser.add_argument('--test', action='store_true', help='Deprecated: Use --dry-run instead')
    parser.add_argument('--add-product', nargs=2, metavar=('CIGAR_ID', 'URL'), 
                        help='Add a new product to track (format: CIGAR_ID URL)')
    
    args = parser.parse_args()
    
    # Handle deprecated --test flag
    dry_run = args.dry_run or args.test
    
    # Handle new product addition
    new_products = None
    if args.add_product:
        new_products = [{
            'cigar_id': args.add_product[0],
            'url': args.add_product[1]
        }]
    
    # Create updater instance
    updater = TwoGuysCSVUpdaterWithMaster(csv_path=args.csv, master_path=args.master, dry_run=dry_run)
    
    if dry_run:
        print("[DRY RUN MODE] Showing metadata changes without updating files")
    
    # Run the update
    success = updater.run_update(new_products=new_products)
    
    if success:
        print("\n[SUCCESS] Two Guys Cigars enhanced update completed successfully")
    else:
        print("\n[FAILED] Two Guys Cigars enhanced update failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
