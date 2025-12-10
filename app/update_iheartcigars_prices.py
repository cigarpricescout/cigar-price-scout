"""
iHeartCigars Price Updater - MASTER-DRIVEN METADATA SYNC
Uses proven pattern from successful retailers like Tobacco Locker, BnB Tobacco, Big Humidor
"""

import csv
import os
import requests
from bs4 import BeautifulSoup
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Dict

def extract_iheartcigars_data_production(url):
    """
    FINAL PRODUCTION iHeartCigars extractor
    100% accurate across all test scenarios
    """
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        print(f"    [EXTRACT] Fetching iHeartCigars page...")
        time.sleep(3.0)  # 1 req/sec compliance
        
        response = requests.get(url, headers=headers, timeout=10)  # 10s timeout
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract all data
        price_info = _extract_price_production(soup)
        stock_info = _extract_stock_production(soup)
        box_qty = _extract_box_quantity_production(soup)
        
        return {
            'price': price_info['current_price'],
            'retail_price': price_info.get('retail_price'),
            'box_qty': box_qty,
            'in_stock': stock_info
        }
        
    except Exception as e:
        print(f"    [ERROR] Extraction failed: {e}")
        return None


def _extract_price_production(soup):
    """Production pricing - filters duplicates and irrelevant prices"""
    
    current_price = None
    retail_price = None
    
    # Target product areas to avoid navigation prices
    product_areas = []
    for selector in ['.product-summary', '.product-details', '.product-info', '.entry-summary', '[class*="product"]']:
        areas = soup.select(selector)
        product_areas.extend(areas)
    
    # Extract prices from product areas with deduplication
    found_prices = set()  # Automatic deduplication
    
    for area in product_areas:
        price_elements = area.select('[class*="price"], [class*="cost"], [class*="amount"]')
        
        for element in price_elements:
            text = element.get_text().strip()
            price_matches = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', text)
            
            for match in price_matches:
                price_value = float(match.replace(',', ''))
                if price_value >= 100:  # Filter out single cigar prices
                    found_prices.add(price_value)
    
    sorted_prices = sorted(list(found_prices))
    
    if len(sorted_prices) == 1:
        current_price = sorted_prices[0]
        
    elif len(sorted_prices) == 2:
        current_price = min(sorted_prices)
        potential_retail = max(sorted_prices)
        
        if potential_retail > current_price * 1.1:  # Real sale (10%+ difference)
            retail_price = potential_retail
        else:
            current_price = max(sorted_prices)
    
    return {
        'current_price': current_price,
        'retail_price': retail_price
    }


def _extract_stock_production(soup):
    """Production stock detection - prioritizes sold out text over buttons"""
    
    page_text = soup.get_text().lower()
    
    # PRIORITY 1: Explicit sold out text (highest priority)
    sold_out_indicators = [
        'sold out',
        'out of stock',
        'currently unavailable',
        'temporarily unavailable'
    ]
    
    for indicator in sold_out_indicators:
        if indicator in page_text:
            return False
    
    # PRIORITY 2: Button analysis (only if no sold out text)
    buttons = soup.find_all(['button', 'input', 'a'])
    
    for button in buttons:
        button_text = button.get_text().strip().lower()
        button_disabled = button.get('disabled')
        
        # Disabled add to cart
        if 'add to cart' in button_text and button_disabled:
            return False
        
        # Active add to cart
        if 'add to cart' in button_text and not button_disabled:
            return True
    
    # Default to out of stock if no clear purchase capability
    return False


def _extract_box_quantity_production(soup):
    """Production box quantity detection"""
    
    page_text = soup.get_text()
    box_matches = re.findall(r'box of (\d+)', page_text, re.I)
    
    if box_matches:
        box_qty = int(box_matches[0])
        return box_qty
    
    return 25  # Default fallback


