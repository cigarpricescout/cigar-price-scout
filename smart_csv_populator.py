#!/usr/bin/env python3
"""
Smart CSV Populator - Add top 100 priority CIDs to retailer CSVs
Ensures no duplicates and preserves existing data
"""

import pandas as pd
import argparse
from pathlib import Path
from datetime import datetime
import shutil
from typing import Dict, List, Tuple

class SmartCIDPopulator:
    def __init__(self, priority_cids_file: str, retailer_csv_dir: str, master_csv: str):
        """Initialize the populator with file paths"""
        self.priority_cids_file = Path(priority_cids_file)
        self.retailer_dir = Path(retailer_csv_dir)
        self.master_csv_path = Path(master_csv)
        
        # Load priority CIDs
        print(f"Loading priority CIDs from: {self.priority_cids_file}")
        self.priority_cids_df = pd.read_csv(self.priority_cids_file)
        print(f"  Loaded {len(self.priority_cids_df)} priority CIDs")
        
        # Load master cigars for metadata
        print(f"Loading master cigars from: {self.master_csv_path}")
        self.master_df = pd.read_csv(self.master_csv_path)
        print(f"  Loaded {len(self.master_df)} total CIDs from master")
        
        # Results tracking
        self.results = {}
        
    def get_retailer_csvs(self) -> List[Path]:
        """Get all active retailer CSV files (exclude backups)"""
        csv_files = [f for f in self.retailer_dir.glob('*.csv') if 'backup' not in f.name.lower()]
        return sorted(csv_files)
    
    def create_backup(self, csv_file: Path) -> Path:
        """Create timestamped backup of CSV file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{csv_file.stem}_backup_{timestamp}{csv_file.suffix}"
        backup_path = csv_file.parent / backup_name
        shutil.copy2(csv_file, backup_path)
        return backup_path
    
    def populate_single_retailer(self, retailer_csv: Path, dry_run: bool = False) -> Dict:
        """
        Populate a single retailer CSV with missing priority CIDs
        
        Returns:
            Dict with results: added_count, skipped_count, etc.
        """
        retailer_name = retailer_csv.stem
        
        # Load existing retailer data
        try:
            existing_df = pd.read_csv(retailer_csv)
        except Exception as e:
            return {
                'retailer': retailer_name,
                'status': 'error',
                'error': str(e),
                'added': 0,
                'skipped': 0
            }
        
        # Get existing CIDs
        existing_cids = set(existing_df['cigar_id'].values)
        
        # Filter priority CIDs to only missing ones
        missing_cids = []
        for _, row in self.priority_cids_df.iterrows():
            cid = row['cigar_id']
            if cid not in existing_cids:
                missing_cids.append(row)
        
        # Create new rows with metadata from master
        new_rows = []
        for cid_row in missing_cids:
            # Get full metadata from master
            master_row = self.master_df[self.master_df['cigar_id'] == cid_row['cigar_id']]
            if master_row.empty:
                continue
            
            master_data = master_row.iloc[0]
            
            # Create new row matching retailer CSV structure
            new_row = {
                'cigar_id': master_data['cigar_id'],
                'title': master_data['product_name'] if pd.notna(master_data['product_name']) else master_data['Vitola'],
                'url': '',  # Empty - to be researched by user
                'brand': master_data['Brand'],
                'line': master_data['Line'],
                'wrapper': master_data['Wrapper'],
                'vitola': master_data['Vitola'],
                'size': f"{master_data['Length']}x{master_data['Ring Gauge']}",
                'box_qty': master_data['Box Quantity'],
                'price': '',  # Empty - will be filled by extractor
                'in_stock': '',  # Empty - will be filled by extractor
                'current_promotions_applied': ''
            }
            new_rows.append(new_row)
        
        result = {
            'retailer': retailer_name,
            'existing_cids': len(existing_cids),
            'added': len(new_rows),
            'skipped': len(self.priority_cids_df) - len(new_rows),
            'total_after': len(existing_cids) + len(new_rows),
            'status': 'success'
        }
        
        # If dry run, don't actually modify files
        if dry_run:
            result['mode'] = 'dry_run'
            return result
        
        # Actually modify the file
        if new_rows:
            # Create backup first
            backup_path = self.create_backup(retailer_csv)
            result['backup'] = str(backup_path)
            
            # Append new rows
            new_df = pd.DataFrame(new_rows)
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            
            # Save updated CSV
            combined.to_csv(retailer_csv, index=False)
            result['mode'] = 'executed'
        else:
            result['mode'] = 'no_changes'
        
        return result
    
    def populate_all_retailers(self, dry_run: bool = False):
        """Populate all retailer CSVs"""
        retailer_csvs = self.get_retailer_csvs()
        
        print("\n" + "="*80)
        if dry_run:
            print("DRY RUN - NO FILES WILL BE MODIFIED")
        else:
            print("EXECUTING - FILES WILL BE MODIFIED")
        print("="*80)
        print(f"\nProcessing {len(retailer_csvs)} retailer CSVs...")
        
        for csv_file in retailer_csvs:
            result = self.populate_single_retailer(csv_file, dry_run=dry_run)
            self.results[result['retailer']] = result
            
            # Print progress
            status_icon = "+" if result.get('added', 0) > 0 else "-"
            print(f"  {status_icon} {result['retailer']:25s} | Existing: {result.get('existing_cids', 0):3d} | "
                  f"Added: {result.get('added', 0):3d} | Skipped: {result.get('skipped', 0):3d} | "
                  f"Total: {result.get('total_after', 0):3d}")
    
    def generate_summary_report(self) -> str:
        """Generate summary report of population results"""
        report = []
        report.append("="*80)
        report.append("SMART CSV POPULATOR - SUMMARY REPORT")
        report.append("="*80)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Priority CIDs: {len(self.priority_cids_df)}")
        report.append(f"Retailers processed: {len(self.results)}")
        report.append("")
        
        # Calculate totals
        total_added = sum(r.get('added', 0) for r in self.results.values())
        total_skipped = sum(r.get('skipped', 0) for r in self.results.values())
        
        report.append("OVERALL STATISTICS:")
        report.append(f"  Total CIDs added across all retailers: {total_added}")
        report.append(f"  Total CIDs skipped (already existed): {total_skipped}")
        report.append("")
        
        # Breakdown by retailer
        report.append("BREAKDOWN BY RETAILER:")
        report.append("")
        report.append(f"{'Retailer':<30} {'Existing':>10} {'Added':>10} {'Total':>10}")
        report.append("-" * 80)
        
        for retailer_name in sorted(self.results.keys()):
            result = self.results[retailer_name]
            if result['status'] == 'success':
                report.append(
                    f"{retailer_name:<30} "
                    f"{result.get('existing_cids', 0):>10} "
                    f"{result.get('added', 0):>10} "
                    f"{result.get('total_after', 0):>10}"
                )
        
        report.append("")
        report.append("="*80)
        
        # Retailers with most additions
        top_additions = sorted(
            [(r['retailer'], r.get('added', 0)) for r in self.results.values()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        report.append("TOP 10 RETAILERS BY CIDS ADDED:")
        for retailer, count in top_additions:
            report.append(f"  {retailer}: {count} CIDs")
        
        report.append("")
        report.append("="*80)
        report.append("NEXT STEPS:")
        report.append("  1. Review this summary report")
        report.append("  2. Manually research and add URLs for the new CIDs")
        report.append("  3. Run retailer updater scripts to populate prices")
        report.append("  4. Commit changes to Git")
        report.append("="*80)
        
        return "\n".join(report)
    
    def save_summary_report(self, filename: str = "population_summary.txt"):
        """Save summary report to file"""
        report = self.generate_summary_report()
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\nSummary report saved to: {filename}")
        return filename

def main():
    parser = argparse.ArgumentParser(
        description='Smart CSV Populator - Add priority CIDs to retailer CSVs'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute and modify retailer CSV files'
    )
    parser.add_argument(
        '--priority-cids',
        default='top_100_priority_cids.csv',
        help='Path to priority CIDs CSV file'
    )
    parser.add_argument(
        '--retailer-dir',
        default='static/data',
        help='Directory containing retailer CSV files'
    )
    parser.add_argument(
        '--master-csv',
        default='data/master_cigars.csv',
        help='Path to master cigars CSV file'
    )
    
    args = parser.parse_args()
    
    # Require either --dry-run or --execute
    if not (args.dry_run or args.execute):
        parser.error('Must specify either --dry-run or --execute')
    
    if args.dry_run and args.execute:
        parser.error('Cannot specify both --dry-run and --execute')
    
    # Initialize populator
    populator = SmartCIDPopulator(
        priority_cids_file=args.priority_cids,
        retailer_csv_dir=args.retailer_dir,
        master_csv=args.master_csv
    )
    
    # Run population
    populator.populate_all_retailers(dry_run=args.dry_run)
    
    # Generate and display summary
    print("\n" + populator.generate_summary_report())
    
    # Save report if executed
    if args.execute:
        populator.save_summary_report()

if __name__ == '__main__':
    main()
