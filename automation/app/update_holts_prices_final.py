#!/usr/bin/env python3
"""
Holt's Cigars Enhanced Price Updater with Master-Driven Metadata Sync
ALWAYS syncs ALL metadata from master_cigars.csv (master is authority source)
Enhanced version: metadata changes in master file auto-propagate to retailer CSV
Following the proven master-sync pattern for true data consistency
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

try:
    from tools.price_monitoring.retailers.holts_cigars_extractor import extract_holts_cigar_data
except ImportError:
    try:
        sys.path.append(os.path.join(project_root, 'tools', 'price_monitoring', 'retailers'))
        from holts_cigars_extractor import extract_holts_cigar_data
    except ImportError:
        print("[ERROR] Could not import extract_holts_cigar_data. Make sure the extractor is in tools/price_monitoring/retailers/")
        sys.exit(1)

def load_master_data():
    """Load the master cigar database for matching and metadata sync"""
    try:
        master_path = os.path.join(project_root, 'data', 'master_cigars.csv')
        if not os.path.exists(master_path):
            master_path = os.path.join(project_root, 'static', 'data', 'master_cigars.csv')
        
        master_df = pd.read_csv(master_path)
        print(f"[INFO] Loaded master file with {len(master_df)} total cigars")
        
        # Handle duplicate cigar_id values by keeping the first occurrence
        if master_df['cigar_id'].duplicated().any():
            print(f"[INFO] Found {master_df['cigar_id'].duplicated().sum()} duplicate cigar_id values, keeping first occurrence")
            master_df = master_df.drop_duplicates(subset=['cigar_id'], keep='first')
            print(f"[INFO] After deduplication: {len(master_df)} unique cigars")
        
        # Create lookup for metadata sync
        master_lookup = master_df.set_index('cigar_id').to_dict('index')
        return master_df, master_lookup
    except Exception as e:
        print(f"[ERROR] Failed to load master data: {e}")
        return None, None

def sync_metadata_from_master(row_dict, master_lookup):
    """ALWAYS sync metadata from master file (master is authority source)"""
    cigar_id = row_dict.get('cigar_id', '')
    if not cigar_id or cigar_id not in master_lookup:
        return row_dict
    
    master_data = master_lookup[cigar_id]
    metadata_changes = []
    
    # Field mapping from master to row
    field_mapping = {
        'title': 'product_name',
        'brand': 'Brand',
        'line': 'Line', 
        'wrapper': 'Wrapper',
        'vitola': 'Vitola',
        'size': lambda data: f"{data.get('Length', '')}x{data.get('Ring Gauge', '')}" if pd.notna(data.get('Length')) and pd.notna(data.get('Ring Gauge')) else '',
        'box_qty': 'Box Quantity'
    }
    
    # ALWAYS override with master data
    for row_field, master_field in field_mapping.items():
        if callable(master_field):
            new_value = master_field(master_data)
        else:
            new_value = master_data.get(master_field, '')
        
        if new_value and str(new_value) != 'nan':
            old_value = row_dict.get(row_field, '')
            if str(old_value) != str(new_value):
                metadata_changes.append(f"{row_field}: '{old_value}' -> '{new_value}'")
            row_dict[row_field] = new_value
    
    # Log metadata sync changes
    if metadata_changes:
        print(f"  [MASTER SYNC] Updated metadata: {', '.join(metadata_changes)}")
    
    return row_dict

def update_holts_prices(dry_run=False):
    """Enhanced Holt's pricing update with master-driven metadata sync"""
    mode_str = "[DRY RUN] " if dry_run else ""
    print("=" * 70)
    print(f"{mode_str}HOLT'S CIGARS ENHANCED PRICE UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("MASTER-DRIVEN METADATA SYNC: All metadata always synced from master file")
    print("=" * 70)
    
    # Load master data
    master_df, master_lookup = load_master_data()
    if master_df is None:
        return False
    
    # Load Holt's CSV
    csv_path = os.path.join(project_root, 'data', 'holts.csv')
    if not os.path.exists(csv_path):
        csv_path = os.path.join(project_root, 'static', 'data', 'holts.csv')
        
    try:
        holts_df = pd.read_csv(csv_path)
        print(f"[INFO] Loaded {len(holts_df)} products from Holt's CSV")
    except Exception as e:
        print(f"[ERROR] Failed to load Holt's CSV: {e}")
        return False
    
    # Create backup (skip in dry run)
    if not dry_run:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = csv_path.replace('.csv', f'_backup_{timestamp}.csv')
            import shutil
            shutil.copy2(csv_path, backup_path)
            print(f"[INFO] Backup created: {backup_path}")
        except Exception as e:
            print(f"[WARNING] Could not create backup: {e}")
    
    # Process each product
    successful_updates = 0
    failed_updates = 0
    metadata_sync_count = 0
    updated_rows = []
    
    for index, row in holts_df.iterrows():
        product_num = index + 1
        cigar_id = row['cigar_id']
        url = row['url']
        
        print(f"\n[{product_num}/{len(holts_df)}] Processing: {cigar_id}")
        
        # Convert to dict for easier manipulation
        row_dict = row.to_dict()
        
        # ALWAYS sync metadata from master file
        original_row = row_dict.copy()
        row_dict = sync_metadata_from_master(row_dict, master_lookup)
        
        # Check if metadata was updated
        metadata_updated = any(original_row.get(field) != row_dict.get(field) 
                             for field in ['title', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty'])
        if metadata_updated:
            metadata_sync_count += 1
        
        # Skip pricing extraction in dry run mode
        if dry_run:
            print("  [DRY RUN] Skipping price extraction")
            successful_updates += 1
            updated_rows.append(row_dict)
            continue
        
        # Extract pricing data
        try:
            pricing_data = extract_holts_cigar_data(url, cigar_id)
            
            if pricing_data.get('error'):
                print(f"  [ERROR] {pricing_data['error']}")
                failed_updates += 1
            else:
                # Update pricing
                if pricing_data.get('price') is not None:
                    row_dict['price'] = pricing_data['price']
                if pricing_data.get('in_stock') is not None:
                    row_dict['in_stock'] = pricing_data['in_stock']
                
                price_str = f"${pricing_data.get('price', 'N/A')}"
                stock_str = "In Stock" if pricing_data.get('in_stock') else "Out of Stock"
                print(f"  [OK] {price_str} | {stock_str}")
                successful_updates += 1
                
        except Exception as e:
            print(f"  [ERROR] Failed to process: {str(e)}")
            failed_updates += 1
        
        updated_rows.append(row_dict)
    
    # Save updated CSV (skip in dry run)
    if not dry_run:
        try:
            updated_df = pd.DataFrame(updated_rows)
            updated_df.to_csv(csv_path, index=False, quoting=csv.QUOTE_MINIMAL)
            print(f"\n[SUCCESS] Updated {successful_updates}/{len(holts_df)} products")
        except Exception as e:
            print(f"[ERROR] Failed to save CSV: {e}")
            return False
    
    print("\n" + "=" * 70)
    print(f"{mode_str}UPDATE COMPLETE")
    print(f"Successful updates: {successful_updates}")
    print(f"Failed updates: {failed_updates}")
    print(f"Metadata synced: {metadata_sync_count} products")
    print("=" * 70)
    return True

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Holt\'s Cigars price updater with master-driven metadata sync')
    parser.add_argument('--dry-run', action='store_true', help='Show what metadata would be updated without making changes')
    parser.add_argument('--test', action='store_true', help='Deprecated: Use --dry-run instead')
    
    args = parser.parse_args()
    dry_run = args.dry_run or args.test
    
    if dry_run:
        print("[DRY RUN MODE] Showing metadata changes without updating files")
    
    try:
        success = update_holts_prices(dry_run=dry_run)
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
