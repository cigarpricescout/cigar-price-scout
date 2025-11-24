#!/usr/bin/env python3
"""
SQLite Database Viewer
View the structure and contents of historical_prices.db
"""

import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path

def view_database():
    """View the complete database structure and contents"""
    
    # Database location
    db_path = Path('../data/historical_prices.db')
    
    if not db_path.exists():
        print(f"Database not found at: {db_path}")
        print("Make sure you're running this from the automation/ folder")
        return
    
    print("=" * 70)
    print("SQLITE DATABASE VIEWER")
    print("=" * 70)
    print(f"Database location: {db_path.absolute()}")
    print(f"Database size: {db_path.stat().st_size / 1024:.1f} KB")
    print(f"Viewing at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    conn = sqlite3.connect(db_path)
    
    try:
        # Show all tables
        print("DATABASE TABLES:")
        print("-" * 30)
        tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
        for table in tables['name']:
            if table != 'sqlite_sequence':  # Skip system table
                count = pd.read_sql(f"SELECT COUNT(*) as count FROM {table}", conn)['count'].iloc[0]
                print(f"  {table}: {count:,} records")
        print()
        
        # Show price_history structure and sample data
        print("PRICE_HISTORY TABLE STRUCTURE:")
        print("-" * 40)
        
        # Get column info
        columns = pd.read_sql("PRAGMA table_info(price_history)", conn)
        print("Columns:")
        for _, col in columns.iterrows():
            print(f"  {col['name']}: {col['type']}")
        print()
        
        # Show data grouped by date
        print("DATA BY DATE:")
        print("-" * 40)
        
        date_summary = pd.read_sql("""
        SELECT 
            date,
            COUNT(*) as total_records,
            COUNT(DISTINCT retailer) as retailers,
            COUNT(DISTINCT cigar_id) as unique_cigars,
            MIN(created_at) as first_update,
            MAX(created_at) as last_update
        FROM price_history 
        GROUP BY date 
        ORDER BY date
        """, conn)
        
        if date_summary.empty:
            print("No data in price_history table yet")
        else:
            print("DATE         RECORDS  RETAILERS  CIGARS  FIRST UPDATE         LAST UPDATE")
            print("-" * 75)
            for _, row in date_summary.iterrows():
                print(f"{row['date']}     {row['total_records']:7d}      {row['retailers']:5d}   {row['unique_cigars']:6d}  "
                      f"{row['first_update'][:16]}  {row['last_update'][:16]}")
        
        print()
        
        # Show sample records from today
        print("SAMPLE RECORDS (First 5 from most recent date):")
        print("-" * 50)
        
        sample = pd.read_sql("""
        SELECT retailer, cigar_id, price, in_stock, date 
        FROM price_history 
        WHERE date = (SELECT MAX(date) FROM price_history)
        LIMIT 5
        """, conn)
        
        if not sample.empty:
            for _, row in sample.iterrows():
                cigar_short = row['cigar_id'][:50] + "..." if len(row['cigar_id']) > 50 else row['cigar_id']
                stock_status = "IN" if row['in_stock'] else "OUT"
                print(f"  {row['retailer']:15} ${row['price']:7.2f} [{stock_status:3}] {cigar_short}")
        
        print()
        
        # Show automation run history
        print("AUTOMATION RUNS:")
        print("-" * 30)
        
        runs = pd.read_sql("SELECT * FROM automation_runs ORDER BY run_date DESC LIMIT 10", conn)
        
        if runs.empty:
            print("No automation runs recorded")
        else:
            for _, row in runs.iterrows():
                success_rate = (row['retailers_successful'] / row['retailers_attempted']) * 100
                duration_min = row['duration_seconds'] // 60
                git_status = "SUCCESS" if row['git_push_successful'] else "FAILED"
                
                print(f"  {row['run_date']} {row['start_time'][11:19]}: "
                      f"{row['retailers_successful']}/{row['retailers_attempted']} retailers ({success_rate:.0f}%), "
                      f"{row['products_updated']} products, {duration_min}m, Git: {git_status}")
        
        print()
        
        # Show what tomorrow's data will look like
        print("TOMORROW'S DATA STRUCTURE:")
        print("-" * 30)
        print("When automation runs tomorrow, you'll see:")
        print("  - New rows in price_history with tomorrow's date")
        print("  - Each cigar will have entries for BOTH days")
        print("  - Price changes tracked in price_changes table")
        print("  - Stock changes tracked in stock_changes table")
        print()
        print("Example of how data accumulates:")
        print("  Day 1: 139 records (today)")  
        print("  Day 2: 278 records (today + tomorrow)")
        print("  Day 3: 417 records (3 days accumulated)")
        print("  etc...")
        
    except Exception as e:
        print(f"Error reading database: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    view_database()
