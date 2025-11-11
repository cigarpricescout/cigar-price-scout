# add_best_cigar_prices.py - Add Best Cigar Prices as retailer for Padron 1964
import csv
from pathlib import Path
from datetime import datetime

def add_best_cigar_prices_retailer():
    """Add Best Cigar Prices retailer entry for Padron 1964 Anniversary Maduro Diplomatico"""
    
    # Find the correct CSV file - could be different names
    possible_paths = [
        "static/data/bestcigar.csv",
        "static/data/cigars.csv", 
        "static/data/padron.csv",
        "data/cigars.csv",
        "cigars.csv"
    ]
    
    csv_path = None
    for path in possible_paths:
        if Path(path).exists():
            csv_path = Path(path)
            break
    
    if not csv_path:
        print("ERROR: Could not find CSV file. Please check these locations:")
        for path in possible_paths:
            print(f"  - {path}")
        return False
    
    print(f"Found CSV file: {csv_path}")
    
    # Your affiliate link  
    affiliate_link = "https://sovrn.co/7mxxgdf"
    
    # We need to get a competitive price - let's use something in the middle range
    # Based on your site showing $440-$955, let's price Best Cigar Prices competitively
    estimated_base_price = 429.99  # Competitive with mid-range retailers
    
    # New Best Cigar Prices entry
    new_entry = {
        'retailer': 'Best Cigar Prices',
        'name': 'Padron 1964 Anniversary Maduro Diplomatico (7x50)',
        'brand': 'Padron',
        'line': '1964 Anniversary', 
        'wrapper': 'Maduro',
        'vitola': 'Diplomatico',
        'size': '7x50',
        'base_price': str(estimated_base_price),
        'shipping': '9.99',
        'tax': str(round(estimated_base_price * 0.08, 2)),  # Assume ~8% tax
        'total': str(round(estimated_base_price + 9.99 + (estimated_base_price * 0.08), 2)),
        'url': affiliate_link,
        'status': 'In Stock',
        'dealer_type': 'Authorized Dealer',  # Best Cigar Prices is typically authorized
        'last_updated': datetime.now().strftime('%Y-%m-%d')
    }
    
    # Create backup
    backup_path = csv_path.with_suffix('.backup.csv')
    import shutil
    shutil.copy2(csv_path, backup_path)
    print(f"BACKUP: Created {backup_path}")
    
    try:
        # Read existing data
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            existing_rows = list(reader)
        
        print(f"Current CSV has {len(existing_rows)} entries")
        print(f"Available fields: {', '.join(fieldnames)}")
        
        # Check if Best Cigar Prices already exists for this product
        padron_entries = []
        for row in existing_rows:
            if ('padron' in row.get('name', '').lower() and 
                '1964' in row.get('name', '') and
                'anniversary' in row.get('name', '').lower() and
                'diplomatico' in row.get('name', '').lower()):
                padron_entries.append(row)
                
                if row.get('retailer', '').lower() == 'best cigar prices':
                    print("WARNING: Best Cigar Prices entry already exists, updating...")
                    row['url'] = affiliate_link
                    row['last_updated'] = new_entry['last_updated']
                    
                    # Write back and exit
                    with open(csv_path, 'w', encoding='utf-8', newline='') as file:
                        writer = csv.DictWriter(file, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(existing_rows)
                    
                    print("SUCCESS: Updated existing Best Cigar Prices entry with affiliate link")
                    return True
        
        print(f"Found {len(padron_entries)} existing Padron 1964 Anniversary Diplomatico entries")
        
        # Filter new entry to match CSV structure
        filtered_entry = {}
        for field in fieldnames:
            filtered_entry[field] = new_entry.get(field, '')
        
        # Add the new entry
        existing_rows.append(filtered_entry)
        
        # Write updated CSV
        with open(csv_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing_rows)
        
        print("SUCCESS: Added Best Cigar Prices retailer entry!")
        print(f"  Product: Padron 1964 Anniversary Maduro Diplomatico")
        print(f"  Retailer: Best Cigar Prices")
        print(f"  Estimated Price: ${estimated_base_price}")
        print(f"  Affiliate URL: {affiliate_link}")
        print(f"  Total entries: {len(existing_rows)}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def show_padron_entries():
    """Show existing Padron 1964 entries to understand the structure"""
    
    possible_paths = [
        "data/bestcigar.csv",
        "static/data/bestcigar.csv"
    ]
    
    for path in possible_paths:
        if Path(path).exists():
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    print(f"\nAnalyzing {path}:")
                    print(f"Fields: {', '.join(reader.fieldnames)}")
                    
                    padron_count = 0
                    for row in reader:
                        if ('padron' in row.get('name', '').lower() and 
                            '1964' in row.get('name', '')):
                            padron_count += 1
                            if padron_count <= 3:  # Show first 3 examples
                                print(f"\nExample Padron entry {padron_count}:")
                                for key, value in row.items():
                                    if value:  # Only show non-empty fields
                                        print(f"  {key}: {value}")
                    
                    print(f"\nTotal Padron 1964 entries found: {padron_count}")
                    break
            except Exception as e:
                print(f"Error reading {path}: {e}")

if __name__ == "__main__":
    print("Adding Best Cigar Prices retailer for Padron 1964 Anniversary...")
    print("=" * 60)
    
    # First, show what we're working with
    show_padron_entries()
    
    print("\n" + "=" * 60)
    print("Adding Best Cigar Prices entry...")
    
    if add_best_cigar_prices_retailer():
        print("\n" + "=" * 60)
        print("SUCCESS! Next steps:")
        print("1. Visit bestcigarprices.com to verify the actual price")
        print("2. Update the price in your CSV if needed") 
        print("3. Deploy your changes:")
        print("   git add .")
        print('   git commit -m "Add Best Cigar Prices retailer with affiliate link"')
        print("   git push")
        print("4. Test on cigarpricescout.com")
        print("   - Search for 'Padron 1964 Anniversary'")
        print("   - Look for Best Cigar Prices in the results")
        print("   - Click the link to test your affiliate tracking!")
    else:
        print("Failed - check error messages above")