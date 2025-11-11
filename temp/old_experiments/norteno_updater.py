#!/usr/bin/env python3
"""
Herrera Esteli Norteno Lonsdale Updates
Updates prices and deletes discontinued products
"""

import pandas as pd
import os

def update_norteno_csvs():
    """Update Herrera Esteli Norteno pricing and remove discontinued products"""
    
    csv_directory = "static/data"
    
    # Updates: price changes and stock status
    updates = [
        {
            'file': 'niceashcigars.csv',
            'url': 'https://www.niceashcigars.com/product-p/hen6544d.htm',
            'price': None,  # Keep same price, just update stock
            'in_stock': True
        },
        {
            'file': 'smokeinn.csv', 
            'url': 'https://www.smokeinn.com/Drew-Estate-Herrera-Esteli-Norteno/',
            'price': 229.95,
            'in_stock': True
        }
    ]
    
    # Deletions: products no longer offered
    deletions = [
        {
            'file': 'nickscigarworld.csv',
            'url': 'https://nickscigarworld.com/shop/premium-cigars/herrera-esteli-norteno/herrera-esteli-norteno-lonsdale-deluxe/'
        },
        {
            'file': 'ci.csv',  # cigars international
            'url': 'https://www.cigarsinternational.com/p/drew-estate-herrera-esteli-norteno-cigars/2016372/'
        },
        {
            'file': 'cubancrafters.csv',
            'url': 'https://cubancrafters.com/drew-estate-herrera-esteli-norteno-lonsdale-deluxe-6-x-44/'
        }
    ]
    
    # Process updates
    print("=== PRICE UPDATES ===")
    for update in updates:
        file_path = os.path.join(csv_directory, update['file'])
        
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            
            # Find row by URL
            mask = df['url'] == update['url']
            
            if mask.any():
                # Update price if specified
                if update['price'] is not None:
                    old_price = df.loc[mask, 'price'].iloc[0]
                    df.loc[mask, 'price'] = update['price']
                    print(f"Updated {update['file']}: ${old_price} -> ${update['price']}")
                
                # Update stock status
                df.loc[mask, 'in_stock'] = update['in_stock']
                print(f"Updated {update['file']}: in_stock = {update['in_stock']}")
                
                # Save changes
                df.to_csv(file_path, index=False)
            else:
                print(f"URL not found in {update['file']}")
        else:
            print(f"File not found: {update['file']}")
    
    # Process deletions
    print("\n=== PRODUCT DELETIONS ===")
    for deletion in deletions:
        file_path = os.path.join(csv_directory, deletion['file'])
        
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            original_count = len(df)
            
            # Find and remove row by URL
            mask = df['url'] == deletion['url']
            
            if mask.any():
                df = df[~mask]  # Remove matching rows
                new_count = len(df)
                
                # Save updated file
                df.to_csv(file_path, index=False)
                print(f"Deleted from {deletion['file']}: {original_count} -> {new_count} rows (-{original_count - new_count})")
            else:
                print(f"URL not found in {deletion['file']} (already removed?)")
        else:
            print(f"File not found: {deletion['file']}")
    
    print("\n=== HERRERA ESTELI NORTENO UPDATES COMPLETE ===")

if __name__ == "__main__":
    update_norteno_csvs()
