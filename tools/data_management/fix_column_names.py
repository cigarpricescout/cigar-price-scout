"""
Fix column name references in all update_*.py scripts.

When master_cigars.csv was migrated to master_cigars.db (SQLite), the column
names changed from Title Case (CSV headers) to snake_case (SQLite schema):

  CSV Name        -> SQLite Name
  Box Quantity    -> box_quantity
  Brand           -> brand
  Line            -> line
  Wrapper         -> wrapper
  Vitola          -> vitola
  Length          -> length
  Ring Gauge      -> ring_gauge

The update scripts were pointed at the .db file but still reference old column names.
"""

import os
import glob

APP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'app')

# All replacements needed (old_string -> new_string)
# These are specific enough to avoid false positives
REPLACEMENTS = [
    # Class-based pattern (foxcigar-style): bracket access on DataFrame
    ("self.master_df['Box Quantity']", "self.master_df['box_quantity']"),
    
    # Class-based pattern: row.get() calls in get_cigar_metadata()
    ("row.get('Box Quantity'", "row.get('box_quantity'"),
    ("row.get('Brand'", "row.get('brand'"),
    ("row.get('Line'", "row.get('line'"),
    ("row.get('Wrapper'", "row.get('wrapper'"),
    ("row.get('Vitola'", "row.get('vitola'"),
    ("row.get('Length'", "row.get('length'"),
    ("row.get('Ring Gauge'", "row.get('ring_gauge'"),
    
    # Function-based pattern (holts-style): field_mapping dict values
    ("'brand': 'Brand'", "'brand': 'brand'"),
    ("'line': 'Line'", "'line': 'line'"),
    ("'wrapper': 'Wrapper'", "'wrapper': 'wrapper'"),
    ("'vitola': 'Vitola'", "'vitola': 'vitola'"),
    ("'box_qty': 'Box Quantity'", "'box_qty': 'box_quantity'"),
    
    # Function-based pattern: data.get() in lambda for size field
    ("data.get('Length'", "data.get('length'"),
    ("data.get('Ring Gauge'", "data.get('ring_gauge'"),
    
    # master_data.get() variant used in some scripts
    ("master_data.get('Box Quantity'", "master_data.get('box_quantity'"),
    ("master_data.get('Brand'", "master_data.get('brand'"),
    ("master_data.get('Line'", "master_data.get('line'"),
    ("master_data.get('Wrapper'", "master_data.get('wrapper'"),
    ("master_data.get('Vitola'", "master_data.get('vitola'"),
    ("master_data.get('Length'", "master_data.get('length'"),
    ("master_data.get('Ring Gauge'", "master_data.get('ring_gauge'"),
]


def fix_file(filepath):
    """Apply all replacements to a single file. Returns count of changes."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    changes = 0
    
    for old, new in REPLACEMENTS:
        count = content.count(old)
        if count > 0:
            content = content.replace(old, new)
            changes += count
    
    if changes > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    return changes


def main():
    # Find all update_*.py files in app/ (not recursing into subdirs we don't want)
    patterns = [
        os.path.join(APP_DIR, 'update_*.py'),
        os.path.join(APP_DIR, 'railway_deployment', 'app', 'update_*.py'),
    ]
    
    all_files = []
    for pattern in patterns:
        all_files.extend(glob.glob(pattern))
    
    all_files.sort()
    
    print(f"Scanning {len(all_files)} update scripts for column name fixes\n")
    
    total_changes = 0
    files_modified = 0
    
    for fpath in all_files:
        fname = os.path.basename(fpath)
        parent = os.path.basename(os.path.dirname(fpath))
        label = f"{parent}/{fname}" if parent != 'app' else fname
        
        changes = fix_file(fpath)
        if changes > 0:
            print(f"  OK   {label}: {changes} replacements")
            files_modified += 1
            total_changes += changes
        else:
            print(f"  SKIP {label}: no changes needed")
    
    print(f"\n=== Summary ===")
    print(f"  Files modified: {files_modified}")
    print(f"  Total replacements: {total_changes}")


if __name__ == '__main__':
    main()
