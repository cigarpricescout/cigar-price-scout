"""
Absolute Cigars CSV Updater with Google Sheets Master File Integration
Uses cigar_id from master_cigars.csv for metadata auto-population
Following the proven Hiland's Cigars updater pattern
"""

import csv
import os
import sys
import shutil
import pandas as pd
from datetime import datetime
from typing import List, Dict

# Add the retailers directory to path
retailers_dir = os.path.join(os.path.dirname(__file__), '..', 'tools', 'price_monitoring', 'retailers')
sys.path.append(retailers_dir)

try:
    # Import the extractor function
    from absolute_cigars_extractor import extract_absolute_cigars_data
except ImportError as e:
    print(f"[ERROR] Could not import extract_absolute_cigars_data. Make sure absolute_cigars_extractor.py is in tools/price_monitoring/retailers/")
    print(f"[ERROR] Import error details: {e}")
    sys.exit(1)


class AbsoluteCigarsCSVUpdaterWithMaster:
    def __init__(self, csv_path: str = None, master_path: str = None):
        if csv_path is None:
            self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'absolutecigars.csv')
        else:
            self.csv_path = csv_path
            
        if master_path is None:
            self.master_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'master_cigars.csv')
        else:
            self.master_path = master_path
            
        self.backup_path = None
        self.master_df = None
        
    def load_master_file(self) -> bool:
        """Load the master cigars file"""
        try:
            self.master_df = pd.read_csv(self.master_path)
            
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
        """Auto-populate missing metadata from master file"""
        cigar_id = row.get('cigar_id', '')
        if not cigar_id:
            return row
        
        metadata = self.get_cigar_metadata(cigar_id)
        
        # Auto-populate fields that are empty or missing
        for field in ['title', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty']:
            if not row.get(field) and field in metadata and metadata[field]:
                row[field] = metadata[field]
        
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
            
            print(f"[INFO] Loaded {len(data)} products from Absolute Cigars CSV")
            return data
        except FileNotFoundError:
            print(f"[ERROR] Absolute Cigars CSV not found at: {self.csv_path}")
            return []
        except Exception as e:
            print(f"[ERROR] Failed to load CSV: {e}")
            return []
    
    def save_csv(self, data: List[Dict]) -> bool:
        """Save the updated data back to CSV"""
        if not data:
            print("[ERROR] No data to save")
            return False
        
        try:
            fieldnames = ['cigar_id', 'title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
            
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
        """Extract live pricing data from Absolute Cigars"""
        try:
            result = extract_absolute_cigars_data(url)
            
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
    
    def run_update(self) -> bool:
        """Run the complete update process"""
        print("=" * 70)
        print(f"ABSOLUTE CIGARS PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        # Load master file
        if not self.load_master_file():
            return False
        
        # Load CSV
        data = self.load_csv()
        if not data:
            return False
        
        # Create backup
        if not self.create_backup():
            return False
        
        # Update each product
        successful_updates = 0
        failed_updates = 0
        
        for i, row in enumerate(data):
            cigar_id = row.get('cigar_id', 'Unknown')
            url = row.get('url', '')
            
            print(f"\n[{i+1}/{len(data)}] Processing: {cigar_id}")
            
            # Auto-populate metadata from master file
            row = self.auto_populate_metadata(row)
            
            # Skip if no URL
            if not url:
                print("  [SKIP] No URL provided")
                failed_updates += 1
                continue
            
            # Extract live pricing
            pricing_data = self.update_pricing_data(url)
            
            if 'error' in pricing_data:
                print(f"  [FAIL] {pricing_data['error']}")
                failed_updates += 1
                continue
            
            # Update the row with new pricing data
            if pricing_data.get('price') is not None:
                row['price'] = pricing_data['price']
            if pricing_data.get('in_stock') is not None:
                row['in_stock'] = pricing_data['in_stock']
            
            # Validate box quantity if available
            if pricing_data.get('box_quantity'):
                extracted_qty = pricing_data['box_quantity']
                csv_qty = row.get('box_qty')
                
                if csv_qty and int(extracted_qty) != int(csv_qty):
                    print(f"  [WARNING] Box quantity mismatch - CSV: {csv_qty}, Extracted: {extracted_qty}")
            
            # Show results
            price_str = f"${pricing_data.get('price', 'N/A')}"
            stock_str = "In Stock" if pricing_data.get('in_stock') else "Out of Stock"
            discount_str = f" ({pricing_data['discount_percent']:.1f}% off)" if pricing_data.get('discount_percent') else ""
            
            print(f"  [OK] {price_str} | {stock_str}{discount_str}")
            successful_updates += 1
        
        # Save updated data
        if self.save_csv(data):
            print("\n" + "=" * 70)
            print("UPDATE COMPLETE")
            print(f"Successful updates: {successful_updates}")
            print(f"Failed updates: {failed_updates}")
            print(f"Total processed: {len(data)}")
            print(f"Updated file: {self.csv_path}")
            print(f"Backup file: {self.backup_path}")
            print("=" * 70)
            return True
        else:
            return False


def main():
    """Main function for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update Absolute Cigars prices from CSV')
    parser.add_argument('--csv', help='Path to Absolute Cigars CSV file')
    parser.add_argument('--master', help='Path to master cigars CSV file')
    parser.add_argument('--test', action='store_true', help='Test mode - show what would be updated without saving')
    
    args = parser.parse_args()
    
    # Create updater instance
    updater = AbsoluteCigarsCSVUpdaterWithMaster(csv_path=args.csv, master_path=args.master)
    
    if args.test:
        print("[TEST MODE] Running in test mode - no changes will be saved")
    
    # Run the update
    success = updater.run_update()
    
    if success:
        print("\n[SUCCESS] Absolute Cigars price update completed successfully")
    else:
        print("\n[FAILED] Absolute Cigars price update failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
