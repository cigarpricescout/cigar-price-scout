# find_pricing_table.py - Locate pricing table in HTML files
import os
import re
from pathlib import Path

def find_pricing_tables():
    """Find and analyze pricing tables in HTML files"""
    
    print("Searching for pricing tables in HTML files...")
    print("=" * 60)
    
    # Look for HTML files
    html_files = []
    for root, dirs, files in os.walk("."):
        if any(skip_dir in root for skip_dir in ['.git', 'node_modules', '__pycache__']):
            continue
            
        for file in files:
            if file.endswith(('.html', '.htm')):
                file_path = os.path.join(root, file)
                html_files.append(file_path)
    
    print(f"Found {len(html_files)} HTML files:")
    for file_path in sorted(html_files):
        print(f"  {file_path}")
    
    print("\n" + "=" * 60)
    
    # Look for tables with pricing data
    table_files = []
    
    for file_path in html_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for table elements
            table_matches = re.findall(r'<table[^>]*>.*?</table>', content, re.DOTALL | re.IGNORECASE)
            
            if table_matches:
                print(f"\nFOUND TABLES IN: {file_path}")
                
                for i, table in enumerate(table_matches, 1):
                    print(f"\n  Table {i}:")
                    
                    # Extract table attributes
                    table_tag = re.search(r'<table[^>]*>', table, re.IGNORECASE)
                    if table_tag:
                        print(f"    Opening tag: {table_tag.group()}")
                    
                    # Look for headers that suggest pricing
                    headers = re.findall(r'<th[^>]*>(.*?)</th>', table, re.DOTALL | re.IGNORECASE)
                    if headers:
                        print(f"    Headers found: {len(headers)}")
                        for j, header in enumerate(headers):
                            clean_header = re.sub(r'<[^>]+>', '', header).strip()
                            print(f"      {j+1}. {clean_header}")
                    
                    # Check if this looks like a pricing table
                    is_pricing_table = any(keyword in table.lower() for keyword in [
                        'price', 'total', 'retailer', 'shipping', 'tax', '$', 'cost'
                    ])
                    
                    if is_pricing_table:
                        print(f"    >>> LIKELY PRICING TABLE <<<")
                        table_files.append((file_path, i, table))
                        
                        # Show first few rows
                        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL | re.IGNORECASE)
                        print(f"    Rows found: {len(rows)}")
                        
                        if len(rows) > 1:  # Skip header row
                            print(f"    Sample data row:")
                            first_data_row = rows[1] if len(rows) > 1 else rows[0]
                            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', first_data_row, re.DOTALL | re.IGNORECASE)
                            for k, cell in enumerate(cells[:6]):  # Show first 6 cells
                                clean_cell = re.sub(r'<[^>]+>', '', cell).strip()[:50]
                                print(f"      Cell {k+1}: {clean_cell}")
                    else:
                        print(f"    (Not a pricing table)")
            
        except Exception as e:
            print(f"Could not read {file_path}: {e}")
    
    print("\n" + "=" * 60)
    
    if table_files:
        print("PRICING TABLES SUMMARY:")
        for file_path, table_num, table_html in table_files:
            print(f"\nFile: {file_path}")
            print(f"Table: #{table_num}")
            
            # Extract current CSS classes/IDs
            table_tag = re.search(r'<table[^>]*>', table_html, re.IGNORECASE)
            if table_tag:
                tag = table_tag.group()
                class_match = re.search(r'class=["\']([^"\']*)["\']', tag, re.IGNORECASE)
                id_match = re.search(r'id=["\']([^"\']*)["\']', tag, re.IGNORECASE)
                
                print(f"  Current classes: {class_match.group(1) if class_match else 'None'}")
                print(f"  Current ID: {id_match.group(1) if id_match else 'None'}")
                
                # Suggest what to change
                print(f"  RECOMMENDED UPDATE:")
                if class_match:
                    current_classes = class_match.group(1)
                    if 'price-table' not in current_classes:
                        new_classes = f"{current_classes} price-table"
                        print(f"    Change class to: '{new_classes.strip()}'")
                    else:
                        print(f"    Already has 'price-table' class - good!")
                else:
                    print(f"    Add class='price-table' to the <table> tag")
                
                # Check if it's wrapped in a container
                container_pattern = r'<div[^>]*>.*?<table[^>]*>.*?</table>.*?</div>'
                has_container = re.search(container_pattern, table_html, re.DOTALL | re.IGNORECASE)
                
                if not has_container:
                    print(f"    Wrap table in: <div class='price-table-container'>")
                
    else:
        print("No pricing tables found in HTML files.")
        print("\nThis might mean:")
        print("- Tables are generated dynamically by JavaScript")
        print("- Tables are in template files we didn't find") 
        print("- Tables are created by your Python backend")
        
        print("\nLet's also check for JavaScript files that might create tables...")
        
        # Look for JS files
        js_files = []
        for root, dirs, files in os.walk("."):
            if any(skip_dir in root for skip_dir in ['.git', 'node_modules', '__pycache__']):
                continue
                
            for file in files:
                if file.endswith('.js'):
                    file_path = os.path.join(root, file)
                    js_files.append(file_path)
        
        print(f"\nFound {len(js_files)} JavaScript files:")
        for file_path in sorted(js_files):
            print(f"  {file_path}")
            
        # Check JS files for table creation
        for file_path in js_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if any(keyword in content.lower() for keyword in ['table', 'price', 'retailer']):
                    print(f"\n  {file_path} might contain table logic")
                    
            except Exception as e:
                print(f"Could not read {file_path}: {e}")

if __name__ == "__main__":
    find_pricing_tables()