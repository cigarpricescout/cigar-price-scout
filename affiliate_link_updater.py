# affiliate_link_updater.py - Replace retailer URLs with affiliate links
import csv
import os
from pathlib import Path
from datetime import datetime

def update_affiliate_link():
    """Update Best Cigar Prices Padron link with affiliate URL"""
    
    csv_path = Path("static/data/bestcigar.csv")
    backup_path = Path("static/data/bestcigar_backup.csv")
    
    # Your affiliate link
    affiliate_link = "https://sovrn.co/7mxxgdf"
    
    if not csv_path.exists():
        print("ERROR: bestcigar.csv not found!")
        return False
    
    # Create backup
    if csv_path.exists():
        import shutil
        shutil.copy2(csv_path, backup_path)
        print("BACKUP: Created bestcigar_backup.csv")
    
    # Read and update CSV
    rows = []
    updated = False
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            
            for row in reader:
                # Look for Padron 1964 Anniversary entries from Best Cigar Prices
                if (row.get('retailer', '').lower() == 'best cigar prices' and 
                    'padron' in row.get('name', '').lower() and 
                    '1964' in row.get('name', '') and
                    'anniversary' in row.get('name', '').lower()):
                    
                    old_url = row.get('url', '')
                    row['url'] = affiliate_link
                    print(f"UPDATED: {row['name']}")
                    print(f"  Old URL: {old_url}")
                    print(f"  New URL: {affiliate_link}")
                    updated = True
                
                rows.append(row)
        
        # Write updated CSV
        if updated:
            with open(csv_path, 'w', encoding='utf-8', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            print("SUCCESS: CSV file updated with affiliate link")
            return True
        else:
            print("WARNING: No matching Padron 1964 entries found to update")
            return False
            
    except Exception as e:
        print(f"ERROR: Failed to update CSV: {e}")
        return False

def create_affiliate_tracker():
    """Create a tracker file for affiliate links"""
    
    tracker_content = f"""# Affiliate Links Tracker
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Active Affiliate Links
- Best Cigar Prices: https://sovrn.co/7mxxgdf
  - Product: Padron 1964 Anniversary Maduro Diplomatico
  - Date Added: {datetime.now().strftime('%Y-%m-%d')}
  - Status: Active

## Pending Applications
- Add other retailers as you get approved...

## Commission Tracking
- Track clicks and conversions in your affiliate dashboards
- Update this file as you add more affiliate links

## Next Steps
1. Apply to more affiliate programs
2. Replace more URLs with affiliate links
3. Monitor performance in affiliate dashboards
"""
    
    try:
        with open("affiliate_links.txt", "w", encoding='utf-8') as f:
            f.write(tracker_content)
        
        print("SUCCESS: Created affiliate_links.txt tracker file")
        
    except Exception as e:
        print(f"ERROR: Could not create tracker file: {e}")

if __name__ == "__main__":
    print("Updating Best Cigar Prices affiliate link for Padron 1964...")
    
    if update_affiliate_link():
        create_affiliate_tracker()
        print("\nDEPLOY NEXT:")
        print("git add .")
        print('git commit -m "Add first affiliate link for Best Cigar Prices"')
        print("git push")
    else:
        print("Update failed - check the CSV file structure")