#!/usr/bin/env python3
"""
Railway Automation Runner for CigarPriceScout
Replaces local automation - maintains identical historical data tracking
"""

import subprocess
import sqlite3
import pandas as pd
import logging
import os
import glob
from datetime import datetime, timedelta
from pathlib import Path
import csv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CigarPriceAutomation:
    def __init__(self):
        self.project_root = Path.cwd()
        self.app_dir = self.project_root / "app"
        self.static_data_dir = self.project_root / "static" / "data"
        self.data_dir = self.project_root / "data"
        self.db_path = self.data_dir / "historical_prices.db"
        
        # Ensure directories exist
        self.data_dir.mkdir(exist_ok=True)
        
        # Initialize database with same structure as local automation
        self.init_database()
        
        # Track automation run
        self.start_time = datetime.now()
        self.retailers_attempted = 0
        self.retailers_successful = 0
        self.products_updated = 0
    
    def init_database(self):
        """Initialize SQLite database - identical to local automation structure"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # price_history table - matches your local automation exactly
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    cigar_id TEXT NOT NULL,
                    price DECIMAL(10,2),
                    in_stock BOOLEAN,
                    date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # price_changes table - tracks price differences like your system
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    cigar_id TEXT NOT NULL,
                    old_price DECIMAL(10,2),
                    new_price DECIMAL(10,2),
                    price_change DECIMAL(10,2),
                    change_type TEXT,
                    date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # stock_changes table - tracks stock status changes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stock_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    cigar_id TEXT NOT NULL,
                    old_stock BOOLEAN,
                    new_stock BOOLEAN,
                    change_type TEXT,
                    date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # automation_runs table - tracks automation performance
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS automation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_seconds INTEGER,
                    retailers_attempted INTEGER,
                    retailers_successful INTEGER,
                    products_updated INTEGER
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Historical database initialized successfully")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
    
    def discover_retailers(self):
        """Auto-discover retailer update scripts - same logic as local automation"""
        retailers = {}
        
        # Look for all update scripts in app/ directory
        update_patterns = [
            "update_*_prices_final.py",
            "update_*_prices.py", 
            "update_*.py"
        ]
        
        for pattern in update_patterns:
            scripts = list(self.app_dir.glob(pattern))
            
            for script_path in scripts:
                script_name = script_path.name
                
                # Skip if not a price update script
                if "update_" not in script_name:
                    continue
                
                # Extract retailer name from script name (same logic as local)
                retailer_key = self.extract_retailer_name(script_name)
                if retailer_key:
                    retailers[retailer_key] = script_name
                    logger.info(f"Found: {retailer_key} -> {script_name}")
        
        logger.info(f"Discovered {len(retailers)} retailers")
        return retailers
    
    def extract_retailer_name(self, script_name):
        """Extract retailer name from script filename - matches local automation"""
        script_lower = script_name.lower()
        
        # Specific mappings (from your automation logs)
        mappings = {
            'absolute': 'absolutecigars',
            'atlantic': 'atlantic', 
            'bighumidor': 'bighumidor',
            'bnbtobacco': 'bnbtobacco',
            'cigarsdirect': 'cigarsdirect',
            'foxcigar': 'foxcigar',
            'gotham': 'gothamcigars',
            'hiland': 'hilands',
            'holts': 'holts',
            'neptune': 'neptune',
            'planet': 'planetcigars',
            'smallbatch': 'smallbatchcigar',
            'smokeinn': 'smokeinn',
            'tampasweethearts': 'tampasweethearts',
            'tobaccolocker': 'tobaccolocker',
            'watchcity': 'watchcity',
            'cccrafter': 'cccrafter',
            'nicks': 'nickscigarworld',
            'two_guys': 'twoguys'
        }
        
        for key, retailer in mappings.items():
            if key in script_lower:
                return retailer
        
        # Fallback - extract from filename
        if "update_" in script_lower and "_prices" in script_lower:
            parts = script_lower.replace("update_", "").replace("_prices_final.py", "").replace("_prices.py", "").replace(".py", "")
            return parts.replace("_", "")
        
        return None
    
    def capture_pre_update_state(self, retailers):
        """Capture current CSV state before updates - matches local automation"""
        pre_state = {}
        today = datetime.now().strftime('%Y-%m-%d')
        
        logger.info("Capturing pre-update state for historical tracking...")
        
        for retailer_key in retailers.keys():
            csv_file = self.static_data_dir / f"{retailer_key}.csv"
            
            if csv_file.exists():
                try:
                    df = pd.read_csv(csv_file)
                    pre_state[retailer_key] = df.copy()
                except Exception as e:
                    logger.error(f"Error reading {retailer_key} CSV: {e}")
                    pre_state[retailer_key] = pd.DataFrame()
            else:
                pre_state[retailer_key] = pd.DataFrame()
        
        return pre_state
    
    def run_retailer_update(self, retailer_key, script_name):
        """Run update for single retailer - same timeout and error handling"""
        logger.info(f"Starting update for {retailer_key}")
        start_time = datetime.now()
        
        try:
            # Run script from app directory
            result = subprocess.run(
                f"python {script_name}",
                shell=True,
                cwd=self.app_dir,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout like local automation
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                # Count products updated
                csv_file = self.static_data_dir / f"{retailer_key}.csv"
                product_count = 0
                
                if csv_file.exists():
                    try:
                        df = pd.read_csv(csv_file)
                        product_count = len(df)
                    except:
                        product_count = 0
                
                logger.info(f"SUCCESS {retailer_key}: {product_count} products updated in {duration:.1f}s")
                return True, product_count
            else:
                logger.error(f"FAILED {retailer_key}: {result.stderr}")
                return False, 0
                
        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"TIMEOUT {retailer_key}: {duration/60:.1f} minute limit exceeded")
            return False, 0
        except Exception as e:
            logger.error(f"ERROR {retailer_key}: {e}")
            return False, 0
    
    def track_changes(self, retailer_key, pre_state, post_state):
        """Track price and stock changes - identical to local automation logic"""
        if pre_state.empty or post_state.empty:
            return
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Compare before and after states
            for _, post_row in post_state.iterrows():
                cigar_id = post_row.get('title', '')
                new_price = float(post_row.get('price', 0))
                new_stock = bool(post_row.get('in_stock', False))
                
                # Find matching row in pre-state
                matching_rows = pre_state[pre_state['title'] == cigar_id]
                
                if not matching_rows.empty:
                    old_row = matching_rows.iloc[0]
                    old_price = float(old_row.get('price', 0))
                    old_stock = bool(old_row.get('in_stock', False))
                    
                    # Track price changes (same logic as local)
                    if old_price != new_price and old_price > 0 and new_price > 0:
                        price_change = new_price - old_price
                        change_type = "increase" if price_change > 0 else "decrease"
                        
                        cursor.execute('''
                            INSERT INTO price_changes 
                            (retailer, cigar_id, old_price, new_price, price_change, change_type, date)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (retailer_key, cigar_id, old_price, new_price, price_change, change_type, today))
                    
                    # Track stock changes
                    if old_stock != new_stock:
                        change_type = "came_in_stock" if new_stock else "went_out_of_stock"
                        
                        cursor.execute('''
                            INSERT INTO stock_changes 
                            (retailer, cigar_id, old_stock, new_stock, change_type, date)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (retailer_key, cigar_id, old_stock, new_stock, change_type, today))
                
                # Always record current state in price_history
                cursor.execute('''
                    INSERT INTO price_history 
                    (retailer, cigar_id, price, in_stock, date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (retailer_key, cigar_id, new_price, new_stock, today))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error tracking changes for {retailer_key}: {e}")
    
    def capture_post_update_state(self, retailers):
        """Capture CSV state after updates and track all changes"""
        logger.info("Capturing post-update state and tracking changes...")
        
        for retailer_key in retailers.keys():
            csv_file = self.static_data_dir / f"{retailer_key}.csv"
            
            if csv_file.exists():
                try:
                    post_df = pd.read_csv(csv_file)
                    pre_df = getattr(self, 'pre_state', {}).get(retailer_key, pd.DataFrame())
                    
                    # Track changes between pre and post states
                    self.track_changes(retailer_key, pre_df, post_df)
                    
                except Exception as e:
                    logger.error(f"Error processing post-update state for {retailer_key}: {e}")
    
    def log_automation_run(self):
        """Log automation run statistics - same as local automation"""
        try:
            end_time = datetime.now()
            duration = (end_time - self.start_time).total_seconds()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO automation_runs 
                (run_date, start_time, end_time, duration_seconds, retailers_attempted, retailers_successful, products_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.start_time.strftime('%Y-%m-%d'),
                self.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                end_time.strftime('%Y-%m-%d %H:%M:%S'),
                int(duration),
                self.retailers_attempted,
                self.retailers_successful,
                self.products_updated
            ))
            
            conn.commit()
            conn.close()
            
            logger.info("=" * 70)
            logger.info("AUTOMATION CYCLE COMPLETE")
            logger.info(f"Duration: {duration/60:.1f} minutes")
            logger.info(f"Retailers: {self.retailers_successful}/{self.retailers_attempted} successful")
            logger.info(f"Products Updated: {self.products_updated}")
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error(f"Error logging automation run: {e}")
    
    def run_complete_automation(self):
        """Main automation workflow - identical to local automation flow"""
        logger.info("=" * 70)
        logger.info("STARTING AUTOMATED CIGAR PRICE UPDATE CYCLE")
        logger.info(f"Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)
        
        # Step 1: Auto-discover retailers
        logger.info("Auto-discovering retailer update scripts in app/ folder...")
        retailers = self.discover_retailers()
        
        if not retailers:
            logger.error("No retailer scripts found")
            return
        
        # Step 2: Capture pre-update state
        self.pre_state = self.capture_pre_update_state(retailers)
        
        # Step 3: Run updates for all retailers
        logger.info(f"Running updates for {len(retailers)} retailers...")
        
        for retailer_key, script_name in retailers.items():
            self.retailers_attempted += 1
            
            success, products = self.run_retailer_update(retailer_key, script_name)
            
            if success:
                self.retailers_successful += 1
                self.products_updated += products
            
            # Small delay between retailers (like local automation)
            import time
            time.sleep(2)
        
        # Step 4: Capture post-update state and track changes
        self.capture_post_update_state(retailers)
        
        # Step 5: Log the automation run
        self.log_automation_run()


def main():
    """Run the complete automation cycle"""
    automation = CigarPriceAutomation()
    
    try:
        automation.run_complete_automation()
    except Exception as e:
        logger.error(f"Automation failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
