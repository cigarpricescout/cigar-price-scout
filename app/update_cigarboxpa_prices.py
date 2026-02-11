#!/usr/bin/env python3
"""
CigarBoxPA Price Updater
Updates pricing data for CigarBoxPA products using master-driven metadata sync approach

Usage:
    python update_cigarboxpa_prices.py [--dry-run]
    
Arguments:
    --dry-run    Show changes without updating files
"""

import sys
import os
import csv
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
import time

# Add the tools directory to Python path for imports
current_dir = Path(__file__).parent
project_root = current_dir.parent
tools_dir = project_root / "tools" / "price_monitoring"
sys.path.insert(0, str(tools_dir))

try:
    from retailers.cigarboxpa_extractor import extract_cigarboxpa_data
except ImportError as e:
    print(f"Error importing CigarBoxPA extractor: {e}")
    print("Make sure cigarboxpa_extractor.py is in tools/price_monitoring/retailers/")
    sys.exit(1)

class CigarBoxPAPriceUpdater:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.project_root = project_root
        self.csv_path = self.project_root / "static" / "data" / "cigarboxpa.csv"
        self.master_csv_path = self.project_root / "data" / "master_cigars.csv"
        
        # Ensure directories exist
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Master data
        self.master_df = None
        
        # Stats tracking
        self.stats = {
            'total_products': 0,
            'successful_updates': 0,
            'failed_extractions': 0,
            'price_changes': 0,
            'stock_changes': 0,
            'metadata_syncs': 0,
            'errors': []
        }
    
    def load_master_file(self):
        """Load the master cigars file for metadata sync"""
        try:
            if not self.master_csv_path.exists():
                print(f"Warning: Master file not found at {self.master_csv_path}")
                return False
                
            self.master_df = pd.read_csv(self.master_csv_path)
            
            # Convert Box Quantity to numeric
            self.master_df['Box Quantity'] = pd.to_numeric(self.master_df['Box Quantity'], errors='coerce').fillna(0)
            
            print(f"Loaded master file with {len(self.master_df)} total cigars")
            return True
            
        except Exception as e:
            print(f"Error loading master file: {e}")
            return False
    
    def get_cigar_metadata(self, cigar_id):
        """Get metadata for a cigar from the master file"""
        if self.master_df is None:
            return {}
        
        # Handle both 'cigar_id' and 'Cigar_ID' column names
        id_column = 'Cigar_ID' if 'Cigar_ID' in self.master_df.columns else 'cigar_id'
        matching_rows = self.master_df[self.master_df[id_column] == cigar_id]
        
        if len(matching_rows) == 0:
            print(f"  Warning: No metadata found for cigar_id: {cigar_id}")
            return {}
        
        if len(matching_rows) > 1:
            print(f"  Warning: Multiple matches found for cigar_id: {cigar_id}, using first match")
        
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
            'title': row.get('product_name', '') or row.get('Product_Name', ''),
            'brand': row.get('Brand', ''), 
            'line': row.get('Line', ''),
            'wrapper': row.get('Wrapper', ''),
            'vitola': row.get('Vitola', ''),
            'size': size,
            'box_qty': box_qty
        }
    
    def sync_with_master(self, row_data):
        """ALWAYS sync metadata from master file (master is authority source)"""
        cigar_id = row_data.get('cigar_id', '').strip()
        if not cigar_id:
            return row_data
        
        metadata = self.get_cigar_metadata(cigar_id)
        if not metadata:
            return row_data
        
        # Track metadata changes for logging
        metadata_changes = []
        for field in ['title', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty']:
            if field in metadata and metadata[field]:
                old_value = str(row_data.get(field, ''))
                new_value = str(metadata[field])
                
                # Track changes for logging
                if old_value != new_value:
                    metadata_changes.append(f"{field}: '{old_value}' -> '{new_value}'")
                
                # Always update from master (master is authority)
                row_data[field] = new_value
        
        # Log metadata sync changes
        if metadata_changes:
            print(f"  MASTER SYNC: {', '.join(metadata_changes)}")
            self.stats['metadata_syncs'] += 1
        
        return row_data
    
    def extract_product_data(self, url):
        """Extract product data from CigarBoxPA URL with error handling"""
        try:
            print(f"  Extracting: {url}")
            result = extract_cigarboxpa_data(url)
            
            if result['success']:
                return {
                    'price': result['price'],
                    'box_qty': result['box_quantity'], 
                    'in_stock': result['in_stock'],
                    'discount_percent': result.get('discount_percent'),
                    'error': None
                }
            else:
                return {
                    'price': None,
                    'box_qty': None,
                    'in_stock': False,
                    'discount_percent': None,
                    'error': result.get('error', 'Unknown extraction error')
                }
                
        except Exception as e:
            return {
                'price': None,
                'box_qty': None,
                'in_stock': False,
                'discount_percent': None,
                'error': str(e)
            }
    
    def update_prices(self):
        """Main update process using master-driven metadata sync"""
        mode_str = "[DRY RUN] " if self.dry_run else ""
        print("=== CigarBoxPA Enhanced Price Update Process ===")
        print(f"{mode_str}MASTER-DRIVEN METADATA SYNC: All metadata always synced from master file")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # Load master file first
        if not self.load_master_file():
            print("Warning: Continuing without master file - metadata sync disabled")
        
        # Load current data
        current_data = self.load_current_data()
        
        if not current_data:
            print("No products to update")
            return
        
        updated_data = []
        
        for url, row in current_data.items():
            self.stats['total_products'] += 1
            
            print(f"\nProcessing: {row.get('title', 'Unknown Product')}")
            
            # ALWAYS sync with master first (master is authority source)
            row = self.sync_with_master(row)
            
            # Extract current pricing data
            extracted = self.extract_product_data(url)
            
            if extracted['error']:
                print(f"  ERROR: Extraction failed: {extracted['error']}")
                self.stats['failed_extractions'] += 1
                self.stats['errors'].append(f"{url}: {extracted['error']}")
                
                # Keep existing data when extraction fails, but with master metadata
                updated_row = row.copy()
            else:
                print(f"  SUCCESS: Extraction successful")
                self.stats['successful_updates'] += 1
                
                # Create updated row with new data
                updated_row = row.copy()
                
                # Update pricing data
                old_price = float(row.get('price', 0)) if row.get('price') else None
                new_price = extracted['price']
                
                if new_price is not None:
                    updated_row['price'] = new_price
                    
                    if old_price and old_price != new_price:
                        print(f"  PRICE CHANGE: ${old_price} -> ${new_price}")
                        self.stats['price_changes'] += 1
                
                # Update stock status
                old_stock = str(row.get('in_stock', '')).lower() == 'true'
                new_stock = extracted['in_stock']
                
                updated_row['in_stock'] = new_stock
                
                if old_stock != new_stock:
                    status = "In Stock" if new_stock else "Out of Stock"
                    print(f"  STOCK CHANGE: {status}")
                    self.stats['stock_changes'] += 1
                
                # Update box quantity if extracted (but master takes precedence)
                if extracted['box_qty'] and not updated_row.get('box_qty'):
                    updated_row['box_qty'] = extracted['box_qty']
            
            # Clear promotions field (will be updated if active promotions detected)
            updated_row['current_promotions_applied'] = ''
            
            updated_data.append(updated_row)
            
            # Rate limiting - 1 request per second
            time.sleep(1)
        
        # Save updated data
        if not self.dry_run:
            self.save_updated_data(updated_data)
        else:
            print("\nDRY RUN - No files updated")
        
        self.print_summary()
    
    def load_current_data(self):
        """Load current CigarBoxPA CSV data"""
        current_data = {}
        
        if not self.csv_path.exists():
            print(f"CSV file not found at {self.csv_path}")
            return current_data
        
        try:
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get('url', '').strip()
                    if url:
                        current_data[url] = row
            
            print(f"Loaded {len(current_data)} existing CigarBoxPA products")
            
        except Exception as e:
            print(f"Error loading current data: {e}")
        
        return current_data
    
    def save_updated_data(self, updated_data):
        """Save updated data to CSV with backup"""
        try:
            # Backup disabled - historical prices tracked in historical_prices.db
            
            # Write updated data
            fieldnames = [
                'cigar_id', 'title', 'url', 'brand', 'line', 'wrapper', 
                'vitola', 'size', 'box_qty', 'price', 'in_stock', 
                'current_promotions_applied'
            ]
            
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(updated_data)
            
            print(f"Updated data saved to {self.csv_path}")
            
        except Exception as e:
            print(f"ERROR: Error saving data: {e}")
            self.stats['errors'].append(f"Save error: {e}")
    
    def print_summary(self):
        """Print update summary statistics"""
        print("\n" + "="*50)
        print("UPDATE SUMMARY")
        print("="*50)
        print(f"Total products processed: {self.stats['total_products']}")
        print(f"Successful extractions: {self.stats['successful_updates']}")
        print(f"Failed extractions: {self.stats['failed_extractions']}")
        print(f"Price changes: {self.stats['price_changes']}")
        print(f"Stock changes: {self.stats['stock_changes']}")
        print(f"Metadata syncs: {self.stats['metadata_syncs']}")
        
        if self.stats['errors']:
            print(f"\nErrors ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:5]:  # Show first 5 errors
                print(f"  • {error}")
            if len(self.stats['errors']) > 5:
                print(f"  • ... and {len(self.stats['errors']) - 5} more")
        
        success_rate = (self.stats['successful_updates'] / self.stats['total_products'] * 100) if self.stats['total_products'] > 0 else 0
        print(f"\nSuccess rate: {success_rate:.1f}%")
        print(f"Master-driven metadata sync: {'Active' if self.master_df is not None else 'Disabled'}")
        print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    parser = argparse.ArgumentParser(description='Update CigarBoxPA pricing data')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show changes without updating files')
    
    args = parser.parse_args()
    
    updater = CigarBoxPAPriceUpdater(dry_run=args.dry_run)
    updater.update_prices()


if __name__ == "__main__":
    main()
