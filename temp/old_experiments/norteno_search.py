# norteno_search.py - Find Herrera Esteli Norteno entries to check for duplicates and pricing
import csv
from pathlib import Path

def search_norteno():
    """Search for Herrera Esteli Norteno cigars and check for issues"""
    data_dir = Path("static/data")
    found_products = []
    
    if not data_dir.exists():
        print("ERROR: static/data directory not found")
        return
    
    csv_files = list(data_dir.glob("*.csv"))
    print(f"Searching {len(csv_files)} CSV files for Herrera Esteli Norteno cigars...")
    print("=" * 80)
    
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = row.get('title', '').lower()
                    brand = row.get('brand', '').lower()  
                    line = row.get('line', '').lower()
                    
                    # Look for variations of Herrera Esteli Norteno
                    norteno_terms = ['norteno', 'norteño', 'herrera esteli']
                    if any(term in title or term in brand or term in line for term in norteno_terms):
                        found_products.append({
                            'file': csv_file.name,
                            'brand': row.get('brand', ''),
                            'line': row.get('line', ''),
                            'size': row.get('size', ''),
                            'wrapper': row.get('wrapper', ''),
                            'vitola': row.get('vitola', ''),
                            'price': row.get('price', ''),
                            'box_qty': row.get('box_qty', ''),
                            'title': row.get('title', '')
                        })
        except Exception as e:
            print(f"Error reading {csv_file.name}: {e}")
    
    if found_products:
        print(f"Found {len(found_products)} Herrera Esteli Norteno products:")
        print()
        
        # Group by retailer to spot duplicates
        by_retailer = {}
        for product in found_products:
            retailer = product['file'].replace('.csv', '')
            if retailer not in by_retailer:
                by_retailer[retailer] = []
            by_retailer[retailer].append(product)
        
        # Check for duplicates and pricing issues
        for retailer, products in by_retailer.items():
            print(f"RETAILER: {retailer.upper()}")
            if len(products) > 1:
                print(f"  WARNING: {len(products)} entries found (possible duplicate)")
            
            for i, product in enumerate(products, 1):
                print(f"  {i}. Brand: '{product['brand']}'")
                print(f"     Line: '{product['line']}'")
                print(f"     Size: '{product['size']}'")
                print(f"     Wrapper: '{product['wrapper']}'")
                print(f"     Vitola: '{product['vitola']}'")
                print(f"     Price: ${product['price']} (Box of {product['box_qty']})")
                
                # Check if it's CI and price is wrong
                if retailer == 'ci' and product['price']:
                    try:
                        price_float = float(product['price'])
                        if abs(price_float - 224.99) > 0.01:
                            print(f"     PRICE ISSUE: Should be $224.99, currently ${price_float}")
                    except ValueError:
                        print(f"     INVALID PRICE FORMAT: '{product['price']}'")
                
                print(f"     Title: {product['title']}")
                print()
            
            print("-" * 60)
    else:
        print("No Herrera Esteli Norteno products found in any CSV files.")
    
    return found_products

if __name__ == "__main__":
    search_norteno()
