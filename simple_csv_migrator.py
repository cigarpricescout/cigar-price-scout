# simple_migrator.py - Debug version with more output
import csv
import os
from pathlib import Path

# Wrapper detection (simplified)
def get_wrapper(title, url=""):
    text = (title + " " + url).lower()
    
    if 'maduro' in text or 'dark' in text:
        return 'Maduro'
    elif 'connecticut' in text or 'shade' in text:
        return 'Connecticut'
    elif 'habano' in text:
        return 'Habano'
    elif 'broadleaf' in text:
        return 'Connecticut Broadleaf'
    else:
        return 'Natural'

# Vitola detection (simplified)
def get_vitola(title, size=""):
    text = (title + " " + size).lower()
    
    if 'churchill' in text or size == '7x47':
        return 'Churchill'
    elif 'robusto' in text or size == '5x50':
        return 'Robusto'
    elif 'toro' in text or size == '6x50':
        return 'Toro'
    elif 'torpedo' in text:
        return 'Torpedo'
    elif 'corona' in text:
        return 'Corona'
    elif 'diplomatico' in text or size == '7x60':
        return 'Diplomatico'
    else:
        return ''

def migrate_one_file(csv_path):
    """Migrate a single CSV file with debug output"""
    print("Processing: {}".format(csv_path))
    
    # Check if file exists
    if not Path(csv_path).exists():
        print("  ERROR: File not found!")
        return False
    
    # Try to read the file
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            print("  Headers found: {}".format(headers))
            
            # Check if already migrated
            if 'wrapper' in headers and 'vitola' in headers:
                print("  Already has wrapper/vitola columns - skipping")
                return True
            
            # Read all rows
            rows = list(reader)
            print("  Found {} rows".format(len(rows)))
            
            if len(rows) == 0:
                print("  No data rows found - skipping")
                return True
                
    except Exception as e:
        print("  ERROR reading file: {}".format(e))
        return False
    
    # Create backup
    backup_path = str(csv_path) + '.backup'
    try:
        with open(backup_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        print("  Backup created: {}".format(backup_path))
    except Exception as e:
        print("  WARNING: Could not create backup: {}".format(e))
    
    # Process each row
    enhanced_rows = []
    for i, row in enumerate(rows):
        if i % 10 == 0:  # Progress indicator
            print("    Processing row {}...".format(i))
        
        title = row.get('title', '')
        url = row.get('url', '')
        size = row.get('size', '')
        
        # Add wrapper and vitola
        row['wrapper'] = get_wrapper(title, url)
        row['vitola'] = get_vitola(title, size)
        enhanced_rows.append(row)
    
    # Write enhanced file
    new_headers = ['title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
    
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=new_headers)
            writer.writeheader()
            writer.writerows(enhanced_rows)
        
        print("  SUCCESS: Enhanced with {} products".format(len(enhanced_rows)))
        return True
    except Exception as e:
        print("  ERROR writing file: {}".format(e))
        return False

def main():
    print("Simple CSV Migrator - Debug Version")
    print("=" * 40)
    
    data_dir = Path("static/data")
    
    if not data_dir.exists():
        print("ERROR: static/data directory not found")
        return
    
    csv_files = list(data_dir.glob("*.csv"))
    print("Found CSV files: {}".format([f.name for f in csv_files]))
    
    if not csv_files:
        print("No CSV files found!")
        return
    
    print("\nStarting migration of {} files...".format(len(csv_files)))
    print("-" * 40)
    
    success_count = 0
    for csv_file in csv_files:
        if migrate_one_file(csv_file):
            success_count += 1
        print()  # Empty line between files
    
    print("=" * 40)
    print("Migration complete: {}/{} files processed".format(success_count, len(csv_files)))

if __name__ == "__main__":
    main()
