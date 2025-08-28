# bulk_import.py - Automatically add products to your CSV files
import csv
import os
from pathlib import Path

def add_products_to_csvs(product_data):
    """
    Takes your formatted product data and automatically adds it to the right CSV files.
    Creates new CSV files for new retailers if needed.
    """
    data_dir = Path("static/data")
    data_dir.mkdir(exist_ok=True)

    # Parse each line of product data
    for line in product_data.strip().split('\n'):
        if not line.strip():
            continue

        # Split the CSV line
        parts = line.split(',')
        if len(parts) < 8:
            print(f"Skipping invalid line: {line}")
            continue

        retailer_key = parts[0]
        retailer_name = parts[1] 
        url = parts[2]
        brand = parts[3]
        line_name = parts[4]
        size = parts[5]
        box_qty = parts[6]
        price = parts[7]

        # Create filename for this retailer
        csv_file = data_dir / f"{retailer_key}.csv"

        # Check if CSV exists, create with header if not
        if not csv_file.exists():
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['title', 'url', 'brand', 'line', 'size', 'box_qty', 'price', 'in_stock'])
            print(f"Created new CSV file: {csv_file}")

        # Create the title from the product info
        title = f"{brand} {line_name} {size} Box of {box_qty}"

        # Add the product to the CSV
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([title, url, brand, line_name, size, box_qty, price, 'true'])

        print(f"Added {title} to {retailer_name}")

def main():
    """
    Main function - paste your product data here and run the script
    """

    # PASTE YOUR FORMATTED PRODUCT DATA BETWEEN THE TRIPLE QUOTES BELOW:
    product_data = """
abcfws,ABC Fine Wine & Spirits,https://abcfws.com/cigars/padron-1964-anniversary-series-maduro-diplomatico-churchill/684271?srsltid=AfmBOor5XPK36rKJ8G5SbPZatR9p3w0I5hEJOPybCVUWt487-AEWqeTt,Padron,1964 Anniversary,7x50,25,404.79
"""

    if not product_data.strip():
        print("No product data found. Please paste your formatted data between the triple quotes above.")
        return

    print("Starting bulk import...")
    add_products_to_csvs(product_data)
    print("Import complete!")

    # List what CSV files now exist
    data_dir = Path("static/data")
    csv_files = list(data_dir.glob("*.csv"))
    print(f"\nYou now have {len(csv_files)} CSV files:")
    for file in sorted(csv_files):
        print(f"  - {file.name}")

if __name__ == "__main__":
    main()