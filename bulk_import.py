# bulk_import.py - Enhanced version with wrapper and vitola support
import csv
import os
from pathlib import Path
import re

# Vitola name to size mapping (common cigar industry standards)
VITOLA_SIZES = {
    'Robusto': '5x50',
    'Churchill': '7x47', 
    'Corona': '5.5x42',
    'Toro': '6x50',
    'Torpedo': '6.125x52',
    'Lonsdale': '6.5x42',
    'Epicure': '5.2x50',
    'Classic': '7x48',
    'Short Story': '4x49',
    'Signature': '6x47',
    'Perfecto': '4.5x48',
    'Belicoso': '5.25x52',
    'Gordo': '6x60',
    'Gran Toro': '6x54',
    'Petit Corona': '4.5x40',
    'Double Corona': '7.5x49',
    'Diplomatico': '7x60',
    'Natural': '5.5x44',
}

# Wrapper detection keywords
WRAPPER_KEYWORDS = {
    'Connecticut': ['connecticut', 'conn', 'ct', 'shade'],
    'Connecticut Broadleaf': ['connecticut broadleaf', 'broadleaf', 'conn broadleaf'],
    'Maduro': ['maduro', 'dark', 'oscuro'],
    'Natural': ['natural', 'cameroon', 'claro'],
    'Habano': ['habano', 'havana', 'habana'],
    'Sun Grown': ['sun grown', 'sungrown', 'ecuadorian'],
    'Colorado': ['colorado', 'colorado maduro'],
    'Corojo': ['corojo'],
    'Candela': ['candela', 'green'],
}

def infer_wrapper_from_text(title, url="", line=""):
    """Infer wrapper type from product title, URL, or line"""
    text = f"{title} {url} {line}".lower()
    
    # Check for specific wrapper keywords
    for wrapper, keywords in WRAPPER_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return wrapper
    
    # Default fallbacks based on brand knowledge
    if 'excalibur' in text:
        if 'broadleaf' in text or 'maduro' in text:
            return 'Connecticut Broadleaf'
        return 'Connecticut'
    
    if 'hemingway' in text:
        if 'maduro' in text:
            return 'Maduro'
        return 'Natural'
    
    if 'norteno' in text:
        return 'Colorado Maduro'
    
    return 'Natural'  # Default

def infer_vitola_from_title(title):
    """Extract vitola name from product title"""
    title_lower = title.lower()
    
    # Look for vitola names in title
    for vitola in VITOLA_SIZES.keys():
        if vitola.lower() in title_lower:
            return vitola
    
    return None

def add_products_to_csvs(product_data):
    """
    Enhanced version that handles wrapper and vitola data
    Expected format: retailer_key,retailer_name,url,brand,line,wrapper,vitola,size,box_qty,price
    """
    data_dir = Path("static/data")
    data_dir.mkdir(exist_ok=True)
    
    # Parse each line of product data
    for line in product_data.strip().split('\n'):
        if not line.strip():
            continue
            
        # Split the CSV line
        parts = line.split(',')
        if len(parts) < 9:
            print(f"Skipping invalid line (need 10 fields): {line}")
            continue
            
        retailer_key = parts[0]
        retailer_name = parts[1]
        url = parts[2]
        brand = parts[3]
        line_name = parts[4]
        wrapper = parts[5] if len(parts) > 5 and parts[5] else infer_wrapper_from_text(f"{brand} {line_name}", url, line_name)
        vitola = parts[6] if len(parts) > 6 and parts[6] else infer_vitola_from_title(f"{brand} {line_name}")
        size = parts[7]
        box_qty = parts[8]
        price = parts[9]
        
        # Create filename for this retailer
        csv_file = data_dir / f"{retailer_key}.csv"
        
        # Check if CSV exists, create with enhanced header if not
        if not csv_file.exists():
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock'])
            print(f"Created new CSV file: {csv_file}")
        
        # Create comprehensive title
        wrapper_text = f" {wrapper}" if wrapper else ""
        vitola_text = f" {vitola}" if vitola else ""
        title = f"{brand} {line_name}{wrapper_text}{vitola_text} {size} Box of {box_qty}"
        
        # Add the product to the CSV
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([title, url, brand, line_name, wrapper or '', vitola or '', size, box_qty, price, 'true'])
        
        print(f"Added {title} to {retailer_name}")

def main():
    """
    Enhanced bulk import with wrapper and vitola support
    Format: retailer_key,retailer_name,url,brand,line,wrapper,vitola,size,box_qty,price
    """
    
    # PASTE YOUR ENHANCED PRODUCT DATA HERE:
    product_data = """
famous,Famous Smoke Shop,https://www.famous-smoke.com/arturo-fuente-hemingway-classic-cigars-natural,Arturo Fuente,Hemingway,Natural,Classic,7x48,25,274.99
famous,Famous Smoke Shop,https://www.famous-smoke.com/excalibur-epicure-cigars-natural,Hoyo de Monterrey,Excalibur,Connecticut,Epicure,5.2x50,20,147.95
ci,Cigars International,https://www.cigarsinternational.com/p/excalibur-cigars/1411249/,Hoyo de Monterrey,Excalibur,Connecticut,Epicure,5.2x50,20,156.99
neptune,Neptune Cigar,https://www.neptunecigar.com/cigars/norteno-lonsdale,Drew Estate,Herrera Esteli Norteno,Colorado Maduro,Lonsdale,6.5x44,25,224.95
"""
    
    if not product_data.strip():
        print("No product data found. Please add your enhanced data above.")
        print("Format: retailer_key,retailer_name,url,brand,line,wrapper,vitola,size,box_qty,price")
        return
    
    print("Starting enhanced bulk import with wrapper/vitola support...")
    add_products_to_csvs(product_data)
    print("Import complete!")
    
    # List what CSV files now exist
    data_dir = Path("static/data")
    csv_files = list(data_dir.glob("*.csv"))
    print(f"\nYou now have {len(csv_files)} CSV files with enhanced data structure.")

if __name__ == "__main__":
    main()
