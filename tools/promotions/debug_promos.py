import csv
import json
from pathlib import Path
from promo_manager import get_active_promos, promo_applies

def debug_promo_system():
    """Debug why promos aren't applying"""
    print("=== PROMO SYSTEM DEBUG ===")
    
    # 1. Check promotions.json
    print("\n1. Checking promotions.json:")
    try:
        with open("promotions.json", 'r') as f:
            promos_data = json.load(f)
        print(f"   Loaded promotions.json successfully")
        print(f"   Hiland promos: {promos_data.get('hiland', [])}")
    except Exception as e:
        print(f"   ERROR loading promotions.json: {e}")
        return
    
    # 2. Check active promos for hiland
    print("\n2. Checking active promos:")
    try:
        active_promos = get_active_promos('hiland')
        print(f"   Active promos for hiland: {len(active_promos)}")
        for promo in active_promos:
            print(f"   - {promo}")
    except Exception as e:
        print(f"   ERROR getting active promos: {e}")
        return
    
    # 3. Check CSV structure
    print("\n3. Checking CSV structure:")
    csv_path = Path("../../static/data/hilands.csv")
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames) if reader.fieldnames else []
            print(f"   CSV columns: {fieldnames}")
            
            # Show first row
            first_row = next(reader, None)
            if first_row:
                print(f"   Sample row data:")
                for key, value in first_row.items():
                    print(f"     {key}: {value}")
    except Exception as e:
        print(f"   ERROR reading CSV: {e}")
        return
    
    # 4. Test promo matching on sample row
    print("\n4. Testing promo matching:")
    if active_promos and first_row:
        promo = active_promos[0]
        print(f"   Testing promo: {promo}")
        print(f"   Against row: brand='{first_row.get('brand')}', line='{first_row.get('line')}'")
        
        applies = promo_applies(promo, first_row)
        print(f"   Promo applies: {applies}")
        
        if not applies:
            print("   Debugging why promo doesn't apply...")
            scope = promo.get('scope', 'sitewide')
            print(f"     Scope: {scope}")
            
            if scope == 'sitewide':
                excluded = promo.get('excluded_brands', [])
                brand = first_row.get('brand')
                print(f"     Brand: '{brand}'")
                print(f"     Excluded brands: {excluded}")
                print(f"     Brand in excluded: {brand in excluded}")

if __name__ == "__main__":
    debug_promo_system()
