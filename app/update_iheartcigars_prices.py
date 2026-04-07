"""
iHeartCigars Price Updater - MASTER-DRIVEN METADATA SYNC
Uses Shopify JSON API for reliable variant-level pricing.
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
from urllib.parse import urlparse


def _get_product_handle(url):
    """Extract the Shopify product handle from any iHeartCigars product URL."""
    path = urlparse(url).path
    match = re.search(r'/products/([^/?#]+)', path)
    return match.group(1) if match else None


def _extract_via_shopify_json(handle):
    """Primary extraction: Shopify product JSON API, targeting the Box variant."""
    json_url = f"https://iheartcigars.com/products/{handle}.json"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }

    resp = requests.get(json_url, headers=headers, timeout=10)
    resp.raise_for_status()
    product = resp.json().get('product', {})
    variants = product.get('variants', [])

    if not variants:
        return None

    box_variant = None
    for v in variants:
        title = (v.get('title') or '').lower()
        if 'box' in title:
            box_variant = v
            break

    if not box_variant:
        box_variant = variants[0]

    price = float(box_variant.get('price', 0))
    compare_at = box_variant.get('compare_at_price')
    retail_price = float(compare_at) if compare_at else None
    available = box_variant.get('available')

    box_qty = None
    title_text = (box_variant.get('title') or '')
    qty_match = re.search(r'(\d+)', title_text)
    if qty_match and 'box' in title_text.lower():
        box_qty = int(qty_match.group(1))

    if box_qty is None:
        body = product.get('body_html') or ''
        body_match = re.search(r'box of (\d+)', body, re.I)
        if body_match:
            box_qty = int(body_match.group(1))

    if box_qty is None:
        full_title = product.get('title') or ''
        title_match = re.search(r'box of (\d+)', full_title, re.I)
        if title_match:
            box_qty = int(title_match.group(1))

    in_stock = available if available is not None else True

    print(f"    [JSON] handle={handle} variant='{box_variant.get('title')}' "
          f"price=${price} retail=${retail_price} qty={box_qty} stock={in_stock}")

    return {
        'price': price if price > 0 else None,
        'retail_price': retail_price,
        'box_qty': box_qty or 25,
        'in_stock': in_stock,
    }


def _extract_via_html(url):
    """Fallback: scrape the rendered HTML page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, 'html.parser')

    current_price = None
    retail_price = None
    el = soup.select_one('.product-price-current')
    if el:
        m = re.search(r'\$([\d,]+(?:\.\d{2})?)', el.get_text())
        if m:
            current_price = float(m.group(1).replace(',', ''))
    el_list = soup.select_one('.product-price-list')
    if el_list:
        m = re.search(r'\$([\d,]+(?:\.\d{2})?)', el_list.get_text())
        if m:
            retail_price = float(m.group(1).replace(',', ''))

    page_text = soup.get_text().lower()
    in_stock = True
    for indicator in ['sold out', 'out of stock', 'currently unavailable']:
        if indicator in page_text:
            in_stock = False
            break

    box_qty = 25
    qty_matches = re.findall(r'box of (\d+)', soup.get_text(), re.I)
    if qty_matches:
        box_qty = int(qty_matches[0])

    print(f"    [HTML] price=${current_price} retail=${retail_price} qty={box_qty} stock={in_stock}")

    return {
        'price': current_price,
        'retail_price': retail_price,
        'box_qty': box_qty,
        'in_stock': in_stock,
    }


def extract_iheartcigars_data_production(url):
    """
    iHeartCigars extractor — Shopify JSON primary, HTML fallback.
    Always targets the 'Box' variant when multiple options exist.
    """
    time.sleep(3.0)

    handle = _get_product_handle(url)
    if not handle:
        print(f"    [ERROR] Could not parse product handle from URL: {url}")
        return None

    try:
        result = _extract_via_shopify_json(handle)
        if result and result['price']:
            return result
        print(f"    [WARN] JSON returned no price, falling back to HTML")
    except Exception as e:
        print(f"    [WARN] JSON failed ({e}), falling back to HTML")

    try:
        return _extract_via_html(url)
    except Exception as e:
        print(f"    [ERROR] HTML fallback also failed: {e}")
        return None


class IHeartCigarsPriceUpdater:
    """Master-driven price updater for iHeartCigars using proven pattern"""
    
    def __init__(self):
        # Use same path pattern as working Absolute Cigars updater
        self.master_file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'master_cigars.db')
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
        length = master_entry.get('length', '')
        ring_gauge = master_entry.get('ring_gauge', '')
        if length and ring_gauge:
            size = f"{length}x{ring_gauge}"
        
        # Get box quantity
        box_qty = 0
        if master_entry.get('box_quantity'):
            try:
                box_qty = int(master_entry.get('box_quantity', 0))
            except (ValueError, TypeError):
                pass
        
        return {
            'title': master_entry.get('product_name', ''),
            'brand': master_entry.get('brand', ''), 
            'line': master_entry.get('line', ''),
            'wrapper': master_entry.get('wrapper', ''),
            'vitola': master_entry.get('vitola', ''),
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
        
        # Backup disabled - historical prices tracked in historical_prices.db
        
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
