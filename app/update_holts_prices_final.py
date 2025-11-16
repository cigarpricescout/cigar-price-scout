#!/usr/bin/env python3
"""
Holt's Cigars Price Updater
Updates pricing data for Holt's Cigars products using the holts_cigars_extractor
Handles multi-product table pages with CID-based matching
"""

import sys
import os
import pandas as pd
import csv
from datetime import datetime
import time

# Add the project root to Python path for imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if 'app' in __file__:
    # If running from app/ directory, go up one level
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

print(f"[DEBUG] Project root: {project_root}")
print(f"[DEBUG] Looking for extractor at: {os.path.join(project_root, 'tools', 'price_monitoring', 'retailers', 'holts_cigars_extractor.py')}")

try:
    from tools.price_monitoring.retailers.holts_cigars_extractor import extract_holts_cigar_data
except ImportError:
    # Alternative import path if structure is different
    try:
        sys.path.append(os.path.join(project_root, 'tools', 'price_monitoring', 'retailers'))
        from holts_cigars_extractor import extract_holts_cigar_data
    except ImportError:
        print("[ERROR] Could not import extract_holts_cigar_data. Make sure the extractor is in tools/price_monitoring/retailers/")
        print(f"[DEBUG] Searched in: {project_root}/tools/price_monitoring/retailers/")
        sys.exit(1)

def load_master_data():
    """Load the master cigar database for matching"""
    try:
        # Try the correct path first (data directory)
        master_path = os.path.join(project_root, 'data', 'master_cigars.csv')
        
        # Fallback to static/data if that doesn't exist
        if not os.path.exists(master_path):
            master_path = os.path.join(project_root, 'static', 'data', 'master_cigars.csv')
        
        master_df = pd.read_csv(master_path)
        print(f"[INFO] Loaded master file with {len(master_df)} total cigars")
        
        # Filter for box SKUs only
        box_df = master_df[master_df['cigar_id'].str.contains('BOX|BUNDLE', case=False, na=False)]
        print(f"[INFO] Found {len(box_df)} box SKUs for retail comparison")
        
        return box_df
    except FileNotFoundError:
        print(f"[ERROR] Master cigar file not found at {master_path}")
        print(f"[DEBUG] Please ensure master_cigars.csv exists in either:")
        print(f"  - {os.path.join(project_root, 'data', 'master_cigars.csv')}")
        print(f"  - {os.path.join(project_root, 'static', 'data', 'master_cigars.csv')}")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to load master data: {e}")
        return None

def load_holts_csv():
    """Load existing Holt's CSV data"""
    try:
        # Try the correct path first (data directory)
        csv_path = os.path.join(project_root, 'data', 'holts.csv')
        
        # Fallback to static/data if that doesn't exist
        if not os.path.exists(csv_path):
            csv_path = os.path.join(project_root, 'static', 'data', 'holts.csv')
            
        if not os.path.exists(csv_path):
            print(f"[ERROR] Holt's CSV not found at: {csv_path}")
            print(f"[DEBUG] Checked paths:")
            print(f"  - {os.path.join(project_root, 'data', 'holts.csv')}")
            print(f"  - {os.path.join(project_root, 'static', 'data', 'holts.csv')}")
            return None
            
        df = pd.read_csv(csv_path)
        print(f"[INFO] Loaded {len(df)} products from Holt's CSV")
        return df
    except Exception as e:
        print(f"[ERROR] Failed to load Holt's CSV: {e}")
        return None

