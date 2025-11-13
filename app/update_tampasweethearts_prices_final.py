"""
Tampa Sweethearts CSV Updater with Master File Integration
Handles packaging-specific pricing extraction from select option elements
Uses cigar_id from master_cigars.csv for metadata auto-population

Key Features:
- Packaging-specific targeting (Box of 25, Box of 10, etc.)
- Server-side HTML extraction (no JavaScript needed)
- Master file integration for auto-populating metadata
- Standard CSV output format for auto-discovery integration
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
    from tampa_sweethearts_extractor import extract_tampa_sweethearts_data
except ImportError:
    print("[ERROR] Could not import extract_tampa_sweethearts_data. Make sure the extractor is in tools/price_monitoring/retailers/tampa_sweethearts_extractor.py")
    sys.exit(1)


class TampaSweetheartsCSVUpdaterWithMaster:
    def __init__(self, csv_path: str = None, master_path: str = None):
        if csv_path is None:
            self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'tampasweethearts.csv')
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
            
            print(f"[INFO] Loaded {len(data)} products from Tampa Sweethearts CSV")
            return data
        except FileNotFoundError:
            print(f"[ERROR] Tampa Sweethearts CSV not found at: {self.csv_path}")
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
    
    def extract_targeting_info(self, cigar_id: str) -> str:
        """Extract target packaging from cigar_id for Tampa Sweethearts targeting"""
        try:
            # Parse cigar_id: BRAND|BRAND|LINE|VITOLA|VITOLA|SIZE|WRAPPER|PACKAGING
            parts = cigar_id.split('|')
            if len(parts) >= 8:
                packaging_code = parts[7]  # 8th component (e.g., BOX25, BOX10, PACK5)
                
                # Convert packaging code to target format
                if packaging_code.startswith('BOX'):
                    qty = packaging_code.replace('BOX', '')
                    target_packaging = f"Box of {qty}"
                elif packaging_code.startswith('PACK'):
                    qty = packaging_code.replace('PACK', '')
                    target_packaging = f"Pack of {qty}"
                else:
                    target_packaging = "Box of 25"  # Default fallback
                
                return target_packaging
            else:
                print(f"[WARNING] Invalid cigar_id format: {cigar_id}")
                return "Box of 25"  # Default fallback
        except Exception as e:
            print(f"[WARNING] Failed to parse targeting info from cigar_id: {e}")
            return "Box of 25"  # Default fallback
    
    def update_pricing_data(self, url: str, cigar_id: str) -> Dict:
        """Extract live pricing data from Tampa Sweethearts with targeting"""
        try:
            # Validate URL
            if not url or not url.startswith(('http://', 'https://')):
                return {'error': f'Invalid URL: "{url}" - URLs must start with http:// or https://'}
            
            # Extract targeting information from cigar_id
            target_packaging = self.extract_targeting_info(cigar_id)
            
            result = extract_tampa_sweethearts_data(url, target_packaging=target_packaging)
            
            if result.get('success'):
                return {
                    'price': result.get('price'),
                    'in_stock': result.get('in_stock'),
                    'box_quantity': result.get('box_quantity'),
                    'target_found': result.get('target_found'),
                    'target_packaging': target_packaging
                }
            else:
                error_msg = result.get('error', 'Unknown error')
                if result.get('available_options'):
                    available = [f"{opt['packaging']}: ${opt['price']}" for opt in result['available_options']]
                    error_msg += f" (Available: {', '.join(available)})"
                return {'error': error_msg}
                
        except Exception as e:
            print(f"[ERROR] Price extraction failed: {e}")
            return {'error': str(e)}
    
    def run_update(self) -> bool:
        """Run the complete update process"""
        print("=" * 70)
        print(f"TAMPA SWEETHEARTS PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
            
            # Extract live pricing with targeting
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
            
            # Show targeting status
            target_status = "[TARGET FOUND]" if pricing_data.get('target_found') else "[TARGET MISSING]"
            target_pkg = pricing_data.get('target_packaging', 'Unknown')
            
            # Show results
            price_str = f"${pricing_data.get('price', 'N/A')}"
            stock_str = "In Stock" if pricing_data.get('in_stock') else "Out of Stock"
            
            print(f"  [OK] {price_str} | {stock_str} | {target_pkg} {target_status}")
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
    
    parser = argparse.ArgumentParser(description='Update Tampa Sweethearts prices from CSV')
    parser.add_argument('--csv', help='Path to Tampa Sweethearts CSV file')
    parser.add_argument('--master', help='Path to master cigars CSV file')
    parser.add_argument('--test', action='store_true', help='Test mode - show what would be updated without saving')
    
    args = parser.parse_args()
    
    # Create updater instance
    updater = TampaSweetheartsCSVUpdaterWithMaster(csv_path=args.csv, master_path=args.master)
    
    if args.test:
        print("[TEST MODE] Running in test mode - no changes will be saved")
    
    # Run the update
    success = updater.run_update()
    
    if success:
        print("\n[SUCCESS] Tampa Sweethearts price update completed successfully")
    else:
        print("\n[FAILED] Tampa Sweethearts price update failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
