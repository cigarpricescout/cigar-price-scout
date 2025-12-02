#!/usr/bin/env python3
"""
Local Auto-Discovery Price Updater
Automatically finds and runs all retailer price update scripts

Usage:
  python local_auto_updater.py           # Run all discovered retailers
  python local_auto_updater.py atlantic  # Run specific retailer only
"""

import os
import sys
import glob
import subprocess
import time
from datetime import datetime
from pathlib import Path


class LocalPriceUpdater:
    def __init__(self):
        self.base_path = Path('.')
        # Try multiple common CSV locations
        self.csv_search_paths = [
            self.base_path / '..' / 'static' / 'data',  # MAIN CSV LOCATION - prioritize this!
            self.base_path / 'static' / 'data',
            self.base_path / 'data', 
            self.base_path,  # Current directory
        ]
        self.results = {}
    
    def find_csv_file(self, csv_name):
        """Search for CSV file in multiple locations"""
        for search_path in self.csv_search_paths:
            csv_path = search_path / csv_name
            if csv_path.exists():
                return csv_path
        return None
    
    def discover_retailers(self):
        """Auto-discover retailers based on file naming convention"""
        print("Auto-discovering retailer update scripts...")
        
        retailers = {}
        
        # Look for update_*_prices*.py scripts
        script_patterns = [
            'update_*_prices_final.py',
            'update_*_prices.py'
        ]
        
        for pattern in script_patterns:
            for script_path in glob.glob(pattern):
                script_name = os.path.basename(script_path)
                
                # Extract retailer name from script name and map to correct CSV names
                script_base = script_name.replace('update_', '').replace('_prices_final.py', '').replace('_prices.py', '')
                
                # Map script names to actual CSV names
                retailer_name_map = {
                    'absolute_cigars': 'absolutecigars',           # update_absolute_cigars_* -> absolutecigars.csv
                    'atlantic': 'atlantic',
                    'bnbtobacco': 'bnbtobacco', 
                    'cccrafter': 'cccrafter',                      # update_cccrafter_* -> cccrafter.csv
                    'cigarplace': 'cigarplace',                    # update_cigarplace_* -> cigarplace.csv
                    'cigarsdirect': 'cigarsdirect',                # update_cigarsdirect_* -> cigarsdirect.csv
                    'foxcigar': 'foxcigar',
                    'gotham': 'gothamcigars',                      # update_gotham_* -> gothamcigars.csv
                    'hilandscigars': 'hilands',                    # update_hilandscigars_* -> hilands.csv
                    'holts': 'holts',                              # update_holts_* -> holts.csv
                    'neptune': 'neptune',
                    'nicks': 'nickscigarworld',                    # update_nicks_* -> nickscigarworld.csv
                    'planet_cigars': 'planetcigars',               # update_planet_cigars_* -> planetcigars.csv
                    'smallbatch_cigar': 'smallbatchcigar',         # update_smallbatch_cigar_* -> smallbatchcigar.csv
                    'smokeinn': 'smokeinn',                        # update_smokeinn_* -> smokeinn.csv
                    'tampasweethearts': 'tampasweethearts',        # update_tampasweethearts_* -> tampasweethearts.csv
                    'tobaccolocker': 'tobaccolocker',              # update_tobaccolocker_* -> tobaccolocker.csv
                    'two_guys': 'twoguys',                         # update_two_guys_* -> twoguys.csv
                    'watchcity': 'watchcity'                       # update_watchcity_* -> watchcity.csv
                }
                
                retailer_name = retailer_name_map.get(script_base, script_base)
                csv_file = f'{retailer_name}.csv'
                
                # Check if CSV exists
                csv_path = self.find_csv_file(csv_file)
                
                if csv_path:
                    retailers[retailer_name] = {
                        'script': script_path,
                        'csv_file': csv_file
                    }
                    print(f"  Found: {retailer_name} -> {script_path} + {csv_file}")
                else:
                    print(f"  Skipping: {script_path} (no matching CSV found: {csv_file})")
        
        return retailers
    
    def run_retailer_update(self, retailer_name, config):
        """Run update for a specific retailer"""
        print(f"\n--- Updating {retailer_name.upper()} ---")
        start_time = datetime.now()
        
        try:
            # Run the update script
            result = subprocess.run(
                [sys.executable, config['script']],
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Parse output for metrics
            output_lines = result.stdout.split('\n') if result.stdout else []
            error_lines = result.stderr.split('\n') if result.stderr else []
            
            success_count = 0
            fail_count = 0
            
            # Look for success/failure indicators in output
            for line in output_lines + error_lines:
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
            
            if result.returncode == 0:
                print(f"SUCCESS - {success_count} products updated in {duration:.1f}s")
                return {
                    'success': True,
                    'duration': duration,
                    'products_updated': success_count,
                    'products_failed': fail_count
                }
            else:
                error_msg = result.stderr or result.stdout or 'Unknown error'
                print(f"FAILED - {error_msg[:200]}")
                return {
                    'success': False,
                    'duration': duration,
                    'error': error_msg,
                    'products_updated': success_count,
                    'products_failed': fail_count
                }
                
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT - Script exceeded 30 minute limit")
            return {
                'success': False,
                'duration': 1800,
                'error': 'Timeout after 30 minutes',
                'products_updated': 0,
                'products_failed': 0
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            print(f"CRASHED - {str(e)}")
            return {
                'success': False,
                'duration': duration,
                'error': str(e),
                'products_updated': 0,
                'products_failed': 0
            }
    
    def apply_promotions(self):
        """Apply active promotions to all retailer CSVs"""
        print("\n--- APPLYING PROMOTIONS ---")
        start_time = datetime.now()
        
        try:
            import subprocess
            import os
            
            # Exact path from app/ to tools/promotions/
            promo_script = "../tools/promotions/apply_promos.py"
            
            # Convert to absolute path to be safe
            promo_script = os.path.abspath(promo_script)
            
            print(f"Looking for promo script at: {promo_script}")
            
            if not os.path.exists(promo_script):
                print(f"Promo script not found at: {promo_script}")
                return False
                
            # Run from the promotions directory so imports work correctly
            promo_dir = os.path.dirname(promo_script)
            
            result = subprocess.run(
                [sys.executable, "apply_promos.py"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=promo_dir  # This is the key - run FROM the promotions directory
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                print(f"Promotions applied successfully in {duration:.1f}s")
                if result.stdout:
                    print(result.stdout)
                return True
            else:
                print(f"Promotion application failed:")
                print(result.stderr)
                return False
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            print(f"Promotion application crashed: {str(e)}")
            return False
    
    def run_all_updates(self, specific_retailer=None):
        """Run updates for all or specific retailer"""
        print("=" * 60)
        print(f"LOCAL PRICE UPDATER - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # Discover available retailers
        retailers = self.discover_retailers()
        
        if not retailers:
            print("No retailer update scripts found!")
            return False
        
        # Filter to specific retailer if requested
        if specific_retailer:
            if specific_retailer in retailers:
                retailers = {specific_retailer: retailers[specific_retailer]}
            else:
                print(f"Retailer '{specific_retailer}' not found!")
                print(f"Available retailers: {', '.join(retailers.keys())}")
                return False
        
        print(f"\nRunning updates for {len(retailers)} retailer(s)...")
        
        # Run updates
        total_start = datetime.now()
        
        for retailer_name, config in retailers.items():
            result = self.run_retailer_update(retailer_name, config)
            self.results[retailer_name] = result
            
            # Small delay between retailers
            if len(retailers) > 1:
                time.sleep(2)
        
        # Apply promotions after all price updates
        print(f"\nAll price updates completed. Applying promotions...")
        promo_success = self.apply_promotions()

        # Summary report
        self.print_summary(total_start)

        return True
    
    def print_summary(self, start_time):
        """Print final summary report"""
        total_duration = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "=" * 60)
        print("UPDATE SUMMARY")
        print("=" * 60)
        
        successful = 0
        failed = 0
        total_products = 0
        total_failures = 0
        
        for retailer, result in self.results.items():
            status = "SUCCESS" if result['success'] else "FAILED"
            duration = result['duration']
            products = result.get('products_updated', 0)
            
            print(f"{retailer:15} | {status:7} | {duration:6.1f}s | {products:3d} products")
            
            if result['success']:
                successful += 1
            else:
                failed += 1
            
            total_products += products
            total_failures += result.get('products_failed', 0)
        
        print("-" * 60)
        print(f"TOTAL RUNTIME: {total_duration/60:.1f} minutes")
        print(f"SUCCESS RATE:  {successful}/{len(self.results)} retailers")
        print(f"PRODUCTS:      {total_products} updated, {total_failures} failed")
        print("=" * 60)


def main():
    updater = LocalPriceUpdater()
    
    # Check for specific retailer argument
    specific_retailer = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Run the updates
    success = updater.run_all_updates(specific_retailer)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
