# fix_ci_norteno.py - Correct the CI Drew Estate price back to $224.99
import csv
from pathlib import Path

def fix_ci_norteno_price():
    csv_path = Path("static/data/ci.csv")
    
    if not csv_path.exists():
        print("ERROR: ci.csv not found")
        return
    
    print("Fixing CI Drew Estate Herrera Esteli Norteno price...")
    
    try:
        # Read the file
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)
        
        # Find and fix the Drew Estate entry
        fixed = False
        for row in rows:
            brand = row.get('brand', '').lower()
            line = row.get('line', '').lower()
            price = row.get('price', '')
            
            if 'drew estate' in brand and 'norteno' in line and price == '156.99':
                print(f"Found: {row.get('title', '')}")
                print(f"  Current price: ${price}")
                row['price'] = '224.99'
                print(f"  Updated price: $224.99")
                fixed = True
                break
        
        if fixed:
            # Create backup
            backup_path = str(csv_path) + '.backup_ci_fix'
            with open(backup_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                # Read original for backup
                with open(csv_path, 'r', newline='', encoding='utf-8') as orig:
                    orig_reader = csv.DictReader(orig)
                    writer.writerows(orig_reader)
            
            # Write corrected data
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
            
            print("SUCCESS: CI price corrected to $224.99")
            print("Backup created: ci.csv.backup_ci_fix")
        else:
            print("No Drew Estate Norteno entry found with $156.99 price")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    fix_ci_norteno_price()
