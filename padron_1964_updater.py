#!/usr/bin/env python3
"""
Padron 1964 Anniversary Updates
Updates stock status and pricing
"""

import pandas as pd
import os

def update_padron_1964_csvs():
    """Update Padron 1964 Anniversary stock and pricing"""
    
    csv_directory = "static/data"
    
    # Padron 1964 Anniversary updates
    updates = [
        {
            'file': 'watchcity.csv',
            'url': 'https://watchcitycigar.com/padron-1964-anniversary-series-diplomatico-maduro-50-x-7/',
            'price': None,  # Keep existing price
            'in_stock': True  # Now in stock
        },
        {
            'file': 'abcfws.csv',
            'url': 'https://abcfws.com/cigars/padron-1964-anniversary-series-maduro-diplomatico-churchill/684271?srsltid=AfmBOor5XPK36rKJ8G5SbPZatR9p3w0I5hEJOPybCVUWt487-AEWqeTt',
            'price': None,  # Keep existing price
            'in_stock': True  # Now in stock
        },
        {
            'file': 'famous.csv',
            'url': 'https://www.famous-smoke.com/brand/padron-1964-anniversary-maduro-cigars/padron-1964-anniversary-maduro-diplomatico-cigars',
            'price': None,  # Keep existing price
            'in_stock': False  # Out of stock
        },
        {
            'file': 'cubancrafters.csv',
            'url': 'https://cubancrafters.com/padron-diplomatico-maduro-1964/',
            'price': 491.40,  # New price
            'in_stock': True
        }
    ]
    
    print("=== PADRON 1964 ANNIVERSARY UPDATES ===")
    
    # Process each update
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
                old_stock = df.loc[mask, 'in_stock'].iloc[0]
                df.loc[mask, 'in_stock'] = update['in_stock']
                stock_change = "IN STOCK" if update['in_stock'] else "OUT OF STOCK"
                print(f"Updated {update['file']}: stock status -> {stock_change}")
                
                # Save changes
                df.to_csv(file_path, index=False)
            else:
                print(f"URL not found in {update['file']}")
        else:
            print(f"File not found: {update['file']}")
    
    print("\n=== PADRON 1964 STOCK SUMMARY ===")
    print("NOW IN STOCK: Watch City Cigar, ABC Fine Wine & Spirits")
    print("OUT OF STOCK: Famous Smoke Shop")
    print("PRICE UPDATE: Cuban Crafters -> $491.40")
    print("\n=== PADRON 1964 UPDATES COMPLETE ===")

if __name__ == "__main__":
    update_padron_1964_csvs()
