#!/usr/bin/env python3
"""
Enhanced automation script with two-way GitHub sync
MINIMAL VERSION - NO HISTORICAL EXPORT FOR TESTING
"""

import os
import sys
import logging
import subprocess
import sqlite3
import csv
from datetime import datetime
from pathlib import Path

# Configure logging
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
            'atlantic': {'csv_file': 'atlantic.csv', 'updater_script': 'update_atlantic_prices_final.py'},
            'foxcigar': {'csv_file': 'foxcigar.csv', 'updater_script': 'update_foxcigar_prices_final.py'},
            'nickscigarworld': {'csv_file': 'nickscigarworld.csv', 'updater_script': 'update_nicks_prices.py'},
            'hilands': {'csv_file': 'hilands.csv', 'updater_script': 'update_hilandscigars_prices_final.py'},
            'gothamcigars': {'csv_file': 'gothamcigars.csv', 'updater_script': 'update_gotham_prices_final.py'},
            'bnbtobacco': {'csv_file': 'bnbtobacco.csv', 'updater_script': 'update_bnbtobacco_prices_final.py'},
            'neptune': {'csv_file': 'neptune.csv', 'updater_script': 'update_neptune_prices_final.py'},
            'tampasweethearts': {'csv_file': 'tampasweethearts.csv', 'updater_script': 'update_tampasweethearts_prices_final.py'},
            'tobaccolocker': {'csv_file': 'tobaccolocker.csv', 'updater_script': 'update_tobaccolocker_prices_final.py'},
            'watchcity': {'csv_file': 'watchcity.csv', 'updater_script': 'update_watchcity_prices_final.py'},
            'cigarsdirect': {'csv_file': 'cigarsdirect.csv', 'updater_script': 'update_cigarsdirect_prices_final.py'},
            'absolute_cigars': {'csv_file': 'absolutecigars.csv', 'updater_script': 'update_absolute_cigars_prices_final.py'},
            'smallbatch_cigar': {'csv_file': 'smallbatchcigar.csv', 'updater_script': 'update_smallbatch_cigar_prices_final.py'},
            'planet_cigars': {'csv_file': 'planetcigars.csv', 'updater_script': 'update_planet_cigars_prices_final.py'},
            'holts': {'csv_file': 'holts.csv', 'updater_script': 'update_holts_prices_final.py'},
            'smokeinn': {'csv_file': 'smokeinn.csv', 'updater_script': 'update_smokeinn_prices_final.py'},
            'twoguys': {'csv_file': 'twoguys.csv', 'updater_script': 'update_two_guys_prices.py'},
            'cccrafter': {'csv_file': 'cccrafter.csv', 'updater_script': 'update_cccrafter_prices.py'},
        }
        
        self.results = {}
        self.git_available = self.setup_git_auth()
    
    def setup_git_auth(self):
        """Configure git with GitHub token for authentication"""
        try:
            subprocess.run(['git', '--version'], check=True, capture_output=True, cwd='/app')
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                logger.warning("No GITHUB_TOKEN found - git sync will be disabled")
                return False
            
            try:
                subprocess.run(['git', 'status'], capture_output=True, check=True, cwd='/app')
                logger.info("Git repository already initialized")
            except subprocess.CalledProcessError:
                logger.info("Initializing git repository...")
                subprocess.run(['git', 'init'], check=True, cwd='/app')
                subprocess.run(['git', 'remote', 'add', 'origin', 'https://github.com/cigarpricescout/cigar-price-scout.git'], check=True, cwd='/app')
                subprocess.run(['git', 'pull', 'origin', 'main'], check=True, cwd='/app')
                logger.info("Git repository initialized and synced")
            
            subprocess.run(['git', 'config', 'user.email', os.getenv('GIT_AUTHOR_EMAIL', 'automation@cigarpricescout.com')], check=True, cwd='/app')
            subprocess.run(['git', 'config', 'user.name', os.getenv('GIT_AUTHOR_NAME', 'Price Scout Automation')], check=True, cwd='/app')
            
            logger.info("Git authentication configured")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup git authentication: {e}")
            return False
    
    def sync_to_git(self) -> bool:
        """Sync updated CSV files back to GitHub"""
        if not self.git_available:
            logger.info("Git sync skipped - not available in this environment")
            return True
            
        try:
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                logger.warning("GITHUB_TOKEN not found - skipping git sync")
                return True
            
            logger.info("Pulling latest changes from GitHub...")
            pull_url = f'https://x-access-token:{github_token}@github.com/cigarpricescout/cigar-price-scout.git'
            
            subprocess.run(['git', 'remote', 'set-url', 'origin', pull_url], check=True, cwd='/app', capture_output=True)
            subprocess.run(['git', 'pull', 'origin', 'main'], check=True, cwd='/app', capture_output=True)
            subprocess.run(['git', 'checkout', 'main'], check=True, cwd='/app', capture_output=True)
            
            csv_files = list(Path('/app/static/data').glob('*.csv'))
            if csv_files:
                subprocess.run(['git', 'add', 'static/data/'], check=True, cwd='/app', capture_output=True)
                
                result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, cwd='/app')
                
                if result.stdout.strip():
                    commit_msg = f"Automated price update - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
                    subprocess.run(['git', 'commit', '-m', commit_msg], check=True, cwd='/app', capture_output=True)
                    logger.info(f"Committed changes: {len(csv_files)} CSV files")
                    
                    logger.info("Pushing updated prices to GitHub...")
                    subprocess.run(['git', 'push', 'origin', 'main'], check=True, cwd='/app', capture_output=True)
                    logger.info("Successfully pushed price updates to GitHub")
                    return True
                else:
                    logger.info("No changes to commit")
                    return True
            else:
                logger.warning("No CSV files found to sync")
                return True
                
        except Exception as e:
            logger.error(f"Git sync error: {e}")
            return False
    
    def update_retailer(self, retailer: str) -> dict:
        """Update prices for a specific retailer"""
        config = self.retailers.get(retailer)
        if not config:
            return {'retailer': retailer, 'success': False, 'error': f'No configuration found for {retailer}', 'duration': 0, 'products_updated': 0}
        
        start_time = datetime.now()
        logger.info(f"Starting {retailer} price update...")
        
        try:
            script_path = self.app_path / config['updater_script']
            result = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True, timeout=1800, cwd='/app')
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                products_updated = 0
                for line in result.stdout.split('\n'):
                    if 'Successful updates:' in line:
                        try:
                            products_updated = int(line.split(':')[1].strip())
                        except:
                            pass
                
                logger.info(f"{retailer} update completed - {products_updated} products updated")
                return {'retailer': retailer, 'success': True, 'error': None, 'duration': duration, 'products_updated': products_updated}
            else:
                error_msg = result.stderr or result.stdout or 'Unknown error'
                logger.error(f"{retailer} update failed: {error_msg}")
                return {'retailer': retailer, 'success': False, 'error': error_msg, 'duration': duration, 'products_updated': 0}
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"{retailer} update crashed: {e}")
            return {'retailer': retailer, 'success': False, 'error': str(e), 'duration': duration, 'products_updated': 0}
    
    def run_full_update(self):
        """Run complete automation cycle with git sync - NO HISTORICAL FEATURES"""
        logger.info("STARTING AUTOMATED PRICE UPDATE CYCLE")
        start_time = datetime.now()
        
        self.results = {}
        
        for retailer in self.retailers.keys():
            result = self.update_retailer(retailer)
            self.results[retailer] = result
        
        git_sync_success = self.sync_to_git()
        
        total_duration = (datetime.now() - start_time).total_seconds()
        successful_retailers = sum(1 for r in self.results.values() if r['success'])
        total_products = sum(r['products_updated'] for r in self.results.values())
        
        logger.info("UPDATE SUMMARY")
        logger.info(f"Duration: {total_duration/60:.1f} minutes")
        logger.info(f"Successful: {successful_retailers}/{len(self.retailers)} retailers")
        logger.info(f"Products Updated: {total_products}")
        logger.info(f"Git Sync: {'SUCCESS' if git_sync_success else 'FAILED'}")
        
        if git_sync_success:
            logger.info("Automation complete! Updated prices are now live on your website.")
            logger.info("Run 'git pull' on your local computer to get the latest data.")
        
        return git_sync_success

# Main execution
if __name__ == "__main__":
    automation = CigarPriceAutomationEnhanced()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'manual':
        automation.run_full_update()
    else:
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger
            
            scheduler = BlockingScheduler()
            scheduler.add_job(automation.run_full_update, trigger=CronTrigger(hour=8, minute=15, timezone='America/Los_Angeles'), id='price_update_job')

            logger.info("Automation scheduled - Daily updates at 8:15 AM Pacific time")
            logger.info("Manual trigger: python automation_master.py manual")
            scheduler.start()
            
        except ImportError:
            logger.error("APScheduler not available - run manually")
            automation.run_full_update()
