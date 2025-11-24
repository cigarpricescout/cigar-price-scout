#!/usr/bin/env python3
"""
Cigar Price Analytics - Historical Data Review
Analyze pricing trends from the automation database
Windows-compatible version (no Unicode emojis)
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

class CigarPriceAnalytics:
    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = Path('../data/historical_prices.db')
        else:
            self.db_path = Path(db_path)
        
        if not self.db_path.exists():
            print(f"Database not found at: {self.db_path}")
            return
        
        self.conn = sqlite3.connect(self.db_path)
        print(f"Connected to database: {self.db_path}")

    def get_price_summary(self):
        """Get overall price summary"""
        print("\n" + "="*60)
        print("PRICE DATABASE SUMMARY")
        print("="*60)
        
        # Total records
        total_records = pd.read_sql("SELECT COUNT(*) as count FROM price_history", self.conn)
        print(f"Total price records: {total_records['count'].iloc[0]}")
        
        # Retailers covered
        retailers = pd.read_sql("SELECT COUNT(DISTINCT retailer) as count FROM price_history", self.conn)
        print(f"Retailers tracking: {retailers['count'].iloc[0]}")
        
        # Products covered
        products = pd.read_sql("SELECT COUNT(DISTINCT cigar_id) as count FROM price_history", self.conn)
        print(f"Unique products: {products['count'].iloc[0]}")
        
        # Date range
        date_range = pd.read_sql("SELECT MIN(date) as first, MAX(date) as last FROM price_history", self.conn)
        print(f"Date range: {date_range['first'].iloc[0]} to {date_range['last'].iloc[0]}")

    def get_highest_prices(self, limit=10):
        """Get highest priced cigars"""
        print(f"\nTOP {limit} HIGHEST PRICED CIGARS")
        print("-" * 50)
        
        query = """
        SELECT retailer, cigar_id, price, date, url
        FROM price_history 
        WHERE price IS NOT NULL 
        ORDER BY price DESC 
        LIMIT ?
        """
        
        high_prices = pd.read_sql(query, self.conn, params=(limit,))
        
        for i, row in high_prices.iterrows():
            print(f"{i+1:2d}. ${row['price']:8.2f} - {row['cigar_id']}")
            print(f"     {row['retailer']} ({row['date']})")
            print()

    def get_lowest_prices(self, limit=10):
        """Get lowest priced cigars"""
        print(f"\nTOP {limit} LOWEST PRICED CIGARS")
        print("-" * 50)
        
        query = """
        SELECT retailer, cigar_id, price, date, url
        FROM price_history 
        WHERE price > 0 
        ORDER BY price ASC 
        LIMIT ?
        """
        
        low_prices = pd.read_sql(query, self.conn, params=(limit,))
        
        for i, row in low_prices.iterrows():
            print(f"{i+1:2d}. ${row['price']:8.2f} - {row['cigar_id']}")
            print(f"     {row['retailer']} ({row['date']})")
            print()

    def get_price_changes_today(self):
        """Get price changes from today's run"""
        print("\nTODAY'S PRICE CHANGES")
        print("-" * 50)
        
        today = datetime.now().date()
        
        query = """
        SELECT retailer, cigar_id, old_price, new_price, price_change, change_type
        FROM price_changes 
        WHERE date = ?
        ORDER BY ABS(price_change) DESC
        """
        
        changes = pd.read_sql(query, self.conn, params=(today,))
        
        if changes.empty:
            print("No price changes recorded for today yet.")
            return
        
        for i, row in changes.iterrows():
            if row['change_type'] == 'increase':
                change_symbol = "[UP]"
            elif row['change_type'] == 'decrease':
                change_symbol = "[DOWN]"
            else:
                change_symbol = "[NEW]"
                
            print(f"{change_symbol} {row['retailer']}: {row['cigar_id']}")
            if row['change_type'] == 'new':
                print(f"   New product: ${row['new_price']:.2f}")
            else:
                print(f"   ${row['old_price']:.2f} -> ${row['new_price']:.2f} ({row['price_change']:+.2f})")
            print()

    def get_retailer_summary(self):
        """Get summary by retailer"""
        print("\nRETAILER SUMMARY")
        print("-" * 50)
        
        query = """
        SELECT 
            retailer,
            COUNT(*) as products,
            AVG(price) as avg_price,
            MIN(price) as min_price,
            MAX(price) as max_price
        FROM price_history 
        WHERE price > 0
        GROUP BY retailer 
        ORDER BY avg_price DESC
        """
        
        summary = pd.read_sql(query, self.conn)
        
        for i, row in summary.iterrows():
            print(f"{row['retailer']:20} {row['products']:3d} products  "
                  f"Avg: ${row['avg_price']:6.2f}  "
                  f"Range: ${row['min_price']:6.2f} - ${row['max_price']:6.2f}")

    def search_cigar(self, search_term):
        """Search for specific cigar pricing"""
        print(f"\nSEARCH RESULTS: '{search_term}'")
        print("-" * 50)
        
        query = """
        SELECT retailer, cigar_id, price, date, in_stock, url
        FROM price_history 
        WHERE LOWER(cigar_id) LIKE LOWER(?)
        ORDER BY price ASC
        """
        
        results = pd.read_sql(query, self.conn, params=(f'%{search_term}%',))
        
        if results.empty:
            print(f"No cigars found matching '{search_term}'")
            return
        
        print(f"Found {len(results)} results:")
        for i, row in results.iterrows():
            stock_status = "[IN STOCK]" if row['in_stock'] else "[OUT OF STOCK]"
            print(f"{stock_status} ${row['price']:8.2f} - {row['cigar_id']}")
            print(f"     {row['retailer']} ({row['date']})")
            print()

    def get_automation_history(self):
        """Get automation run history"""
        print("\nAUTOMATION RUN HISTORY")
        print("-" * 50)
        
        query = """
        SELECT run_date, retailers_attempted, retailers_successful, 
               products_updated, duration_seconds, git_push_successful
        FROM automation_runs 
        ORDER BY run_date DESC
        """
        
        runs = pd.read_sql(query, self.conn)
        
        if runs.empty:
            print("No automation runs recorded yet.")
            return
        
        for i, row in runs.iterrows():
            success_rate = (row['retailers_successful'] / row['retailers_attempted']) * 100
            git_status = "[SUCCESS]" if row['git_push_successful'] else "[FAILED]"
            
            print(f"Date: {row['run_date']}")
            print(f"   Retailers: {row['retailers_successful']}/{row['retailers_attempted']} ({success_rate:.0f}%)")
            print(f"   Products: {row['products_updated']} updated")
            print(f"   Duration: {row['duration_seconds']//60:.0f}m {row['duration_seconds']%60:.0f}s")
            print(f"   Git Push: {git_status}")
            print()

    def run_full_analysis(self):
        """Run complete analysis"""
        self.get_price_summary()
        self.get_automation_history()
        self.get_retailer_summary()
        self.get_price_changes_today()
        self.get_highest_prices(5)
        self.get_lowest_prices(5)

    def close(self):
        """Close database connection"""
        self.conn.close()


