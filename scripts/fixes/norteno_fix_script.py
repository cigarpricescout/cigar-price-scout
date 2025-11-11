# norteno_fix.py - Fix duplicates and pricing for Herrera Esteli Norteno
import csv
from pathlib import Path

def fix_norteno_issues():
    """Fix duplicates and pricing issues for Herrera Esteli Norteno cigars"""
    
    # Specific fixes needed
    fixes_applied = {
        'duplicates_removed': 0,
        'prices_corrected': 0,
        'files_modified': []
    }
    
    # Files known to have duplicate issues
    duplicate_files = ['ci.csv', 'bighumidor.csv', 'bonitasmokeshop.csv']
    
    data_dir = Path("static/data")
    
    for csv_filename in duplicate_files:
        csv_path = data_dir / csv_filename
        
        if not csv_path.exists():
            print(f"File not found: {csv_filename}")
            continue
            
        print(f"Processing {csv_filename}...")
        
        # Read the CSV file
        rows = []
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                
                seen_norteno = False
                for row in reader:
                    title = row.get('title', '').lower()
                    brand = row.get('brand', '').lower()
                    line = row.get('line', '').lower()
                    
                    # Check if this is a Norteno product
                    is_norteno = any(term in title or term in brand or term in line 
                                   for term in ['norteno', 'norteño', 'herrera esteli'])
                    
                    if is_norteno:
                        # Only keep the first Norteno entry, skip duplicates
                        if seen_norteno:
                            print(f"  Removing duplicate Norteno entry")
                            fixes_applied['duplicates_removed'] += 1
                            continue
                        else:
                            seen_norteno = True
                            
                            # Fix CI pricing if needed
                            if csv_filename == 'ci.csv':
                                old_price = row.get('price', '')
                                if old_price == '163.99':
                                    row['price'] = '224.99'
                                    print(f"  Corrected price from ${old_price} to $224.99")
                                    fixes_applied['prices_corrected'] += 1
                    
                    rows.append(row)
                
        except Exception as e:
            print(f"  Error reading {csv_filename}: {e}")
            continue
        
        # Write back the cleaned data if changes were made
        if seen_norteno:
            try:
                # Create backup
                backup_path = str(csv_path) + '.backup_norteno_fix'
                with open(backup_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    # Re-read original for backup
                    with open(csv_path, 'r', newline='', encoding='utf-8') as orig:
                        orig_reader = csv.DictReader(orig)
                        writer.writerows(orig_reader)
                
                # Write fixed data
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)
                
                print(f"  Fixed and saved {csv_filename}")
                fixes_applied['files_modified'].append(csv_filename)
                
            except Exception as e:
                print(f"  Error writing {csv_filename}: {e}")
    
    return fixes_applied

def verify_fixes():
    """Verify that the fixes worked correctly"""
    print("\nVerifying fixes...")
    print("-" * 40)
    
    data_dir = Path("static/data")
    duplicate_files = ['ci.csv', 'bighumidor.csv', 'bonitasmokeshop.csv']
    
    for csv_filename in duplicate_files:
        csv_path = data_dir / csv_filename
        
        if not csv_path.exists():
            continue
            
        norteno_count = 0
        norteno_price = None
        
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = row.get('title', '').lower()
                    brand = row.get('brand', '').lower()
                    line = row.get('line', '').lower()
                    
                    is_norteno = any(term in title or term in brand or term in line 
                                   for term in ['norteno', 'norteño', 'herrera esteli'])
                    
                    if is_norteno:
                        norteno_count += 1
                        norteno_price = row.get('price', '')
                        
        except Exception as e:
            print(f"{csv_filename}: Error reading - {e}")
            continue
        
        print(f"{csv_filename}: {norteno_count} Norteno entries", end="")
        if norteno_price:
            print(f" at ${norteno_price}")
            if csv_filename == 'ci.csv' and norteno_price == '224.99':
                print("  ✓ CI price corrected successfully")
        else:
            print()

def main():
    print("Herrera Esteli Norteno Duplicate and Pricing Fix")
    print("=" * 50)
    
    fixes = fix_norteno_issues()
    
    print(f"\nSummary:")
    print(f"Duplicates removed: {fixes['duplicates_removed']}")
    print(f"Prices corrected: {fixes['prices_corrected']}")
    print(f"Files modified: {', '.join(fixes['files_modified'])}")
    
    verify_fixes()
    
    print(f"\nBackup files created with '.backup_norteno_fix' extension")
    print("Restart your FastAPI server to see the changes.")

if __name__ == "__main__":
    main()
