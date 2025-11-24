#!/usr/bin/env python3
"""
Cigar Business Intelligence Analytics
Focus on cigar-specific insights and retailer performance metrics

Key Questions This Answers:
1. What's the lowest/highest price for [specific cigar] in last 30 days?
2. Which retailer has best average pricing vs market?
3. How long do specific cigars stay out of stock per retailer?
4. What's the average market price for [specific cigar] to benchmark new retailers?
5. Which retailer has most stock-outs and loses potential clicks?
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

class CigarBusinessIntelligence:
    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = Path('../../data/historical_prices.db')
        else:
            self.db_path = Path(db_path)
        
        if not self.db_path.exists():
            print(f"Database not found at: {self.db_path}")
            print("Run the automation first to create historical data.")
            return
        
        self.conn = sqlite3.connect(self.db_path)

    def generate_business_report(self):
        """Generate business-focused analytics report"""
        print("=" * 80)
        print("CIGAR PRICE SCOUT - BUSINESS INTELLIGENCE REPORT")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        self._data_coverage_summary()
        self._retailer_performance_metrics()
        self._top_tracked_cigars_analysis()
        self._retailer_competitive_positioning()
        self._stock_availability_analysis()
        self._price_spread_analysis()
        
        print("=" * 80)
        print("END BUSINESS INTELLIGENCE REPORT")
        print("=" * 80)

    def _data_coverage_summary(self):
        """Current data coverage and monitoring status"""
        print("DATA COVERAGE SUMMARY")
        print("-" * 40)
        
        try:
            # Overall coverage
            coverage_query = """
            SELECT 
                COUNT(DISTINCT retailer) as retailers,
                COUNT(DISTINCT cigar_id) as unique_cigars,
                COUNT(*) as total_price_points,
                COUNT(DISTINCT date) as days_tracked,
                MIN(date) as start_date,
                MAX(date) as latest_date
            FROM price_history
            """
            
            coverage = pd.read_sql(coverage_query, self.conn)
            row = coverage.iloc[0]
            
            print(f"Active Retailers: {row['retailers']}")
            print(f"Unique Cigars: {row['unique_cigars']}")
            print(f"Total Price Points: {row['total_price_points']:,}")
            print(f"Days of Data: {row['days_tracked']}")
            print(f"Date Range: {row['start_date']} to {row['latest_date']}")
            
        except Exception as e:
            print(f"Error: {e}")
        
        print()

    def _retailer_performance_metrics(self):
        """Retailer performance: stock rates, product counts, competitive metrics"""
        print("RETAILER PERFORMANCE METRICS")
        print("-" * 40)
        
        try:
            retailer_query = """
            SELECT 
                retailer,
                COUNT(DISTINCT cigar_id) as products_monitored,
                COUNT(*) as total_data_points,
                ROUND(AVG(CASE WHEN in_stock = 1 THEN 100.0 ELSE 0.0 END), 1) as stock_rate_pct,
                COUNT(CASE WHEN in_stock = 0 THEN 1 END) as out_of_stock_instances,
                ROUND(AVG(price), 2) as avg_price_all_cigars,
                MIN(date) as first_tracked,
                MAX(date) as last_updated
            FROM price_history 
            WHERE price > 0
            GROUP BY retailer 
            ORDER BY products_monitored DESC, stock_rate_pct DESC
            """
            
            retailers = pd.read_sql(retailer_query, self.conn)
            
            if retailers.empty:
                print("No retailer data available")
                return
            
            print("RETAILER                 PRODUCTS  DATA PTS  STOCK RATE  OOS EVENTS  AVG PRICE")
            print("-" * 75)
            
            for _, row in retailers.iterrows():
                print(f"{row['retailer']:22} {row['products_monitored']:8d} {row['total_data_points']:8d} "
                      f"{row['stock_rate_pct']:9.1f}% {row['out_of_stock_instances']:10d} "
                      f"${row['avg_price_all_cigars']:8.2f}")
            
            # Stock performance summary
            avg_stock_rate = retailers['stock_rate_pct'].mean()
            total_oos_events = retailers['out_of_stock_instances'].sum()
            
            print()
            print(f"Network Average Stock Rate: {avg_stock_rate:.1f}%")
            print(f"Total Out-of-Stock Events: {total_oos_events}")
            
        except Exception as e:
            print(f"Error: {e}")
        
        print()

    def _top_tracked_cigars_analysis(self):
        """Analysis of most-tracked cigars and their market dynamics"""
        print("TOP TRACKED CIGARS ANALYSIS")
        print("-" * 40)
        
        try:
            # Find cigars tracked across most retailers
            cigar_coverage_query = """
            SELECT 
                cigar_id,
                COUNT(DISTINCT retailer) as retailer_count,
                COUNT(*) as total_price_points,
                ROUND(AVG(price), 2) as market_avg_price,
                ROUND(MIN(price), 2) as lowest_price,
                ROUND(MAX(price), 2) as highest_price,
                ROUND((MAX(price) - MIN(price)), 2) as price_spread,
                COUNT(CASE WHEN in_stock = 1 THEN 1 END) as in_stock_instances,
                COUNT(CASE WHEN in_stock = 0 THEN 1 END) as out_of_stock_instances
            FROM price_history 
            WHERE price > 0
            GROUP BY cigar_id 
            HAVING COUNT(DISTINCT retailer) >= 3
            ORDER BY retailer_count DESC, total_price_points DESC
            LIMIT 10
            """
            
            top_cigars = pd.read_sql(cigar_coverage_query, self.conn)
            
            if top_cigars.empty:
                print("Insufficient data - need cigars tracked across multiple retailers")
                return
            
            print("Most widely tracked cigars (3+ retailers):")
            print()
            
            for i, row in top_cigars.iterrows():
                cigar_name = row['cigar_id'][:50] + "..." if len(row['cigar_id']) > 50 else row['cigar_id']
                stock_rate = (row['in_stock_instances'] / (row['in_stock_instances'] + row['out_of_stock_instances'])) * 100
                
                print(f"{i+1}. {cigar_name}")
                print(f"   Retailers tracking: {row['retailer_count']} | "
                      f"Market avg: ${row['market_avg_price']} | "
                      f"Range: ${row['lowest_price']}-${row['highest_price']} | "
                      f"Spread: ${row['price_spread']}")
                print(f"   Market stock rate: {stock_rate:.1f}% | "
                      f"Total data points: {row['total_price_points']}")
                print()
                
        except Exception as e:
            print(f"Error: {e}")
        
        print()

    def _retailer_competitive_positioning(self):
        """Which retailers offer best pricing vs market average"""
        print("RETAILER COMPETITIVE POSITIONING")
        print("-" * 40)
        
        try:
            # For cigars tracked by multiple retailers, compare each retailer's pricing to market average
            positioning_query = """
            WITH market_prices AS (
                SELECT 
                    cigar_id,
                    AVG(price) as market_avg_price,
                    COUNT(DISTINCT retailer) as retailer_count
                FROM price_history 
                WHERE price > 0 AND in_stock = 1
                GROUP BY cigar_id 
                HAVING COUNT(DISTINCT retailer) >= 2
            ),
            retailer_vs_market AS (
                SELECT 
                    ph.retailer,
                    ph.cigar_id,
                    ph.price as retailer_price,
                    mp.market_avg_price,
                    (ph.price - mp.market_avg_price) as price_difference,
                    ((ph.price - mp.market_avg_price) / mp.market_avg_price) * 100 as pct_vs_market
                FROM price_history ph
                JOIN market_prices mp ON ph.cigar_id = mp.cigar_id
                WHERE ph.price > 0 AND ph.in_stock = 1
            )
            SELECT 
                retailer,
                COUNT(*) as comparable_products,
                ROUND(AVG(pct_vs_market), 1) as avg_pct_vs_market,
                ROUND(AVG(price_difference), 2) as avg_dollar_difference,
                COUNT(CASE WHEN pct_vs_market <= -5 THEN 1 END) as significantly_below_market,
                COUNT(CASE WHEN pct_vs_market >= 5 THEN 1 END) as significantly_above_market
            FROM retailer_vs_market 
            GROUP BY retailer 
            HAVING COUNT(*) >= 3
            ORDER BY avg_pct_vs_market ASC
            """
            
            positioning = pd.read_sql(positioning_query, self.conn)
            
            if positioning.empty:
                print("Insufficient data for competitive analysis")
                print("Need same cigars tracked across multiple retailers")
                return
            
            print("Retailer pricing vs market average (lower % = better value):")
            print()
            print("RETAILER                 PRODUCTS  AVG VS MKT  $ DIFF   BELOW MKT  ABOVE MKT")
            print("-" * 75)
            
            for _, row in positioning.iterrows():
                vs_market_str = f"{row['avg_pct_vs_market']:+.1f}%"
                dollar_diff_str = f"{row['avg_dollar_difference']:+.2f}"
                
                print(f"{row['retailer']:22} {row['comparable_products']:8d} "
                      f"{vs_market_str:10} ${dollar_diff_str:7} "
                      f"{row['significantly_below_market']:9d} {row['significantly_above_market']:9d}")
                
        except Exception as e:
            print(f"Error: {e}")
        
        print()

    def _stock_availability_analysis(self):
        """Stock availability patterns per retailer"""
        print("STOCK AVAILABILITY ANALYSIS")
        print("-" * 40)
        
        print("NOTE: Stock-out duration analysis requires multiple days of data.")
        print("Current analysis shows current stock status patterns.")
        print()
        
        try:
            stock_query = """
            SELECT 
                retailer,
                COUNT(*) as total_products,
                COUNT(CASE WHEN in_stock = 1 THEN 1 END) as in_stock,
                COUNT(CASE WHEN in_stock = 0 THEN 1 END) as out_of_stock,
                ROUND(COUNT(CASE WHEN in_stock = 1 THEN 1 END) * 100.0 / COUNT(*), 1) as availability_rate
            FROM price_history 
            WHERE date = (SELECT MAX(date) FROM price_history)
            GROUP BY retailer 
            ORDER BY availability_rate DESC
            """
            
            stock_analysis = pd.read_sql(stock_query, self.conn)
            
            if stock_analysis.empty:
                print("No stock data available")
                return
            
            print("Current stock availability by retailer:")
            print()
            print("RETAILER                 TOTAL  IN STOCK  OUT STOCK  AVAIL RATE")
            print("-" * 60)
            
            for _, row in stock_analysis.iterrows():
                print(f"{row['retailer']:22} {row['total_products']:5d} "
                      f"{row['in_stock']:9d} {row['out_of_stock']:10d} "
                      f"{row['availability_rate']:9.1f}%")
                
        except Exception as e:
            print(f"Error: {e}")
        
        print()

    def _price_spread_analysis(self):
        """Price spread analysis for business insights"""
        print("PRICE SPREAD ANALYSIS")
        print("-" * 40)
        
        try:
            spread_query = """
            SELECT 
                cigar_id,
                COUNT(DISTINCT retailer) as retailer_count,
                ROUND(MIN(price), 2) as min_price,
                ROUND(MAX(price), 2) as max_price,
                ROUND(MAX(price) - MIN(price), 2) as price_spread,
                ROUND(AVG(price), 2) as avg_price,
                ROUND(((MAX(price) - MIN(price)) / AVG(price)) * 100, 1) as spread_pct
            FROM price_history 
            WHERE price > 0 AND in_stock = 1
            GROUP BY cigar_id 
            HAVING COUNT(DISTINCT retailer) >= 2
            ORDER BY spread_pct DESC
            LIMIT 10
            """
            
            spreads = pd.read_sql(spread_query, self.conn)
            
            if spreads.empty:
                print("Insufficient data for spread analysis")
                return
            
            print("Cigars with highest price spreads across retailers:")
            print("(High spreads = opportunity for price arbitrage)")
            print()
            
            for i, row in spreads.iterrows():
                cigar_name = row['cigar_id'][:45] + "..." if len(row['cigar_id']) > 45 else row['cigar_id']
                print(f"{i+1}. {cigar_name}")
                print(f"   Price range: ${row['min_price']} - ${row['max_price']} "
                      f"(${row['price_spread']} spread, {row['spread_pct']}% of avg)")
                print(f"   Tracked by {row['retailer_count']} retailers | "
                      f"Market avg: ${row['avg_price']}")
                print()
                
        except Exception as e:
            print(f"Error: {e}")

    def get_specific_cigar_analysis(self, cigar_search_term):
        """Detailed analysis for a specific cigar across all retailers"""
        print(f"SPECIFIC CIGAR ANALYSIS: '{cigar_search_term}'")
        print("-" * 50)
        
        try:
            # Search in the cigar_id field which uses format: BRAND|BRAND|LINE|VITOLA|PRODUCT|SIZE|WRAPPER|BOXQTY
            cigar_query = """
            SELECT 
                retailer,
                cigar_id,
                price,
                in_stock,
                date
            FROM price_history 
            WHERE LOWER(cigar_id) LIKE LOWER(?)
            ORDER BY price ASC
            """
            
            # Try multiple search patterns to catch different formats
            search_patterns = [
                f'%{cigar_search_term}%',
                f'%{cigar_search_term.upper()}%',
                f'%{cigar_search_term.replace(" ", "")}%',
                f'%{cigar_search_term.replace(" ", "|")}%'
            ]
            
            results = pd.DataFrame()
            for pattern in search_patterns:
                temp_results = pd.read_sql(cigar_query, self.conn, params=(pattern,))
                results = pd.concat([results, temp_results]).drop_duplicates()
                if not temp_results.empty:
                    break
            
            if results.empty:
                print(f"No cigars found matching '{cigar_search_term}'")
                return
            
            # Group by exact cigar_id
            for cigar_id in results['cigar_id'].unique():
                cigar_data = results[results['cigar_id'] == cigar_id]
                
                print(f"Cigar: {cigar_id}")
                print("-" * 40)
                
                for _, row in cigar_data.iterrows():
                    stock_status = "IN STOCK" if row['in_stock'] else "OUT OF STOCK"
                    print(f"  {row['retailer']:20} ${row['price']:8.2f}  {stock_status}")
                
                if len(cigar_data) > 1:
                    min_price = cigar_data['price'].min()
                    max_price = cigar_data['price'].max()
                    avg_price = cigar_data['price'].mean()
                    spread = max_price - min_price
                    
                    print(f"  Market Summary: ${min_price:.2f} - ${max_price:.2f} "
                          f"(avg: ${avg_price:.2f}, spread: ${spread:.2f})")
                
                print()
                
        except Exception as e:
            print(f"Error: {e}")

    def show_sample_cigar_ids(self, limit=20):
        """Show sample cigar_ids to understand the data format"""
        print("SAMPLE CIGAR IDS IN DATABASE")
        print("-" * 50)
        
        try:
            sample_query = """
            SELECT DISTINCT cigar_id 
            FROM price_history 
            ORDER BY cigar_id 
            LIMIT ?
            """
            
            samples = pd.read_sql(sample_query, self.conn, params=(limit,))
            
            if samples.empty:
                print("No cigar IDs found")
                return
            
            print("Format appears to be: BRAND|BRAND|LINE|VITOLA|PRODUCT|SIZE|WRAPPER|BOXQTY")
            print()
            
            for i, row in samples.iterrows():
                # Try to parse the format
                parts = row['cigar_id'].split('|')
                if len(parts) >= 4:
                    brand = parts[0] if parts[0] else "N/A"
                    line = parts[2] if len(parts) > 2 else "N/A"
                    vitola = parts[3] if len(parts) > 3 else "N/A"
                    
                    print(f"{i+1:2d}. {row['cigar_id']}")
                    print(f"     Brand: {brand}, Line: {line}, Vitola: {vitola}")
                else:
                    print(f"{i+1:2d}. {row['cigar_id']}")
                print()
                
        except Exception as e:
            print(f"Error: {e}")

    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()


def main():
    """Generate business intelligence report"""
    bi = CigarBusinessIntelligence()
    
    try:
        bi.generate_business_report()
        
        # Show sample cigar IDs to understand format
        print("\n" + "="*50)
        print("SAMPLE CIGAR IDS FOR REFERENCE")
        print("="*50)
        bi.show_sample_cigar_ids(15)
        
        # Example: Analyze specific cigars with correct search terms
        print("\n" + "="*50)
        print("EXAMPLE: SPECIFIC CIGAR ANALYSIS")
        print("="*50)
        bi.get_specific_cigar_analysis("PADRON")  # Search for PADRON brand
        bi.get_specific_cigar_analysis("1964")    # Search for 1964 line
        bi.get_specific_cigar_analysis("FUENTE")  # Search for Fuente
        
    except Exception as e:
        print(f"Error generating report: {e}")
    finally:
        bi.close()


if __name__ == "__main__":
    main()
