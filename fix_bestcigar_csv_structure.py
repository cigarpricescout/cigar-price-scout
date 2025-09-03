# fix_bestcigar_csv.py - Fix the Best Cigar Prices entry with correct CSV structure
import csv
from pathlib import Path
from datetime import datetime

def show_csv_content():
    """Show the actual content of the CSV"""
    csv_path = Path("static/data/bestcigar.csv")
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        print(f"CSV Structure:")
        print(f"Fields: {', '.join(fieldnames)}")
        print(f"Total rows: {len(rows)}")
        print("\nAll entries:")
        
        for i, row in enumerate(rows, 1):
            print(f"\nRow {i}:")
            for key, value in row.items():
                print(f"  {key}: '{value}'")
                
    except Exception as e:
        print(f"ERROR: {e}")

def fix_bestcigar_entry():
    """Add/fix the Best Cigar Prices entry with correct structure"""
    csv_path = Path("static/data/bestcigar.csv")
    
    # Your affiliate link
    affiliate_link = "https://sovrn.co/7mxxgdf"
    
    # Correct entry for your CSV structure
    new_entry = {
        'title': 'Padron 1964 Anniversary Maduro Diplomatico',
        'url': affiliate_link,
        'brand': 'Padron',
        'line': '1964 Anniversary',
        'wrapper': 'Maduro',
        'vitola': 'Diplomatico', 
        'size': '7x50',
        'box_qty': '25',  # Standard box quantity for this cigar
        'price': '455.97',
        'in_stock': 'Yes'
    }
    
    # Create backup
    backup_path = csv_path.with_name("bestcigar_backup_structure_fix.csv")
    import shutil
    shutil.copy2(csv_path, backup_path)
    print(f"BACKUP: Created {backup_path}")
    
    try:
        # Read existing data
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        print(f"Current entries: {len(rows)}")
        
        # Remove any empty or incomplete entries first
        cleaned_rows = []
        for i, row in enumerate(rows):
            # Keep rows that have meaningful content
            if (row.get('title') and row.get('title').strip() and 
                row.get('price') and row.get('price').strip() and 
                row.get('price') != '0.00'):
                cleaned_rows.append(row)
            else:
                print(f"Removing incomplete row {i+1}: {row.get('title', 'No title')} - ${row.get('price', 'No price')}")
        
        # Check if Padron entry already exists
        padron_exists = False
        for row in cleaned_rows:
            if ('padron' in row.get('title', '').lower() and 
                '1964' in row.get('title', '') and
                'anniversary' in row.get('title', '').lower()):
                print(f"Found existing Padron entry: {row.get('title')}")
                # Update it with affiliate link
                row['url'] = affiliate_link
                row['price'] = '455.97'
                row['in_stock'] = 'Yes'
                padron_exists = True
                break
        
        # Add new entry if it doesn't exist
        if not padron_exists:
            cleaned_rows.append(new_entry)
            print("Added new Padron 1964 Anniversary entry")
        
        # Write the cleaned and updated CSV
        with open(csv_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(cleaned_rows)
        
        print(f"SUCCESS: Updated CSV with {len(cleaned_rows)} clean entries")
        print(f"Padron 1964 Anniversary entry:")
        print(f"  Title: {new_entry['title']}")
        print(f"  Price: ${new_entry['price']}")
        print(f"  URL: {affiliate_link}")
        print(f"  In Stock: {new_entry['in_stock']}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    print("Examining and fixing bestcigar.csv structure...")
    print("=" * 80)
    
    print("CURRENT CSV CONTENT:")
    show_csv_content()
    
    print("\n" + "=" * 80)
    print("FIXING CSV...")
    
    if fix_bestcigar_entry():
        print("\n" + "=" * 80)
        print("UPDATED CSV CONTENT:")
        show_csv_content()
        
        print("\n" + "=" * 80)
        print("SUCCESS! Next steps:")
        print("1. Deploy your changes:")
        print("   git add .")
        print('   git commit -m "Fix Best Cigar Prices entry with correct pricing"')
        print("   git push")
        print("2. Test on cigarpricescout.com")
        print("3. Your affiliate link should now work!")
    else:
        print("Update failed")