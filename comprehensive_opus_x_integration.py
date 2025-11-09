#!/usr/bin/env python3
"""
Comprehensive script to add OpusX Robusto entries to ALL retailer CSV files
Creates new files if they don't exist, updates existing ones
"""

import csv
import os
from pathlib import Path

# All OpusX entries including new retailers and existing ones
ALL_OPUS_X_ENTRIES = {
    # Existing retailers (need to add to their CSV files)
    'cigarplace': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://www.cigarplace.biz/arturo-fuente-opus-x-robusto.html',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '667.95',
        'in_stock': 'false'
    },
    'cigarsdirect': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://www.cigarsdirect.com/collections/arturo-fuente-opus-x/products/arturo-fuente-opus-x-robusto?variant=19712418119777',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '1649.99',
        'in_stock': 'false'
    },
    'secretocigarbar': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://secretocigarbar.com/products/f-f-opusx-robusto-29',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '949',
        'in_stock': 'true'
    },
    'tobaccolocker': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://tobaccolocker.com/products/opus_x_robusto_cigars_box?variant=44022945382574',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '1400',
        'in_stock': 'true'
    },
    
    # New retailers (create new CSV files)
    'baysidecigars': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://baysidecigars.com/product/arturo-fuente-opusx-robusto/',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '900',
        'in_stock': 'false'
    },
    'cigarboxinc': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://www.cigarboxinc.com/product/arturo-fuente-opus-x-robusto-514-50/',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '900',
        'in_stock': 'false'
    },
    'cigarcountry': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://cigarcountry.com/product/fuente-opus-x-robusto/',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '1128',
        'in_stock': 'false'
    },
    'cigarprimestore': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://cigarprimestore.com/en/product/arturo-fuente-opus-x-robusto/',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '935.09',
        'in_stock': 'true'
    },
    'karmacigar': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://karmacigar.com/product/arturo-fuente-opus-x-robusto-5-1-4-x-50/',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '806.70',
        'in_stock': 'true'
    },
    'mailcubancigars': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://mailcubancigars.com/product/opus-x-robusto-n-29/',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '1425',
        'in_stock': 'true'
    },
    'pyramidcigars': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://pyramidcigars.com/products/arturo-fuente-opus-x-robusto?variant=45272298062105',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '1339',
        'in_stock': 'false'
    },
    'thecigarshouse': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://thecigarshouse.com/aj-fernandez/arturo-fuente-opus-x-robusto?category=cigar-brands',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '1491',
        'in_stock': 'false'
    },
    'tobacconistofgreenwich': {
        'title': 'Fuente Fuente OpusX Robusto (Box of 29)',
        'url': 'https://tobacconistofgreenwich.com/product/fuente-fuente-opus-x-robusto',
        'brand': 'Arturo Fuente',
        'line': 'OpusX',
        'wrapper': 'Dominican',
        'vitola': 'Robusto',
        'size': '5.25x50',
        'box_qty': '29',
        'price': '1102.50',
        'in_stock': 'false'
    }
}

def backup_csv(csv_path):
    """Create a backup of existing CSV file"""
    if csv_path.exists():
        backup_path = csv_path.with_suffix('.csv.backup')
        try:
            import shutil
            shutil.copy2(csv_path, backup_path)
            print(f"📋 Backup created: {backup_path}")
            return True
        except Exception as e:
            print(f"⚠️  Could not create backup: {e}")
            return False
    return True

def opus_x_already_exists(csv_path):
    """Check if OpusX entry already exists in the CSV"""
    if not csv_path.exists():
        return False
        
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ('OpusX' in row.get('line', '') or 
                    'Opus X' in row.get('title', '') or
                    'opus-x' in row.get('url', '').lower()):
                    return True
        return False
    except Exception as e:
        print(f"❌ Error checking for existing OpusX in {csv_path}: {e}")
        return False

def add_opus_x_to_existing_csv(retailer_key, csv_path, opus_x_data):
    """Add OpusX entry to existing CSV file"""
    
    if opus_x_already_exists(csv_path):
        print(f"✅ OpusX already exists in {retailer_key} - skipping")
        return True
    
    try:
        # Backup first
        backup_csv(csv_path)
        
        # Read existing data
        rows = []
        fieldnames = None
        
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        # Add OpusX entry
        rows.append(opus_x_data)
        
        # Write back to file
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"✅ Added OpusX to existing {retailer_key}")
        return True
        
    except Exception as e:
        print(f"❌ Error adding OpusX to existing {retailer_key}: {e}")
        return False

def create_new_csv(retailer_key, csv_path, opus_x_data):
    """Create a new CSV file with OpusX entry"""
    try:
        # Standard CSV headers
        fieldnames = ['title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
        
        # Ensure directory exists
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(opus_x_data)
        
        print(f"✅ Created new CSV with OpusX for {retailer_key}")
        return True
        
    except Exception as e:
        print(f"❌ Error creating CSV for {retailer_key}: {e}")
        return False

def main():
    print("🎯 Comprehensive OpusX Robusto CSV Integration")
    print("Adding to existing files and creating new ones as needed...")
    print("=" * 70)
    
    # Define the static/data directory path
    static_data_dir = Path("static/data")
    
    if not static_data_dir.exists():
        print(f"❌ Directory does not exist: {static_data_dir}")
        print("Creating static/data directory...")
        static_data_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    total_count = len(ALL_OPUS_X_ENTRIES)
    new_files = []
    updated_files = []
    
    for retailer_key, opus_x_data in ALL_OPUS_X_ENTRIES.items():
        csv_path = static_data_dir / f"{retailer_key}.csv"
        
        print(f"\n📁 Processing {retailer_key}...")
        
        if csv_path.exists():
            # File exists - add to it
            if add_opus_x_to_existing_csv(retailer_key, csv_path, opus_x_data):
                success_count += 1
                updated_files.append(retailer_key)
        else:
            # File doesn't exist - create it
            if create_new_csv(retailer_key, csv_path, opus_x_data):
                success_count += 1
                new_files.append(retailer_key)
    
    print("\n" + "=" * 70)
    print(f"🎯 SUMMARY: {success_count}/{total_count} retailers processed successfully")
    
    if new_files:
        print(f"\n✨ NEW CSV files created ({len(new_files)}):")
        for retailer in new_files:
            print(f"   - {retailer}.csv")
    
    if updated_files:
        print(f"\n📝 EXISTING CSV files updated ({len(updated_files)}):")
        for retailer in updated_files:
            print(f"   - {retailer}.csv")
    
    if success_count == total_count:
        print("\n🎉 ALL OPUS X ENTRIES PROCESSED SUCCESSFULLY!")
        print("\n📋 NEXT STEPS:")
        print("1. Add new retailers to main.py RETAILERS list")
        print("2. Add retailer nexus information to main.py")
        print("3. Restart your FastAPI server")
        print("4. Test localhost to verify OpusX appears in comparisons")
        
        print(f"\n💡 New retailers to add to main.py RETAILERS list:")
        for retailer in new_files:
            print(f'   {{"key": "{retailer}", "name": "{retailer.title()}", "csv": "../static/data/{retailer}.csv", "authorized": False}},')
    else:
        print("\n⚠️  Some entries failed - check the errors above")

if __name__ == "__main__":
    main()
