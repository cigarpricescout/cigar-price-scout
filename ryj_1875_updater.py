#!/usr/bin/env python3
"""
Romeo y Julieta 1875 Pricing Updates
Updates pricing for RyJ 1875 Churchill
"""

import pandas as pd
import os

def update_ryj_1875_csvs():
    """Update Romeo y Julieta 1875 pricing"""
    
    csv_directory = "static/data"
    
    # Romeo y Julieta 1875 pricing updates
    updates = [
        {
            'file': 'nickscigarworld.csv',
            'url': 'https://nickscigarworld.com/shop/premium-cigars/romeo-y-julieta-1875/romeo-y-julieta-1875-churchill/',
            'price': 199.95,
            'in_stock': True
        },
        {
            'file': 'atlantic.csv',
            'url': 'https://atlanticcigar.com/romeo-y-julieta-1875-churchill/',
            'price': 174.04,
            'in_stock': True
        }
    ]
    
    print("=== ROMEO Y JULIETA 1875 PRICING UPDATES ===")
    
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
    print("Best price: Atlantic Cigar at $174.04")
    print("Higher price: Nick's Cigar World at $199.95")
    print("Price difference: $25.91 savings at Atlantic")
    print("\n=== ROMEO Y JULIETA 1875 UPDATES COMPLETE ===")

if __name__ == "__main__":
    update_ryj_1875_csvs()
