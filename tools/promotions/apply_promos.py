import csv
import sys
from pathlib import Path
from promo_manager import calculate_best_promo

# Add the parent directories to sys.path to import from main app
sys.path.append(str(Path(__file__).parent.parent.parent))

# Hardcode RETAILERS to avoid import issues
RETAILERS = [
    {"key": "hilands", "csv": "../../static/data/hilands.csv"},
    {"key": "atlanticcigars", "csv": "../../static/data/atlantic.csv"},
    {"key": "absolutecigars", "csv": "../../static/data/absolutecigars.csv"},
    {"key": "bighumidor", "csv": "../../static/data/bighumidor.csv"},
    {"key": "bnbtobacco", "csv": "../../static/data/bnbtobacco.csv"},
    {"key": "cigarboxpa", "csv": "../../static/data/cigarboxpa.csv"},
    {"key": "cigarsdirect", "csv": "../../static/data/cigarsdirect.csv"},
    {"key": "foxcigar", "csv": "../../static/data/foxcigar.csv"},
    {"key": "gothamcigars", "csv": "../../static/data/gothamcigars.csv"},
    {"key": "holts", "csv": "../../static/data/holts.csv"},
    {"key": "neptune", "csv": "../../static/data/neptune.csv"},
    {"key": "planetcigars", "csv": "../../static/data/planetcigars.csv"},
    {"key": "smallbatchcigar", "csv": "../../static/data/smallbatchcigar.csv"},
    {"key": "smokeinn", "csv": "../../static/data/smokeinn.csv"},
    {"key": "tampasweethearts", "csv": "../../static/data/tampasweethearts.csv"},
    {"key": "tobaccolocker", "csv": "../../static/data/tobaccolocker.csv"},
    {"key": "watchcity", "csv": "../../static/data/watchcity.csv"},
    {"key": "cccrafter", "csv": "../../static/data/cccrafter.csv"},
    {"key": "nickscigarworld", "csv": "../../static/data/nickscigarworld.csv"},
    {"key": "twoguys", "csv": "../../static/data/twoguys.csv"},
    {"key": "thompson", "csv": "../../static/data/thompson.csv"},
    {"key": "thecigarshop", "csv": "../../static/data/thecigarshop.csv"},
    {"key": "tobaccostock", "csv": "../../static/data/tobaccostock.csv"},
]

def apply_promos_to_csv(retailer_info, dry_run=False):
    """Apply promotions to a single retailer's CSV"""
    csv_path = Path(retailer_info['csv'])
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return
    
    retailer_key = retailer_info['key']
    print(f"Processing promos for {retailer_key}...")
    print(f"  Reading from: {csv_path}")
    
    # Read CSV
    rows = []
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        
        print(f"  Original fieldnames: {fieldnames}")
        
        # Add promo column if it doesn't exist
        if 'current_promotions_applied' not in fieldnames:
            fieldnames.append('current_promotions_applied')
            print(f"  Added promo column")
        
        for row in reader:
            # Calculate promo for this product
            promo_text = calculate_best_promo(retailer_key, row)
            row['current_promotions_applied'] = promo_text
            rows.append(row)
    
    print(f"  Read {len(rows)} rows from CSV")
    
    promo_count = sum(1 for row in rows if row.get('current_promotions_applied'))
    
    if dry_run:
        print(f"  DRY RUN: Would apply promos to {promo_count} products")
        return
    
    # SAFETY CHECK: Don't write if we lost data
    if len(rows) == 0:
        print(f"  ERROR: No rows to write! Skipping CSV write to prevent data loss.")
        return
    
    print(f"  Writing {len(rows)} rows back to CSV...")
    
    # Write back
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Applied promos to {promo_count} products")
    except Exception as e:
        print(f"  ERROR writing CSV: {e}")

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
