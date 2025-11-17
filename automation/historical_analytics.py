#!/usr/bin/env python3
"""
Historical Price Analytics Script
Query and analyze collected historical pricing data for retailer performance insights
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

class HistoricalPriceAnalyzer:
    def __init__(self, db_path="data/historical_prices.db"):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            print(f"Historical database not found at {self.db_path}")
            print("Make sure historical data collection has started.")
            self.db_available = False
        else:
            self.db_available = True
    
    def get_connection(self):
        """Get database connection"""
        if not self.db_available:
            return None
        return sqlite3.connect(self.db_path)
    
    def get_data_summary(self):
        """Get overview of collected data"""
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            query = '''
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT retailer) as unique_retailers,
                COUNT(DISTINCT cigar_id) as unique_cigars,
                MIN(timestamp) as first_record,
                MAX(timestamp) as latest_record,
                COUNT(DISTINCT DATE(timestamp)) as days_collected
            FROM price_history
            '''
            
            result = pd.read_sql_query(query, conn)
            conn.close()
            
            return result.iloc[0].to_dict()
            
        except Exception as e:
            print(f"Error getting data summary: {e}")
            conn.close()
            return None
    
    def get_retailer_performance(self, days=30):
        """Get retailer performance metrics for the last N days"""
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            query = '''
            SELECT 
                retailer,
                COUNT(*) as total_observations,
                COUNT(DISTINCT cigar_id) as products_tracked,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price,
                COUNT(CASE WHEN in_stock = 1 THEN 1 END) as in_stock_count,
                COUNT(CASE WHEN in_stock = 1 THEN 1 END) * 100.0 / COUNT(*) as stock_rate,
                COUNT(DISTINCT DATE(timestamp)) as days_active
            FROM price_history 
            WHERE timestamp > ?
              AND price IS NOT NULL
            GROUP BY retailer
            ORDER BY stock_rate DESC, avg_price ASC
            '''
            
            result = pd.read_sql_query(query, conn, params=[cutoff_date])
            conn.close()
            
            return result
            
        except Exception as e:
            print(f"Error getting retailer performance: {e}")
            conn.close()
            return None
    
    def get_price_trends(self, cigar_id, days=30):
        """Get price trends for a specific cigar over time"""
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            query = '''
            SELECT 
                retailer,
                DATE(timestamp) as date,
                price,
                in_stock
            FROM price_history 
            WHERE cigar_id = ?
              AND timestamp > ?
              AND price IS NOT NULL
            ORDER BY timestamp DESC
            '''
            
            result = pd.read_sql_query(query, conn, params=[cigar_id, cutoff_date])
            conn.close()
            
            return result
            
        except Exception as e:
            print(f"Error getting price trends: {e}")
            conn.close()
            return None
    
    def get_top_cigars_by_tracking(self, limit=20):
        """Get most tracked cigars (most retailer coverage)"""
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            query = '''
            SELECT 
                cigar_id,
                brand,
                line,
                wrapper,
                vitola,
                COUNT(DISTINCT retailer) as retailer_count,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price,
                COUNT(CASE WHEN in_stock = 1 THEN 1 END) * 100.0 / COUNT(*) as avg_stock_rate
            FROM price_history 
            WHERE price IS NOT NULL
            GROUP BY cigar_id, brand, line, wrapper, vitola
            HAVING COUNT(DISTINCT retailer) > 2
            ORDER BY retailer_count DESC, avg_stock_rate DESC
            LIMIT ?
            '''
            
            result = pd.read_sql_query(query, conn, params=[limit])
            conn.close()
            
            return result
            
        except Exception as e:
            print(f"Error getting top cigars: {e}")
            conn.close()
            return None
    
    def get_stock_out_events(self, days=7):
        """Get recent stock-out events"""
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            query = '''
            SELECT 
                retailer,
                brand,
                line,
                wrapper,
                vitola,
                price,
                timestamp
            FROM price_history 
            WHERE timestamp > ?
              AND in_stock = 0
              AND price IS NOT NULL
            ORDER BY timestamp DESC
            '''
            
            result = pd.read_sql_query(query, conn, params=[cutoff_date])
            conn.close()
            
            return result
            
        except Exception as e:
            print(f"Error getting stock-out events: {e}")
            conn.close()
            return None

def main():
    """Demo analysis functions"""
    analyzer = HistoricalPriceAnalyzer()
    
    if not analyzer.db_available:
        print("❌ Historical database not available")
        print("Deploy the enhanced automation_master.py and wait for the next automation run.")
        return
    
    print("📊 HISTORICAL PRICE ANALYTICS")
    print("=" * 50)
    
    # Data summary
    summary = analyzer.get_data_summary()
    if summary:
        print(f"📈 Data Collection Status:")
        print(f"  Total Records: {summary['total_records']:,}")
        print(f"  Retailers: {summary['unique_retailers']}")
        print(f"  Unique Cigars: {summary['unique_cigars']}")
        print(f"  Days Collected: {summary['days_collected']}")
        print(f"  First Record: {summary['first_record'][:10]}")
        print(f"  Latest Record: {summary['latest_record'][:10]}")
        print()
    
    # Retailer performance
    performance = analyzer.get_retailer_performance(30)
    if performance is not None and not performance.empty:
        print("🏪 Retailer Performance (Last 30 Days):")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        print(performance.round(2))
        print()
    
    # Top tracked cigars
    top_cigars = analyzer.get_top_cigars_by_tracking(10)
    if top_cigars is not None and not top_cigars.empty:
        print("🔥 Most Tracked Cigars:")
        for _, row in top_cigars.iterrows():
            print(f"  {row['brand']} {row['line']} ({row['wrapper']}) - "
                  f"{row['retailer_count']} retailers, "
                  f"${row['avg_price']:.2f} avg, "
                  f"{row['avg_stock_rate']:.1f}% in stock")
        print()
    
    # Recent stock-outs
    stock_outs = analyzer.get_stock_out_events(7)
    if stock_outs is not None and not stock_outs.empty:
        print("🚨 Recent Stock-Outs (Last 7 Days):")
        for _, row in stock_outs.head(10).iterrows():
            print(f"  {row['retailer']}: {row['brand']} {row['line']} "
                  f"({row['wrapper']}) - ${row['price']:.2f} - {row['timestamp'][:16]}")
    
    print("\n✅ Analysis complete!")
    print("Run this script regularly to monitor retailer performance and market trends.")

if __name__ == "__main__":
    main()
