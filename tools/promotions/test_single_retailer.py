import csv
import sys
from pathlib import Path
from promo_manager import calculate_best_promo

def test_single_retailer(retailer_key, csv_path):
    """Test promotions on a single retailer's CSV"""
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"CSV not found: {csv_file}")
        return
    
    print(f"Testing promos for {retailer_key} on {csv_file.name}...")
    
    # Read CSV
    rows = []
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        
        # Add promo column if it doesn't exist
        if 'current_promotions_applied' not in fieldnames:
            fieldnames.append('current_promotions_applied')
            print("Added 'current_promotions_applied' column")
        
        for row in reader:
            # Calculate promo for this product
            promo_text = calculate_best_promo(retailer_key, row)
            row['current_promotions_applied'] = promo_text
            rows.append(row)
            
            # Show first few results for verification
            if len(rows) <= 3 and promo_text:
                print(f"  Product: {row.get('brand', '')} {row.get('line', '')}")
                print(f"  Original: ${row.get('price', '0')}")
                print(f"  Promo: {promo_text}")
                print()
    
    # Write back
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    promo_count = sum(1 for row in rows if row.get('current_promotions_applied'))
    total_count = len(rows)
    
    print(f"Test complete!")
    print(f"   Total products: {total_count}")
    print(f"   Products with promos: {promo_count}")
    print(f"   CSV updated: {csv_file}")

if __name__ == "__main__":
    # Test with Hiland
    # Path from tools/promotions/ to main_directory/static/data/
    retailer_key = "hiland"
    csv_path = "../../static/data/hilands.csv"  # Go up 2 levels, then into static/data
    
    print("=== SINGLE RETAILER PROMO TEST ===")
    test_single_retailer(retailer_key, csv_path)
