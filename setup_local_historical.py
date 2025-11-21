#!/usr/bin/env python3
"""
Setup script to initialize local historical database for testing
Run this from your cigar-price-scout directory
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime

def create_local_historical_db():
    """Create local historical database with proper structure"""
    
    # Create data directory if it doesn't exist
    data_dir = Path('data')
    data_dir.mkdir(exist_ok=True)
    
    db_path = data_dir / 'historical_prices.db'
    
    print(f"Creating historical database at: {db_path.absolute()}")
    
    # Create database and tables
    conn = sqlite3.connect(str(db_path))
    
    # Create price_history table (matching your automation_master.py schema)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            cigar_id TEXT NOT NULL,
            retailer TEXT NOT NULL,
            price REAL,
            in_stock BOOLEAN,
            box_qty INTEGER,
            title TEXT,
            brand TEXT,
            line TEXT,
            wrapper TEXT,
            vitola TEXT,
            size TEXT,
            url TEXT,
            UNIQUE(timestamp, cigar_id, retailer)
        )
    ''')
    
    # Create indexes for performance
    conn.execute('CREATE INDEX IF NOT EXISTS idx_retailer_timestamp ON price_history(retailer, timestamp)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cigar_timestamp ON price_history(cigar_id, timestamp)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_brand_line ON price_history(brand, line)')
    
    conn.commit()
    
    # Insert a test record to verify it works
    test_record = (
        datetime.now().isoformat(),
        'PADRON|1964|ANNIVERSARY|PRINCIPE|NATURAL|ROBUSTO|25',
        'test_retailer',
        299.99,
        1,
        25,
        'Padron 1964 Anniversary Principe Natural (Robusto)',
        'Padron',
        '1964 Anniversary',
        'Natural',
        'Principe', 
        '5.5 x 50',
        'https://example.com/test'
    )
    
    conn.execute('''
        INSERT OR REPLACE INTO price_history 
        (timestamp, cigar_id, retailer, price, in_stock, box_qty, 
         title, brand, line, wrapper, vitola, size, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', test_record)
    
    conn.commit()
    conn.close()
    
    print("SUCCESS: Historical database created successfully!")
    print(f"   Location: {db_path.absolute()}")
    print("   Test record inserted")
    print("\nNext steps:")
    print("1. Run: python historical_analytics.py")
    print("2. Check Railway logs to see if automation is running")
    print("3. Enable the scheduler in main.py if needed")

def check_csv_data():
    """Check if we have any current CSV data to populate historical database"""
    # Try multiple possible locations
    possible_locations = [
        Path('app/static/data'),
        Path('static/data'),
        Path('app') / 'static' / 'data'
    ]
    
    csv_files = []
    static_data_dir = None
    
    for location in possible_locations:
        if location.exists():
            static_data_dir = location
            csv_files = list(location.glob('*.csv'))
            break
    
    if static_data_dir and csv_files:
        print(f"\nFound {len(csv_files)} CSV files in {static_data_dir}/")
        for csv_file in csv_files[:5]:  # Show first 5
            print(f"  - {csv_file.name}")
        if len(csv_files) > 5:
            print(f"  ... and {len(csv_files) - 5} more")
        
        return len(csv_files) > 0
    else:
        print(f"\nNo CSV files found. Checked locations:")
        for location in possible_locations:
            print(f"  - {location}")
        return False

if __name__ == "__main__":
    print("=== CIGAR PRICE SCOUT HISTORICAL DATABASE SETUP ===")
    print("Setting up local historical database for development/testing\n")
    
    # Check current directory
    current_dir = Path.cwd()
    print(f"Current directory: {current_dir}")
    
    # Look for project markers
    if not (current_dir / 'app' / 'main.py').exists():
        print("ERROR: app/main.py not found - are you in the cigar-price-scout root directory?")
        print("   Please run: cd /c/Users/briah/cigar-price-scout")
        print("   Expected structure: cigar-price-scout/app/main.py")
        exit(1)
    
    # Create database
    create_local_historical_db()
    
    # Check for CSV data
    has_csv_data = check_csv_data()
    
    if has_csv_data:
        print("\n💡 You have CSV data! Consider running a manual automation cycle:")
        print("   cd automation")
        print("   python automation_master.py manual")
    
    print("\nSUCCESS: Database setup complete!")
