#!/usr/bin/env python3
"""
Hoyo de Monterrey Excalibur Pricing Updates
Updates pricing across multiple retailers
"""

import pandas as pd
import os

def update_excalibur_csvs():
    """Update Hoyo de Monterrey Excalibur pricing"""
    
    csv_directory = "static/data"
    
    # Excalibur pricing updates
    updates = [
        {
            'file': 'holts.csv',
            'url': 'https://www.holts.com/cigars/all-cigar-brands/excalibur.html',
            'price': 160.04,
            'in_stock': True
        },
        {
            'file': 'bonitasmokeshop.csv',
            'url': 'https://bonitasmokeshop.com/hoyo-de-monterrey-excalibur-epicure-natural-5-25x50/',
            'price': 159.92,
            'in_stock': True
        },
        {
            'file': 'neptune.csv',
            'url': 'https://www.neptunecigar.com/excalibur-cigar',
            'price': 164.80,
            'in_stock': True
        },
        {
            'file': 'bestcigar.csv',
            'url': 'https://www.bestcigarprices.com/cigar-directory/excalibur-cigars/excalibur-epicures-natural-4656/?srsltid=AfmBOop7KES4yE9fKdqWK3TCszTftBCre-lqwSNlzTiLh5ITpuPRdypk',
            'price': 160.99,
            'in_stock': True
        },
        {
            'file': 'absolutecigars.csv',
            'url': 'https://absolutecigars.com/product/hoyo-de-monterrey-excalibur-epicure-natural/',
            'price': 203.00,
            'in_stock': True
        },
        {
            'file': 'cigar.csv',
            'url': 'https://www.cigar.com/product/hoyo-excalibur/HEA-PM.html?redirectedUrl=%2Fp%2Fhoyo-excalibur-cigars%2F1411249%2F&',
            'price': 162.99,
            'in_stock': True
        },
        {
            'file': 'pipesandcigars.csv',
            'url': 'https://www.pipesandcigars.com/product/hoyo-excalibur/HEA-PM.html',
            'price': 162.99,
            'in_stock': True
        },
        {
            'file': 'ci.csv',
            'url': 'https://www.cigarsinternational.com/p/excalibur-cigars/1411249/',
            'price': 162.99,
            'in_stock': True
        },
        {
            'file': 'cubancrafters.csv',
            'url': 'https://cubancrafters.com/hoyo-de-monterrey-excalibur-english-claro-epicure-5-1-4-x-50/',
            'price': 214.20,
            'in_stock': True
        }
    ]
    
    print("=== HOYO DE MONTERREY EXCALIBUR PRICING UPDATES ===")
    
    # Process each update
    for update in updates:
        file_path = os.path.join(csv_directory, update['file'])
        
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            
            # Find row by URL
            mask = df['url'] == update['url']
            
            if mask.any():
                # Get old price for comparison
                old_price = df.loc[mask, 'price'].iloc[0]
                
                # Update price and stock status
                df.loc[mask, 'price'] = update['price']
                df.loc[mask, 'in_stock'] = update['in_stock']
                
                # Save changes
                df.to_csv(file_path, index=False)
                print(f"Updated {update['file']}: ${old_price} -> ${update['price']}")
            else:
                print(f"URL not found in {update['file']}")
        else:
            print(f"File not found: {update['file']}")
    
    print("\n=== PRICING COMPARISON ===")
    print("Best price: bonitasmokeshop.com at $159.92")
    print("Highest price: cubancrafters.com at $214.20")
    print("Price range: $54.28 spread")
    print("\n=== EXCALIBUR UPDATES COMPLETE ===")

if __name__ == "__main__":
    update_excalibur_csvs()
