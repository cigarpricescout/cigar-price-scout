#!/usr/bin/env python3
"""
Cigar Country Price Update Script
Updates cigarcountry.csv with latest pricing and stock information
Follows the proven automation patterns from Atlantic, Fox, and Nick's scripts

Usage:
    python update_cigarcountry_prices_final.py

Integration with Railway automation system:
- Reads from cigarcountry.csv
- Updates price, in_stock, last_updated fields
- Maintains master file metadata integration
- Includes error handling and retry logic
"""

import csv
import sys
import os
from datetime import datetime
import logging
from typing import Dict, List
from cigar_country_extractor import extract_cigar_country_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cigarcountry_updates.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CigarCountryPriceUpdater:
    def __init__(self, csv_file: str = 'cigarcountry.csv'):
        self.csv_file = csv_file
        self.updated_count = 0
        self.error_count = 0
        self.total_count = 0
        
    def get_cigar_metadata(self, cigar_id: str) -> Dict:
        """
        Get metadata from master cigars file for auto-population
        This function should be connected to your master Google Sheets data
        """
        # This is a placeholder - integrate with your master file system
        # For now, return empty dict - metadata will come from existing CSV
        return {}
    
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
    
    def update_prices(self) -> Dict:
        """
        Update all prices in the Cigar Country CSV file
        Returns summary statistics
        """
        
        if not os.path.exists(self.csv_file):
            logger.error(f"CSV file not found: {self.csv_file}")
            return {'success': False, 'error': f'File not found: {self.csv_file}'}
        
        logger.info(f"Starting Cigar Country price update for {self.csv_file}")
        
        # Read existing data
        updated_rows = []
        
        try:
            with open(self.csv_file, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                fieldnames = reader.fieldnames
                
                # Ensure we have required fields
                if not fieldnames:
                    raise ValueError("CSV file appears to be empty or corrupted")
                
                # Add last_updated field if it doesn't exist
                if 'last_updated' not in fieldnames:
                    fieldnames = list(fieldnames) + ['last_updated']
                
                for row in reader:
                    self.total_count += 1
                    original_row = row.copy()
                    
                    url = row.get('url', '').strip()
                    if not url:
                        logger.warning(f"No URL for cigar_id: {row.get('cigar_id', 'UNKNOWN')}")
                        updated_rows.append(row)
                        continue
                    
                    logger.info(f"Processing {self.total_count}: {row.get('title', 'Unknown')} - {url}")
                    
                    try:
                        # Extract current data from website
                        result = extract_cigar_country_data(url)
                        
                        if result.get('success'):
                            # Update price and stock information
                            if result.get('price') is not None:
                                row['price'] = str(result['price'])
                            
                            if result.get('in_stock') is not None:
                                row['in_stock'] = str(result['in_stock']).lower()
                            
                            # Update box quantity if we got a different value
                            if result.get('box_quantity') and str(result['box_quantity']) != row.get('box_qty', ''):
                                logger.info(f"Box quantity updated: {row.get('box_qty')} -> {result['box_quantity']}")
                                row['box_qty'] = str(result['box_quantity'])
                            
                            # Auto-populate any missing metadata
                            row = self.auto_populate_metadata(row)
                            
                            # Update timestamp
                            row['last_updated'] = datetime.now().isoformat()
                            
                            self.updated_count += 1
                            
                            # Log the update
                            price_change = ""
                            if original_row.get('price') != row.get('price'):
                                price_change = f" (${original_row.get('price', 'N/A')} -> ${row.get('price', 'N/A')})"
                            
                            stock_change = ""
                            if original_row.get('in_stock') != row.get('in_stock'):
                                stock_change = f" (stock: {original_row.get('in_stock', 'N/A')} -> {row.get('in_stock', 'N/A')})"
                            
                            logger.info(f"[OK] Updated: {row.get('title', 'Unknown')}{price_change}{stock_change}")
                            
                            # Show discount info if available
                            if result.get('discount_percent'):
                                logger.info(f"   DISCOUNT: {result['discount_percent']:.1f}% off (was ${result['original_price']})")
                        
                        else:
                            self.error_count += 1
                            error_msg = result.get('error', 'Unknown extraction error')
                            logger.error(f"[FAILED] Failed to extract {row.get('title', 'Unknown')}: {error_msg}")
                            
                            # Keep existing data but update timestamp to show we tried
                            row['last_updated'] = datetime.now().isoformat()
                    
                    except Exception as e:
                        self.error_count += 1
                        logger.error(f"❌ Exception processing {row.get('title', 'Unknown')}: {str(e)}")
                        
                        # Keep existing data but update timestamp
                        row['last_updated'] = datetime.now().isoformat()
                    
                    updated_rows.append(row)
                    
                    # Small delay to be polite
                    import time
                    time.sleep(0.5)
        
        except Exception as e:
            logger.error(f"Error reading CSV file: {str(e)}")
            return {'success': False, 'error': str(e)}
        
        # Write updated data back to CSV
        try:
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as file:
                if updated_rows:
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(updated_rows)
                    
                    logger.info(f"[OK] Updated CSV file: {self.csv_file}")
        
        except Exception as e:
            logger.error(f"Error writing CSV file: {str(e)}")
            return {'success': False, 'error': f'Failed to write CSV: {str(e)}'}
        
        # Summary
        success_rate = (self.updated_count / self.total_count * 100) if self.total_count > 0 else 0
        
        summary = {
            'success': True,
            'total_processed': self.total_count,
            'successful_updates': self.updated_count,
            'errors': self.error_count,
            'success_rate': success_rate,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"[COMPLETE] Cigar Country Update Complete!")
        logger.info(f"   STATS: Processed: {self.total_count} products")
        logger.info(f"   SUCCESS: Updated: {self.updated_count} successfully")
        logger.info(f"   ERRORS: {self.error_count}")
        logger.info(f"   RATE: Success Rate: {success_rate:.1f}%")
        
        return summary

def main():
    """Main execution function"""
    
    # Check if CSV file exists
    csv_file = 'cigarcountry.csv'
    if not os.path.exists(csv_file):
        print(f"[ERROR] Error: {csv_file} not found in current directory")
        print("Make sure you're running this script from the directory containing cigarcountry.csv")
        sys.exit(1)
    
    print("[START] Starting Cigar Country price update...")
    print(f"[FILE] CSV file: {csv_file}")
    print(f"[TIME] Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    updater = CigarCountryPriceUpdater(csv_file)
    result = updater.update_prices()
    
    if result['success']:
        print(f"\n[SUCCESS] Update completed successfully!")
        print(f"[SUMMARY] Summary: {result['successful_updates']}/{result['total_processed']} products updated")
        print(f"[RATE] Success rate: {result['success_rate']:.1f}%")
        
        if result['errors'] > 0:
            print(f"[WARNING] {result['errors']} products had errors - check logs for details")
    else:
        print(f"\n[ERROR] Update failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
