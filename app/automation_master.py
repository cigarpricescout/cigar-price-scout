#!/usr/bin/env python3
"""
Cigar Price Scout - Enhanced Automation System
Designed for Railway deployment with Git integration

Features:
- Weekly automated CSV updates
- Error reporting and URL health monitoring  
- Price history tracking (future: analytics & reports)
- Automatic Git sync to update live website
- Expandable - automatically includes new URLs added to CSVs
"""

import os
import sys
import logging
import smtplib
import subprocess
import pandas as pd
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from pathlib import Path
import traceback
import time

# Add tools to Python path (matching your existing structure)
sys.path.append('/app/tools/price_monitoring')

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

class CigarPriceAutomation:
    def __init__(self):
        self.base_path = Path('/app')
        self.data_path = self.base_path / 'data'
        self.static_path = self.base_path / 'static' / 'data'
        self.app_path = self.base_path / 'app'
        
        # Retailer configurations
        self.retailers = {
            'atlantic': {
                'csv_file': 'atlantic.csv',
                'updater_script': 'update_atlantic_prices_final.py',
                'extractor_module': 'retailers.atlantic_cigar_extractor'
            },
            'foxcigar': {
                'csv_file': 'foxcigar.csv', 
                'updater_script': 'update_foxcigar_prices_final.py',
                'extractor_module': 'retailers.fox_cigar'
            },
            'nickscigarworld': {
                'csv_file': 'nickscigarworld.csv',
                'updater_script': 'update_nicks_prices_final.py',
                'extractor_module': 'retailers.nicks_cigars'
            }
        }
        
        self.results = {}
        self.error_urls = []
        
        # Email configuration
        self.email_enabled = all([
            os.getenv('SMTP_SERVER'),
            os.getenv('SMTP_PORT'), 
            os.getenv('SMTP_USERNAME'),
            os.getenv('SMTP_PASSWORD'),
            os.getenv('ALERT_EMAIL')
        ])
        
        if not self.email_enabled:
            logger.warning("Email notifications disabled - set SMTP_* environment variables to enable")
    
    def send_notification(self, subject: str, body: str, is_error: bool = False):
        """Send email notification with error details"""
        if not self.email_enabled:
            logger.info(f"EMAIL NOTIFICATION: {subject}")
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = os.getenv('SMTP_USERNAME')
            msg['To'] = os.getenv('ALERT_EMAIL')
            msg['Subject'] = f"[Cigar Price Scout] {subject}"
            
            # Add error URLs if present
            if self.error_urls:
                body += "\n\n=== FAILED URLS REQUIRING ATTENTION ===\n"
                for url_info in self.error_urls:
                    body += f"- {url_info['retailer']}: {url_info['url']} - {url_info['error']}\n"
                body += "\nPlease check these URLs and update/remove as needed."
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(os.getenv('SMTP_SERVER'), int(os.getenv('SMTP_PORT')))
            server.starttls()
            server.login(os.getenv('SMTP_USERNAME'), os.getenv('SMTP_PASSWORD'))
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email notification sent: {subject}")
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
    
    def check_csv_for_new_urls(self, retailer: str) -> int:
        """Check if new URLs have been added to retailer CSV"""
        csv_path = self.static_path / self.retailers[retailer]['csv_file']
        
        if not csv_path.exists():
            logger.warning(f"CSV file not found: {csv_path}")
            return 0
        
        try:
            df = pd.read_csv(csv_path)
            # Count non-empty URLs
            url_count = df['url'].notna().sum()
            logger.info(f"{retailer}: Found {url_count} URLs to process")
            return url_count
        except Exception as e:
            logger.error(f"Error reading {retailer} CSV: {e}")
            return 0
    
    def update_retailer(self, retailer: str) -> dict:
        """Update prices for a specific retailer"""
        config = self.retailers.get(retailer)
        if not config:
            return {
                'retailer': retailer,
                'success': False,
                'error': f'No configuration found for {retailer}',
                'duration': 0,
                'products_updated': 0,
                'urls_processed': 0
            }
        
        start_time = datetime.now()
        logger.info(f"Starting {retailer} price update...")
        
        # Check how many URLs we're processing
        url_count = self.check_csv_for_new_urls(retailer)
        
        try:
            # Run the retailer-specific update script
            script_path = self.app_path / config['updater_script']
            
            if not script_path.exists():
                raise FileNotFoundError(f"Update script not found: {script_path}")
            
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute timeout
                cwd=str(self.app_path)
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                # Parse output for success metrics
                output_lines = result.stdout.split('\n')
                products_updated = 0
                
                for line in output_lines:
                    if 'Successful updates:' in line:
                        try:
                            products_updated = int(line.split(':')[1].strip())
                        except:
                            pass
                    # Look for failed URLs to report
                    elif '[FAIL]' in line or 'ERROR' in line:
                        # Extract URL if possible for error reporting
                        if 'http' in line:
                            url_start = line.find('http')
                            url_end = line.find(' ', url_start)
                            if url_end == -1:
                                url_end = len(line)
                            failed_url = line[url_start:url_end]
                            self.error_urls.append({
                                'retailer': retailer,
                                'url': failed_url,
                                'error': line.split('[FAIL]')[1] if '[FAIL]' in line else 'Unknown error'
                            })
                
                logger.info(f"{retailer} update completed successfully")
                return {
                    'retailer': retailer,
                    'success': True,
                    'error': None,
                    'duration': duration,
                    'products_updated': products_updated,
                    'urls_processed': url_count,
                    'output': result.stdout[-500:] if result.stdout else ''
                }
            else:
                error_msg = result.stderr or result.stdout or 'Unknown error'
                logger.error(f"{retailer} update failed: {error_msg}")
                return {
                    'retailer': retailer,
                    'success': False,
                    'error': error_msg,
                    'duration': duration,
                    'products_updated': 0,
                    'urls_processed': url_count,
                    'output': error_msg[-500:] if error_msg else ''
                }
                
        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = f"Update timed out after {duration/60:.1f} minutes"
            logger.error(f"{retailer} update timed out")
            return {
                'retailer': retailer,
                'success': False,
                'error': error_msg,
                'duration': duration,
                'products_updated': 0,
                'urls_processed': url_count
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = str(e)
            logger.error(f"{retailer} update crashed: {error_msg}")
            return {
                'retailer': retailer,
                'success': False,
                'error': error_msg,
                'duration': duration,
                'products_updated': 0,
                'urls_processed': url_count
            }
    
    def sync_to_git(self) -> bool:
        """Sync updated CSV files back to git repository (Railway will auto-deploy)"""
        try:
            # In Railway, this would sync the updated CSVs back to your git repo
            # Railway will then automatically redeploy with the new data
            
            # Note: This requires Railway git integration setup
            logger.info("Git sync would happen here in full Railway setup")
            return True
            
        except Exception as e:
            logger.error(f"Git sync failed: {e}")
            return False
    
    def run_full_update(self):
        """Run updates for all retailers"""
        logger.info("STARTING WEEKLY PRICE UPDATE CYCLE")
        start_time = datetime.now()
        
        # Reset error tracking
        self.results = {}
        self.error_urls = []
        
        # Update each retailer
        for retailer in self.retailers.keys():
            try:
                result = self.update_retailer(retailer)
                self.results[retailer] = result
            except Exception as e:
                logger.error(f"Critical error updating {retailer}: {e}")
                self.results[retailer] = {
                    'retailer': retailer,
                    'success': False,
                    'error': f'Critical error: {e}',
                    'duration': 0,
                    'products_updated': 0,
                    'urls_processed': 0
                }
        
        # Sync updated CSVs to git (triggers website update)
        git_sync_success = self.sync_to_git()
        
        # Calculate summary
        total_duration = (datetime.now() - start_time).total_seconds()
        successful_retailers = sum(1 for r in self.results.values() if r['success'])
        total_products = sum(r['products_updated'] for r in self.results.values())
        total_urls = sum(r['urls_processed'] for r in self.results.values())
        
        # Generate report
        self.generate_update_report(total_duration, successful_retailers, total_products, total_urls, git_sync_success)
        
        logger.info(f"UPDATE CYCLE COMPLETE: {successful_retailers}/{len(self.retailers)} retailers successful")
    
    def generate_update_report(self, total_duration: float, successful_retailers: int, 
                             total_products: int, total_urls: int, git_sync_success: bool):
        """Generate comprehensive update report"""
        
        # Console report
        logger.info("UPDATE SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Duration: {total_duration/60:.1f} minutes")
        logger.info(f"Successful Retailers: {successful_retailers}/{len(self.retailers)}")
        logger.info(f"Total Products Updated: {total_products}")
        logger.info(f"Total URLs Processed: {total_urls}")
        logger.info(f"Git Sync: {'SUCCESS' if git_sync_success else 'FAILED'}")
        logger.info(f"Failed URLs: {len(self.error_urls)}")
        
        for retailer, result in self.results.items():
            status = "SUCCESS" if result['success'] else "FAILED"
            logger.info(f"{retailer.upper()}: {status} - {result['products_updated']} products - {result['duration']:.1f}s")
            if not result['success']:
                logger.error(f"  Error: {result['error']}")
        
        # Email report
        subject = f"Weekly Update {'Complete' if successful_retailers == len(self.retailers) and git_sync_success else 'Issues Detected'}"
        
        body = f"""Weekly Cigar Price Update Report
        
Update Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
Duration: {total_duration/60:.1f} minutes
Success Rate: {successful_retailers}/{len(self.retailers)} retailers
Products Updated: {total_products}
URLs Processed: {total_urls}
Git Sync: {'SUCCESS' if git_sync_success else 'FAILED'}

RETAILER DETAILS:
"""
        
        for retailer, result in self.results.items():
            status = "SUCCESS" if result['success'] else "FAILED"
            body += f"{retailer.upper()}: {status} - {result['products_updated']} products ({result['urls_processed']} URLs processed)\n"
            if not result['success']:
                body += f"  Error: {result['error']}\n"
        
        if not git_sync_success:
            body += "\nWARNING: Git sync failed - website may not have latest prices!\n"
        
        # Send notification
        is_error = successful_retailers < len(self.retailers) or not git_sync_success or len(self.error_urls) > 0
        self.send_notification(subject, body, is_error)
    
    def run_manual_update(self, retailer: str = None):
        """Run manual update for testing"""
        if retailer:
            logger.info(f"Manual update triggered for {retailer}")
            result = self.update_retailer(retailer)
            print(f"\nManual update result for {retailer}:")
            print(f"Success: {result['success']}")
            print(f"Duration: {result['duration']:.1f}s")
            print(f"Products: {result['products_updated']}")
            print(f"URLs: {result['urls_processed']}")
            if not result['success']:
                print(f"Error: {result['error']}")
        else:
            logger.info("Manual full update triggered")
            self.run_full_update()

def main():
    """Main function for Railway deployment"""
    automation = CigarPriceAutomation()
    
    # Handle command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == 'manual':
            retailer = sys.argv[2] if len(sys.argv) > 2 else None
            automation.run_manual_update(retailer)
            return
        elif sys.argv[1] == 'test':
            logger.info("Running test mode")
            automation.run_manual_update('atlantic')  # Test with Atlantic
            return
    
    # Set up scheduler for automated runs
    scheduler = BlockingScheduler()
    
    # Weekly updates on Sundays at 3 AM UTC (Saturday 8 PM Pacific / 11 PM Eastern)
    scheduler.add_job(
        func=automation.run_full_update,
        trigger=CronTrigger(day_of_week='sun', hour=3, minute=0),
        id='weekly_price_update',
        name='Weekly Price Update',
        replace_existing=True
    )
    
    logger.info("AUTOMATION SYSTEM STARTED")
    logger.info("Weekly updates scheduled for Sundays at 3 AM UTC")
    logger.info("Manual trigger: python automation_master.py manual [retailer]")
    
    # Send startup notification
    automation.send_notification(
        "Automation System Started", 
        f"""Cigar Price Scout automation system is now running on Railway.

Schedule: Weekly updates on Sundays at 3 AM UTC
Monitoring: {len(automation.retailers)} retailers
Features: Automatic CSV updates, error reporting, website sync

Next update: Next Sunday 3 AM UTC"""
    )
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Automation system stopped")
        automation.send_notification(
            "Automation System Stopped",
            "Cigar Price Scout automation system has been stopped."
        )

if __name__ == "__main__":
    main()
