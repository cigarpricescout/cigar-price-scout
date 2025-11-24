#!/usr/bin/env python3
"""
Historical Database Health Check
Verify data collection robustness and identify any gaps
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

class DatabaseHealthCheck:
    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = Path('../../data/historical_prices.db')
        else:
            self.db_path = Path(db_path)
        
        if not self.db_path.exists():
            print(f"Database not found at: {self.db_path}")
            print("Historical data collection may not be working.")
            return
        
        self.conn = sqlite3.connect(self.db_path)
        print(f"Connected to database: {self.db_path}")

    def check_database_health(self):
        """Complete database health assessment"""
        print("=" * 70)
        print("HISTORICAL DATABASE HEALTH CHECK")
        print("=" * 70)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        self._check_table_structure()
        self._check_data_continuity()
        self._check_retailer_coverage()
        self._check_data_quality()
        self._check_storage_efficiency()
        self._recommend_improvements()

    def _check_table_structure(self):
        """Verify all required tables exist"""
        print("TABLE STRUCTURE CHECK")
        print("-" * 30)
        
        required_tables = ['price_history', 'price_changes', 'automation_runs', 'stock_changes']
        
        try:
            tables_query = "SELECT name FROM sqlite_master WHERE type='table'"
            tables = pd.read_sql(tables_query, self.conn)
            existing_tables = tables['name'].tolist()
            
            for table in required_tables:
                if table in existing_tables:
                    count_query = f"SELECT COUNT(*) as count FROM {table}"
                    count = pd.read_sql(count_query, self.conn)['count'].iloc[0]
                    print(f"{table}: {count:,} records")
                else:
                    print(f"{table}: Missing")
            
            # Check for unexpected tables
            extra_tables = [t for t in existing_tables if t not in required_tables]
            if extra_tables:
                print(f"Extra tables: {', '.join(extra_tables)}")
                
        except Exception as e:
            print(f"Error checking tables: {e}")
        
        print()

    def _check_data_continuity(self):
        """Check for gaps in daily data collection"""
        print("DATA CONTINUITY CHECK")
        print("-" * 30)
        
        try:
            # Get date range and count by date
            continuity_query = """
            SELECT 
                date,
                COUNT(*) as records,
                COUNT(DISTINCT retailer) as retailers,
                COUNT(DISTINCT cigar_id) as unique_cigars
            FROM price_history 
            GROUP BY date 
            ORDER BY date
            """
            
            continuity = pd.read_sql(continuity_query, self.conn)
            
            if continuity.empty:
                print("No historical data found")
                return
            
            start_date = continuity['date'].min()
            end_date = continuity['date'].max()
            total_days = len(continuity)
            
            print(f"Date range: {start_date} to {end_date}")
            print(f"Days with data: {total_days}")
            
            # Check for missing days
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            expected_days = (end - start).days + 1
            
            if total_days < expected_days:
                missing_days = expected_days - total_days
                print(f"Missing {missing_days} days of data")
            else:
                print("No gaps in daily data collection")
            
            # Show recent activity
            print("\nRecent data collection:")
            recent = continuity.tail(7)
            for _, row in recent.iterrows():
                print(f"  {row['date']}: {row['records']:3d} records, {row['retailers']:2d} retailers, {row['unique_cigars']:3d} cigars")
                
        except Exception as e:
            print(f"Error checking continuity: {e}")
        
        print()

    def _check_retailer_coverage(self):
        """Verify all retailers are being tracked consistently"""
        print("RETAILER COVERAGE CHECK")
        print("-" * 30)
        
        try:
            coverage_query = """
            SELECT 
                retailer,
                COUNT(*) as total_records,
                COUNT(DISTINCT date) as days_active,
                COUNT(DISTINCT cigar_id) as unique_cigars,
                MIN(date) as first_seen,
                MAX(date) as last_seen
            FROM price_history 
            GROUP BY retailer 
            ORDER BY total_records DESC
            """
            
            coverage = pd.read_sql(coverage_query, self.conn)
            
            if coverage.empty:
                print("No retailer data found")
                return
            
            print("RETAILER                 RECORDS  DAYS  CIGARS  FIRST SEEN  LAST SEEN")
            print("-" * 70)
            
            for _, row in coverage.iterrows():
                print(f"{row['retailer']:22} {row['total_records']:7d} {row['days_active']:5d} "
                      f"{row['unique_cigars']:7d} {row['first_seen']:>10} {row['last_seen']:>10}")
            
            # Check for inactive retailers
            latest_date = coverage['last_seen'].max()
            inactive = coverage[coverage['last_seen'] != latest_date]
            
            if not inactive.empty:
                print(f"\nRetailers not updated on {latest_date}:")
                for _, row in inactive.iterrows():
                    print(f"  {row['retailer']} (last: {row['last_seen']})")
            else:
                print(f"\nAll {len(coverage)} retailers updated on {latest_date}")
                
        except Exception as e:
            print(f"Error checking retailer coverage: {e}")
        
        print()

    def _check_data_quality(self):
        """Check for data quality issues"""
        print("DATA QUALITY CHECK")
        print("-" * 30)
        
        try:
            # Check for common data issues
            quality_checks = [
                ("NULL prices", "SELECT COUNT(*) FROM price_history WHERE price IS NULL"),
                ("Zero prices", "SELECT COUNT(*) FROM price_history WHERE price = 0"),
                ("Negative prices", "SELECT COUNT(*) FROM price_history WHERE price < 0"),
                ("Empty cigar_ids", "SELECT COUNT(*) FROM price_history WHERE cigar_id IS NULL OR cigar_id = ''"),
                ("Empty retailers", "SELECT COUNT(*) FROM price_history WHERE retailer IS NULL OR retailer = ''"),
                ("Extreme prices (>$2000)", "SELECT COUNT(*) FROM price_history WHERE price > 2000"),
                ("Very low prices (<$50)", "SELECT COUNT(*) FROM price_history WHERE price < 50 AND price > 0")
            ]
            
            total_records = pd.read_sql("SELECT COUNT(*) as count FROM price_history", self.conn)['count'].iloc[0]
            
            for check_name, query in quality_checks:
                count = pd.read_sql(query, self.conn)['count'].iloc[0]
                pct = (count / total_records) * 100 if total_records > 0 else 0
                
                if count > 0:
                    print(f"{check_name}: {count:,} records ({pct:.1f}%)")
                else:
                    print(f"{check_name}: None found")
                    
        except Exception as e:
            print(f"Error checking data quality: {e}")
        
        print()

    def _check_storage_efficiency(self):
        """Check database size and efficiency"""
        print("STORAGE EFFICIENCY CHECK")
        print("-" * 30)
        
        try:
            # Database file size
            db_size_bytes = self.db_path.stat().st_size
            db_size_mb = db_size_bytes / (1024 * 1024)
            
            print(f"Database file size: {db_size_mb:.2f} MB")
            
            # Records per MB
            total_records = pd.read_sql("SELECT COUNT(*) as count FROM price_history", self.conn)['count'].iloc[0]
            records_per_mb = total_records / db_size_mb if db_size_mb > 0 else 0
            
            print(f"Records per MB: {records_per_mb:,.0f}")
            
            # Estimate future growth
            days_of_data = pd.read_sql("SELECT COUNT(DISTINCT date) as count FROM price_history", self.conn)['count'].iloc[0]
            if days_of_data > 0:
                mb_per_day = db_size_mb / days_of_data
                estimated_year_size = mb_per_day * 365
                
                print(f"Growth rate: ~{mb_per_day:.2f} MB/day")
                print(f"Estimated yearly size: ~{estimated_year_size:.0f} MB")
                
                if estimated_year_size > 1000:
                    print(f"Large database expected - consider optimization")
                else:
                    print(f"Storage growth is manageable")
            
        except Exception as e:
            print(f"Error checking storage: {e}")
        
        print()

    def _recommend_improvements(self):
        """Suggest improvements based on health check"""
        print("RECOMMENDATIONS")
        print("-" * 30)
        
        recommendations = []
        
        try:
            # Check if we have recent data
            latest_date_query = "SELECT MAX(date) as latest FROM price_history"
            latest_date = pd.read_sql(latest_date_query, self.conn)['latest'].iloc[0]
            
            if latest_date:
                latest = pd.to_datetime(latest_date).date()
                today = datetime.now().date()
                days_old = (today - latest).days
                
                if days_old > 1:
                    recommendations.append(f"Data is {days_old} days old - check automation")
                elif days_old == 1:
                    recommendations.append("Data is 1 day old - normal if automation runs nightly")
                else:
                    recommendations.append("Data is current")
            
            # Check automation runs
            try:
                runs_query = "SELECT COUNT(*) as count FROM automation_runs WHERE run_date >= date('now', '-7 days')"
                recent_runs = pd.read_sql(runs_query, self.conn)['count'].iloc[0]
                
                if recent_runs == 0:
                    recommendations.append("No automation runs in last 7 days - check scheduler")
                elif recent_runs < 7:
                    recommendations.append(f"Only {recent_runs} automation runs in last 7 days - check reliability")
                else:
                    recommendations.append("Automation running consistently")
                    
            except:
                recommendations.append("Cannot check automation runs (table may not exist)")
            
            # Data retention recommendation
            total_records = pd.read_sql("SELECT COUNT(*) as count FROM price_history", self.conn)['count'].iloc[0]
            if total_records > 100000:
                recommendations.append("Consider data archival strategy for records >1 year old")
            
            # Display recommendations
            if recommendations:
                for rec in recommendations:
                    print(f"  {rec}")
            else:
                print("No specific recommendations - database looks healthy!")
                
        except Exception as e:
            print(f"Error generating recommendations: {e}")

    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()


def main():
    """Run complete database health check"""
    health_check = DatabaseHealthCheck()
    
    try:
        health_check.check_database_health()
    except Exception as e:
        print(f"Error running health check: {e}")
    finally:
        health_check.close()


if __name__ == "__main__":
    main()
