#!/usr/bin/env python3
"""
Simple CSV Price Updater - Direct Updates Only
Updates existing CSV files directly with new pricing data
"""

import pandas as pd
import os

def update_csvs():
    """Update existing CSV files with new pricing data"""
    
    csv_directory = "static/data"
    
    # Hemingway pricing updates
    updates = [
        {
            'file': 'tampasweethearts.csv',
            'url': 'https://www.tampasweethearts.com/hemingwayclassic.aspx',
            'price': 273.95,
            'in_stock': True
        },
        {
            'file': 'smokeinn.csv', 
            'url': 'https://www.smokeinn.com/arturo-fuente-cigars/fuente-hemingway-classics.html',
            'price': 273.95,
            'in_stock': True
        },
        {
            'file': 'atlantic.csv',
            'url': 'https://atlanticcigar.com/arturo-fuente-hemingway-classic-natural/',
            'price': 272.95,
            'in_stock': True
        },
        {
            'file': 'cuencacigars.csv',
            'url': 'https://www.cuencacigars.com/arturo-fuente-hemingway-v-classic-cigars-box-of-25/',
            'price': 273.94,
            'in_stock': False
        },
        {
            'file': 'cigarboxpa.csv',
            'url': 'https://www.cigarboxpa.com/af-hemingway-signature-natural-box.html',
            'price': 0.00,
            'in_stock': False
        },
        {
            'file': 'cigarhustler.csv',
            'url': 'https://cigarhustler.com/arturo-fuente-hemingway-c-1_178/arturo-fuente-hemingway-classic-v-natural-cigar-box-p-4927.html',
            'price': 314.88,
            'in_stock': False
        }
    ]
    
    # Process each update
    for update in updates:
        file_path = os.path.join(csv_directory, update['file'])
        
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            
            # Find row by URL
            mask = df['url'] == update['url']
            
            if mask.any():
                # Update price and stock status
                df.loc[mask, 'price'] = update['price']
                df.loc[mask, 'in_stock'] = update['in_stock']
                
                # Save directly back to file
                df.to_csv(file_path, index=False)
                print(f"Updated {update['file']}: ${update['price']} (in_stock: {update['in_stock']})")
            else:
                print(f"URL not found in {update['file']}")
        else:
            print(f"File not found: {update['file']}")

if __name__ == "__main__":
    update_csvs()
