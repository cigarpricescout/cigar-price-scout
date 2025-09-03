# direct_fix.py - Directly fix the cigar.com Excalibur price
import csv
from pathlib import Path

def fix_cigar_excalibur():
    csv_path = Path("static/data/cigar.csv")
    
    if not csv_path.exists():
        print("ERROR: cigar.csv not found")
        return
    
    print("Reading cigar.csv...")
    
    try:
        # Read the file
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)
        
        print(f"Found {len(rows)} total rows")
        
        # Find and fix Excalibur entries
        for i, row in enumerate(rows):
            title = row.get('title', '')
            brand = row.get('brand', '')
            line = row.get('line', '')
            price = row.get('price', '')
            
            print(f"Row {i+1}: {brand} - {line} - ${price}")
            
            # Check if this is an Excalibur entry with wrong price
            if ('excalibur' in title.lower() or 'excalibur' in line.lower()) and price == '113.99':
                print(f"  FOUND ISSUE: {title} has price ${price}")
                row['price'] = '156.99'
                print(f"  FIXED: Updated price to $156.99")
        
        # Create backup
        backup_path = str(csv_path) + '.backup_direct_fix'
        with open(backup_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            # Read original again for clean backup
            with open(csv_path, 'r', newline='', encoding='utf-8') as orig:
                orig_reader = csv.DictReader(orig)
                writer.writerows(orig_reader)
        
        # Write the fixed data
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        
        print("\nSUCCESS: cigar.csv updated")
        print("Backup created: cigar.csv.backup_direct_fix")
        print("Restart your FastAPI server to see the change")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    fix_cigar_excalibur()
