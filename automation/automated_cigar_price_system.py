#!/usr/bin/env python3
"""
Fully Automated Cigar Price System
Complete hands-off solution for daily price updates with historical tracking

Features:
- Automatic daily price updates for all retailers
- Git commit and push automation 
- Historical price tracking database
- Comprehensive logging and monitoring
- Email notifications (optional)
- Recovery from failures

Author: Bri's Assistant
Date: November 24, 2025
"""

import os
import sys
import sqlite3
import json
import subprocess
import time
import glob
import smtplib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class AutomatedCigarPriceSystem:
    def __init__(self, project_root: Optional[str] = None):
        # Auto-detect project root
        if project_root:
            self.project_root = Path(project_root)
        else:
            # If running from automation/ folder, go up one level to project root
            current_dir = Path.cwd()
            if current_dir.name == 'automation':
                self.project_root = current_dir.parent
            else:
                # Assume we're already in project root
                self.project_root = current_dir
        
        # Directory structure based on Bri's actual layout
        self.automation_dir = self.project_root / 'automation'  # Where this script lives
        self.app_dir = self.project_root / 'app'  # Where main.py and updater scripts live
        self.static_data_dir = self.project_root / 'static' / 'data'  # CSV files location
        self.tools_dir = self.project_root / 'tools' / 'price_monitoring' / 'retailers'  # Extractors
        self.data_dir = self.project_root / 'data'  # Master CSV and historical DB
        self.historical_db_path = self.data_dir / 'historical_prices.db'
        self.log_dir = self.automation_dir / 'logs'  # Logs in automation folder
        self.config_file = self.automation_dir / 'automation_config.json'  # Config in automation folder
        
        # Ensure directories exist
        self.log_dir.mkdir(exist_ok=True)
        (self.project_root / 'data').mkdir(exist_ok=True)
        
        # Setup logging
        self.setup_logging()
        
        # Load configuration
        self.config = self.load_config()
        
        # Initialize historical database
        self.init_historical_database()
        
        # Track results for this run
        self.run_results = {}
        
        self.logger.info("Automated Cigar Price System initialized")

    def setup_logging(self):
        """Configure comprehensive logging"""
        log_file = self.log_dir / f'automation_{datetime.now().strftime("%Y%m%d")}.log'
        
        self.logger = logging.getLogger('CigarAutomation')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter('%(asctime)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def load_config(self) -> Dict:
        """Load or create automation configuration"""
        default_config = {
            "email_notifications": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "sender_email": "",
                "sender_password": "",
                "recipient_email": "",
                "send_on_success": True,
                "send_on_failure": True
            },
            "git_automation": {
                "enabled": True,
                "auto_commit": True,
                "auto_push": True,
                "commit_message_template": "Automated price update - {date}"
            },
            "price_update_settings": {
                "timeout_minutes": 30,
                "retry_failed_retailers": True,
                "delay_between_retailers": 2
            },
            "historical_tracking": {
                "enabled": True,
                "track_price_changes": True,
                "track_stock_changes": True,
                "retention_days": 365
            }
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                # Merge with defaults
                for key, value in default_config.items():
                    if key not in loaded_config:
                        loaded_config[key] = value
                    elif isinstance(value, dict):
                        for subkey, subvalue in value.items():
                            if subkey not in loaded_config[key]:
                                loaded_config[key][subkey] = subvalue
                return loaded_config
            except Exception as e:
                self.logger.warning(f"Failed to load config, using defaults: {e}")
        
        # Save default config
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        return default_config

    def init_historical_database(self):
        """Initialize SQLite database for historical price tracking"""
        try:
            conn = sqlite3.connect(self.historical_db_path, detect_types=0)
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    cigar_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    price REAL,
                    in_stock BOOLEAN,
                    url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(retailer, cigar_id, date)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    cigar_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    old_price REAL,
                    new_price REAL,
                    price_change REAL,
                    change_type TEXT, -- 'increase', 'decrease', 'new'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stock_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    cigar_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    old_stock BOOLEAN,
                    new_stock BOOLEAN,
                    change_type TEXT, -- 'in_stock', 'out_of_stock'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS automation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date DATE NOT NULL,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER,
                    retailers_attempted INTEGER,
                    retailers_successful INTEGER,
                    products_updated INTEGER,
                    errors_encountered TEXT,
                    git_push_successful BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS retailer_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    automation_run_id INTEGER,
                    retailer TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    duration_seconds REAL,
                    products_updated INTEGER,
                    products_failed INTEGER,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (automation_run_id) REFERENCES automation_runs(id)
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_retailer_runs_run_id ON retailer_runs(automation_run_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_retailer_runs_retailer ON retailer_runs(retailer)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_history_retailer_date ON price_history(retailer, date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_changes_date ON price_changes(date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_changes_date ON stock_changes(date)')
            
            conn.commit()
            conn.close()
            
            self.logger.info("Historical database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize historical database: {e}")
            raise

    def discover_retailers(self) -> Dict:
        """Auto-discover available retailer update scripts in the app/ folder"""
        self.logger.info("Auto-discovering retailer update scripts in app/ folder...")
        
        retailers = {}
        
        # Look for update scripts in the app/ directory
        script_patterns = ['update_*_prices_final.py', 'update_*_prices.py']
        
        for pattern in script_patterns:
            # Search in the app/ directory
            search_path = self.app_dir / pattern
            for script_path in self.app_dir.glob(pattern):
                script_name = script_path.name
                
                # Extract retailer name and map to CSV
                script_base = script_name.replace('update_', '').replace('_prices_final.py', '').replace('_prices.py', '')
                
                # Retailer name mapping (based on your existing structure)
                retailer_name_map = {
                    'absolute_cigars': 'absolutecigars',
                    'atlantic': 'atlantic',
                    'bighumidor': 'bighumidor',
                    'bnbtobacco': 'bnbtobacco', 
                    'cccrafter': 'cccrafter',
                    'cigarboxpa': 'cigarboxpa',
                    'cigarplace': 'cigarplace',
                    'cigarsdirect': 'cigarsdirect',
                    'foxcigar': 'foxcigar',
                    'gotham': 'gothamcigars',
                    'hilandscigars': 'hilands',
                    'holts': 'holts',
                    'iheartcigars': 'iheartcigars',
                    'neptune': 'neptune',
                    'nicks': 'nickscigarworld',
                    'planet_cigars': 'planetcigars',
                    'pyramidcigars': 'pyramidcigars',
                    'smallbatch_cigar': 'smallbatchcigar',
                    'smokeinn': 'smokeinn',
                    'tampasweethearts': 'tampasweethearts',
                    'thecigarshop': 'thecigarshop',
                    'tobaccolocker': 'tobaccolocker',
                    'two_guys': 'twoguys',
                    'watchcity': 'watchcity'
                }
                
                retailer_name = retailer_name_map.get(script_base, script_base)
                csv_file = f'{retailer_name}.csv'
                csv_path = self.static_data_dir / csv_file
                
                if csv_path.exists():
                    retailers[retailer_name] = {
                        'script_path': str(script_path),
                        'csv_path': csv_path,
                        'csv_file': csv_file
                    }
                    self.logger.info(f"  Found: {retailer_name} -> {script_name}")
                else:
                    self.logger.warning(f"  Skipping: {script_name} (CSV not found: {csv_file})")
        
        self.logger.info(f"Discovered {len(retailers)} retailers")
        return retailers

    def capture_pre_update_state(self, retailers: Dict) -> Dict:
        """Capture current state before updates for comparison"""
        self.logger.info("Capturing pre-update state for historical tracking...")
        
        pre_state = {}
        
        for retailer_name, config in retailers.items():
            try:
                csv_path = config['csv_path']
                if csv_path.exists():
                    df = pd.read_csv(csv_path)
                    pre_state[retailer_name] = df.to_dict('records')
            except Exception as e:
                self.logger.warning(f"Failed to capture pre-state for {retailer_name}: {e}")
                pre_state[retailer_name] = []
        
        return pre_state

    def run_retailer_update(self, retailer_name: str, config: Dict) -> Dict:
        """Run price update for a single retailer"""
        self.logger.info(f"Starting update for {retailer_name}")
        start_time = datetime.now()
        
        try:
            # Run the update script from the app directory (where the scripts expect to run)
            result = subprocess.run(
                [sys.executable, config['script_path']],
                capture_output=True,
                text=True,
                timeout=self.config['price_update_settings']['timeout_minutes'] * 60,
                cwd=self.app_dir  # Run from app/ directory where scripts expect to be
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Parse results from output
            success_count = 0
            fail_count = 0
            
            output_lines = (result.stdout or '').split('\n') + (result.stderr or '').split('\n')
            
            for line in output_lines:
                if 'Successful updates:' in line or 'successful updates' in line.lower():
                    try:
                        success_count = int(line.split(':')[1].strip())
                    except:
                        pass
                elif 'Failed updates:' in line or 'failed updates' in line.lower():
                    try:
                        fail_count = int(line.split(':')[1].strip())
                    except:
                        pass
            
            success = result.returncode == 0
            
            if success:
                self.logger.info(f"✓ {retailer_name}: {success_count} products updated in {duration:.1f}s")
            else:
                error_msg = result.stderr or result.stdout or 'Unknown error'
                self.logger.error(f"✗ {retailer_name}: Failed - {error_msg[:200]}...")
            
            return {
                'success': success,
                'duration': duration,
                'products_updated': success_count,
                'products_failed': fail_count,
                'error': None if success else (result.stderr or result.stdout or 'Unknown error')
            }
            
        except subprocess.TimeoutExpired:
            duration = self.config['price_update_settings']['timeout_minutes'] * 60
            self.logger.error(f"✗ {retailer_name}: Timeout after {duration/60:.0f} minutes")
            return {
                'success': False,
                'duration': duration,
                'products_updated': 0,
                'products_failed': 0,
                'error': f'Timeout after {duration/60:.0f} minutes'
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"✗ {retailer_name}: Crashed - {str(e)}")
            return {
                'success': False,
                'duration': duration,
                'products_updated': 0,
                'products_failed': 0,
                'error': str(e)
            }

    def track_changes(self, retailer_name: str, pre_state: List, post_state: List):
        """Track price and stock changes to historical database"""
        if not self.config['historical_tracking']['enabled']:
            return
        
        try:
            conn = sqlite3.connect(self.historical_db_path, detect_types=0)
            cursor = conn.cursor()
            
            today = datetime.now().date()
            
            # Create lookup dictionaries
            pre_lookup = {row.get('cigar_id', ''): row for row in pre_state}
            post_lookup = {row.get('cigar_id', ''): row for row in post_state}
            
            # Track all current prices/stock status
            for row in post_state:
                cigar_id = row.get('cigar_id', '')
                price = row.get('price')
                in_stock = row.get('in_stock', True)
                url = row.get('url', '')
                
                if cigar_id and price is not None:
                    # Insert current state (ignore duplicates)
                    cursor.execute('''
                        INSERT OR IGNORE INTO price_history 
                        (retailer, cigar_id, date, price, in_stock, url)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (retailer_name, cigar_id, today, float(price), bool(in_stock), url))
            
            # Track price changes
            if self.config['historical_tracking']['track_price_changes']:
                for cigar_id, post_row in post_lookup.items():
                    if cigar_id in pre_lookup:
                        pre_price = pre_lookup[cigar_id].get('price')
                        post_price = post_row.get('price')
                        
                        if pre_price is not None and post_price is not None:
                            pre_price = float(pre_price)
                            post_price = float(post_price)
                            
                            if abs(pre_price - post_price) > 0.01:  # Price changed
                                price_change = post_price - pre_price
                                change_type = 'increase' if price_change > 0 else 'decrease'
                                
                                cursor.execute('''
                                    INSERT INTO price_changes 
                                    (retailer, cigar_id, date, old_price, new_price, price_change, change_type)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                ''', (retailer_name, cigar_id, today, pre_price, post_price, price_change, change_type))
                    else:
                        # New product
                        post_price = post_row.get('price')
                        if post_price is not None:
                            cursor.execute('''
                                INSERT INTO price_changes 
                                (retailer, cigar_id, date, old_price, new_price, price_change, change_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (retailer_name, cigar_id, today, None, float(post_price), float(post_price), 'new'))
            
            # Track stock changes
            if self.config['historical_tracking']['track_stock_changes']:
                for cigar_id, post_row in post_lookup.items():
                    if cigar_id in pre_lookup:
                        pre_stock = pre_lookup[cigar_id].get('in_stock', True)
                        post_stock = post_row.get('in_stock', True)
                        
                        # Convert to boolean
                        pre_stock = str(pre_stock).lower() not in ('false', '0', 'no', '')
                        post_stock = str(post_stock).lower() not in ('false', '0', 'no', '')
                        
                        if pre_stock != post_stock:  # Stock status changed
                            change_type = 'in_stock' if post_stock else 'out_of_stock'
                            
                            cursor.execute('''
                                INSERT INTO stock_changes 
                                (retailer, cigar_id, date, old_stock, new_stock, change_type)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (retailer_name, cigar_id, today, pre_stock, post_stock, change_type))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to track changes for {retailer_name}: {e}")

    def capture_post_update_state(self, retailers: Dict, pre_state: Dict):
        """Capture post-update state and track changes"""
        self.logger.info("Capturing post-update state and tracking changes...")
        
        for retailer_name, config in retailers.items():
            try:
                csv_path = config['csv_path']
                if csv_path.exists():
                    df = pd.read_csv(csv_path)
                    post_state = df.to_dict('records')
                    
                    # Track changes
                    self.track_changes(
                        retailer_name, 
                        pre_state.get(retailer_name, []), 
                        post_state
                    )
                    
            except Exception as e:
                self.logger.warning(f"Failed to capture post-state for {retailer_name}: {e}")

    def git_commit_and_push(self) -> bool:
        """Commit and push changes to git"""
        if not self.config['git_automation']['enabled']:
            self.logger.info("Git automation disabled in config")
            return True
        
        try:
            self.logger.info("Starting git commit and push...")
            
            # Check if there are changes
            result = subprocess.run(['git', 'status', '--porcelain'], 
                                  capture_output=True, text=True, cwd=self.project_root)
            
            if not result.stdout.strip():
                self.logger.info("No git changes to commit")
                return True
            
            # Add all changes
            subprocess.run(['git', 'add', '.'], cwd=self.project_root, check=True)
            
            # Commit changes
            if self.config['git_automation']['auto_commit']:
                commit_message = self.config['git_automation']['commit_message_template'].format(
                    date=datetime.now().strftime('%Y-%m-%d %H:%M')
                )
                
                subprocess.run(['git', 'commit', '-m', commit_message], 
                             cwd=self.project_root, check=True)
                self.logger.info(f"Git commit successful: {commit_message}")
            
            # Push changes
            if self.config['git_automation']['auto_push']:
                result = subprocess.run(['git', 'push'], 
                                      capture_output=True, text=True, cwd=self.project_root)
                
                if result.returncode == 0:
                    self.logger.info("Git push successful")
                    return True
                else:
                    self.logger.error(f"Git push failed: {result.stderr}")
                    return False
            
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git operation failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Git operation crashed: {e}")
            return False

    def send_notification_email(self, subject: str, body: str):
        """Send email notification if configured"""
        email_config = self.config['email_notifications']
        
        if not email_config['enabled'] or not email_config['sender_email']:
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = email_config['sender_email']
            msg['To'] = email_config['recipient_email'] or email_config['sender_email']
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
            server.starttls()
            server.login(email_config['sender_email'], email_config['sender_password'])
            
            text = msg.as_string()
            server.sendmail(email_config['sender_email'], 
                          email_config['recipient_email'] or email_config['sender_email'], 
                          text)
            server.quit()
            
            self.logger.info("Notification email sent successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to send notification email: {e}")

    def log_automation_run(self, start_time: datetime, end_time: datetime, 
                          git_success: bool, errors: List[str]):
        """Log this automation run to the database and return its ID"""
        try:
            conn = sqlite3.connect(self.historical_db_path, detect_types=0)
            cursor = conn.cursor()
            
            duration = int((end_time - start_time).total_seconds())
            retailers_attempted = len(self.run_results)
            retailers_successful = sum(
                1 for r in self.run_results.values() if r.get('success')
            )
            products_updated = sum(
                r.get('products_updated', 0) for r in self.run_results.values()
            )
            
            cursor.execute('''
                INSERT INTO automation_runs 
                (run_date, start_time, end_time, duration_seconds, retailers_attempted, 
                 retailers_successful, products_updated, errors_encountered, git_push_successful)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                start_time.date(), start_time, end_time, duration,
                retailers_attempted, retailers_successful, products_updated,
                json.dumps(errors) if errors else None,
                git_success
            ))
            
            # 🔹 This is what was missing
            run_id = cursor.lastrowid
            
            conn.commit()
            conn.close()

            return run_id
            
        except Exception as e:
            self.logger.error(f"Failed to log automation run: {e}")
            return None
        
    def log_retailer_runs(self, automation_run_id):
        """Log per-retailer results for this automation run"""
        if automation_run_id is None:
            self.logger.warning("Skipping retailer_runs logging because automation_run_id is None")
            return

        try:
            conn = sqlite3.connect(self.historical_db_path, detect_types=0)
            cursor = conn.cursor()

            for retailer_name, result in self.run_results.items():
                cursor.execute('''
                    INSERT INTO retailer_runs
                    (automation_run_id, retailer, success, duration_seconds,
                     products_updated, products_failed, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    automation_run_id,
                    retailer_name,
                    1 if result.get('success') else 0,
                    result.get('duration'),
                    result.get('products_updated'),
                    result.get('products_failed'),
                    result.get('error'),
                ))

            conn.commit()
            conn.close()

        except Exception as e:
            self.logger.error(f"Failed to log retailer runs: {e}")

    def apply_promotions(self) -> bool:
        """Apply promotional discounts after price updates"""
        try:
            self.logger.info("Applying promotional discounts...")
            
            # Path to promotional processing script
            promo_script = self.project_root / "tools" / "promotions" / "apply_promos.py"
            promo_dir = promo_script.parent
            
            if not promo_script.exists():
                self.logger.warning(f"Promo script not found at {promo_script}")
                return True  # Not critical - continue without promos
            
            # Run promotional processing
            result = subprocess.run(
                [sys.executable, "apply_promos.py"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=promo_dir
            )
            
            if result.returncode == 0:
                self.logger.info("✓ Promotional processing completed successfully")
                return True
            else:
                error_msg = f"Promotional processing failed: {result.stderr}"
                self.logger.error(error_msg)
                return False
                
        except Exception as e:
            self.logger.error(f"Error applying promotions: {e}")
            return False

    def run_full_automation(self) -> bool:
        """Run the complete automation cycle"""
        start_time = datetime.now()
        errors = []
        
        self.logger.info("=" * 70)
        self.logger.info("STARTING AUTOMATED CIGAR PRICE UPDATE CYCLE")
        self.logger.info(f"Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 70)
        
        try:
            # 1. Discover retailers
            retailers = self.discover_retailers()
            if not retailers:
                error_msg = "No retailer update scripts found!"
                self.logger.error(error_msg)
                errors.append(error_msg)
                return False
            
            # 2. Capture pre-update state for historical tracking
            pre_state = self.capture_pre_update_state(retailers)
            
            # 3. Run all retailer updates
            self.logger.info(f"Running updates for {len(retailers)} retailers...")
            
            for retailer_name, config in retailers.items():
                result = self.run_retailer_update(retailer_name, config)
                self.run_results[retailer_name] = result
                
                if not result['success']:
                    errors.append(f"{retailer_name}: {result['error']}")
                
                # Delay between retailers
                delay = self.config['price_update_settings']['delay_between_retailers']
                if delay > 0 and len(retailers) > 1:
                    time.sleep(delay)
            
            # 4. Capture post-update state and track changes
            self.capture_post_update_state(retailers, pre_state)

            # 4.5. Apply promotional discounts  ← ADD THIS
            promo_success = self.apply_promotions()
            if not promo_success:
                errors.append("Promotional processing failed")
            
            # 5. Git commit and push
            git_success = self.git_commit_and_push()
            if not git_success:
                errors.append("Git push failed")
            
            # 6. Generate summary
            end_time = datetime.now()
            duration_minutes = (end_time - start_time).total_seconds() / 60
            successful_retailers = sum(1 for r in self.run_results.values() if r['success'])
            total_products = sum(r.get('products_updated', 0) for r in self.run_results.values())
            
            self.logger.info("=" * 70)
            self.logger.info("AUTOMATION CYCLE COMPLETE")
            self.logger.info(f"Duration: {duration_minutes:.1f} minutes")
            self.logger.info(f"Retailers: {successful_retailers}/{len(retailers)} successful")
            self.logger.info(f"Products Updated: {total_products}")
            self.logger.info(f"Git Push: {'SUCCESS' if git_success else 'FAILED'}")
            if errors:
                self.logger.error(f"Errors: {len(errors)} encountered")
            self.logger.info("=" * 70)
            
            # 7. Log to database
            automation_run_id = self.log_automation_run(start_time, end_time, git_success, errors)
            self.log_retailer_runs(automation_run_id)
            
            # 8. Send notifications
            email_config = self.config['email_notifications']
            overall_success = successful_retailers == len(retailers) and git_success
            
            if (overall_success and email_config['send_on_success']) or (not overall_success and email_config['send_on_failure']):
                status = "SUCCESS" if overall_success else "PARTIAL SUCCESS" if successful_retailers > 0 else "FAILED"
                subject = f"Cigar Price Automation - {status} - {start_time.strftime('%Y-%m-%d')}"
                
                body = f"""
Automated Cigar Price Update Report
{'='*40}

Status: {status}
Date: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
Duration: {duration_minutes:.1f} minutes

Results:
- Retailers processed: {len(retailers)}
- Successful updates: {successful_retailers}
- Products updated: {total_products}
- Git push: {'SUCCESS' if git_success else 'FAILED'}

"""
                
                if errors:
                    body += f"\nErrors encountered:\n"
                    for error in errors:
                        body += f"- {error}\n"
                
                body += f"\nDetailed logs available at: {self.log_dir}"
                
                self.send_notification_email(subject, body)
            
            return overall_success
            
        except Exception as e:
            end_time = datetime.now()
            error_msg = f"Automation cycle crashed: {str(e)}"
            self.logger.error(error_msg)
            errors.append(error_msg)
            
            # Still log the failed run
            self.log_automation_run(start_time, end_time, False, errors)
            
            # Send failure notification
            if self.config['email_notifications']['send_on_failure']:
                self.send_notification_email(
                    f"Cigar Price Automation - CRASHED - {start_time.strftime('%Y-%m-%d')}",
                    f"Automation cycle crashed with error:\n\n{str(e)}\n\nCheck logs for details."
                )
            
            return False


def main():
    """Main function for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Automated Cigar Price Update System')
    parser.add_argument('--project-root', help='Path to project root directory')
    parser.add_argument('--config-only', action='store_true', help='Create config file and exit')
    
    args = parser.parse_args()
    
    # Create automation system
    automation = AutomatedCigarPriceSystem(project_root=args.project_root)
    
    if args.config_only:
        print(f"Configuration file created at: {automation.config_file}")
        print("Edit this file to configure email notifications and other settings.")
        return
    
    # Run the automation
    success = automation.run_full_automation()
    
    if success:
        print("\nAutomation completed successfully!")
        sys.exit(0)
    else:
        print("\nAutomation completed with errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
