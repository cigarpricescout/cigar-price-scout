import csv
import sys
from pathlib import Path
from promo_manager import calculate_best_promo

# Add the parent directories to sys.path to import from main app
sys.path.append(str(Path(__file__).parent.parent.parent))

# Import RETAILERS from your main.py
try:
    from app.main import RETAILERS
except ImportError:
    # Fallback if path is different
    try:
        from main import RETAILERS
    except ImportError:
        print("Error: Could not import RETAILERS. Check file paths.")
        sys.exit(1)

def apply_promos_to_csv(retailer_info, dry_run=False):
    """Apply promotions to a single retailer's CSV"""
    csv_path = Path(retailer_info['csv'])
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return
    
    retailer_key = retailer_info['key']
    print(f"Processing promos for {retailer_key}...")
    
    # Read CSV
    rows = []
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        
        # Add promo column if it doesn't exist
        if 'current_promotions_applied' not in fieldnames:
            fieldnames.append('current_promotions_applied')
        
        for row in reader:
            # Calculate promo for this product
            promo_text = calculate_best_promo(retailer_key, row)
            row['current_promotions_applied'] = promo_text
            rows.append(row)
    
    promo_count = sum(1 for row in rows if row.get('current_promotions_applied'))
    
    if dry_run:
        print(f"  DRY RUN: Would apply promos to {promo_count} products")
        # Show sample results
        for i, row in enumerate(rows[:3]):
            if row.get('current_promotions_applied'):
                print(f"    Sample {i+1}: {row.get('brand')} {row.get('line')} -> {row.get('current_promotions_applied')}")
    else:
        # Write back
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Applied promos to {promo_count} products")

def main():
    """Apply promotions to all retailer CSVs"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Apply promotions to retailer CSVs')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--retailer', help='Process only specific retailer (e.g., hiland)')
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("=== DRY RUN MODE ===")
    
    print("Applying promotions to retailer CSVs...")
    
    for retailer in RETAILERS:
        # Skip if specific retailer requested
        if args.retailer and retailer['key'] != args.retailer:
            continue
            
        try:
            apply_promos_to_csv(retailer, dry_run=args.dry_run)
        except Exception as e:
            print(f"Error processing {retailer['key']}: {e}")
            continue
    
    print("Promotion application complete!")

if __name__ == "__main__":
    main()
