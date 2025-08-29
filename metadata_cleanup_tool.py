# metadata_cleanup.py - Fix specific cigar metadata and identify issues
import csv
import os
from pathlib import Path
import re

# Known correct metadata for specific cigars
CORRECT_METADATA = {
    # Format: (brand, line, size) -> {wrapper, vitola, notes}
    ('Arturo Fuente', 'Hemingway', '7x48'): {
        'wrapper': 'Cameroon',
        'vitola': 'Classic',
        'notes': 'All Hemingways are perfectos'
    },
    ('Hoyo de Monterrey', 'Excalibur', '5.2x50'): {
        'wrapper': 'Connecticut Shade',
        'vitola': 'Epicure',
        'notes': 'Natural Connecticut wrapper'
    },
    ('Drew Estate', 'Herrera Esteli Norteno', '6x44'): {
        'wrapper': 'Mexican San Andres Maduro',
        'vitola': 'Lonsdale',
        'notes': 'Box-pressed, some retailers list 6.5x44'
    },
    ('Drew Estate', 'Herrera Esteli Norteno', '6.5x44'): {
        'wrapper': 'Mexican San Andres Maduro',
        'vitola': 'Lonsdale',
        'notes': 'Box-pressed, alternate size listing'
    },
    ('Padron', '1964 Anniversary', '7x50'): {
        'wrapper': 'Maduro',
        'vitola': 'Diplomatico',
        'notes': 'Box-pressed, entire 1964 line is box-pressed'
    }
}

# Brand-specific rules for common patterns
BRAND_RULES = {
    'Arturo Fuente': {
        'Hemingway': {
            'wrapper_default': 'Cameroon',
            'vitola_mappings': {
                '4x49': 'Short Story',
                '5x47': 'Signature', 
                '6x47': 'Signature',
                '7x48': 'Classic'
            }
        }
    },
    'Hoyo de Monterrey': {
        'Excalibur': {
            'wrapper_default': 'Connecticut Shade'
        }
    },
    'Drew Estate': {
        'Herrera Esteli Norteno': {
            'wrapper_default': 'Mexican San Andres Maduro'
        }
    },
    'Padron': {
        '1964 Anniversary': {
            'wrapper_default': 'Maduro'
        }
    }
}

def normalize_size(size_str):
    """Normalize size strings for comparison"""
    if not size_str:
        return ''
    # Remove spaces and standardize format
    size_clean = re.sub(r'[^\d.x]', '', size_str.lower())
    return size_clean

def find_matching_key(brand, line, size):
    """Find matching key in CORRECT_METADATA, handling size variations"""
    size_normalized = normalize_size(size)
    
    # Try exact match first
    key = (brand, line, size)
    if key in CORRECT_METADATA:
        return key
    
    # Try with normalized size
    for (b, l, s) in CORRECT_METADATA.keys():
        if b == brand and l == line and normalize_size(s) == size_normalized:
            return (b, l, s)
    
    return None

def fix_product_metadata(product):
    """Fix metadata for a single product"""
    brand = product.get('brand', '').strip()
    line = product.get('line', '').strip()
    size = product.get('size', '').strip()
    
    # Check for exact corrections
    key = find_matching_key(brand, line, size)
    if key:
        correct = CORRECT_METADATA[key]
        product['wrapper'] = correct['wrapper']
        product['vitola'] = correct['vitola']
        return True, correct['notes']
    
    # Apply brand-specific rules
    if brand in BRAND_RULES:
        brand_rules = BRAND_RULES[brand]
        if line in brand_rules:
            line_rules = brand_rules[line]
            changed = False
            notes = []
            
            # Set default wrapper if missing
            if not product.get('wrapper') and 'wrapper_default' in line_rules:
                product['wrapper'] = line_rules['wrapper_default']
                changed = True
                notes.append(f"Set wrapper to {line_rules['wrapper_default']}")
            
            # Set vitola from size mapping
            if 'vitola_mappings' in line_rules:
                size_normalized = normalize_size(size)
                for mapped_size, vitola in line_rules['vitola_mappings'].items():
                    if normalize_size(mapped_size) == size_normalized:
                        product['vitola'] = vitola
                        changed = True
                        notes.append(f"Set vitola to {vitola}")
                        break
            
            if changed:
                return True, "; ".join(notes)
    
    return False, "No corrections applied"

