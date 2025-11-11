# check_cigar_csv.py - Find all Excalibur entries in cigar.csv
import csv
from pathlib import Path

def check_excalibur_entries():
    """Check what Excalibur entries exist in cigar.csv"""
    csv_path = Path("static/data/cigar.csv")
    
    if not csv_path.exists():
        print("ERROR: cigar.csv not found")
        return
    
    print("Checking cigar.csv for Excalibur entries...")
    print("=" * 50)
    
    excalibur_found = []
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            print(f"Headers: {headers}")
            print()
            
            for i, row in enumerate(reader):
                title = row.get('title', '').lower()
                brand = row.get('brand', '').lower()
                line = row.get('line', '').lower()
                
                if 'excalibur' in title or 'excalibur' in brand or 'excalibur' in line:
                    excalibur_found.append({
                        'row_number': i + 1,
                        'brand': row.get('brand', ''),
                        'line': row.get('line', ''),
                        'wrapper': row.get('wrapper', ''),
                        'vitola': row.get('vitola', ''),
                        'size': row.get('size', ''),
                        'price': row.get('price', ''),
                        'title': row.get('title', '')
                    })
    
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    if excalibur_found:
        print(f"Found {len(excalibur_found)} Excalibur entries:")
        print()
        
        for entry in excalibur_found:
            print(f"Row {entry['row_number']}:")
            print(f"  Brand: '{entry['brand']}'")
            print(f"  Line: '{entry['line']}'")
            print(f"  Wrapper: '{entry['wrapper']}'")
            print(f"  Vitola: '{entry['vitola']}'")
            print(f"  Size: '{entry['size']}'")
            print(f"  Price: ${entry['price']}")
            print(f"  Title: {entry['title']}")
            print()
    else:
        print("No Excalibur entries found in cigar.csv")

def fix_cigar_price():
    """Fix the specific price issue"""
    csv_path = Path("static/data/cigar.csv")
    
    if not csv_path.exists():
        print("ERROR: cigar.csv not found")
        return
    
    try:
        # Read all data
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)
        
        # Find and fix Excalibur entries
        updates_made = 0
        for row in rows:
            brand = row.get('brand', '').lower()
            line = row.get('line', '').lower()
            
            if 'hoyo' in brand and 'excalibur' in line:
                old_price = row.get('price', '')
                if old_price == '113.99':
                    row['price'] = '156.99'
                    print(f"Updated Excalibur price from ${old_price} to $156.99")
                    updates_made += 1
        
        if updates_made > 0:
            # Create backup
            backup_path = str(csv_path) + '.backup_excalibur_fix'
            with open(backup_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                # Read original for backup
                with open(csv_path, 'r', newline='', encoding='utf-8') as orig:
                    orig_reader = csv.DictReader(orig)
                    writer.writerows(orig_reader)
            
            # Write fixed data
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
            
            print(f"SUCCESS: Made {updates_made} price corrections")
        else:
            print("No price corrections needed")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_excalibur_entries()
    print("\nWould you like to fix the $113.99 price to $156.99? (y/n)")
    response = input().lower()
    if response == 'y':
        fix_cigar_price()
        print("\nRestart your FastAPI server to see the change.")
