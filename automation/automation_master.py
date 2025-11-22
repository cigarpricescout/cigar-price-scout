#!/usr/bin/env python3
"""
Cigar Price Automation - Working Version from Nov 19th
Updated for 2:50 PM PST schedule
"""

import os
import sys
import logging
import subprocess
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

class CigarPriceAutomation:
    def __init__(self):
        self.base_path = Path('/app')
        self.static_path = self.base_path / 'static' / 'data'
        
        # Retailer configurations - exact list from your working system
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
    
    def update_retailer(self, retailer: str) -> dict:
        """Update prices for a specific retailer"""
        config = self.retailers.get(retailer)
        if not config:
            return {'retailer': retailer, 'success': False, 'error': 'No configuration found', 'duration': 0}
        
        start_time = datetime.now()
        logger.info(f"Starting {retailer} price update...")
        
        try:
            script_path = Path('/app/app') / config['updater_script']
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
        """Run complete automation cycle"""
        logger.info("STARTING AUTOMATED PRICE UPDATE CYCLE")
        start_time = datetime.now()
        
        self.results = {}
        
        for retailer in self.retailers.keys():
            result = self.update_retailer(retailer)
            self.results[retailer] = result
        
        # Calculate summary
        total_duration = (datetime.now() - start_time).total_seconds()
        successful_retailers = sum(1 for r in self.results.values() if r['success'])
        total_products = sum(r.get('products_updated', 0) for r in self.results.values())
        
        logger.info("UPDATE SUMMARY")
        logger.info(f"Duration: {total_duration/60:.1f} minutes")
        logger.info(f"Successful: {successful_retailers}/{len(self.retailers)} retailers")
        logger.info(f"Products Updated: {total_products}")
        
        return True

# Main execution
if __name__ == "__main__":
    automation = CigarPriceAutomation()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'manual':
        automation.run_full_update()
    else:
        # Set up scheduler
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.cron import CronTrigger
            
            scheduler = BlockingScheduler()
            scheduler.add_job(automation.run_full_update, trigger=CronTrigger(hour=14, minute=50, timezone='America/Los_Angeles'), id='price_update_job')

            logger.info("Automation scheduled - Daily updates at 2:50 PM Pacific time")
            scheduler.start()
            
        except ImportError:
            logger.error("APScheduler not available - running manually")
            automation.run_full_update()
