#!/usr/bin/env python3
"""
SQLite to CSV Exporter
Export historical database to CSV files for Excel/Google Sheets analysis
"""

import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path

def export_to_csv():
    """Export all tables to CSV files for Excel analysis"""
    
    db_path = Path('../../data/historical_prices.db')
    output_dir = Path('../../data/csv_exports')
    
    if not db_path.exists():
        print(f"Database not found at: {db_path}")
        return
    
    # Create output directory
    output_dir.mkdir(exist_ok=True)
    
    print("=" * 60)
    print("EXPORTING SQLITE DATA TO CSV FILES")
    print("=" * 60)
    print(f"Database: {db_path}")
    print(f"Output directory: {output_dir}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    conn = sqlite3.connect(db_path)
    
    try:
        # Export main tables
        tables_to_export = [
            'price_history',
            'price_changes', 
            'stock_changes',
            'automation_runs'
        ]
        
        for table in tables_to_export:
            try:
                # Check if table has data
                count_df = pd.read_sql(f"SELECT COUNT(*) as count FROM {table}", conn)
                count = count_df['count'].iloc[0]
                
                if count > 0:
                    # Export table
                    df = pd.read_sql(f"SELECT * FROM {table}", conn)
                    
                    # Add timestamp to filename
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{table}_{timestamp}.csv"
                    filepath = output_dir / filename
                    
                    df.to_csv(filepath, index=False)
                    print(f"Exported {table}: {count:,} records -> {filename}")
                else:
                    print(f"Skipped {table}: No data")
                    
            except Exception as e:
                print(f"Error exporting {table}: {e}")
        
        # Create analysis-ready views
        print("\n" + "=" * 40)
        print("CREATING ANALYSIS-READY VIEWS")
        print("=" * 40)
        
        # Daily price summary
        try:
            daily_summary = pd.read_sql("""
            SELECT 
                date,
                cigar_id,
                COUNT(*) as retailers_tracking,
                ROUND(AVG(price), 2) as avg_price,
                ROUND(MIN(price), 2) as min_price,
                ROUND(MAX(price), 2) as max_price,
                ROUND(MAX(price) - MIN(price), 2) as price_spread,
                ROUND(((MAX(price) - MIN(price)) / AVG(price)) * 100, 1) as spread_pct,
                SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) as in_stock_count,
                SUM(CASE WHEN in_stock = 0 THEN 1 ELSE 0 END) as out_of_stock_count
            FROM price_history 
            GROUP BY date, cigar_id
            ORDER BY date DESC, avg_price DESC
            """, conn)
            
            if not daily_summary.empty:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"daily_price_summary_{timestamp}.csv"
                filepath = output_dir / filename
                daily_summary.to_csv(filepath, index=False)
                print(f"Created daily price summary: {len(daily_summary):,} rows -> {filename}")
        
        except Exception as e:
            print(f"Error creating daily summary: {e}")
        
        # Retailer performance summary
        try:
            retailer_summary = pd.read_sql("""
            SELECT 
                retailer,
                COUNT(DISTINCT cigar_id) as unique_cigars,
                COUNT(DISTINCT date) as days_active,
                COUNT(*) as total_records,
                ROUND(AVG(price), 2) as avg_price,
                ROUND(MIN(price), 2) as lowest_price,
                ROUND(MAX(price), 2) as highest_price,
                ROUND(SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as stock_rate_pct,
                MIN(date) as first_tracked,
                MAX(date) as last_tracked
            FROM price_history 
            GROUP BY retailer
            ORDER BY unique_cigars DESC, avg_price ASC
            """, conn)
            
            if not retailer_summary.empty:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"retailer_summary_{timestamp}.csv"
                filepath = output_dir / filename
                retailer_summary.to_csv(filepath, index=False)
                print(f"Created retailer summary: {len(retailer_summary):,} rows -> {filename}")
        
        except Exception as e:
            print(f"Error creating retailer summary: {e}")
        
        # Price trend analysis (when you have multiple days)
        try:
            price_trends = pd.read_sql("""
            SELECT 
                cigar_id,
                retailer,
                COUNT(*) as days_tracked,
                GROUP_CONCAT(date || ':' || price, ', ') as price_timeline,
                ROUND(AVG(price), 2) as avg_price,
                ROUND(MIN(price), 2) as min_price,
                ROUND(MAX(price), 2) as max_price,
                CASE 
                    WHEN COUNT(*) > 1 THEN 
                        ROUND((MAX(price) - MIN(price)), 2)
                    ELSE 0 
                END as price_volatility
            FROM price_history 
            GROUP BY cigar_id, retailer
            HAVING COUNT(*) >= 1
            ORDER BY price_volatility DESC, avg_price DESC
            """, conn)
            
            if not price_trends.empty:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"price_trends_{timestamp}.csv"
                filepath = output_dir / filename
                price_trends.to_csv(filepath, index=False)
                print(f"Created price trends: {len(price_trends):,} rows -> {filename}")
        
        except Exception as e:
            print(f"Error creating price trends: {e}")
        
        print(f"\nAll files exported to: {output_dir.absolute()}")
        print("\nYou can now:")
        print("   1. Open CSV files in Excel/Google Sheets")
        print("   2. Create pivot tables and charts")
        print("   3. Perform your own analysis")
        print("   4. Verify Claude's analysis independently")
        
    except Exception as e:
        print(f"❌ Error accessing database: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    export_to_csv()
