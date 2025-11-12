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
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/automation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CigarPriceAutomationEnhanced:
    def __init__(self):
        self.base_path = Path('/app')
        self.static_path = self.base_path / 'static' / 'data'
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
        }
        
        self.results = {}
        self.error_urls = []
        
        # Setup git authentication
        self.setup_git_auth()
    
    def setup_git_auth(self):
        """Configure git with GitHub token for authentication"""
        try:
            # Get GitHub token from environment
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                logger.warning("No GITHUB_TOKEN found - git sync will be disabled")
                return False
            
            # Configure git credentials
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
            
            logger.info("✓ Git authentication configured")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup git authentication: {e}")
            return False
    
    def sync_to_git(self) -> bool:
        """Sync updated CSV files back to GitHub"""
        try:
            # Check if we have git authentication
            if not os.path.exists('/app/.git-credentials'):
                logger.warning("Git credentials not configured - skipping sync")
                return False
            
            # Pull latest changes first
            logger.info("Pulling latest changes from GitHub...")
            subprocess.run(['git', 'pull', 'origin', 'main'], 
                          check=True, cwd='/app', capture_output=True)
            
            # Add the updated CSV files
            subprocess.run(['git', 'add', 'static/data/*.csv'], 
                          check=True, cwd='/app')
            
            # Check if there are any changes to commit
            result = subprocess.run(['git', 'diff', '--cached', '--exit-code'], 
                                  capture_output=True, cwd='/app')
            
            if result.returncode == 0:
                logger.info("No price changes detected - skipping commit")
                return True
            
            # Commit the changes
            commit_msg = f"🤖 Automated price update - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
            subprocess.run(['git', 'commit', '-m', commit_msg], 
                          check=True, cwd='/app')
            
            # Push to GitHub
            logger.info("Pushing updated prices to GitHub...")
            push_result = subprocess.run(['git', 'push', 'origin', 'main'], 
                                       capture_output=True, text=True, cwd='/app')
            
            if push_result.returncode == 0:
                logger.info("✅ Updated CSV files synced back to GitHub")
                return True
            else:
                logger.error(f"Git push failed: {push_result.stderr}")
                return False
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git sync failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in git sync: {e}")
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
        logger.info(f"🔄 Starting {retailer} price update...")
        
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
                
                logger.info(f"✅ {retailer} update completed - {products_updated} products updated")
                return {
                    'retailer': retailer,
                    'success': True,
                    'error': None,
                    'duration': duration,
                    'products_updated': products_updated
                }
            else:
                error_msg = result.stderr or result.stdout or 'Unknown error'
                logger.error(f"❌ {retailer} update failed: {error_msg}")
                return {
                    'retailer': retailer,
                    'success': False,
                    'error': error_msg,
                    'duration': duration,
                    'products_updated': 0
                }
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"💥 {retailer} update crashed: {e}")
            return {
                'retailer': retailer,
                'success': False,
                'error': str(e),
                'duration': duration,
                'products_updated': 0
            }
    
    def run_full_update(self):
        """Run complete automation cycle with git sync"""
        logger.info("🚀 STARTING AUTOMATED PRICE UPDATE CYCLE")
        start_time = datetime.now()
        
        # Reset tracking
        self.results = {}
        
        # Update each retailer
        for retailer in self.retailers.keys():
            result = self.update_retailer(retailer)
            self.results[retailer] = result
        
        # Sync updated CSVs back to GitHub
        git_sync_success = self.sync_to_git()
        
        # Calculate summary
        total_duration = (datetime.now() - start_time).total_seconds()
        successful_retailers = sum(1 for r in self.results.values() if r['success'])
        total_products = sum(r['products_updated'] for r in self.results.values())
        
        # Generate report
        logger.info("📊 UPDATE SUMMARY")
        logger.info(f"Duration: {total_duration/60:.1f} minutes")
        logger.info(f"Successful: {successful_retailers}/{len(self.retailers)} retailers")
        logger.info(f"Products Updated: {total_products}")
        logger.info(f"Git Sync: {'SUCCESS' if git_sync_success else 'FAILED'}")
        
        if git_sync_success:
            logger.info("🎉 Automation complete! Updated prices are now live on your website.")
            logger.info("💡 Run 'git pull' on your local computer to get the latest data.")
        
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
            scheduler.add_job(
                func=automation.run_full_update,
                trigger=CronTrigger(day_of_week='sun', hour=3, minute=0),
                id='weekly_update',
                replace_existing=True
            )
            
            logger.info("📅 Automation scheduled - Weekly updates Sundays 3 AM UTC")
            logger.info("🔧 Manual trigger: python automation_master_enhanced.py manual")
            scheduler.start()
            
        except ImportError:
            logger.error("APScheduler not available - run manually")
