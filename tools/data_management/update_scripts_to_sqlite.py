#!/usr/bin/env python3
"""
One-time script to update all update_*.py scripts to read from SQLite instead of CSV.
Changes:
1. master_cigars.csv -> master_cigars.db in path references
2. pd.read_csv(path) -> pd.read_sql_query("SELECT * FROM cigars", conn)
3. Adds sqlite3 import if missing
"""

import glob
import re

updated_files = []

for filepath in sorted(glob.glob('app/update_*.py')):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Skip files that don't reference master_cigars
    if 'master_cigars' not in content:
        continue
    
    # 1. Add sqlite3 import if not present
    if 'import sqlite3' not in content:
        if 'import pandas as pd' in content:
            content = content.replace('import pandas as pd', 'import pandas as pd\nimport sqlite3', 1)
        elif 'import pd' in content:
            content = content.replace('import pandas', 'import pandas\nimport sqlite3', 1)
    
    # 2. Change .csv to .db in path strings
    content = content.replace("master_cigars.csv", "master_cigars.db")
    
    # 3. Replace pd.read_csv with pd.read_sql_query (class-based pattern)
    content = content.replace(
        'self.master_df = pd.read_csv(self.master_path)',
        'conn = sqlite3.connect(self.master_path)\n            self.master_df = pd.read_sql_query("SELECT * FROM cigars", conn)\n            conn.close()'
    )
    
    # 4. Replace pd.read_csv with pd.read_sql_query (function-based pattern)
    content = content.replace(
        'master_df = pd.read_csv(master_path)',
        'conn = sqlite3.connect(master_path)\n        master_df = pd.read_sql_query("SELECT * FROM cigars", conn)\n        conn.close()'
    )
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        updated_files.append(filepath)
        print(f"Updated: {filepath}")

print(f"\nTotal files updated: {len(updated_files)}")
