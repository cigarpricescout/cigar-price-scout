#!/usr/bin/env python3
"""
Database Optimization for Long-term Scalability
Optimize the database structure for years of data collection
"""

import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path

def optimize_database():
    """Optimize database structure for long-term use"""
    
    db_path = Path('../../data/historical_prices.db')
    
    if not db_path.exists():
        print(f"Database not found at: {db_path}")
        return
    
    print("=" * 70)
    print("DATABASE OPTIMIZATION FOR LONG-TERM SCALABILITY")
    print("=" * 70)
    
    conn = sqlite3.connect(db_path)
    
    try:
        # Create indexes for faster queries
        print("Creating performance indexes...")
        
        indexes = [
            ("idx_price_history_date", "CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(date)"),
            ("idx_price_history_retailer", "CREATE INDEX IF NOT EXISTS idx_price_history_retailer ON price_history(retailer)"),
            ("idx_price_history_cigar", "CREATE INDEX IF NOT EXISTS idx_price_history_cigar ON price_history(cigar_id)"),
            ("idx_price_history_date_retailer", "CREATE INDEX IF NOT EXISTS idx_price_history_date_retailer ON price_history(date, retailer)"),
            ("idx_price_history_date_cigar", "CREATE INDEX IF NOT EXISTS idx_price_history_date_cigar ON price_history(date, cigar_id)"),
            ("idx_price_changes_date", "CREATE INDEX IF NOT EXISTS idx_price_changes_date ON price_changes(date)"),
            ("idx_automation_runs_date", "CREATE INDEX IF NOT EXISTS idx_automation_runs_date ON automation_runs(run_date)")
        ]
        
        for index_name, sql in indexes:
            try:
                conn.execute(sql)
                print(f"Created index: {index_name}")
            except Exception as e:
                print(f"Index {index_name}: {e}")
        
        # Optimize database file
        print("\nOptimizing database file...")
        conn.execute("VACUUM")
        print("Database file optimized")
        
        # Create views for common queries
        print("\nCreating analysis views...")
        
        views = [
            ("daily_summary", """
                CREATE VIEW IF NOT EXISTS daily_summary AS
                SELECT 
                    date,
                    COUNT(*) as total_records,
                    COUNT(DISTINCT retailer) as active_retailers,
                    COUNT(DISTINCT cigar_id) as unique_cigars,
                    ROUND(AVG(price), 2) as avg_price,
                    ROUND(MIN(price), 2) as min_price,
                    ROUND(MAX(price), 2) as max_price,
                    SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) as in_stock_count,
                    SUM(CASE WHEN in_stock = 0 THEN 1 ELSE 0 END) as out_of_stock_count
                FROM price_history 
                GROUP BY date
                ORDER BY date DESC
            """),
            
            ("retailer_performance", """
                CREATE VIEW IF NOT EXISTS retailer_performance AS
                SELECT 
                    retailer,
                    COUNT(DISTINCT cigar_id) as products_tracked,
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
                ORDER BY products_tracked DESC, avg_price ASC
            """),
            
            ("current_market_prices", """
                CREATE VIEW IF NOT EXISTS current_market_prices AS
                SELECT 
                    cigar_id,
                    COUNT(*) as retailers_tracking,
                    ROUND(AVG(price), 2) as market_avg_price,
                    ROUND(MIN(price), 2) as lowest_price,
                    ROUND(MAX(price), 2) as highest_price,
                    ROUND(MAX(price) - MIN(price), 2) as price_spread,
                    ROUND(((MAX(price) - MIN(price)) / AVG(price)) * 100, 1) as spread_percentage,
                    SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) as in_stock_retailers,
                    SUM(CASE WHEN in_stock = 0 THEN 1 ELSE 0 END) as out_of_stock_retailers
                FROM price_history 
                WHERE date = (SELECT MAX(date) FROM price_history)
                GROUP BY cigar_id
                ORDER BY market_avg_price DESC
            """)
        ]
        
        for view_name, sql in views:
            try:
                conn.execute(sql)
                print(f"Created view: {view_name}")
            except Exception as e:
                print(f"View {view_name}: {e}")
        
        # Test query performance
        print("\nTesting query performance...")
        
        start_time = datetime.now()
        result = pd.read_sql("SELECT COUNT(*) as count FROM price_history", conn)
        query_time = (datetime.now() - start_time).total_seconds()
        
        print(f"Query test: {result['count'].iloc[0]:,} records in {query_time:.3f} seconds")
        
        # Storage analysis
        print("\nStorage analysis:")
        
        # Get file size
        db_size = db_path.stat().st_size
        print(f"Current size: {db_size / 1024:.1f} KB")
        
        # Estimate future growth
        records_count = result['count'].iloc[0]
        if records_count > 0:
            bytes_per_record = db_size / records_count
            
            # Project growth
            daily_records = 139  # Current daily volume
            annual_records = daily_records * 365
            five_year_records = annual_records * 5
            
            annual_size_mb = (annual_records * bytes_per_record) / (1024 * 1024)
            five_year_size_mb = (five_year_records * bytes_per_record) / (1024 * 1024)
            
            print(f"Bytes per record: {bytes_per_record:.1f}")
            print(f"Projected annual size: {annual_size_mb:.1f} MB")
            print(f"Projected 5-year size: {five_year_size_mb:.1f} MB")
            
            if five_year_size_mb > 1000:
                print("⚠️  Consider data archival strategy for 5+ year data")
            else:
                print("✅ Database size manageable for 5+ years")
        
        # Commit all changes
        conn.commit()
        
        print("\n" + "=" * 50)
        print("OPTIMIZATION COMPLETE")
        print("=" * 50)
        print("Database is now optimized for:")
        print("✅ Fast queries across years of data")
        print("✅ Efficient storage and growth")
        print("✅ Ready-made views for common analysis")
        print("✅ Professional reporting capabilities")
        
    except Exception as e:
        print(f"❌ Optimization error: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    optimize_database()