def create_backup(csv_path):
    """Create a backup of the current CSV"""
    try:
        if os.path.exists(csv_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = csv_path.replace('.csv', f'_backup_{timestamp}.csv')
            
            import shutil
            shutil.copy2(csv_path, backup_path)
            print(f"[INFO] Backup created: {backup_path}")
            return backup_path
    except Exception as e:
        print(f"[WARNING] Could not create backup: {e}")
    return None

def update_holts_prices():
    """Main function to update Holt's pricing data"""
    print("=" * 70)
    print(f"HOLT'S CIGARS PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Load master data for validation
    master_df = load_master_data()
    if master_df is None:
        print("[FAILED] Holt's Cigars price update failed")
        return False
    
    # Load Holt's CSV
    holts_df = load_holts_csv()
    if holts_df is None:
        print("[FAILED] Holt's Cigars price update failed")
        return False
    
    # Create backup  
    csv_path = os.path.join(project_root, 'data', 'holts.csv')
    if not os.path.exists(csv_path):
        csv_path = os.path.join(project_root, 'static', 'data', 'holts.csv')
    
    create_backup(csv_path)
    
    # Process each product
    total_products = len(holts_df)
    successful_updates = 0
    failed_updates = 0
    
    updated_rows = []
    
    for index, row in holts_df.iterrows():
        product_num = index + 1
        cigar_id = row['cigar_id']
        url = row['url']
        
        print(f"[{product_num}/{total_products}] Processing: {cigar_id}")
        
        try:
            # Extract pricing data using the multi-product extractor
            # Pass both URL and cigar_id for table matching
            pricing_data = extract_holts_cigar_data(url, cigar_id)
            
            if pricing_data.get('error'):
                print(f"  [ERROR] {pricing_data['error']}")
                failed_updates += 1
                updated_rows.append(row.to_dict())  # Keep original data
                continue
            
            # Update row with new pricing data (exclude MSRP from CSV storage)
            updated_row = row.copy()
            
            if pricing_data.get('price') is not None:
                updated_row['price'] = pricing_data['price']
            if pricing_data.get('in_stock') is not None:
                updated_row['in_stock'] = pricing_data['in_stock']
            if pricing_data.get('box_qty') is not None:
                updated_row['box_qty'] = pricing_data['box_qty']
            
            # Populate metadata from CID - always populate if fields are empty/null
            if 'cigar_id' in updated_row and updated_row['cigar_id']:
                cid_parts = updated_row['cigar_id'].split('|')
                if len(cid_parts) >= 8:
                    # Parse CID: BRAND|BRAND|LINE|VITOLA|VITOLA|SIZE|WRAPPER|PACKAGING
                    
                    # Check if fields need population (empty string, None, or NaN)
                    def needs_population(field_value):
                        return pd.isna(field_value) or field_value == '' or field_value is None
                    
                    # Helper function to format brand names properly
                    def format_brand_name(brand_code):
                        brand_mapping = {
                            'ARTUROFUENTE': 'Arturo Fuente',
                            'ROMEOYJULIETA': 'Romeo y Julieta', 
                            'HOYODEMONTERREY': 'Hoyo de Monterrey',
                            'PERDOMO': 'Perdomo',
                            'PADRON': 'Padron',
                            'MYFATHER': 'My Father',
                            'ASHTON': 'Ashton'
                        }
                        return brand_mapping.get(brand_code, brand_code.title())
                    
                    # Helper function to format line names
                    def format_line_name(line_code):
                        line_mapping = {
                            'HEMINGWAY': 'Hemingway',
                            'EXCALIBUR': 'Excalibur', 
                            '1875': '1875',
                            '1964ANNIVERSARY': '1964 Anniversary',
                            'RESERVE10THANNIVERSARYCHAMPAGNE': 'Reserve 10th Anniversary Champagne'
                        }
                        return line_mapping.get(line_code, line_code.title())
                    
                    # Helper function to format wrapper names  
                    def format_wrapper_name(wrapper_code):
                        wrapper_mapping = {
                            'CAM': 'Cameroon',
                            'CT': 'Connecticut Shade',
                            'MAD': 'Maduro',
                            'ECU': 'Ecuadorian Connecticut',
                            'IND': 'Indonesian Shade Grown TBN'
                        }
                        return wrapper_mapping.get(wrapper_code, wrapper_code)
                    
                    if needs_population(updated_row.get('brand')):
                        updated_row['brand'] = format_brand_name(cid_parts[0])
                    if needs_population(updated_row.get('line')):
                        updated_row['line'] = format_line_name(cid_parts[2])  
                    if needs_population(updated_row.get('wrapper')):
                        updated_row['wrapper'] = format_wrapper_name(cid_parts[6])
                    if needs_population(updated_row.get('vitola')):
                        # Just use the vitola name with proper capitalization
                        vitola_name = cid_parts[3].title()
                        if vitola_name == 'Bestseller':
                            vitola_name = 'Best Seller'
                        elif vitola_name == 'Diplomatico':
                            vitola_name = 'Diplomatico'
                        updated_row['vitola'] = vitola_name
                    if needs_population(updated_row.get('size')):
                        updated_row['size'] = cid_parts[5]
                    
                    # Generate title - use just the vitola name like other retailers
                    if needs_population(updated_row.get('title')):
                        updated_row['title'] = updated_row['vitola']
            
            # Calculate discount for display only (not stored)
            discount_text = ""
            if pricing_data.get('msrp_price') and pricing_data.get('price'):
                msrp = float(pricing_data['msrp_price'])
                sale = float(pricing_data['price'])
                if msrp > sale:
                    discount_percent = ((msrp - sale) / msrp) * 100
                    discount_text = f" ({discount_percent:.1f}% off)"
            
            # Format status message
            price_info = f"${pricing_data.get('price', 'N/A')}"
            if pricing_data.get('msrp_price'):
                price_info += f" (MSRP: ${pricing_data['msrp_price']})"
            
            stock_status = "In Stock" if pricing_data.get('in_stock', False) else "Out of Stock"
            
            print(f"  [OK] {price_info} | {stock_status}{discount_text}")
            print(f"  [INFO] Title: {updated_row.get('title', 'N/A')}")
            
            successful_updates += 1
            updated_rows.append(updated_row.to_dict())
            
        except Exception as e:
            print(f"  [ERROR] Failed to process: {str(e)}")
            failed_updates += 1
            updated_rows.append(row.to_dict())  # Keep original data
            continue
    
    # Save updated CSV
    try:
        updated_df = pd.DataFrame(updated_rows)
        
        # Ensure consistent column order (remove msrp_price from saved columns)
        expected_columns = ['cigar_id', 'title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
        
        # Reorder columns and fill missing ones
        for col in expected_columns:
            if col not in updated_df.columns:
                updated_df[col] = None
        
        updated_df = updated_df[expected_columns]
        
        # Save to CSV without excessive quoting
        updated_df.to_csv(csv_path, index=False, quoting=csv.QUOTE_MINIMAL)
        
        print(f"\n[SUCCESS] Updated {successful_updates}/{total_products} products")
        if failed_updates > 0:
            print(f"[WARNING] {failed_updates} products failed to update")
        
        print("[SUCCESS] Holt's Cigars price update completed")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to save CSV: {e}")
        print("[FAILED] Holt's Cigars price update failed")
        return False

def main():
    """Main entry point"""
    try:
        success = update_holts_prices()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n[INFO] Update interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
