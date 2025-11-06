#!/usr/bin/env python3
"""
Cross-Retailer Comparison Checker
Validates that scraped products can be matched across multiple retailers
"""

import pandas as pd
import os
import glob
from collections import defaultdict

def check_cross_retailer_matches(static_data_dir="static/data"):
    """Check which products can be compared across retailers"""
    
    print("CROSS-RETAILER COMPARISON ANALYSIS")
    print("="*60)
    
    # Load all retailer CSV files
    retailer_files = glob.glob(os.path.join(static_data_dir, "*.csv"))
    retailer_files = [f for f in retailer_files if not f.endswith("master_comparison.csv")]
    
    if len(retailer_files) < 2:
        print(f"Need at least 2 retailer CSV files for comparison")
        print(f"Found: {len(retailer_files)} files")
        return
    
    # Track products by standardized key
    product_tracker = defaultdict(list)
    all_products = []
    
    for csv_file in retailer_files:
        retailer_name = os.path.basename(csv_file).replace('.csv', '').replace('_', ' ').title()
        
        try:
            df = pd.read_csv(csv_file)
            print(f"\nLoaded {len(df)} products from {retailer_name}")
            
            for _, row in df.iterrows():
                # Create standardized product key
                product_key = create_product_key(row)
                
                product_info = {
                    'retailer': retailer_name,
                    'title': row['title'],
                    'brand': row['brand'],
                    'line': row['line'],
                    'vitola': row['vitola'],
                    'size': row['size'],
                    'price': row['price'],
                    'box_qty': row['box_qty'],
                    'product_key': product_key
                }
                
                product_tracker[product_key].append(product_info)
                all_products.append(product_info)
                
        except Exception as e:
            print(f"Error loading {csv_file}: {e}")
    
    # Analyze comparability
    comparable_products = {k: v for k, v in product_tracker.items() if len(v) > 1}
    single_retailer_products = {k: v for k, v in product_tracker.items() if len(v) == 1}
    
    print(f"\n{'='*60}")
    print("COMPARISON ANALYSIS RESULTS")
    print(f"{'='*60}")
    print(f"Total unique products: {len(product_tracker)}")
    print(f"Products with multiple retailers: {len(comparable_products)}")
    print(f"Products from single retailer only: {len(single_retailer_products)}")
    print(f"Total retailer files: {len(retailer_files)}")
    
    if comparable_products:
        print(f"\nCOMPARABLE PRODUCTS (will show in comparison tables):")
        print("-" * 60)
        
        for product_key, retailers in comparable_products.items():
            product = retailers[0]  # Get first instance for details
            retailer_names = [r['retailer'] for r in retailers]
            prices = [f"${r['price']:.2f}" for r in retailers]
            
            print(f"{product['brand']} {product['line']} - {product['vitola']}")
            print(f"  Retailers: {', '.join(retailer_names)}")
            print(f"  Prices: {', '.join(prices)}")
            
            # Calculate price spread
            price_values = [r['price'] for r in retailers]
            min_price = min(price_values)
            max_price = max(price_values)
            savings = max_price - min_price
            
            if savings > 10:
                print(f"  💰 Potential savings: ${savings:.2f}")
            print()
    
    if single_retailer_products:
        print(f"\nSINGLE-RETAILER PRODUCTS (won't appear in comparison):")
        print("-" * 60)
        print("These products need matches from other retailers to be included:")
        
        retailer_counts = defaultdict(int)
        for retailers in single_retailer_products.values():
            retailer = retailers[0]['retailer']
            retailer_counts[retailer] += 1
        
        for retailer, count in retailer_counts.items():
            print(f"  {retailer}: {count} unique products")
    
    return comparable_products, single_retailer_products

def create_product_key(row):
    """Create standardized product key for matching"""
    brand = str(row.get('brand', '')).strip().lower()
    line = str(row.get('line', '')).strip().lower() 
    vitola = str(row.get('vitola', '')).strip().lower()
    size = str(row.get('size', '')).strip().lower()
    
    # Normalize common variations
    brand = brand.replace(' ', '_').replace('-', '_')
    line = line.replace(' ', '_').replace('-', '_')
    vitola = vitola.replace(' ', '_').replace('-', '_')
    
    return f"{brand}|{line}|{vitola}|{size}"

def generate_comparison_ready_csv(static_data_dir="static/data"):
    """Generate a CSV with only products that can be compared across retailers"""
    
    comparable_products, _ = check_cross_retailer_matches(static_data_dir)
    
    if not comparable_products:
        print("\nNo comparable products found across retailers")
        return None
    
    # Flatten comparable products for CSV
    comparison_data = []
    for product_key, retailers in comparable_products.items():
        for retailer_info in retailers:
            comparison_data.append(retailer_info)
    
    df = pd.DataFrame(comparison_data)
    
    # Reorder columns
    columns = ['title', 'brand', 'line', 'vitola', 'size', 'box_qty', 'price', 'retailer', 'product_key']
    df = df[columns]
    
    # Save comparison-ready CSV
    output_file = os.path.join(static_data_dir, "comparison_ready.csv")
    df.to_csv(output_file, index=False)
    
    print(f"\nGenerated comparison-ready CSV: {output_file}")
    print(f"Contains {len(df)} products from {len(comparable_products)} unique cigars")
    
    return output_file

if __name__ == "__main__":
    check_cross_retailer_matches()
    generate_comparison_ready_csv()