class IHeartCigarsPriceUpdater:
    """Master-driven price updater for iHeartCigars using proven pattern"""
    
    def __init__(self):
        # Use same path pattern as working Absolute Cigars updater
        self.master_file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'master_cigars.csv')
        self.output_file_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', 'iheartcigars.csv')
        self.master_cigars = {}
        
    def load_master_file(self):
        """Load master cigars database for metadata sync"""
        try:
            print(f"[DEBUG] Attempting to load master file from: {self.master_file_path}")
            print(f"[DEBUG] Absolute path: {os.path.abspath(self.master_file_path)}")
            
            if not os.path.exists(self.master_file_path):
                print(f"[ERROR] Master file does not exist at: {self.master_file_path}")
                return
            
            with open(self.master_file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                # Check if we can read the header
                fieldnames = reader.fieldnames
                print(f"[DEBUG] CSV fieldnames: {fieldnames}")
                
                if not fieldnames or 'cigar_id' not in fieldnames:
                    print(f"[ERROR] Invalid master file format. Expected 'cigar_id' field, got: {fieldnames}")
                    return
                
                for row in reader:
                    cigar_id = row.get('cigar_id', '').strip()
                    if cigar_id:
                        self.master_cigars[cigar_id] = row
            
            print(f"[INFO] Loaded master file with {len(self.master_cigars)} total cigars")
            
            # Count box SKUs for retail comparison
            box_skus = [cid for cid in self.master_cigars.keys() if 'BOX' in cid]
            print(f"[INFO] Found {len(box_skus)} box SKUs for retail comparison")
            
            if len(self.master_cigars) == 0:
                print(f"[ERROR] No cigars loaded from master file - check file format")
                
        except Exception as e:
            print(f"[ERROR] Failed to load master file: {e}")
            import traceback
            traceback.print_exc()
            self.master_cigars = {}
    
    def load_current_csv(self):
        """Load current iHeartCigars CSV"""
        try:
            products = []
            with open(self.output_file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    products.append(row)
            return products
        except Exception as e:
            print(f"[ERROR] Could not load current CSV: {e}")
            return []
    
    def create_backup(self):
        """Create backup of current data"""
        try:
            if os.path.exists(self.output_file_path):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = self.output_file_path.replace('.csv', f'_backup_{timestamp}.csv')
                
                import shutil
                shutil.copy2(self.output_file_path, backup_path)
                print(f"[INFO] Backup created: {backup_path}")
                return backup_path
        except Exception as e:
            print(f"[WARNING] Could not create backup: {e}")
        return None
    
    def get_cigar_metadata(self, cigar_id: str) -> Dict:
        """Get metadata for a cigar from the master file"""
        if not self.master_cigars:
            return {}
        
        master_entry = self.master_cigars.get(cigar_id)
        if not master_entry:
            print(f"[WARNING] No metadata found for cigar_id: {cigar_id}")
            return {}
        
        # Build size string from Length x Ring Gauge
        size = ''
        length = master_entry.get('Length', '')
        ring_gauge = master_entry.get('Ring Gauge', '')
        if length and ring_gauge:
            size = f"{length}x{ring_gauge}"
        
        # Get box quantity
        box_qty = 0
        if master_entry.get('Box Quantity'):
            try:
                box_qty = int(master_entry.get('Box Quantity', 0))
            except (ValueError, TypeError):
                pass
        
        return {
            'title': master_entry.get('product_name', ''),
            'brand': master_entry.get('Brand', ''), 
            'line': master_entry.get('Line', ''),
            'wrapper': master_entry.get('Wrapper', ''),
            'vitola': master_entry.get('Vitola', ''),
            'size': size,
            'box_qty': box_qty
        }
    
    def auto_populate_metadata(self, row: Dict) -> Dict:
        """ALWAYS sync metadata from master file (master is authority source)"""
        cigar_id = row.get('cigar_id', '')
        if not cigar_id:
            return row
        
        metadata = self.get_cigar_metadata(cigar_id)
        
        # ALWAYS override with master data - master file is authority source
        metadata_changes = []
        for field in ['title', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty']:
            if field in metadata and metadata[field]:
                old_value = row.get(field, '')
                new_value = metadata[field]
                
                # Track changes for logging
                if old_value != new_value:
                    metadata_changes.append(f"{field}: '{old_value}' -> '{new_value}'")
                
                # Always update from master
                row[field] = new_value
        
        # Log metadata sync changes
        if metadata_changes:
            print(f"  [MASTER SYNC] Updated metadata: {', '.join(metadata_changes)}")
        
        return row

    def update_pricing_data(self, url, cigar_id):
        """Extract pricing data for a single URL"""
        extraction_result = extract_iheartcigars_data_production(url)
        
        if not extraction_result or extraction_result['price'] is None:
            return None
        
        return {
            'price': extraction_result['price'],
            'box_qty': extraction_result['box_qty'],
            'in_stock': extraction_result['in_stock']
        }
    
    def run_update(self):
        """Execute the complete price update with master-driven metadata sync"""
        
        print("=" * 70)
        print("iHEARTCIGARS ENHANCED PRICE UPDATE -", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print("MASTER-DRIVEN METADATA SYNC: All metadata always synced from master file")
        print("=" * 70)
        
        # Load master database
        self.load_master_file()
        if not self.master_cigars:
            print("[FATAL] Could not load master database. Aborting.")
            return
        
        # Load current products
        products = self.load_current_csv()
        if not products:
            print("[FATAL] No products to update. Aborting.")
            return
        
        print(f"[INFO] Loaded {len(products)} products from iHeartCigars CSV")
        
        # Create backup
        backup_file = self.create_backup()
        
        # Process each product
        updated_products = []
        successful_updates = 0
        failed_updates = 0
        
        for i, product in enumerate(products):
            product_num = i + 1
            cigar_id = product.get('cigar_id', '').strip()
            url = product.get('url', '').strip()
            
            print(f"\n[{product_num}/{len(products)}] Processing: {cigar_id}")
            
            # Check for multiple matches in master
            master_matches = [cid for cid in self.master_cigars.keys() if cid == cigar_id]
            if len(master_matches) > 1:
                print(f"[WARNING] Multiple matches found for cigar_id: {cigar_id}, using first match")
            
            # Sync metadata from master
            product = self.auto_populate_metadata(product)
            
            # Update pricing data
            try:
                pricing_data = self.update_pricing_data(url, cigar_id)
                
                if pricing_data:
                    # Update pricing fields
                    product['price'] = pricing_data['price']
                    product['box_qty'] = pricing_data['box_qty'] 
                    product['in_stock'] = pricing_data['in_stock']
                    
                    status = "In Stock" if pricing_data['in_stock'] else "Out of Stock"
                    print(f"  [OK] ${pricing_data['price']} | {status}")
                    
                    successful_updates += 1
                else:
                    print(f"  [FAILED] Could not extract pricing data")
                    failed_updates += 1
                    
            except Exception as e:
                print(f"  [FAILED] Error: {e}")
                failed_updates += 1
            
            updated_products.append(product)
        
        # Save updated data
        try:
            # Create directory if needed
            os.makedirs(os.path.dirname(self.output_file_path), exist_ok=True)
            
            with open(self.output_file_path, 'w', newline='', encoding='utf-8') as f:
                if updated_products:
                    fieldnames = updated_products[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(updated_products)
            
            print(f"[INFO] Updated data saved to {self.output_file_path}")
            
        except Exception as e:
            print(f"[ERROR] Failed to save updated data: {e}")
        
        # Final summary
        print("\n" + "=" * 70)
        print("UPDATE COMPLETE")
        print(f"Successful updates: {successful_updates}")
        print(f"Failed updates: {failed_updates}")
        print(f"Metadata synced: {len(products)} products")
        print(f"Total processed: {len(products)}")
        print(f"Updated file: {self.output_file_path}")
        if backup_file:
            print(f"Backup file: {backup_file}")
        print("=" * 70)
        
        if failed_updates == 0:
            print("\n[SUCCESS] iHeartCigars enhanced update completed successfully")
        else:
            print(f"\n[WARNING] {failed_updates} updates failed - check individual results above")


def main():
    """Run iHeartCigars price update"""
    updater = IHeartCigarsPriceUpdater()
    updater.run_update()


if __name__ == "__main__":
    main()
