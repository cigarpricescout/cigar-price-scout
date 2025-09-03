# add_padron_affiliate.py - Add new Padron 1964 entry with affiliate link
import csv
import os
from pathlib import Path
from datetime import datetime

def add_padron_entry():
    """Add new Padron 1964 Anniversary Maduro Diplomatico entry"""
    
    csv_path = Path("static/data/bestcigar.csv")
    backup_path = Path("static/data/bestcigar_backup.csv")
    
    # Your affiliate link and product details
    affiliate_link = "https://sovrn.co/7mxxgdf"
    
    # New product entry - adjust these details as needed
    new_entry = {
        'name': 'Padron 1964 Anniversary Maduro Diplomatico',
        'brand': 'Padron',
        'size': 'Diplomatico',  # Adjust if you know the exact dimensions
        'wrapper': 'Maduro',
        'strength': 'Medium-Full',  # Adjust based on actual strength
        'price': '0.00',  # You'll need to get the actual price from Best Cigar Prices
        'retailer': 'Best Cigar Prices',
        'url': affiliate_link,
        'in_stock': 'Yes',  # Assume in stock unless you know otherwise
        'last_updated': datetime.now().strftime('%Y-%m-%d')
    }
    
    if not csv_path.exists():
        print("ERROR: bestcigar.csv not found!")
        print("Make sure you're in the cigar-price-scout directory")
        return False
    
    # Create backup
    import shutil
    shutil.copy2(csv_path, backup_path)
    print("BACKUP: Created bestcigar_backup.csv")
    
    # Read existing CSV to get the correct fieldnames
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            existing_rows = list(reader)
        
        print(f"Current CSV has {len(existing_rows)} entries")
        print(f"CSV fields: {', '.join(fieldnames)}")
        
        # Check if entry already exists
        for row in existing_rows:
            if (row.get('name', '').lower() == new_entry['name'].lower() and 
                row.get('retailer', '').lower() == 'best cigar prices'):
                print("WARNING: Entry already exists, updating URL instead...")
                row['url'] = affiliate_link
                row['last_updated'] = new_entry['last_updated']
                
                # Write updated CSV
                with open(csv_path, 'w', encoding='utf-8', newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(existing_rows)
                
                print("SUCCESS: Updated existing entry with affiliate link")
                return True
        
        # Add new entry if it doesn't exist
        # Make sure new_entry only has fields that exist in CSV
        filtered_entry = {}
        for field in fieldnames:
            filtered_entry[field] = new_entry.get(field, '')
        
        existing_rows.append(filtered_entry)
        
        # Write updated CSV with new entry
        with open(csv_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing_rows)
        
        print("SUCCESS: Added new Padron 1964 Anniversary entry")
        print(f"  Product: {new_entry['name']}")
        print(f"  Retailer: {new_entry['retailer']}")
        print(f"  Affiliate URL: {affiliate_link}")
        print(f"  Total entries now: {len(existing_rows)}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to update CSV: {e}")
        return False

def show_csv_structure():
    """Show the structure of the CSV to help debug"""
    csv_path = Path("static/data/bestcigar.csv")
    
    if not csv_path.exists():
        print("ERROR: bestcigar.csv not found!")
        return
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            first_few_rows = []
            
            for i, row in enumerate(reader):
                if i < 3:  # Show first 3 rows as examples
                    first_few_rows.append(row)
                else:
                    break
        
        print("CSV STRUCTURE:")
        print(f"Fields: {', '.join(fieldnames)}")
        print("\nExample rows:")
        for i, row in enumerate(first_few_rows):
            print(f"Row {i+1}: {dict(row)}")
            
    except Exception as e:
        print(f"ERROR reading CSV: {e}")

def create_affiliate_tracker():
    """Create/update the affiliate tracker file"""
    
    tracker_content = f"""# Affiliate Links Tracker
# Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Active Affiliate Links
- Best Cigar Prices: https://sovrn.co/7mxxgdf
  - Product: Padron 1964 Anniversary Maduro Diplomatico
  - Date Added: {datetime.now().strftime('%Y-%m-%d')}
  - Status: Active
  - Action: NEW ENTRY ADDED

## Next Steps
1. Visit Best Cigar Prices to get the actual price for this cigar
2. Update the price field in the CSV if needed
3. Apply to more affiliate programs
4. Test the affiliate link on your site

## Notes
- This is your first commission-earning product!
- Monitor clicks in your Sovrn dashboard
- Consider adding more Padron varieties as you get pricing data
"""
    
    try:
        with open("affiliate_links.txt", "w", encoding='utf-8') as f:
            f.write(tracker_content)
        print("SUCCESS: Updated affiliate_links.txt tracker")
    except Exception as e:
        print(f"ERROR: Could not create tracker: {e}")

if __name__ == "__main__":
    print("Adding Padron 1964 Anniversary Maduro Diplomatico to Best Cigar Prices...")
    print()
    
    # First show current CSV structure
    show_csv_structure()
    print()
    
    # Add the new entry
    if add_padron_entry():
        create_affiliate_tracker()
        print()
        print("NEXT STEPS:")
        print("1. Check the actual price on Best Cigar Prices website")
        print("2. Update the price in the CSV if needed")
        print("3. Deploy your changes:")
        print("   git add .")
        print('   git commit -m "Add Padron 1964 Anniversary with affiliate link"')
        print("   git push")
        print()
        print("4. Test on cigarpricescout.com - search for 'Padron 1964'")
    else:
        print("Failed to add entry - check the error messages above")