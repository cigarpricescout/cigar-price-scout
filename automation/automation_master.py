#!/usr/bin/env python3
"""
Enhanced automation script with two-way GitHub sync
This replaces automation_master.py with full git integration
"""

import os
import sys
import logging
import subprocess
import pandas as pd
import sqlite3
import csv
import json  # Add this if not already present
from datetime import datetime
from pathlib import Path


# Configure logging
import os
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'automation.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CigarPriceAutomationEnhanced:
    def __init__(self):
        self.base_path = Path('/app')
        self.static_path = self.base_path / 'static' / 'data'
        self.tools_path = self.base_path / 'tools'
        self.app_path = self.base_path / 'app'
        
        # Retailer configurations
        self.retailers = {
            'atlantic': {
                'csv_file': 'atlantic.csv',
                'updater_script': 'update_atlantic_prices_final.py'
            },
            'foxcigar': {
                'csv_file': 'foxcigar.csv', 
                'updater_script': 'update_foxcigar_prices_final.py'
            },
            'nickscigarworld': {
                'csv_file': 'nickscigarworld.csv',
                'updater_script': 'update_nicks_prices.py'
            },
            'hilands': {
                'csv_file': 'hilands.csv',
                'updater_script': 'update_hilandscigars_prices_final.py'
            },
            'gothamcigars': {
                'csv_file': 'gothamcigars.csv',
                'updater_script': 'update_gotham_prices_final.py'
            },
            'bnbtobacco': {
                'csv_file': 'bnbtobacco.csv',
                'updater_script': 'update_bnbtobacco_prices_final.py'
            },
            'neptune': {
                'csv_file': 'neptune.csv',
                'updater_script': 'update_neptune_prices_final.py'
            },
            'tampasweethearts': {
                'csv_file': 'tampasweethearts.csv',
                'updater_script': 'update_tampasweethearts_prices_final.py'
            },
            'tobaccolocker': {
                'csv_file': 'tobaccolocker.csv',
                'updater_script': 'update_tobaccolocker_prices_final.py'
            },
            'watchcity': {
                'csv_file': 'watchcity.csv',
                'updater_script': 'update_watchcity_prices_final.py'
            },
            'cigarsdirect': {
                'csv_file': 'cigarsdirect.csv',
                'updater_script': 'update_cigarsdirect_prices_final.py'
            },
            'absolute_cigars': {
                'csv_file': 'absolutecigars.csv',
                'updater_script': 'update_absolute_cigars_prices_final.py'
            },
            'smallbatch_cigar': {
                'csv_file': 'smallbatchcigar.csv',
                'updater_script': 'update_smallbatch_cigar_prices_final.py'
            },
            'planet_cigars': {
                'csv_file': 'planetcigars.csv',
                'updater_script': 'update_planet_cigars_prices_final.py'
            },
            'holts': {
                'csv_file': 'holts.csv',
                'updater_script': 'update_holts_prices_final.py'
            },
            'smokeinn': {
                'csv_file': 'smokeinn.csv',
                'updater_script': 'update_smokeinn_prices_final.py'
            },
            'twoguys': {
                'csv_file': 'twoguys.csv',
                'updater_script': 'update_two_guys_prices.py'
            },
            'cccrafter': {
                'csv_file': 'cccrafter.csv', 
                'updater_script': 'update_cccrafter_prices.py'
            },
        }
        
        self.results = {}
        self.error_urls = []
        
        # Setup git authentication
        self.git_available = self.setup_git_auth()
    
    def setup_git_auth(self):
        """Configure git with GitHub token for authentication"""
        try:
            # Check if git is available
            subprocess.run(['git', '--version'], 
                        check=True, capture_output=True, cwd='/app')
            
            # Get GitHub token from environment
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                logger.warning("No GITHUB_TOKEN found - git sync will be disabled")
                return False
            
            # Initialize git repository if needed
            try:
                subprocess.run(['git', 'status'], capture_output=True, check=True, cwd='/app')
                logger.info("Git repository already initialized")
            except subprocess.CalledProcessError:
                logger.info("Initializing git repository...")
                subprocess.run(['git', 'init'], check=True, cwd='/app')
                subprocess.run(['git', 'remote', 'add', 'origin', 'https://github.com/cigarpricescout/cigar-price-scout.git'], check=True, cwd='/app')
                
                # Initial pull to get the repository structure  
                subprocess.run(['git', 'pull', 'origin', 'main'], check=True, cwd='/app')
                logger.info("Git repository initialized and synced")
            
            # Configure git credentials (now this will work)
            subprocess.run(['git', 'config', 'user.email', 
                        os.getenv('GIT_AUTHOR_EMAIL', 'automation@cigarpricescout.com')], 
                        check=True, cwd='/app')
            subprocess.run(['git', 'config', 'user.name', 
                        os.getenv('GIT_AUTHOR_NAME', 'Price Scout Automation')], 
                        check=True, cwd='/app')
            
            # Set up credential helper for GitHub token
            subprocess.run(['git', 'config', 'credential.helper', 'store'], 
                          check=True, cwd='/app')
            
            # Create credentials file
            with open('/app/.git-credentials', 'w') as f:
                f.write(f"https://x-access-token:{github_token}@github.com\n")
            
            logger.info("Git authentication configured")
            return True
            
        except FileNotFoundError:
            logger.warning("Git not available in this environment - sync disabled")
            return False
        except Exception as e:
            logger.error(f"Failed to setup git authentication: {e}")
            return False
    
    def sync_to_git(self) -> bool:
        """Sync updated CSV files back to GitHub - FIXED VERSION"""
        if not self.git_available:
            logger.info("Git sync skipped - not available in this environment")
            return True
            
        try:
            # Get GitHub token from environment
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                logger.warning("GITHUB_TOKEN not found - skipping git sync")
                return True
            
            # Pull latest changes first using token in URL
            logger.info("Pulling latest changes from GitHub...")
            pull_url = f'https://x-access-token:{github_token}@github.com/cigarpricescout/cigar-price-scout.git'
            
            # Set remote URL with token
            subprocess.run(['git', 'remote', 'set-url', 'origin', pull_url], 
                        check=True, cwd='/app', capture_output=True)
            
            # Pull changes
            subprocess.run(['git', 'pull', 'origin', 'main'], 
                        check=True, cwd='/app', capture_output=True)
            
            # Switch to main branch
            subprocess.run(['git', 'checkout', 'main'], 
                        check=True, cwd='/app', capture_output=True)
            
            # Add the updated CSV files (including subdirectories)
            subprocess.run(['git', 'add', 'static/data/'], 
                          check=True, cwd='/app', capture_output=True)
            
            # Check if there are changes to commit
            result = subprocess.run(['git', 'status', '--porcelain'], 
                                capture_output=True, text=True, cwd='/app')
                
            if result.stdout.strip():
                # Create commit
                commit_msg = f"Automated price update - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
                subprocess.run(['git', 'commit', '-m', commit_msg], 
                            check=True, cwd='/app', capture_output=True)
                
                logger.info("Committed changes to git")
                
                # Push changes using token URL
                logger.info("Pushing updated prices to GitHub...")
                subprocess.run(['git', 'push', 'origin', 'main'], 
                            check=True, cwd='/app', capture_output=True)
                
                logger.info("Successfully pushed price updates to GitHub")
                return True
            else:
                logger.info("No changes to commit")
                return True
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e}")
            if e.stdout:
                logger.error(f"STDOUT: {e.stdout.decode()}")
            if e.stderr:
                logger.error(f"STDERR: {e.stderr.decode()}")
            return False
        except Exception as e:
            logger.error(f"Git sync error: {e}")
            return False
    
    def setup_historical_db(self, db_path):
        """Create historical database tables if they don't exist"""
        try:
            conn = sqlite3.connect(db_path)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    cigar_id TEXT,
                    retailer TEXT,
                    price REAL,
                    in_stock BOOLEAN,
                    box_qty INTEGER,
                    title TEXT,
                    brand TEXT,
                    line TEXT,
                    wrapper TEXT,
                    vitola TEXT,
                    size TEXT,
                    UNIQUE(timestamp, cigar_id, retailer)
                )
            ''')
            
            # Create index for better query performance
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_price_history_lookup 
                ON price_history(cigar_id, retailer, timestamp)
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Historical database tables ready")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up historical database: {e}")
            return False
    
    def capture_historical_snapshot(self):
        """Capture current state after all retailer updates complete"""
        try:
            db_path = self.base_path / 'data' / 'historical_prices.db'
            
            # Ensure directory exists
            db_path.parent.mkdir(exist_ok=True)
            
            # Setup database if first run
            if not self.setup_historical_db(db_path):
                logger.error("Failed to setup historical database")
                return False
            
            timestamp = datetime.now().isoformat()
            records = []
            
            logger.info("Capturing historical price snapshot...")
            
            # Read current state from all retailer CSVs
            for retailer_key, config in self.retailers.items():
                csv_path = self.static_path / config['csv_file']
                
                if csv_path.exists():
                    try:
                        with open(csv_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            retailer_records = 0
                            
                            for row in reader:
                                # Parse price safely
                                price = None
                                if row.get('price'):
                                    try:
                                        price = float(str(row['price']).replace('$', '').replace(',', ''))
                                    except (ValueError, AttributeError):
                                        price = None
                                
                                # Parse stock status
                                in_stock = str(row.get('in_stock', 'False')).lower() in ['true', '1', 'yes']
                                
                                # Parse box quantity
                                box_qty = 0
                                if row.get('box_qty'):
                                    try:
                                        box_qty = int(row['box_qty'])
                                    except (ValueError, TypeError):
                                        box_qty = 0
                                
                                record = {
                                    'timestamp': timestamp,
                                    'cigar_id': row.get('cigar_id', ''),
                                    'retailer': retailer_key,
                                    'price': price,
                                    'in_stock': in_stock,
                                    'box_qty': box_qty,
                                    'title': row.get('title', ''),
                                    'brand': row.get('brand', ''),
                                    'line': row.get('line', ''),
                                    'wrapper': row.get('wrapper', ''),
                                    'vitola': row.get('vitola', ''),
                                    'size': row.get('size', '')
                                }
                                
                                records.append(record)
                                retailer_records += 1
                            
                            logger.info(f"  {retailer_key}: {retailer_records} products")
                            
                    except Exception as e:
                        logger.error(f"Error reading {retailer_key} CSV: {e}")
                else:
                    logger.warning(f"CSV file not found for {retailer_key}: {csv_path}")
            
            # Insert into database
            if records:
                success = self.insert_historical_records(db_path, records)
                if success:
                    logger.info(f"Historical snapshot captured: {len(records)} records")
                    return True
                else:
                    logger.error("Failed to insert historical records")
                    return False
            else:
                logger.warning("No records to capture for historical snapshot")
                return False
                
        except Exception as e:
            logger.error(f"Error capturing historical snapshot: {e}")
            return False
    
    def insert_historical_records(self, db_path, records):
        """Insert historical records into database"""
        try:
            conn = sqlite3.connect(db_path)
            inserted = 0
            
            for record in records:
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO price_history 
                        (timestamp, cigar_id, retailer, price, in_stock, box_qty, 
                         title, brand, line, wrapper, vitola, size)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        record['timestamp'], record['cigar_id'], record['retailer'],
                        record['price'], record['in_stock'], record['box_qty'],
                        record['title'], record['brand'], record['line'], 
                        record['wrapper'], record['vitola'], record['size']
                    ))
                    inserted += 1
                    
                except sqlite3.IntegrityError:
                    # Record already exists, skip
                    pass
                except Exception as e:
                    logger.error(f"Error inserting record for {record.get('retailer', 'unknown')}: {e}")
            
            conn.commit()
            conn.close()
            
            logger.info(f"Successfully inserted {inserted} historical records")
            return True
            
        except Exception as e:
            logger.error(f"Database error: {e}")
            return False
        
    def export_historical_data(self):
        """Export historical database to CSV files for local analysis"""
        try:
            db_path = '/app/data/historical_prices.db'
            if not Path(db_path).exists():
                logger.warning("Historical database not found - skipping export")
                return False
            
            # Create export directory
            export_dir = Path('/app/static/data/historical')
            export_dir.mkdir(exist_ok=True)
            
            conn = sqlite3.connect(db_path)
            
            # Export full historical data
            logger.info("Exporting historical price data...")
            full_data = pd.read_sql_query('''
                SELECT 
                    timestamp,
                    retailer,
                    cigar_id,
                    brand,
                    line,
                    wrapper,
                    vitola,
                    size,
                    box_qty,
                    price,
                    in_stock,
                    title
                FROM price_history 
                ORDER BY timestamp DESC, retailer, brand, line
            ''', conn)
            
            if not full_data.empty:
                full_data.to_csv(export_dir / 'complete_price_history.csv', index=False)
                logger.info(f"Exported {len(full_data)} historical records")
            
            # Export retailer performance summary
            performance_data = pd.read_sql_query('''
                SELECT 
                    retailer,
                    COUNT(*) as total_observations,
                    COUNT(DISTINCT cigar_id) as products_tracked,
                    AVG(price) as avg_price,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    COUNT(CASE WHEN in_stock = 1 THEN 1 END) as in_stock_count,
                    COUNT(CASE WHEN in_stock = 1 THEN 1 END) * 100.0 / COUNT(*) as stock_rate,
                    COUNT(DISTINCT DATE(timestamp)) as days_active,
                    MIN(DATE(timestamp)) as first_seen,
                    MAX(DATE(timestamp)) as last_seen
                FROM price_history 
                WHERE price IS NOT NULL
                GROUP BY retailer
                ORDER BY stock_rate DESC, avg_price ASC
            ''', conn)
            
            if not performance_data.empty:
                performance_data.to_csv(export_dir / 'retailer_performance.csv', index=False)
                logger.info(f"Exported performance data for {len(performance_data)} retailers")
            
            # Export daily price snapshots (for trend analysis)
            daily_snapshots = pd.read_sql_query('''
                SELECT 
                    DATE(timestamp) as date,
                    retailer,
                    brand,
                    line,
                    wrapper,
                    vitola,
                    AVG(price) as avg_daily_price,
                    COUNT(*) as observations,
                    COUNT(CASE WHEN in_stock = 1 THEN 1 END) as in_stock_count
                FROM price_history 
                WHERE price IS NOT NULL
                GROUP BY DATE(timestamp), retailer, brand, line, wrapper, vitola
                ORDER BY date DESC, retailer, brand, line
            ''', conn)
            
            if not daily_snapshots.empty:
                daily_snapshots.to_csv(export_dir / 'daily_price_snapshots.csv', index=False)
                logger.info(f"Exported {len(daily_snapshots)} daily price snapshots")
            
            # Export top tracked cigars
            top_cigars = pd.read_sql_query('''
                SELECT 
                    brand,
                    line,
                    wrapper,
                    vitola,
                    COUNT(DISTINCT retailer) as retailer_count,
                    AVG(price) as avg_price,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    COUNT(CASE WHEN in_stock = 1 THEN 1 END) * 100.0 / COUNT(*) as avg_stock_rate,
                    COUNT(*) as total_observations
                FROM price_history 
                WHERE price IS NOT NULL
                GROUP BY brand, line, wrapper, vitola
                HAVING COUNT(DISTINCT retailer) > 2
                ORDER BY retailer_count DESC, avg_stock_rate DESC
            ''', conn)
            
            if not top_cigars.empty:
                top_cigars.to_csv(export_dir / 'top_tracked_cigars.csv', index=False)
                logger.info(f"Exported data for {len(top_cigars)} top tracked cigars")
            
            conn.close()
            
            # Create analysis summary
            summary = {
                'export_timestamp': datetime.now().isoformat(),
                'total_records': len(full_data) if not full_data.empty else 0,
                'retailers': len(performance_data) if not performance_data.empty else 0,
                'unique_cigars': len(top_cigars) if not top_cigars.empty else 0,
                'files_exported': [
                    'complete_price_history.csv',
                    'retailer_performance.csv', 
                    'daily_price_snapshots.csv',
                    'top_tracked_cigars.csv'
                ]
            }
            
            with open(export_dir / 'export_summary.json', 'w') as f:
                import json
                json.dump(summary, f, indent=2)
            
            logger.info("Historical data export completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting historical data: {e}")
            return False
    
    def update_retailer(self, retailer: str) -> dict:
        """Update prices for a specific retailer"""
        config = self.retailers.get(retailer)
        if not config:
            return {
                'retailer': retailer,
                'success': False,
                'error': f'No configuration found for {retailer}',
                'duration': 0,
                'products_updated': 0
            }
        
        start_time = datetime.now()
        logger.info(f"Starting {retailer} price update...")
        
        try:
            # Run the retailer-specific update script
            script_path = self.app_path / config['updater_script']
            
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute timeout
                cwd='/app'
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                # Parse output for success metrics
                products_updated = 0
                for line in result.stdout.split('\n'):
                    if 'Successful updates:' in line:
                        try:
                            products_updated = int(line.split(':')[1].strip())
                        except:
                            pass
                
                logger.info(f"{retailer} update completed - {products_updated} products updated")
                return {
                    'retailer': retailer,
                    'success': True,
                    'error': None,
                    'duration': duration,
                    'products_updated': products_updated
                }
            else:
                error_msg = result.stderr or result.stdout or 'Unknown error'
                logger.error(f"{retailer} update failed: {error_msg}")
                return {
                    'retailer': retailer,
                    'success': False,
                    'error': error_msg,
                    'duration': duration,
                    'products_updated': 0
                }
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"{retailer} update crashed: {e}")
            return {
                'retailer': retailer,
                'success': False,
                'error': str(e),
                'duration': duration,
                'products_updated': 0
            }
    
    def run_full_update(self):
        """Run complete automation cycle with git sync"""
        logger.info("STARTING AUTOMATED PRICE UPDATE CYCLE")
        start_time = datetime.now()
        
        # Reset tracking
        self.results = {}
        
        # Update each retailer
        for retailer in self.retailers.keys():
            result = self.update_retailer(retailer)
            self.results[retailer] = result
        
        # Sync updated CSVs back to GitHub
        git_sync_success = self.sync_to_git()
        
        # Capture historical price snapshot after all updates complete
        historical_success = self.capture_historical_snapshot()

        # Export historical data for local analysis
        historical_export_success = self.export_historical_data()
        
        # Calculate summary
        total_duration = (datetime.now() - start_time).total_seconds()
        successful_retailers = sum(1 for r in self.results.values() if r['success'])
        total_products = sum(r['products_updated'] for r in self.results.values())
        
        # Generate report
        logger.info("UPDATE SUMMARY")
        logger.info(f"Duration: {total_duration/60:.1f} minutes")
        logger.info(f"Successful: {successful_retailers}/{len(self.retailers)} retailers")
        logger.info(f"Products Updated: {total_products}")
        logger.info(f"Git Sync: {'SUCCESS' if git_sync_success else 'FAILED'}")
        logger.info(f"Historical Snapshot: {'SUCCESS' if historical_success else 'FAILED'}")
        logger.info(f"Historical Export: {'SUCCESS' if historical_export_success else 'FAILED'}")
        
        if git_sync_success:
            logger.info("Automation complete! Updated prices are now live on your website.")
            logger.info("Run 'git pull' on your local computer to get the latest data.")
        
        return git_sync_success

# Main execution
if __name__ == "__main__":
    automation = CigarPriceAutomationEnhanced()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'manual':
        retailer = sys.argv[2] if len(sys.argv) > 2 else None
        if retailer:
            result = automation.update_retailer(retailer)
            print(f"Manual update for {retailer}: {'SUCCESS' if result['success'] else 'FAILED'}")
        else:
            automation.run_full_update()
    else:
        # Set up weekly scheduler
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger
            
            scheduler = BlockingScheduler()
            # Daily trigger at 11:!5 AM PST
            scheduler.add_job(
                automation.run_full_update,
                trigger=CronTrigger(hour=11, minute=15, timezone='America/Los_Angeles'),
                id='price_update_job'
            )

            logger.info("Automation scheduled - Daily updates at 11:!5 AM Pacific time")
            logger.info("Manual trigger: python automation_master.py manual")
            scheduler.start()
            
        except ImportError:
            logger.error("APScheduler not available - run manually")
            automation.run_full_update()