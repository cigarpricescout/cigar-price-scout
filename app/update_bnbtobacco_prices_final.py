"""
BnB Tobacco Enhanced CSV Updater with Master-Driven Metadata Sync
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
tools_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tools', 'price_monitoring', 'retailers')
sys.path.insert(0, tools_path)

try:
    from bnb_tobacco_extractor import extract_bnb_tobacco_data
except ImportError:
    print("[ERROR] Could not import extract_bnb_tobacco_data. Make sure the extractor is in tools/price_monitoring/retailers/bnb_tobacco_extractor.py")
    sys.exit(1)


class BnBTobaccoCSVUpdaterWithMaster:
    def __init__(self, csv_path: str = None, master_path: str = None, dry_run: bool = False):
        if csv_path is None:
            self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'bnbtobacco.csv')
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
            self.master_df['box_quantity'] = pd.to_numeric(self.master_df['box_quantity'], errors='coerce').fillna(0)
            
            # Filter to box quantities (10+)
            box_skus = self.master_df[self.master_df['box_quantity'] >= 10]
            
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
        if pd.notna(row.get('length')) and pd.notna(row.get('ring_gauge')):
            size = f"{row.get('length')}x{row.get('ring_gauge')}"
        
        # Get box quantity
        box_qty = 0
        if pd.notna(row.get('box_quantity')):
            try:
                box_qty = int(row.get('box_quantity', 0))
            except (ValueError, TypeError):
                pass
        
        return {
            'title': row.get('product_name', ''),
            'brand': row.get('brand', ''), 
            'line': row.get('line', ''),
            'wrapper': row.get('wrapper', ''),
            'vitola': row.get('vitola', ''),
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
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_path = self.csv_path.replace('.csv', f'_backup_{timestamp}.csv')
            shutil.copy2(self.csv_path, self.backup_path)
            print(f"[INFO] Backup created: {self.backup_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create backup: {e}")
            return False
    
    def load_csv(self) -> List[Dict]:
        """Load the CSV file"""
        try:
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                data = list(reader)
            
            print(f"[INFO] Loaded {len(data)} products from BnB Tobacco CSV")
            return data
        except FileNotFoundError:
            print(f"[ERROR] BnB Tobacco CSV not found at: {self.csv_path}")
            return []
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
    
    def update_pricing_data(self, url: str, cigar_id: str) -> Dict:
        """Extract live pricing data from BnB Tobacco with variant targeting"""
        try:
            # Parse cigar_id to get target vitola and packaging
            targets = self.parse_cigar_id_for_targets(cigar_id)
            target_vitola = targets.get('target_vitola')
            target_packaging = targets.get('target_packaging', 'Box of 25')
            
            if not targets.get('parsed_successfully'):
                print(f"[WARNING] Could not parse targeting info from cigar_id: {cigar_id}")
                print(f"[WARNING] Using default targets: vitola=None, packaging={target_packaging}")
            
            # Call the extractor with specific targeting
            result = extract_bnb_tobacco_data(url, target_vitola, target_packaging)
            
            if result.get('success'):
                return {
                    'price': result.get('price'),
                    'in_stock': result.get('in_stock'),
                    'box_quantity': result.get('box_quantity'),
                    'discount_percent': result.get('discount_percent')
                }
            else:
                print(f"[WARNING] Extraction failed: {result.get('error', 'Unknown error')}")
                return {'error': result.get('error', 'Extraction failed')}
                
        except Exception as e:
            print(f"[ERROR] Price extraction failed: {e}")
            return {'error': str(e)}
    
    def parse_cigar_id_for_targets(self, cigar_id: str) -> Dict:
        """Parse cigar_id to extract target vitola and packaging for BnB extraction"""
        try:
            parts = cigar_id.split('|')
            if len(parts) >= 8:
                vitola = parts[3]
                packaging = parts[7]
                
                target_vitola = vitola.title()
                target_packaging = "Box of 25"
                if packaging.startswith('BOX'):
                    import re
                    qty_match = re.search(r'(\d+)', packaging)
                    if qty_match:
                        qty = qty_match.group(1)
                        target_packaging = f"Box of {qty}"
                
                return {
                    'target_vitola': target_vitola,
                    'target_packaging': target_packaging,
                    'parsed_successfully': True
                }
            else:
                return {
                    'target_vitola': None,
                    'target_packaging': "Box of 25",
                    'parsed_successfully': False
                }
        except Exception:
            return {
                'target_vitola': None,
                'target_packaging': "Box of 25", 
                'parsed_successfully': False
            }
    
    def run_update(self) -> bool:
        """Run the complete update process"""
        mode_str = "[DRY RUN] " if self.dry_run else ""
        print("=" * 70)
        print(f"{mode_str}BNB TOBACCO ENHANCED PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("MASTER-DRIVEN METADATA SYNC: All metadata always synced from master file")
        print("=" * 70)
        
        # Load master file
        if not self.load_master_file():
            return False
        
        # Load CSV
        data = self.load_csv()
        if not data:
            return False
        
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
                continue
            
            # Skip if no URL
            if not url:
                print("  [SKIP] No URL provided")
                failed_updates += 1
                continue
            
            # Extract live pricing with variant targeting
            pricing_data = self.update_pricing_data(url, cigar_id)
            
            if 'error' in pricing_data:
                print(f"  [FAIL] {pricing_data['error']}")
                failed_updates += 1
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
    
    parser = argparse.ArgumentParser(description='Enhanced BnB Tobacco price updater with master-driven metadata sync')
    parser.add_argument('--csv', help='Path to BnB Tobacco CSV file')
    parser.add_argument('--master', help='Path to master cigars CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Show what metadata would be updated without making changes')
    parser.add_argument('--test', action='store_true', help='Deprecated: Use --dry-run instead')
    
    args = parser.parse_args()
    
    # Handle deprecated --test flag
    dry_run = args.dry_run or args.test
    
    # Create updater instance
    updater = BnBTobaccoCSVUpdaterWithMaster(csv_path=args.csv, master_path=args.master, dry_run=dry_run)
    
    if dry_run:
        print("[DRY RUN MODE] Showing metadata changes without updating files")
    
    # Run the update
    success = updater.run_update()
    
    if success:
        print("\n[SUCCESS] BnB Tobacco enhanced update completed successfully")
    else:
        print("\n[FAILED] BnB Tobacco enhanced update failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
