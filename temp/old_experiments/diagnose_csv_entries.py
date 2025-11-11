# diagnose_csv.py - Find and examine all entries in the CSV
import csv
from pathlib import Path

def diagnose_csv():
    """Show all entries and find the Best Cigar Prices entry"""
    
    # Check both possible locations
    possible_paths = [
        "data/bestcigar.csv",
        "static/data/bestcigar.csv"
    ]
    
    csv_path = None
    for path in possible_paths:
        if Path(path).exists():
            csv_path = Path(path)
            break
    
    if not csv_path:
        print("ERROR: Could not find bestcigar.csv file")
        return
    
    print(f"Examining: {csv_path}")
    print("=" * 80)
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        print(f"Total entries: {len(rows)}")
        print(f"Fields: {', '.join(fieldnames)}")
        print("=" * 80)
        
        # Look for any entries containing "best cigar" (case insensitive)
        print("SEARCHING FOR 'BEST CIGAR' ENTRIES:")
        best_cigar_entries = []
        for i, row in enumerate(rows):
            for field, value in row.items():
                if value and 'best cigar' in str(value).lower():
                    best_cigar_entries.append((i, row))
                    break
        
        if best_cigar_entries:
            for i, (row_num, row) in enumerate(best_cigar_entries):
                print(f"\nBest Cigar entry #{i+1} (Row {row_num + 2}):")  # +2 because CSV row 1 is header
                for key, value in row.items():
                    if value:
                        print(f"  {key}: {value}")
        else:
            print("No entries found containing 'best cigar'")
        
        print("\n" + "=" * 80)
        
        # Look for any Padron 1964 entries
        print("SEARCHING FOR 'PADRON 1964' ENTRIES:")
        padron_entries = []
        for i, row in enumerate(rows):
            name = row.get('name', '')
            if 'padron' in name.lower() and '1964' in name:
                padron_entries.append((i, row))
        
        if padron_entries:
            print(f"Found {len(padron_entries)} Padron 1964 entries:")
            for i, (row_num, row) in enumerate(padron_entries):
                retailer = row.get('retailer', 'No retailer field')
                name = row.get('name', 'No name field')
                price = row.get('price', row.get('base_price', 'No price field'))
                print(f"  {i+1}. Row {row_num + 2}: {retailer} - {name} - ${price}")
        else:
            print("No Padron 1964 entries found")
        
        print("\n" + "=" * 80)
        
        # Show the last 5 entries (most recently added)
        print("LAST 5 ENTRIES (most recently added):")
        for i, row in enumerate(rows[-5:], len(rows) - 4):
            retailer = row.get('retailer', 'No retailer')
            name = row.get('name', 'No name')
            price = row.get('price', row.get('base_price', 'No price'))
            print(f"  Row {i + 1}: {retailer} - {name} - ${price}")
            
        print("\n" + "=" * 80)
        
        # Show all unique retailers
        retailers = set()
        for row in rows:
            retailer = row.get('retailer', '')
            if retailer:
                retailers.add(retailer)
        
        print("ALL UNIQUE RETAILERS:")
        for retailer in sorted(retailers):
            print(f"  - {retailer}")
            
    except Exception as e:
        print(f"ERROR reading CSV: {e}")

if __name__ == "__main__":
    diagnose_csv()