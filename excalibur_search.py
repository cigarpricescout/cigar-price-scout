# excalibur_search.py - Find how Excalibur cigars are stored in your data
import csv
from pathlib import Path

def search_excalibur():
    """Search for Excalibur cigars across all CSV files"""
    data_dir = Path("static/data")
    found_products = []
    
    if not data_dir.exists():
        print("ERROR: static/data directory not found")
        return
    
    csv_files = list(data_dir.glob("*.csv"))
    print(f"Searching {len(csv_files)} CSV files for Excalibur cigars...")
    print("=" * 60)
    
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = row.get('title', '').lower()
                    brand = row.get('brand', '').lower()  
                    line = row.get('line', '').lower()
                    
                    if 'excalibur' in title or 'excalibur' in brand or 'excalibur' in line:
                        found_products.append({
                            'file': csv_file.name,
                            'brand': row.get('brand', ''),
                            'line': row.get('line', ''),
                            'size': row.get('size', ''),
                            'wrapper': row.get('wrapper', ''),
                            'vitola': row.get('vitola', ''),
                            'title': row.get('title', '')
                        })
        except Exception as e:
            print(f"Error reading {csv_file.name}: {e}")
    
    if found_products:
        print(f"Found {len(found_products)} Excalibur products:")
        print()
        
        for i, product in enumerate(found_products, 1):
            print(f"{i}. File: {product['file']}")
            print(f"   Brand: '{product['brand']}'")
            print(f"   Line: '{product['line']}'")
            print(f"   Size: '{product['size']}'")
            print(f"   Wrapper: '{product['wrapper']}'")
            print(f"   Vitola: '{product['vitola']}'")
            print(f"   Title: {product['title']}")
            print()
    else:
        print("No Excalibur products found in any CSV files.")
    
    return found_products

if __name__ == "__main__":
    search_excalibur()
