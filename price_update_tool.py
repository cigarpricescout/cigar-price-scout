# price_updater.py - Update specific cigar prices across retailers
import csv
from pathlib import Path
import re

class PriceUpdater:
    def __init__(self):
        self.data_dir = Path("static/data")
        self.updates_applied = []
        self.retailer_mapping = {
            # Common retailer name variations to CSV file mapping
            'famous': 'famous.csv',
            'famous smoke': 'famous.csv',
            'famous smoke shop': 'famous.csv',
            'ci': 'ci.csv',
            'cigars international': 'ci.csv',
            'jr': 'jr.csv', 
            'jr cigar': 'jr.csv',
            'neptune': 'neptune.csv',
            'neptune cigar': 'neptune.csv',
            'atlantic': 'atlantic.csv',
            'atlantic cigar': 'atlantic.csv',
            'thompson': 'thompson.csv',
            'thompson cigar': 'thompson.csv',
            'holts': 'holts.csv',
            'holt\'s': 'holts.csv',
            'corona': 'corona.csv',
            'corona cigar': 'corona.csv',
            'smokeinn': 'smokeinn.csv',
            'smoke inn': 'smokeinn.csv',
            'pipesandcigars': 'pipesandcigars.csv',
            'pipes and cigars': 'pipesandcigars.csv',
            'smallbatchcigar': 'smallbatchcigar.csv',
            'small batch': 'smallbatchcigar.csv',
            'small batch cigar': 'smallbatchcigar.csv',
            'bestcigar': 'bestcigar.csv',
            'best cigar': 'bestcigar.csv',
            'best cigar prices': 'bestcigar.csv',
            'mikescigars': 'mikescigars.csv',
            'mikes cigars': 'mikescigars.csv',
            'mike\'s cigars': 'mikescigars.csv',
            'niceashcigars': 'niceashcigars.csv',
            'nice ash': 'niceashcigars.csv',
            'nice ash cigars': 'niceashcigars.csv',
        }
    
    def normalize_retailer_name(self, retailer_name):
        """Convert retailer name to CSV filename"""
        normalized = retailer_name.lower().strip()
        
        # Check direct mapping first
        if normalized in self.retailer_mapping:
            return self.retailer_mapping[normalized]
        
        # Try partial matches
        for key, csv_file in self.retailer_mapping.items():
            if key in normalized or normalized in key:
                return csv_file
        
        # Fallback: try to construct filename
        clean_name = re.sub(r'[^a-z0-9]', '', normalized)
        return f"{clean_name}.csv"
    
    def find_matching_product(self, csv_file, brand, line, wrapper=None, vitola=None, size=None):
        """Find a product in the CSV that matches the criteria"""
        csv_path = self.data_dir / csv_file
        
        if not csv_path.exists():
            return None, f"CSV file not found: {csv_file}"
        
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
                for i, row in enumerate(rows):
                    # Check brand match
                    if not brand.lower() in row.get('brand', '').lower():
                        continue
                    
                    # Check line match
                    if not line.lower() in row.get('line', '').lower():
                        continue
                    
                    # Optional wrapper match
                    if wrapper and wrapper.lower() not in row.get('wrapper', '').lower():
                        continue
                    
                    # Optional vitola match
                    if vitola and vitola.lower() not in row.get('vitola', '').lower():
                        continue
                    
                    # Optional size match
                    if size and size.lower() not in row.get('size', '').lower():
                        continue
                    
                    return i, row
                
                return None, f"No matching product found in {csv_file}"
                
        except Exception as e:
            return None, f"Error reading {csv_file}: {e}"
    
    def update_price(self, retailer_name, brand, line, new_price, wrapper=None, vitola=None, size=None):
        """Update price for a specific cigar at a specific retailer"""
        
        # Get CSV filename
        csv_file = self.normalize_retailer_name(retailer_name)
        csv_path = self.data_dir / csv_file
        
        print(f"Updating {retailer_name} -> {csv_file}")
        print(f"  Looking for: {brand} {line}", end="")
        if wrapper: print(f" {wrapper}", end="")
        if vitola: print(f" {vitola}", end="")
        if size: print(f" {size}", end="")
        print(f" -> ${new_price}")
        
        # Find the matching product
        row_index, result = self.find_matching_product(csv_file, brand, line, wrapper, vitola, size)
        
        if row_index is None:
            print(f"  ERROR: {result}")
            return False
        
        # Read all rows
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                all_rows = list(reader)
            
            # Create backup
            backup_path = str(csv_path) + '.backup_price_update'
            with open(backup_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(all_rows)
            
            # Update the price
            old_price = all_rows[row_index].get('price', 'N/A')
            all_rows[row_index]['price'] = str(new_price)
            
            # Write back the updated data
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(all_rows)
            
            update_info = {
                'retailer': retailer_name,
                'csv_file': csv_file,
                'product': f"{brand} {line}",
                'old_price': old_price,
                'new_price': new_price
            }
            self.updates_applied.append(update_info)
            
            print(f"  SUCCESS: Updated price from ${old_price} to ${new_price}")
            return True
            
        except Exception as e:
            print(f"  ERROR: Failed to update - {e}")
            return False
    
    def batch_update(self, updates_data):
        """Process multiple price updates from structured data"""
        
        print("Cigar Price Update Tool")
        print("=" * 50)
        
        for update in updates_data:
            brand = update.get('brand')
            line = update.get('line') 
            wrapper = update.get('wrapper')
            vitola = update.get('vitola')
            size = update.get('size')
            
            print(f"\nUpdating {brand} {line}:")
            print("-" * 30)
            
            # Process each retailer price update
            for retailer_update in update.get('retailers', []):
                retailer = retailer_update.get('retailer')
                price = retailer_update.get('price')
                
                if retailer and price:
                    self.update_price(retailer, brand, line, price, wrapper, vitola, size)
        
        # Summary report
        print("\n" + "=" * 50)
        print(f"UPDATE SUMMARY: {len(self.updates_applied)} prices updated")
        print("=" * 50)
        
        for update in self.updates_applied:
            print(f"{update['retailer']}: {update['product']}")
            print(f"  ${update['old_price']} -> ${update['new_price']}")
        
        print(f"\nBackup files created with '.backup_price_update' extension")

def main():
    """
    Price updates based on your data review
    """
    updater = PriceUpdater()
    
    # Your specific price updates
    updates_data = [
        {
            'brand': 'Arturo Fuente',
            'line': 'Hemingway',
            'wrapper': 'Cameroon', 
            'vitola': 'Classic',
            'size': '7x48',
            'retailers': [
                {'retailer': 'cigarcountry', 'price': '273.94'},
            ]
        },
        {
            'brand': 'Drew Estate',
            'line': 'Herrera Esteli Norteno',
            'wrapper': 'Mexican San Andres Maduro',
            'vitola': 'Lonsdale', 
            'size': '6.5x44',
            'retailers': [
                {'retailer': 'nice ash cigars', 'price': '196.84'},
                {'retailer': 'cigar.com', 'price': '156.99'},
            ]
        },
        {
            'brand': 'Hoyo de Monterrey',
            'line': 'Excalibur',
            'wrapper': 'Connecticut Shade',
            'vitola': 'Epicure',
            'size': '5.2x50', 
            'retailers': [
                {'retailer': 'cigar.com', 'price': '156.99'},
                {'retailer': 'famous smoke shop', 'price': '147.95'},
                {'retailer': 'nickscigarworld', 'price': '150.95'},
            ]
        }
    ]
    
    print("Processing your price updates...")
    updater.batch_update(updates_data)
    
    # Handle Padron duplicate removal
    print("\n" + "=" * 50)
    print("REMOVING PADRON DUPLICATE FROM ABC FINE WINE & SPIRITS")
    print("=" * 50)
    
    csv_path = updater.data_dir / "abcfws.csv"
    if csv_path.exists():
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                rows = list(reader)
            
            # Find Padron products and keep only the first one
            padron_seen = False
            filtered_rows = []
            removed_count = 0
            
            for row in rows:
                brand = row.get('brand', '').lower()
                if 'padron' in brand:
                    if padron_seen:
                        print(f"  Removing duplicate: {row.get('title', '')}")
                        removed_count += 1
                        continue
                    else:
                        padron_seen = True
                        print(f"  Keeping: {row.get('title', '')}")
                
                filtered_rows.append(row)
            
            if removed_count > 0:
                # Create backup
                backup_path = str(csv_path) + '.backup_padron_dedup'
                with open(backup_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)
                
                # Write cleaned data
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(filtered_rows)
                
                print(f"  SUCCESS: Removed {removed_count} duplicate Padron entries")
            else:
                print("  No duplicates found")
                
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print("  ERROR: abcfws.csv not found")
    
    print("\nPrice update complete! Restart your FastAPI server to see changes.")
    print("Next: Update age verification and stock notice on your website.")

if __name__ == "__main__":
    main()
