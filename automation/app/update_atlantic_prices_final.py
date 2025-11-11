"""
Atlantic Cigar CSV Updater with Google Sheets Master File Integration
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
sys.path.append(os.path.join(os.path.dirname(__file__), 'tools', 'price_monitoring'))

try:
    from retailers.atlantic_cigar import extract_atlantic_cigar_data
except ImportError:
    print("[ERROR] Could not import extract_atlantic_cigar_data. Make sure the extractor is in tools/price_monitoring/retailers/")
    sys.exit(1)


class AtlanticCSVUpdaterWithMaster:
    def __init__(self, csv_path: str = None, master_path: str = None):
        if csv_path is None:
            # Default path relative to app directory
            self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'atlantic.csv')
        else:
            self.csv_path = csv_path
            
        if master_path is None:
            # Default path to master file
            self.master_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'master_cigars.csv')
        else:
            self.master_path = master_path
            
        self.backup_path = None
        self.master_df = None
        
    def load_master_file(self) -> bool:
        """Load the master cigars file"""
        try:
            self.master_df = pd.read_csv(self.master_path)
            
            # Convert Box Quantity to numeric, replacing any non-numeric values with 0
            self.master_df['Box Quantity'] = pd.to_numeric(self.master_df['Box Quantity'], errors='coerce').fillna(0)
            
            # Filter to only box quantities (10+) for retail comparison
            box_skus = self.master_df[self.master_df['Box Quantity'] >= 10]
            
            print(f"[OK] Loaded {len(self.master_df)} total SKUs from master file")
            print(f"[OK] Found {len(box_skus)} box quantity SKUs (10+ cigars)")
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to load master file: {str(e)}")
            return False
    
    def get_master_data_by_cigar_id(self, cigar_id: str) -> Dict:
        """Get metadata from master file for a given cigar_id"""
        try:
            # Find the row with matching cigar_id
            matching_rows = self.master_df[self.master_df['cigar_id'] == cigar_id]
            
            if matching_rows.empty:
                return {}
                
            row = matching_rows.iloc[0]  # Take first match
            
            return {
                'brand': str(row['Brand']),
                'line': str(row['Line']),
                'wrapper': str(row['Wrapper']),
                'vitola': str(row['Vitola']),
                'size': f"{row['Length']}x{row['Ring Gauge']}",
                'box_qty': int(row['Box Quantity']),
                'binder': str(row.get('Binder', '')),
                'filler': str(row.get('Filler', '')),
                'strength': str(row.get('Strength', '')),
                'style': str(row.get('Style', '')),
                'wrapper_alias': str(row.get('Wrapper_Alias', '')),
                'country': str(row.get('country_of_origin', '')),
                'factory': str(row.get('factory', ''))
            }
        except Exception as e:
            print(f"[ERROR] Failed to get master data for cigar_id {cigar_id}: {str(e)}")
            return {}
    
    def find_matching_cigar_id(self, title: str, brand: str = "", line: str = "", vitola: str = "") -> str:
        """Find a matching cigar_id from the master file based on product details"""
        try:
            # Filter box quantities only
            box_skus = self.master_df[self.master_df['Box Quantity'] >= 10].copy()
            
            # Simple matching - look for brand and vitola in title
            matches = []
            
            for idx, row in box_skus.iterrows():
                score = 0
                
                # Check if brand matches
                if brand.lower() in row['Brand'].lower() or row['Brand'].lower() in brand.lower():
                    score += 3
                elif brand.lower() in title.lower():
                    score += 2
                
                # Check if line matches
                if line and (line.lower() in row['Line'].lower() or row['Line'].lower() in line.lower()):
                    score += 2
                
                # Check if vitola matches
                if vitola and (vitola.lower() in row['Vitola'].lower() or row['Vitola'].lower() in vitola.lower()):
                    score += 2
                
                # Check title contains vitola
                if row['Vitola'].lower() in title.lower():
                    score += 1
                
                if score >= 3:  # Minimum threshold for a match
                    matches.append({
                        'cigar_id': row['cigar_id'],
                        'score': score,
                        'match_text': f"{row['Brand']} {row['Line']} {row['Vitola']} ({row['Length']}x{row['Ring Gauge']})"
                    })
            
            if matches:
                # Sort by score and return best match
                matches.sort(key=lambda x: x['score'], reverse=True)
                best_match = matches[0]
                print(f"             [AUTO-MATCH] Found: {best_match['match_text']} (Score: {best_match['score']})")
                return best_match['cigar_id']
            
            return ""
            
        except Exception as e:
            print(f"[ERROR] Failed to find matching cigar_id: {str(e)}")
            return ""
        
    def create_backup(self) -> bool:
        """Create a backup of the current CSV file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = os.path.dirname(self.csv_path)
            backup_filename = f"atlantic_backup_{timestamp}.csv"
            self.backup_path = os.path.join(backup_dir, backup_filename)
            
            shutil.copy2(self.csv_path, self.backup_path)
            print(f"[OK] Backup created: {backup_filename}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to create backup: {str(e)}")
            return False
    
    def read_csv_data(self) -> List[Dict]:
        """Read the current CSV data"""
        try:
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                data = list(reader)
                print(f"[OK] Read {len(data)} products from CSV")
                return data
                
        except Exception as e:
            print(f"[ERROR] Failed to read CSV: {str(e)}")
            return []
    
    def write_csv_data(self, data: List[Dict]) -> bool:
        """Write updated data back to CSV"""
        try:
            if not data:
                print("[ERROR] No data to write")
                return False
                
            # Ensure all required columns exist
            required_columns = ['cigar_id', 'title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
            
            fieldnames = required_columns.copy()
            # Add any additional columns that might exist
            for row in data:
                for key in row.keys():
                    if key not in fieldnames:
                        fieldnames.append(key)
            
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
                
            print(f"[OK] Updated CSV file with {len(data)} products")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to write CSV: {str(e)}")
            return False
    
    def update_product_data(self, product: Dict) -> Dict:
        """Update a single product's pricing data AND metadata from master file"""
        url = product.get('url', '').strip()
        title = product.get('title', 'Unknown Product')
        cigar_id = product.get('cigar_id', '').strip()
        
        if not url:
            print(f"[SKIP] No URL for: {title}")
            return product
        
        print(f"[PROCESSING] {title}")
        print(f"             URL: {url}")
        
        # Auto-find cigar_id if missing
        if not cigar_id:
            print(f"             Cigar ID: Missing - attempting auto-match...")
            brand = product.get('brand', '')
            line = product.get('line', '')
            vitola = product.get('vitola', '')
            
            cigar_id = self.find_matching_cigar_id(title, brand, line, vitola)
            if cigar_id:
                product['cigar_id'] = cigar_id
                print(f"             Cigar ID: Set to {cigar_id}")
            else:
                print(f"             [WARNING] Could not auto-match cigar_id")
        else:
            print(f"             Cigar ID: {cigar_id}")
        
        # Update metadata from master file if cigar_id exists
        if cigar_id:
            master_data = self.get_master_data_by_cigar_id(cigar_id)
            
            if master_data:
                # Update all metadata from master file
                old_metadata = {
                    'brand': product.get('brand', ''),
                    'line': product.get('line', ''),
                    'wrapper': product.get('wrapper', ''),
                    'vitola': product.get('vitola', ''),
                    'size': product.get('size', ''),
                    'box_qty': product.get('box_qty', '')
                }
                
                # Update with master data (only core fields for CSV)
                core_fields = ['brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty']
                for field in core_fields:
                    if field in master_data:
                        product[field] = master_data[field]
                
                # Show what was updated from master file
                changes = []
                for key in core_fields:
                    old_val = old_metadata.get(key, '')
                    new_val = master_data.get(key, '')
                    if str(old_val) != str(new_val):
                        changes.append(f"{key}: {old_val} -> {new_val}")
                
                if changes:
                    print(f"             Metadata updated from master: {', '.join(changes)}")
                else:
                    print(f"             Metadata: Already matches master file")
                    
            else:
                print(f"             [WARNING] No master data found for cigar_id: {cigar_id}")
        
        # Extract live pricing data
        extraction_result = extract_atlantic_cigar_data(url)
        
        if not extraction_result.get('success'):
            error_msg = extraction_result.get('error', 'Extraction failed')
            print(f"[ERROR] {error_msg}")
            return product
        
        # Update price if we got a valid result
        if extraction_result.get('price') is not None:
            old_price = product.get('price', 'N/A')
            new_price = extraction_result['price']
            
            product['price'] = new_price
            
            # Show price change
            if str(old_price) != str(new_price):
                print(f"             Price: ${old_price} -> ${new_price}")
            else:
                print(f"             Price: ${new_price} (unchanged)")
        else:
            print(f"             Price: No valid price found")
        
        # Update stock status
        if extraction_result.get('in_stock') is not None:
            old_stock = product.get('in_stock', 'N/A')
            new_stock = extraction_result['in_stock']
            
            product['in_stock'] = str(new_stock).lower()
            
            # Show stock change
            if str(old_stock) != str(new_stock).lower():
                stock_text = "IN STOCK" if new_stock else "OUT OF STOCK"
                print(f"             Stock: {old_stock} -> {stock_text}")
        
        # Cross-check box quantity from extraction vs master file
        if extraction_result.get('box_quantity') is not None:
            extracted_qty = extraction_result['box_quantity']
            master_qty = product.get('box_qty', '')
            
            try:
                master_qty_int = int(master_qty) if master_qty else None
                if master_qty_int and master_qty_int != extracted_qty:
                    print(f"             [WARNING] Box qty mismatch: Master={master_qty_int}, Extracted={extracted_qty}")
                    # Keep master file quantity as authoritative
                elif not master_qty_int:
                    product['box_qty'] = extracted_qty
                    print(f"             Box qty: Updated to {extracted_qty} (from page)")
            except ValueError:
                product['box_qty'] = extracted_qty
        
        # Show discount info if available
        if extraction_result.get('discount_percent'):
            print(f"             Discount: {extraction_result['discount_percent']:.1f}% off")
        
        print(f"[OK] Updated: {title}")
        return product
    
    def update_all_products(self, max_products: int = None) -> bool:
        """Update pricing and metadata for all products in the CSV"""
        print("=== Atlantic Cigar CSV Updater with Master File Integration ===")
        print(f"CSV File: {self.csv_path}")
        print(f"Master File: {self.master_path}")
        
        # Load master file
        if not self.load_master_file():
            print("[ERROR] Cannot proceed without master file")
            return False
        
        # Check if CSV exists
        if not os.path.exists(self.csv_path):
            print(f"[ERROR] CSV file not found: {self.csv_path}")
            return False
        
        # Create backup
        if not self.create_backup():
            print("[ERROR] Cannot proceed without backup")
            return False
        
        # Read current data
        products = self.read_csv_data()
        if not products:
            print("[ERROR] No products to process")
            return False
        
        # Limit products if specified (for testing)
        if max_products:
            products = products[:max_products]
            print(f"[INFO] Processing first {max_products} products only")
        
        print(f"\n=== Processing {len(products)} products ===")
        
        updated_count = 0
        error_count = 0
        
        # Process each product
        for i, product in enumerate(products, 1):
            print(f"\n[{i}/{len(products)}]", end=" ")
            
            try:
                original_product = product.copy()
                updated_product = self.update_product_data(product)
                
                # Check if anything actually changed
                if updated_product != original_product:
                    updated_count += 1
                
            except Exception as e:
                error_count += 1
                print(f"[ERROR] Failed to process {product.get('title', 'Unknown')}: {str(e)}")
                continue
        
        # Write updated data back to CSV
        if self.write_csv_data(products):
            print(f"\n=== Update Complete ===")
            print(f"Products processed: {len(products)}")
            print(f"Products updated: {updated_count}")
            print(f"Errors: {error_count}")
            print(f"Backup saved as: {os.path.basename(self.backup_path)}")
            return True
        else:
            print(f"\n[ERROR] Failed to save updated data")
            return False


def main():
    """Main function for running the updater"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update Atlantic Cigar CSV with live pricing and master metadata')
    parser.add_argument('--csv', help='Path to Atlantic CSV file', default=None)
    parser.add_argument('--master', help='Path to master cigars CSV file', default=None)
    parser.add_argument('--max', type=int, help='Maximum number of products to process (for testing)', default=None)
    parser.add_argument('--test', action='store_true', help='Test mode - process only first 3 products')
    
    args = parser.parse_args()
    
    # Test mode
    if args.test:
        args.max = 3
        print("[TEST MODE] Processing only first 3 products")
    
    # Create updater and run
    updater = AtlanticCSVUpdaterWithMaster(csv_path=args.csv, master_path=args.master)
    
    try:
        success = updater.update_all_products(max_products=args.max)
        if success:
            print("\n[SUCCESS] CSV update completed successfully")
            sys.exit(0)
        else:
            print("\n[FAILURE] CSV update failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n[CANCELLED] Update cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FATAL ERROR] {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
