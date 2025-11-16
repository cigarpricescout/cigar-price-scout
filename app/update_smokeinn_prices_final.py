#!/usr/bin/env python3
"""
Smoke Inn Price Updater
Updates pricing data for Smoke Inn products using the smokeinn_extractor
Handles single-product pages with retail vs sale pricing
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
print(f"[DEBUG] Looking for extractor at: {os.path.join(project_root, 'tools', 'price_monitoring', 'retailers', 'smokeinn_extractor.py')}")

try:
    from tools.price_monitoring.retailers.smokeinn_extractor import extract_smokeinn_cigar_data
except ImportError:
    # Alternative import path if structure is different
    try:
        sys.path.append(os.path.join(project_root, 'tools', 'price_monitoring', 'retailers'))
        from smokeinn_extractor import extract_smokeinn_cigar_data
    except ImportError:
        print("[ERROR] Could not import extract_smokeinn_cigar_data. Make sure the extractor is in tools/price_monitoring/retailers/")
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

def load_smokeinn_csv():
    """Load existing Smoke Inn CSV data"""
    try:
        # Try the correct path first (data directory)
        csv_path = os.path.join(project_root, 'data', 'smokeinn.csv')
        
        # Fallback to static/data if that doesn't exist
        if not os.path.exists(csv_path):
            csv_path = os.path.join(project_root, 'static', 'data', 'smokeinn.csv')
            
        if not os.path.exists(csv_path):
            print(f"[ERROR] Smoke Inn CSV not found at: {csv_path}")
            print(f"[DEBUG] Checked paths:")
            print(f"  - {os.path.join(project_root, 'data', 'smokeinn.csv')}")
            print(f"  - {os.path.join(project_root, 'static', 'data', 'smokeinn.csv')}")
            return None
            
        df = pd.read_csv(csv_path)
        print(f"[INFO] Loaded {len(df)} products from Smoke Inn CSV")
        return df
    except Exception as e:
        print(f"[ERROR] Failed to load Smoke Inn CSV: {e}")
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

def update_smokeinn_prices():
    """Main function to update Smoke Inn pricing data"""
    print("=" * 70)
    print(f"SMOKE INN PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Load master data for validation
    master_df = load_master_data()
    if master_df is None:
        print("[FAILED] Smoke Inn price update failed")
        return False
    
    # Load Smoke Inn CSV
    smokeinn_df = load_smokeinn_csv()
    if smokeinn_df is None:
        print("[FAILED] Smoke Inn price update failed")
        return False
    
    # Create backup
    csv_path = os.path.join(project_root, 'data', 'smokeinn.csv')
    if not os.path.exists(csv_path):
        csv_path = os.path.join(project_root, 'static', 'data', 'smokeinn.csv')
    
    create_backup(csv_path)
    
    # Process each product
    total_products = len(smokeinn_df)
    successful_updates = 0
    failed_updates = 0
    
    updated_rows = []
    
    for index, row in smokeinn_df.iterrows():
        product_num = index + 1
        cigar_id = row.get('cigar_id', 'N/A') if pd.notna(row.get('cigar_id')) else 'N/A'
        url = row['url']
        
        print(f"[{product_num}/{total_products}] Processing: {cigar_id}")
        print(f"  [DEBUG] URL: {url}")
        
        try:
            # Extract pricing data using the single-product extractor
            pricing_data = extract_smokeinn_cigar_data(url)
            
            if pricing_data.get('error'):
                print(f"  [ERROR] {pricing_data['error']}")
                failed_updates += 1
                # Preserve original row completely
                original_dict = row.to_dict()
                updated_rows.append(original_dict)
                continue
            
            # Create updated row while preserving all original data
            updated_row = row.to_dict()  # Convert to dict first to preserve all columns
            
            # Update pricing data
            if pricing_data.get('price') is not None:
                updated_row['price'] = pricing_data['price']
            if pricing_data.get('in_stock') is not None:
                updated_row['in_stock'] = pricing_data['in_stock']
            if pricing_data.get('box_qty') is not None:
                updated_row['box_qty'] = pricing_data['box_qty']
            
            # Ensure cigar_id is preserved
            if 'cigar_id' not in updated_row or pd.isna(updated_row.get('cigar_id')):
                if cigar_id != 'N/A':
                    updated_row['cigar_id'] = cigar_id
                else:
                    print(f"  [WARNING] No cigar_id found for this product")
            
            print(f"  [DEBUG] Preserved CID: {updated_row.get('cigar_id', 'MISSING')}")
            
            # Populate metadata from CID if available and fields are empty
            if updated_row.get('cigar_id') and updated_row['cigar_id'] != 'N/A':
                cid_parts = updated_row['cigar_id'].split('|')
                if len(cid_parts) >= 8:
                    print(f"  [DEBUG] Parsing CID with {len(cid_parts)} parts")
                    
                    # Helper function to check if fields need population
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
                            'ASHTON': 'Ashton',
                            'DAVIDOFF': 'Davidoff',
                            'DIAMONDCROWN': 'Diamond Crown',
                            'DREWESTATE': 'Drew Estate'
                        }
                        return brand_mapping.get(brand_code, brand_code.title())
                    
                    # Helper function to format line names
                    def format_line_name(line_code):
                        line_mapping = {
                            'HEMINGWAY': 'Hemingway',
                            'EXCALIBUR': 'Excalibur', 
                            '1875': '1875',
                            '1964ANNIVERSARY': '1964 Anniversary',
                            'THOUSANDSERIES': 'Thousand Series',
                            'MAXIMUS': 'Maximus',
                            'HERRERAESTELI': 'Herrera Esteli',
                            'HERRERAESTELINORTENO': 'Herrera Esteli Norteno',
                            'NORTENO': 'Norteno'
                        }
                        return line_mapping.get(line_code, line_code.title())
                    
                    # Helper function to format wrapper names  
                    def format_wrapper_name(wrapper_code):
                        wrapper_mapping = {
                            'CAM': 'Cameroon',
                            'CT': 'Connecticut Shade',
                            'MAD': 'Maduro',
                            'ECU': 'Ecuadorian Connecticut',
                            'NAT': 'Natural',
                            'NIC': 'Nicaraguan'
                        }
                        return wrapper_mapping.get(wrapper_code, wrapper_code)
                    
                    if needs_population(updated_row.get('brand')):
                        updated_row['brand'] = format_brand_name(cid_parts[0])
                    if needs_population(updated_row.get('line')):
                        updated_row['line'] = format_line_name(cid_parts[2])  
                    if needs_population(updated_row.get('wrapper')):
                        updated_row['wrapper'] = format_wrapper_name(cid_parts[6])
                    if needs_population(updated_row.get('vitola')):
                        # Use the vitola name with proper capitalization and spacing
                        vitola_raw = cid_parts[3]
                        
                        # Handle specific multi-word vitolas
                        vitola_mapping = {
                            'BESTSELLER': 'Best Seller',
                            'LONSDALEDELUXE': 'Lonsdale Deluxe',
                            'DIPLOMATICO': 'Diplomatico',
                            'SIGNATURE': 'Signature',
                            'CLASSIC': 'Classic',
                            'CHURCHILL': 'Churchill',
                            'ROBUSTO': 'Robusto',
                            'TORO': 'Toro'
                        }
                        
                        vitola_name = vitola_mapping.get(vitola_raw, vitola_raw.title())
                        updated_row['vitola'] = vitola_name
                    if needs_population(updated_row.get('size')):
                        updated_row['size'] = cid_parts[5]
                    
                    # Generate title - use just the vitola name like other retailers
                    if needs_population(updated_row.get('title')):
                        updated_row['title'] = updated_row.get('vitola', 'Unknown')
                else:
                    print(f"  [WARNING] CID has insufficient parts: {len(cid_parts)}")
            else:
                print(f"  [WARNING] No valid CID for metadata population")
            
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
            updated_rows.append(updated_row)
            
        except Exception as e:
            print(f"  [ERROR] Failed to process: {str(e)}")
            failed_updates += 1
            # Preserve original row completely on error
            original_dict = row.to_dict()
            updated_rows.append(original_dict)
            continue
    
    # Save updated CSV
    try:
        updated_df = pd.DataFrame(updated_rows)
        
        print(f"[DEBUG] DataFrame columns: {list(updated_df.columns)}")
        print(f"[DEBUG] Sample cigar_id values: {updated_df['cigar_id'].head(3).tolist()}")
        
        # Ensure consistent column order (cigar_id MUST be first and preserved)
        expected_columns = ['cigar_id', 'title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
        
        # Add missing columns with None values (but preserve cigar_id!)
        for col in expected_columns:
            if col not in updated_df.columns:
                updated_df[col] = None
                print(f"[DEBUG] Added missing column: {col}")
        
        # Reorder columns but keep all data
        updated_df = updated_df[expected_columns]
        
        # Verify cigar_id column is preserved
        print(f"[DEBUG] Final cigar_id check: {updated_df['cigar_id'].head(3).tolist()}")
        
        # Save to CSV without excessive quoting
        updated_df.to_csv(csv_path, index=False, quoting=csv.QUOTE_MINIMAL)
        
        print(f"\n[SUCCESS] Updated {successful_updates}/{total_products} products")
        if failed_updates > 0:
            print(f"[WARNING] {failed_updates} products failed to update")
        
        print("[SUCCESS] Smoke Inn price update completed")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to save CSV: {e}")
        print("[FAILED] Smoke Inn price update failed")
        return False

def main():
    """Main entry point"""
    try:
        success = update_smokeinn_prices()
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
