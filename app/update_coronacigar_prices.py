"""
Corona Cigar Co. Enhanced CSV Updater with Master-Driven Metadata Sync
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

# Add the tools directory to path for importing the extractor
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
tools_path = os.path.join(project_root, 'tools', 'price_monitoring')
sys.path.append(tools_path)

# Import the Corona Cigar extractor
try:
    from retailers.coronacigar_extractor import extract_coronacigar_data
except ImportError:
    print("[ERROR] Could not import extract_coronacigar_data. Make sure coronacigar_extractor.py is in tools/price_monitoring/retailers/")
    sys.exit(1)


class CoronaCigarCSVUpdater:
    def __init__(self, csv_path: str = None, master_path: str = None, dry_run: bool = False):
        if csv_path is None:
            self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'coronacigar.csv')
        else:
            self.csv_path = csv_path
            
        if master_path is None:
            self.master_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'master_cigars.db')
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
    
    def create_backup(self) -> bool:
        """Create a backup of the CSV file"""
        if self.dry_run:
            print("[DRY RUN] Would create backup")
            return True
            
        if not os.path.exists(self.csv_path):
            print(f"[WARNING] CSV file does not exist yet: {self.csv_path}")
            return True
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"coronacigar_backup_{timestamp}.csv"
        self.backup_path = os.path.join(os.path.dirname(self.csv_path), backup_name)
        
        try:
            shutil.copy2(self.csv_path, self.backup_path)
            print(f"[INFO] Backup created: {self.backup_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create backup: {e}")
            return False
    
    def load_products(self) -> List[Dict]:
        """Load existing products from CSV"""
        if not os.path.exists(self.csv_path):
            print(f"[INFO] No existing CSV file found at: {self.csv_path}")
            return []
        
        products = []
        try:
            with open(self.csv_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    products.append(row)
            print(f"[INFO] Loaded {len(products)} products from Corona Cigar CSV")
            return products
        except Exception as e:
            print(f"[ERROR] Failed to load CSV: {e}")
            return []
    
    def update_product(self, product: Dict) -> Dict:
        """Update a single product with live data from extractor"""
        cigar_id = product.get('cigar_id', '')
        url = product.get('url', '')
        
        if not cigar_id or not url:
            return {**product, 'error': 'Missing cigar_id or url'}
        
        print(f"\n[{product.get('cigar_id', 'UNKNOWN')}] Processing: {cigar_id}")
        
        # Get metadata from master file
        master_metadata = self.get_cigar_metadata(cigar_id)
        
        # Track metadata changes
        metadata_changes = []
        for field in ['title', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty']:
            old_value = product.get(field, 'None')
            new_value = master_metadata.get(field, 'None')
            
            # Convert to strings for comparison
            old_str = str(old_value) if old_value is not None else 'None'
            new_str = str(new_value) if new_value is not None else 'None'
            
            if old_str != new_str:
                metadata_changes.append(f"{field}: '{old_str}' -> '{new_str}'")
                product[field] = new_value
        
        if metadata_changes:
            print(f"  [MASTER SYNC] Updated metadata: {', '.join(metadata_changes)}")
        
        # Extract live pricing data
        try:
            result = extract_coronacigar_data(url)
            
            if result['success']:
                # Check for box quantity mismatch
                extracted_qty = result.get('box_quantity')
                master_qty = master_metadata.get('box_qty', 0)
                
                if extracted_qty and master_qty and extracted_qty != master_qty:
                    print(f"  [WARNING] Box quantity mismatch - CSV: {master_qty}, Extracted: {extracted_qty}")
                
                # Update price and stock data
                product['price'] = result.get('price')
                product['in_stock'] = result.get('in_stock', False)
                product['current_promotions_applied'] = ''
                
                # Display status
                discount_text = ""
                if result.get('discount_percent'):
                    discount_text = f" ({result['discount_percent']:.1f}% off)"
                
                stock_status = "In Stock" if result['in_stock'] else "Out of Stock"
                print(f"  [OK] ${product['price']}{discount_text} | {stock_status}")
                
            else:
                print(f"  [ERROR] {result.get('error', 'Unknown error')}")
                product['error'] = result.get('error', 'Unknown error')
                
        except Exception as e:
            print(f"  [ERROR] Exception during extraction: {e}")
            product['error'] = str(e)
        
        return product
    
    def save_products(self, products: List[Dict]) -> bool:
        """Save updated products to CSV"""
        if self.dry_run:
            print("\n[DRY RUN] Would save updated data")
            return True
            
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            
            # Define field order
            fieldnames = [
                'cigar_id', 'title', 'url', 'brand', 'line', 'wrapper', 
                'vitola', 'size', 'box_qty', 'price', 'in_stock', 
                'current_promotions_applied'
            ]
            
            with open(self.csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for product in products:
                    # Only write the defined fields
                    row = {k: product.get(k, '') for k in fieldnames}
                    writer.writerow(row)
            
            print(f"[INFO] Updated data saved to {self.csv_path}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to save CSV: {e}")
            return False
    
    def run(self) -> bool:
        """Main update process"""
        print("=" * 70)
        print(f"CORONA CIGAR CO. ENHANCED PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("MASTER-DRIVEN METADATA SYNC: All metadata always synced from master file")
        print("=" * 70)
        
        # Load master file
        if not self.load_master_file():
            return False
        
        # Load products
        products = self.load_products()
        if not products:
            print("[WARNING] No products to update")
            return False
        
        # Backup disabled - historical prices tracked in historical_prices.db
        
        # Update each product
        updated_products = []
        success_count = 0
        fail_count = 0
        
        for product in products:
            updated = self.update_product(product)
            updated_products.append(updated)
            
            if 'error' not in updated or not updated['error']:
                success_count += 1
            else:
                fail_count += 1
        
        # Save results
        if not self.save_products(updated_products):
            return False
        
        # Print summary
        print("\n" + "=" * 70)
        print("UPDATE COMPLETE")
        print(f"Successful updates: {success_count}")
        print(f"Failed updates: {fail_count}")
        print(f"Metadata synced: {len(products)} products")
        print(f"Total processed: {len(products)}")
        print(f"Updated file: {self.csv_path}")
        if self.backup_path:
            print(f"Backup file: {self.backup_path}")
        print("=" * 70)
        
        return True


def main():
    """Main entry point"""
    updater = CoronaCigarCSVUpdater()
    
    try:
        success = updater.run()
        if success:
            print("\n[SUCCESS] Corona Cigar Co. enhanced update completed successfully")
            sys.exit(0)
        else:
            print("\n[FAILED] Corona Cigar Co. update encountered errors")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n[CANCELLED] Update cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