def main():
    print("CIGAR PRICE ANALYTICS")
    print("=" * 60)
    
    analytics = CigarPriceAnalytics()
    
    while True:
        print("\nChoose an option:")
        print("1. Full Analysis Report")
        print("2. Price Summary")
        print("3. Today's Price Changes")
        print("4. Highest Priced Cigars")
        print("5. Lowest Priced Cigars")
        print("6. Retailer Summary")
        print("7. Search for Specific Cigar")
        print("8. Automation History")
        print("9. Exit")
        
        choice = input("\nEnter choice (1-9): ").strip()
        
        if choice == '1':
            analytics.run_full_analysis()
        elif choice == '2':
            analytics.get_price_summary()
        elif choice == '3':
            analytics.get_price_changes_today()
        elif choice == '4':
            limit = input("How many top prices? (default 10): ").strip()
            limit = int(limit) if limit.isdigit() else 10
            analytics.get_highest_prices(limit)
        elif choice == '5':
            limit = input("How many lowest prices? (default 10): ").strip()
            limit = int(limit) if limit.isdigit() else 10
            analytics.get_lowest_prices(limit)
        elif choice == '6':
            analytics.get_retailer_summary()
        elif choice == '7':
            search_term = input("Enter cigar name to search: ").strip()
            if search_term:
                analytics.search_cigar(search_term)
        elif choice == '8':
            analytics.get_automation_history()
        elif choice == '9':
            break
        else:
            print("Invalid choice. Please try again.")
    
    analytics.close()
    print("\nGoodbye!")


if __name__ == "__main__":
    main()
