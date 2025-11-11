"""
Nick's Cigar World CSV Updater with Master File Integration
Updates pricing AND auto-populates all metadata from master file
Works with minimal CSV input - just cigar_id + URL needed
"""

import csv
import os
import sys
import shutil
import pandas as pd
from datetime import datetime
from typing import List, Dict

# Add the tools directory to path for importing the extractor
current_dir = os.path.dirname(os.path.abspath(__file__))
tools_dir = os.path.join(current_dir, '..', 'tools', 'price_monitoring', 'retailers')
sys.path.insert(0, tools_dir)

try:
    from nicks_cigars import extract_nicks_cigars_data
except ImportError as e:
    print(f"[ERROR] Could not import extract_nicks_cigars_data: {e}")
    print(f"[INFO] Looking in: {tools_dir}")
    print(f"[INFO] Files in directory: {os.listdir(tools_dir) if os.path.exists(tools_dir) else 'Directory not found'}")
    sys.exit(1)


class NicksCSVUpdaterWithMaster:
    def __init__(self, csv_path: str = None, master_path: str = None):
        if csv_path is None:
            # Default path relative to app directory - updated to match actual filename
            self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'nickscigarworld.csv')
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
        
    def create_backup(self) -> bool:
        """Create a backup of the current CSV file"""
        try:
            if not os.path.exists(self.csv_path):
                print(f"[INFO] CSV file doesn't exist yet: {self.csv_path}")
                return True
                
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = os.path.dirname(self.csv_path)
            backup_filename = f"nicks_backup_{timestamp}.csv"
            self.backup_path = os.path.join(backup_dir, backup_filename)
            
            shutil.copy2(self.csv_path, self.backup_path)
            print(f"[OK] Backup created: {backup_filename}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to create backup: {str(e)}")
            return False
    
    def read_csv_data(self) -> List[Dict]:
        """Read the current CSV data (handles minimal input format)"""
        try:
            if not os.path.exists(self.csv_path):
                print(f"[INFO] Creating new CSV file: {self.csv_path}")
                return []
                
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                data = list(reader)
                print(f"[OK] Read {len(data)} products from CSV")
                return data
                
        except Exception as e:
            print(f"[ERROR] Failed to read CSV: {str(e)}")
            return []
    
    def write_csv_data(self, data: List[Dict]) -> bool:
        """Write updated data back to CSV with complete structure"""
        try:
            if not data:
                print("[ERROR] No data to write")
                return False
                
            # Ensure all required columns exist with proper order
            required_columns = [
                'cigar_id', 'title', 'url', 'brand', 'line', 
                'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock'
            ]
            
            # Make sure each row has all columns
            complete_data = []
            for row in data:
                complete_row = {}
                for col in required_columns:
                    complete_row[col] = row.get(col, '')
                complete_data.append(complete_row)
            
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=required_columns)
                writer.writeheader()
                writer.writerows(complete_data)
                
            print(f"[OK] Updated CSV file with {len(complete_data)} products")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to write CSV: {str(e)}")
            return False
    
    def generate_title_from_master(self, master_data: Dict) -> str:
        """Generate a descriptive title from master file data"""
        try:
            brand = master_data.get('brand', '')
            line = master_data.get('line', '')
            vitola = master_data.get('vitola', '')
            size = master_data.get('size', '')
            box_qty = master_data.get('box_qty', '')
            
            # Create title: "Brand Line Vitola Size (Box of X)"
            title_parts = []
            if brand: title_parts.append(brand)
            if line: title_parts.append(line)
            if vitola: title_parts.append(vitola)
            if size: title_parts.append(size)
            
            title = ' '.join(title_parts)
            if box_qty: title += f" (Box of {box_qty})"
            
            return title
        except Exception:
            return "Unknown Product"
    
    def update_product_data(self, product: Dict) -> Dict:
        """Update a single product's data - auto-populate everything from minimal input"""
        cigar_id = product.get('cigar_id', '').strip() if product.get('cigar_id') else ''
        url = product.get('url', '').strip() if product.get('url') else ''
        existing_title = product.get('title', '').strip() if product.get('title') else ''
        
        if not cigar_id:
            print(f"[SKIP] No cigar_id provided")
            return product
            
        if not url:
            print(f"[SKIP] No URL provided for cigar_id: {cigar_id}")
            return product
        
        print(f"[PROCESSING] {existing_title or cigar_id}")
        print(f"             Cigar ID: {cigar_id}")
        print(f"             URL: {url}")
        
        # Get metadata from master file
        master_data = self.get_master_data_by_cigar_id(cigar_id)
        
        if master_data:
            # Auto-populate ALL metadata from master file
            for field in ['brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty']:
                if field in master_data:
                    old_val = product.get(field, '')
                    new_val = master_data[field]
                    product[field] = new_val
                    
                    if not old_val or str(old_val) != str(new_val):
                        print(f"             {field.title()}: Set to '{new_val}'")
            
            # Generate title if not provided
            if not existing_title:
                generated_title = self.generate_title_from_master(master_data)
                product['title'] = generated_title
                print(f"             Title: Generated '{generated_title}'")
        else:
            print(f"             [WARNING] No master data found for cigar_id: {cigar_id}")
        
        # Extract live pricing data from Nick's
        extraction_result = extract_nicks_cigars_data(url)
        
        if not extraction_result.get('success'):
            error_msg = extraction_result.get('error', 'Extraction failed')
            print(f"             [ERROR] {error_msg}")
            return product
        
        # Update price
        if extraction_result.get('price') is not None:
            old_price = product.get('price', 'N/A')
            new_price = extraction_result['price']
            
            product['price'] = new_price
            print(f"             Price: ${new_price}")
        else:
            print(f"             Price: No valid price found")
        
        # Update stock status
        if extraction_result.get('in_stock') is not None:
            old_stock = product.get('in_stock', 'N/A')
            new_stock = extraction_result['in_stock']
            
            product['in_stock'] = str(new_stock).lower()
            
            stock_text = "IN STOCK" if new_stock else "OUT OF STOCK"
            print(f"             Stock: {stock_text}")
        
        # Cross-check box quantity from extraction vs master file
        if extraction_result.get('box_quantity') is not None:
            extracted_qty = extraction_result['box_quantity']
            master_qty = master_data.get('box_qty', '')
            
            if master_qty and extracted_qty and master_qty != extracted_qty:
                print(f"             [WARNING] Box qty mismatch: Master={master_qty}, Extracted={extracted_qty}")
                # Keep master file quantity as authoritative
            elif not master_qty and extracted_qty:
                product['box_qty'] = extracted_qty
                print(f"             Box qty: Updated to {extracted_qty} (from page)")
        
        # Show discount info if available
        if extraction_result.get('discount_percent'):
            print(f"             Discount: {extraction_result['discount_percent']:.1f}% off")
        
        print(f"[OK] Updated: {product.get('title', cigar_id)}")
        return product
    
    def update_all_products(self, max_products: int = None) -> bool:
        """Update pricing and metadata for all products in the CSV"""
        print("=== Nick's Cigar World CSV Updater with Master File Integration ===")
        print(f"CSV File: {self.csv_path}")
        print(f"Master File: {self.master_path}")
        print(f"Supports minimal input: Just cigar_id + URL required!")
        
        # Load master file
        if not self.load_master_file():
            print("[ERROR] Cannot proceed without master file")
            return False
        
        # Create backup
        if not self.create_backup():
            print("[ERROR] Cannot proceed without backup")
            return False
        
        # Read current data
        products = self.read_csv_data()
        if not products:
            print("[ERROR] No products to process")
            print("[HINT] Add products to CSV with format: cigar_id,url,title,brand,line,wrapper,vitola,size,box_qty,price,in_stock")
            print("[HINT] Minimal input works: just fill cigar_id and url, leave other fields empty")
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
                print(f"[ERROR] Failed to process {product.get('cigar_id', 'Unknown')}: {str(e)}")
                continue
        
        # Write updated data back to CSV
        if self.write_csv_data(products):
            print(f"\n=== Update Complete ===")
            print(f"Products processed: {len(products)}")
            print(f"Products updated: {updated_count}")
            print(f"Errors: {error_count}")
            if self.backup_path:
                print(f"Backup saved as: {os.path.basename(self.backup_path)}")
            return True
        else:
            print(f"\n[ERROR] Failed to save updated data")
            return False


def main():
    """Main function for running the updater"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Update Nick's Cigar World CSV with live pricing and master metadata")
    parser.add_argument('--csv', help="Path to Nick's CSV file", default=None)
    parser.add_argument('--master', help='Path to master cigars CSV file', default=None)
    parser.add_argument('--max', type=int, help='Maximum number of products to process (for testing)', default=None)
    parser.add_argument('--test', action='store_true', help='Test mode - process only first 3 products')
    
    args = parser.parse_args()
    
    # Test mode
    if args.test:
        args.max = 3
        print("[TEST MODE] Processing only first 3 products")
    
    # Create updater and run
    updater = NicksCSVUpdaterWithMaster(csv_path=args.csv, master_path=args.master)
    
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