def analyze_csv_file(csv_path):
    """Analyze a single CSV file for metadata issues"""
    results = {
        'file': csv_path,
        'total_products': 0,
        'fixed_products': 0,
        'missing_wrapper': 0,
        'missing_vitola': 0,
        'fixes': [],
        'issues': []
    }
    
    if not Path(csv_path).exists():
        results['issues'].append("File not found")
        return results
    
    # Read and process the CSV
    rows = []
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            
            if not headers or 'wrapper' not in headers or 'vitola' not in headers:
                results['issues'].append("Missing wrapper/vitola columns")
                return results
            
            for row in reader:
                results['total_products'] += 1
                
                # Track missing data
                if not row.get('wrapper', '').strip():
                    results['missing_wrapper'] += 1
                if not row.get('vitola', '').strip():
                    results['missing_vitola'] += 1
                
                # Try to fix metadata
                was_fixed, notes = fix_product_metadata(row)
                if was_fixed:
                    results['fixed_products'] += 1
                    results['fixes'].append({
                        'title': row.get('title', ''),
                        'brand': row.get('brand', ''),
                        'line': row.get('line', ''),
                        'size': row.get('size', ''),
                        'wrapper': row.get('wrapper', ''),
                        'vitola': row.get('vitola', ''),
                        'notes': notes
                    })
                
                rows.append(row)
    
    except Exception as e:
        results['issues'].append(f"Error reading file: {e}")
        return results
    
    # Write back the fixed data if any fixes were made
    if results['fixed_products'] > 0:
        try:
            backup_path = str(csv_path) + '.backup_cleanup'
            # Create backup
            with open(backup_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                # Re-read original for backup
                with open(csv_path, 'r', newline='', encoding='utf-8') as orig:
                    orig_reader = csv.DictReader(orig)
                    writer.writerows(orig_reader)
            
            # Write fixed data
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
            
            results['backup_created'] = backup_path
        except Exception as e:
            results['issues'].append(f"Error writing fixes: {e}")
    
    return results

def generate_report(all_results):
    """Generate a comprehensive cleanup report"""
    total_files = len(all_results)
    total_products = sum(r['total_products'] for r in all_results)
    total_fixes = sum(r['fixed_products'] for r in all_results)
    total_missing_wrapper = sum(r['missing_wrapper'] for r in all_results)
    total_missing_vitola = sum(r['missing_vitola'] for r in all_results)
    
    print("\n" + "=" * 60)
    print("CIGAR METADATA CLEANUP REPORT")
    print("=" * 60)
    print(f"Files processed: {total_files}")
    print(f"Total products: {total_products}")
    print(f"Products fixed: {total_fixes}")
    print(f"Missing wrapper: {total_missing_wrapper}")
    print(f"Missing vitola: {total_missing_vitola}")
    print()
    
    # Show files with fixes
    files_with_fixes = [r for r in all_results if r['fixed_products'] > 0]
    if files_with_fixes:
        print("FILES WITH CORRECTIONS:")
        print("-" * 30)
        for result in files_with_fixes:
            filename = Path(result['file']).name
            print(f"{filename}: {result['fixed_products']} fixes")
            
            # Show specific fixes
            for fix in result['fixes'][:3]:  # Show first 3 fixes per file
                print(f"  • {fix['brand']} {fix['line']} ({fix['size']})")
                print(f"    Wrapper: {fix['wrapper']}, Vitola: {fix['vitola']}")
            
            if len(result['fixes']) > 3:
                print(f"  ... and {len(result['fixes']) - 3} more")
            print()
    
    # Show problematic files
    files_with_issues = [r for r in all_results if r['issues']]
    if files_with_issues:
        print("FILES WITH ISSUES:")
        print("-" * 20)
        for result in files_with_issues:
            filename = Path(result['file']).name
            print(f"{filename}: {', '.join(result['issues'])}")
        print()
    
    # Show data quality summary
    print("DATA QUALITY OVERVIEW:")
    print("-" * 25)
    files_missing_data = [r for r in all_results if r['missing_wrapper'] > 0 or r['missing_vitola'] > 0]
    for result in sorted(files_missing_data, key=lambda x: x['missing_wrapper'] + x['missing_vitola'], reverse=True)[:10]:
        filename = Path(result['file']).name
        missing = result['missing_wrapper'] + result['missing_vitola']
        print(f"{filename}: {missing} missing fields ({result['missing_wrapper']} wrapper, {result['missing_vitola']} vitola)")

def main():
    print("Cigar Metadata Cleanup Tool")
    print("=" * 40)
    
    data_dir = Path("static/data")
    if not data_dir.exists():
        print("ERROR: static/data directory not found")
        return
    
    csv_files = list(data_dir.glob("*.csv"))
    if not csv_files:
        print("No CSV files found")
        return
    
    print(f"Processing {len(csv_files)} CSV files...")
    print()
    
    all_results = []
    for csv_file in csv_files:
        print(f"Processing {csv_file.name}...", end=" ")
        result = analyze_csv_file(csv_file)
        all_results.append(result)
        
        if result['fixed_products'] > 0:
            print(f"Fixed {result['fixed_products']} products")
        elif result['issues']:
            print(f"Issues: {', '.join(result['issues'])}")
        else:
            print("No fixes needed")
    
    generate_report(all_results)
    
    print("\nBackup files created with '.backup_cleanup' extension")
    print("Review the fixes and run your FastAPI server to test the changes.")

if __name__ == "__main__":
    main()
