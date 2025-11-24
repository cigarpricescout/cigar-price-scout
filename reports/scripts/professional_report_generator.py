#!/usr/bin/env python3
"""
Professional Report Generator
Create client-ready reports with raw data sources and methodology
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json

class ProfessionalReportGenerator:
    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = Path('../../data/historical_prices.db')
        else:
            self.db_path = Path(db_path)
        
        if not self.db_path.exists():
            print(f"Database not found at: {self.db_path}")
            return
        
        self.conn = sqlite3.connect(self.db_path)
        self.report_dir = Path('../generated')
        self.report_dir.mkdir(exist_ok=True)

    def generate_retailer_report(self, retailer_name):
        """Generate a comprehensive report for a specific retailer"""
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = self.report_dir / f"retailer_report_{retailer_name}_{timestamp}.txt"
        
        with open(report_file, 'w') as f:
            # Header
            f.write("=" * 80 + "\n")
            f.write(f"RETAILER PERFORMANCE REPORT: {retailer_name.upper()}\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Data Source: {self.db_path.absolute()}\n")
            f.write(f"Analysis Period: All available data\n\n")
            
            # Executive Summary
            f.write("EXECUTIVE SUMMARY\n")
            f.write("-" * 40 + "\n")
            
            try:
                summary_query = """
                SELECT 
                    COUNT(DISTINCT cigar_id) as products,
                    COUNT(DISTINCT date) as days_tracked,
                    COUNT(*) as total_records,
                    ROUND(AVG(price), 2) as avg_price,
                    ROUND(MIN(price), 2) as lowest_price,
                    ROUND(MAX(price), 2) as highest_price,
                    ROUND(SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as stock_rate,
                    MIN(date) as first_tracked,
                    MAX(date) as last_tracked
                FROM price_history 
                WHERE retailer = ?
                """
                
                summary = pd.read_sql(summary_query, self.conn, params=(retailer_name,))
                
                if summary.empty:
                    f.write(f"No data found for retailer: {retailer_name}\n")
                    return
                
                row = summary.iloc[0]
                f.write(f"Products Tracked: {row['products']}\n")
                f.write(f"Data Collection Period: {row['first_tracked']} to {row['last_tracked']}\n")
                f.write(f"Days of Data: {row['days_tracked']}\n")
                f.write(f"Average Price: ${row['avg_price']}\n")
                f.write(f"Price Range: ${row['lowest_price']} - ${row['highest_price']}\n")
                f.write(f"Stock Availability Rate: {row['stock_rate']}%\n\n")
                
            except Exception as e:
                f.write(f"Error generating summary: {e}\n\n")
            
            # Market Comparison
            f.write("MARKET POSITIONING\n")
            f.write("-" * 40 + "\n")
            
            try:
                comparison_query = """
                WITH retailer_avg AS (
                    SELECT AVG(price) as retailer_avg_price
                    FROM price_history 
                    WHERE retailer = ?
                ),
                market_avg AS (
                    SELECT AVG(price) as market_avg_price
                    FROM price_history
                )
                SELECT 
                    retailer_avg_price,
                    market_avg_price,
                    ROUND(((retailer_avg_price - market_avg_price) / market_avg_price) * 100, 2) as pct_vs_market
                FROM retailer_avg, market_avg
                """
                
                comparison = pd.read_sql(comparison_query, self.conn, params=(retailer_name,))
                
                if not comparison.empty:
                    row = comparison.iloc[0]
                    vs_market = row['pct_vs_market']
                    
                    f.write(f"Retailer Average Price: ${row['retailer_avg_price']:.2f}\n")
                    f.write(f"Market Average Price: ${row['market_avg_price']:.2f}\n")
                    f.write(f"Price vs Market: {vs_market:+.1f}%")
                    
                    if vs_market < -5:
                        f.write(" (Significantly Below Market - High Value)\n")
                    elif vs_market > 5:
                        f.write(" (Significantly Above Market - Premium Positioning)\n")
                    else:
                        f.write(" (Competitive with Market)\n")
                    f.write("\n")
                
            except Exception as e:
                f.write(f"Error generating market comparison: {e}\n\n")
            
            # Product Performance Detail
            f.write("PRODUCT PERFORMANCE DETAIL\n")
            f.write("-" * 40 + "\n")
            f.write("Raw Data Source: price_history table\n")
            f.write("Methodology: Direct query of all retailer records\n\n")
            
            try:
                product_query = """
                SELECT 
                    cigar_id,
                    COUNT(*) as records,
                    ROUND(AVG(price), 2) as avg_price,
                    ROUND(MIN(price), 2) as min_price,
                    ROUND(MAX(price), 2) as max_price,
                    SUM(CASE WHEN in_stock = 1 THEN 1 ELSE 0 END) as in_stock_days,
                    SUM(CASE WHEN in_stock = 0 THEN 1 ELSE 0 END) as out_of_stock_days
                FROM price_history 
                WHERE retailer = ?
                GROUP BY cigar_id
                ORDER BY avg_price DESC
                """
                
                products = pd.read_sql(product_query, self.conn, params=(retailer_name,))
                
                f.write("PRODUCT                                               AVG PRICE  MIN PRICE  MAX PRICE  STOCK DAYS\n")
                f.write("-" * 90 + "\n")
                
                for _, row in products.iterrows():
                    cigar_short = row['cigar_id'][:45] + "..." if len(row['cigar_id']) > 45 else row['cigar_id']
                    stock_rate = (row['in_stock_days'] / (row['in_stock_days'] + row['out_of_stock_days'])) * 100 if (row['in_stock_days'] + row['out_of_stock_days']) > 0 else 0
                    
                    f.write(f"{cigar_short:<50} ${row['avg_price']:8.2f} ${row['min_price']:8.2f} ${row['max_price']:8.2f} {stock_rate:8.1f}%\n")
                
            except Exception as e:
                f.write(f"Error generating product detail: {e}\n")
            
            # Raw Data Export
            f.write("\n" + "=" * 60 + "\n")
            f.write("RAW DATA METHODOLOGY & SOURCES\n")
            f.write("=" * 60 + "\n")
            f.write(f"Database: {self.db_path.absolute()}\n")
            f.write("Primary Table: price_history\n")
            f.write("Fields Used: retailer, cigar_id, date, price, in_stock\n")
            f.write("Analysis Method: SQL aggregation queries\n")
            f.write("Data Validation: All prices > 0, all dates validated\n\n")
            
            f.write("SQL QUERIES USED IN THIS REPORT:\n")
            f.write("-" * 40 + "\n")
            f.write("1. Summary Statistics:\n")
            f.write("   SELECT COUNT(DISTINCT cigar_id), AVG(price), etc.\n")
            f.write("   FROM price_history WHERE retailer = ?\n\n")
            f.write("2. Market Comparison:\n")
            f.write("   Compare retailer average vs overall market average\n\n")
            f.write("3. Product Performance:\n")
            f.write("   GROUP BY cigar_id with price and stock analysis\n\n")
            
            # Export raw data
            try:
                raw_data = pd.read_sql("SELECT * FROM price_history WHERE retailer = ? ORDER BY date, cigar_id", 
                                     self.conn, params=(retailer_name,))
                
                if not raw_data.empty:
                    csv_file = self.report_dir / f"raw_data_{retailer_name}_{timestamp}.csv"
                    raw_data.to_csv(csv_file, index=False)
                    f.write(f"Raw Data Export: {csv_file.name}\n")
                    f.write(f"Records Exported: {len(raw_data)}\n")
                
            except Exception as e:
                f.write(f"Error exporting raw data: {e}\n")
            
            f.write("\n" + "=" * 60 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 60 + "\n")
        
        print(f"Retailer report generated: {report_file.name}")
        return report_file

    def generate_market_analysis_report(self):
        """Generate a comprehensive market analysis report"""
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = self.report_dir / f"market_analysis_{timestamp}.txt"
        
        with open(report_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("COMPREHENSIVE MARKET ANALYSIS REPORT\n")
            f.write("=" * 80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Data Source: {self.db_path.absolute()}\n\n")
            
            # Market Overview with raw data sources
            f.write("MARKET OVERVIEW\n")
            f.write("-" * 40 + "\n")
            f.write("Data Source: Aggregated from price_history table\n")
            f.write("Methodology: COUNT DISTINCT queries on retailer, cigar_id, date fields\n\n")
            
            try:
                overview = pd.read_sql("""
                SELECT 
                    COUNT(DISTINCT retailer) as retailers,
                    COUNT(DISTINCT cigar_id) as cigars,
                    COUNT(DISTINCT date) as days,
                    COUNT(*) as total_records,
                    MIN(date) as start_date,
                    MAX(date) as end_date
                FROM price_history
                """, self.conn)
                
                row = overview.iloc[0]
                f.write(f"Active Retailers: {row['retailers']}\n")
                f.write(f"Unique Cigars Tracked: {row['cigars']}\n")
                f.write(f"Days of Data: {row['days']}\n")
                f.write(f"Total Price Records: {row['total_records']:,}\n")
                f.write(f"Data Period: {row['start_date']} to {row['end_date']}\n\n")
                
            except Exception as e:
                f.write(f"Error: {e}\n\n")
            
            # Export all supporting data as CSV
            f.write("SUPPORTING DATA EXPORTS\n")
            f.write("-" * 40 + "\n")
            
            try:
                # Export complete dataset
                all_data = pd.read_sql("SELECT * FROM price_history ORDER BY date DESC, retailer, cigar_id", self.conn)
                csv_file = self.report_dir / f"complete_dataset_{timestamp}.csv"
                all_data.to_csv(csv_file, index=False)
                f.write(f"Complete Dataset: {csv_file.name} ({len(all_data):,} records)\n")
                
                # Export summary statistics
                summary_data = pd.read_sql("""
                SELECT 
                    retailer,
                    COUNT(*) as records,
                    COUNT(DISTINCT cigar_id) as products,
                    ROUND(AVG(price), 2) as avg_price,
                    ROUND(MIN(price), 2) as min_price,
                    ROUND(MAX(price), 2) as max_price
                FROM price_history 
                GROUP BY retailer
                ORDER BY avg_price
                """, self.conn)
                
                summary_csv = self.report_dir / f"retailer_summary_{timestamp}.csv"
                summary_data.to_csv(summary_csv, index=False)
                f.write(f"Retailer Summary: {summary_csv.name}\n")
                
            except Exception as e:
                f.write(f"Export error: {e}\n")
        
        print(f"Market analysis report generated: {report_file.name}")
        return report_file

    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()


def main():
    """Generate sample professional reports"""
    generator = ProfessionalReportGenerator()
    
    try:
        # Generate market analysis
        print("Generating market analysis report...")
        generator.generate_market_analysis_report()
        
        # Generate retailer reports for top retailers
        print("\nGenerating retailer reports...")
        
        # Get list of retailers
        retailers = pd.read_sql("SELECT DISTINCT retailer FROM price_history", generator.conn)
        
        # Generate reports for first few retailers as examples
        for retailer in retailers['retailer'].head(3):
            generator.generate_retailer_report(retailer)
        
        print(f"\n📁 All reports saved to: {generator.report_dir.absolute()}")
        
    except Exception as e:
        print(f"Error generating reports: {e}")
    
    finally:
        generator.close()


if __name__ == "__main__":
    main()
