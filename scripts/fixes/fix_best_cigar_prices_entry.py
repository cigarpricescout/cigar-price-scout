# fix_best_cigar_prices.py - Fix the pricing and stock status for Best Cigar Prices entry
import csv
from pathlib import Path
from datetime import datetime

def fix_best_cigar_prices_entry():
    """Fix the Best Cigar Prices entry with correct pricing and stock status"""
    
    csv_path = Path("data/bestcigar.csv")
    
    if not csv_path.exists():
        csv_path = Path("static/data/bestcigar.csv")
    
    if not csv_path.exists():
        print("ERROR: Could not find bestcigar.csv file")
        return False
    
    # Correct pricing for Best Cigar Prices
    base_price = 455.97
    shipping = 9.99
    tax_rate = 0.08  # Assume 8% tax
    tax = round(base_price * tax_rate, 2)
    total = round(base_price + shipping + tax, 2)
    
    print(f"Updating Best Cigar Prices entry:")
    print(f"  Base Price: ${base_price}")
    print(f"  Shipping: ${shipping}")
    print(f"  Tax: ${tax}")
    print(f"  Total: ${total}")
    
    # Create backup
    backup_path = csv_path.with_name("bestcigar_backup_fixed.csv")
    import shutil
    shutil.copy2(csv_path, backup_path)
    print(f"BACKUP: Created {backup_path}")
    
    try:
        # Read existing data
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        # Find and update the Best Cigar Prices entry
        updated = False
        for row in rows:
            if (row.get('retailer', '').lower() == 'best cigar prices' and 
                'padron' in row.get('name', '').lower() and 
                '1964' in row.get('name', '') and
                'anniversary' in row.get('name', '').lower() and
                'diplomatico' in row.get('name', '').lower()):
                
                # Update all the pricing fields
                old_values = {}
                for field in ['base_price', 'price', 'shipping', 'tax', 'total', 'status', 'in_stock']:
                    if field in row:
                        old_values[field] = row[field]
                
                # Set the correct values
                if 'base_price' in row:
                    row['base_price'] = str(base_price)
                if 'price' in row:
                    row['price'] = str(base_price)
                if 'shipping' in row:
                    row['shipping'] = str(shipping)
                if 'tax' in row:
                    row['tax'] = str(tax)
                if 'total' in row:
                    row['total'] = str(total)
                if 'status' in row:
                    row['status'] = 'In Stock'
                if 'in_stock' in row:
                    row['in_stock'] = 'Yes'
                if 'dealer_type' in row:
                    row['dealer_type'] = 'Authorized Dealer'
                if 'last_updated' in row:
                    row['last_updated'] = datetime.now().strftime('%Y-%m-%d')
                
                print(f"\nUPDATED Best Cigar Prices entry:")
                print(f"  Product: {row.get('name', 'N/A')}")
                for field in ['base_price', 'price', 'shipping', 'tax', 'total', 'status', 'in_stock']:
                    if field in row:
                        old_val = old_values.get(field, 'N/A')
                        new_val = row[field]
                        print(f"  {field}: {old_val} → {new_val}")
                
                updated = True
                break
        
        if not updated:
            print("ERROR: Could not find Best Cigar Prices entry to update")
            return False
        
        # Write the updated CSV
        with open(csv_path, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"\nSUCCESS: Updated Best Cigar Prices entry in {csv_path}")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def show_best_cigar_prices_entry():
    """Show the current Best Cigar Prices entry"""
    
    csv_path = Path("data/bestcigar.csv")
    if not csv_path.exists():
        csv_path = Path("static/data/bestcigar.csv")
    
    if not csv_path.exists():
        print("ERROR: Could not find bestcigar.csv file")
        return
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                if (row.get('retailer', '').lower() == 'best cigar prices' and 
                    'padron' in row.get('name', '').lower() and 
                    '1964' in row.get('name', '')):
                    
                    print("CURRENT Best Cigar Prices entry:")
                    for key, value in row.items():
                        if value:  # Only show non-empty fields
                            print(f"  {key}: {value}")
                    return
            
            print("No Best Cigar Prices entry found")
            
    except Exception as e:
        print(f"ERROR reading CSV: {e}")

if __name__ == "__main__":
    print("Fixing Best Cigar Prices entry for Padron 1964...")
    print("=" * 60)
    
    # Show current entry
    print("BEFORE:")
    show_best_cigar_prices_entry()
    
    print("\n" + "=" * 60)
    
    # Fix the entry
    if fix_best_cigar_prices_entry():
        print("\n" + "=" * 60)
        print("AFTER:")
        show_best_cigar_prices_entry()
        
        print("\n" + "=" * 60)
        print("SUCCESS! Next steps:")
        print("1. Deploy your changes:")
        print("   git add .")
        print('   git commit -m "Fix Best Cigar Prices pricing and stock status"')
        print("   git push")
        print("2. Test on cigarpricescout.com:")
        print("   - Search for 'Padron 1964 Anniversary'") 
        print("   - Best Cigar Prices should now show $455.97 and 'In Stock'")
        print("   - Click the link to test your affiliate tracking!")
        print("3. Monitor your Sovrn affiliate dashboard for clicks and conversions")
    else:
        print("Update failed - check error messages above")