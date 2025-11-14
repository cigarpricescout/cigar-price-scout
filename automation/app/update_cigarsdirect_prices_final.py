"""
CigarsDirect CSV Updater with Master File Integration
Handles comprehensive pricing extraction with MSRP vs sale price detection
Supports premium pricing range ($200-$2000) and various package sizes
Uses cigar_id from master_cigars.csv for metadata auto-population
"""

import csv
import os
import sys
import shutil
import pandas as pd
from datetime import datetime
from typing import List, Dict

# Add the tools directory to path for importing the extractor
tools_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tools', 'price_monitoring', 'retailers')
sys.path.insert(0, tools_path)

try:
    from cigarsdirect_extractor import extract_cigarsdirect_data
except ImportError:
    print("[ERROR] Could not import extract_cigarsdirect_data. Make sure the extractor is in tools/price_monitoring/retailers/cigarsdirect_extractor.py")
    sys.exit(1)


class CigarsDirectCSVUpdaterWithMaster:
    def __init__(self, csv_path: str = None, master_path: str = None):
        if csv_path is None:
            self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'cigarsdirect.csv')
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
            
            # Filter to box quantities (5+)
            box_skus = self.master_df[self.master_df['Box Quantity'] >= 5]
            
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
            
            print(f"[INFO] Loaded {len(data)} products from CigarsDirect CSV")
            return data
        except FileNotFoundError:
            print(f"[ERROR] CigarsDirect CSV not found at: {self.csv_path}")
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
            
            # Clean the data to ensure no None keys and all required fields exist
            cleaned_data = []
            for row in data:
                # Remove any None keys
                clean_row = {k: v for k, v in row.items() if k is not None}
                
                # Ensure all required fieldnames exist
                for field in fieldnames:
                    if field not in clean_row:
                        clean_row[field] = ''
                
                # Keep only the fieldnames we want
                final_row = {field: clean_row.get(field, '') for field in fieldnames}
                cleaned_data.append(final_row)
            
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(cleaned_data)
            
            print(f"[INFO] Updated data saved to {self.csv_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save CSV: {e}")
            return False
    
    def update_pricing_data(self, url: str) -> Dict:
        """Extract live pricing data from CigarsDirect"""
        try:
            # Validate URL
            if not url or not url.startswith(('http://', 'https://')):
                return {'error': f'Invalid URL: "{url}" - URLs must start with http:// or https://'}
            
            result = extract_cigarsdirect_data(url)
            
            if result.get('success'):
                return {
                    'price': result.get('price'),
                    'original_price': result.get('original_price'),
                    'discount_percent': result.get('discount_percent'),
                    'in_stock': result.get('in_stock'),
                    'box_quantity': result.get('box_quantity')
                }
            else:
                return {'error': result.get('error', 'Unknown error')}
                
        except Exception as e:
            print(f"[ERROR] Price extraction failed: {e}")
            return {'error': str(e)}
    
    def run_update(self) -> bool:
        """Run the complete update process"""
        print("=" * 70)
        print(f"CIGARSDIRECT PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
            
            # Show results with comprehensive pricing info
            price_str = f"${pricing_data.get('price', 'N/A')}"
            
            if pricing_data.get('original_price'):
                msrp_str = f" (MSRP ${pricing_data['original_price']})"
            else:
                msrp_str = " (Single Price)"
            
            if pricing_data.get('discount_percent'):
                discount_str = f" | {pricing_data['discount_percent']:.1f}% off"
            else:
                discount_str = ""
            
            stock_str = "In Stock" if pricing_data.get('in_stock') else "Out of Stock"
            
            print(f"  [OK] {price_str}{msrp_str}{discount_str} | {stock_str}")
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
    
    parser = argparse.ArgumentParser(description='Update CigarsDirect prices from CSV')
    parser.add_argument('--csv', help='Path to CigarsDirect CSV file')
    parser.add_argument('--master', help='Path to master cigars CSV file')
    
    args = parser.parse_args()
    
    # Create updater instance
    updater = CigarsDirectCSVUpdaterWithMaster(csv_path=args.csv, master_path=args.master)
    
    # Run the update
    success = updater.run_update()
    
    if success:
        print("\n[SUCCESS] CigarsDirect price update completed successfully")
    else:
        print("\n[FAILED] CigarsDirect price update failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
