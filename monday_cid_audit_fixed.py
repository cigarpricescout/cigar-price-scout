#!/usr/bin/env python3
"""
CID Metadata Consistency Audit - Fixed Version
Monday Task: Identify exact scope of metadata inconsistencies
Goal: Generate prioritized fix list for master-driven metadata sync
"""

import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

class CIDMetadataAuditor:
    def __init__(self, data_path=None):
        self.data_path = data_path
        self.master_df = None
        self.master_lookup = {}
        self.retailer_data = {}
        self.mismatches = []
        self.summary_stats = {}
        
    def load_master_database(self):
        """Load master cigars database and create lookup"""
        try:
            # Check multiple possible locations
            possible_paths = [
                'master_cigars.csv',
                'static/data/master_cigars.csv', 
                'data/master_cigars.csv',
                '../data/master_cigars.csv',
                '../../data/master_cigars.csv',
                '../static/data/master_cigars.csv',
                '../../static/data/master_cigars.csv'
            ]
            
            master_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    master_path = path
                    break
            
            if master_path is None:
                print("[ERROR] Master cigars file not found in any of these locations:")
                for path in possible_paths:
                    abs_path = os.path.abspath(path)
                    exists = "✓" if os.path.exists(path) else "✗"
                    print(f"  {exists} {abs_path}")
                
                print("\n[DEBUG] Current working directory:", os.getcwd())
                print("[DEBUG] Files in current directory:")
                try:
                    for f in sorted(os.listdir('.')):
                        if f.endswith('.csv') or 'master' in f.lower():
                            print(f"  {f}")
                except:
                    print("  Could not list files")
                
                return False
            
            self.master_df = pd.read_csv(master_path)
            print(f"[INFO] Loaded master database from: {master_path}")
            print(f"[INFO] Master database: {len(self.master_df)} products")
            
            # Show sample of columns to verify structure
            print(f"[DEBUG] Master columns: {list(self.master_df.columns[:8])}")
            
            # Create lookup dictionary
            for _, row in self.master_df.iterrows():
                cid = row.get('cigar_id', '')
                if cid:
                    self.master_lookup[cid] = {
                        'brand': row.get('Brand', ''),
                        'line': row.get('Line', ''),
                        'wrapper': row.get('Wrapper', ''),
                        'wrapper_alias': row.get('Wrapper_Alias', ''),
                        'vitola': row.get('Vitola', ''),
                        'size': f"{row.get('Length', '')}x{row.get('Ring Gauge', '')}" if row.get('Length') and row.get('Ring Gauge') else '',
                        'box_qty': row.get('Box Quantity', ''),
                        'packaging_type': row.get('packaging_type', ''),
                        'country_of_origin': row.get('country_of_origin', ''),
                        'strength': row.get('Strength', '')
                    }
            
            print(f"[INFO] Created lookup for {len(self.master_lookup)} master CIDs")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to load master database: {e}")
            return False
    
    def load_retailer_csvs(self):
        """Load all retailer CSV files"""
        retailer_files = [
            'smokeinn.csv', 'holts.csv', 'atlantic.csv', 'foxcigar.csv',
            'nickscigarworld.csv', 'hilands.csv', 'gothamcigars.csv',
            'bnbtobacco.csv', 'neptune.csv', 'tampasweethearts.csv',
            'tobaccolocker.csv', 'watchcity.csv', 'cigarsdirect.csv',
            'absolutecigars.csv', 'smallbatch_cigar.csv', 'planet_cigars.csv'
        ]
        
        # Try multiple data directories
        data_dirs = ['.', 'static/data', 'data', '../static/data', '../data']
        
        for file in retailer_files:
            found = False
            for data_dir in data_dirs:
                file_path = os.path.join(data_dir, file)
                if os.path.exists(file_path):
                    try:
                        df = pd.read_csv(file_path)
                        retailer = file.replace('.csv', '')
                        self.retailer_data[retailer] = df
                        print(f"[INFO] Loaded {retailer}: {len(df)} products from {file_path}")
                        found = True
                        break
                    except Exception as e:
                        print(f"[WARNING] Could not load {file}: {e}")
            
            if not found:
                print(f"[WARNING] Could not find {file} in any data directory")
        
        print(f"[INFO] Successfully loaded {len(self.retailer_data)} retailer CSVs")
        
        if len(self.retailer_data) == 0:
            print("[ERROR] No retailer CSVs found!")
            print("[DEBUG] Checking for CSV files in current directory:")
            try:
                csv_files = [f for f in os.listdir('.') if f.endswith('.csv')]
                for f in csv_files:
                    print(f"  {f}")
            except:
                print("  Could not list files")
            return False
        
        return True
    
    def audit_metadata_consistency(self):
        """Compare retailer metadata against master database"""
        print("\n" + "="*70)
        print("METADATA CONSISTENCY AUDIT")
        print("="*70)
        
        metadata_fields = ['brand', 'line', 'wrapper', 'vitola', 'size']
        
        retailer_stats = {}
        
        for retailer, df in self.retailer_data.items():
            print(f"\n[AUDITING] {retailer.upper()}")
            
            retailer_mismatches = 0
            missing_cids = 0
            orphaned_cids = 0
            
            if df.empty:
                print("  [WARNING] No data in CSV")
                continue
            
            retailer_stats[retailer] = {
                'total_products': len(df),
                'mismatches_by_field': defaultdict(int),
                'missing_cids': 0,
                'orphaned_cids': 0
            }
            
            # Show sample of columns for debugging
            print(f"  [DEBUG] CSV columns: {list(df.columns[:8])}")
            
            for _, row in df.iterrows():
                cid = row.get('cigar_id', '')
                
                if not cid or pd.isna(cid):
                    missing_cids += 1
                    continue
                
                if cid not in self.master_lookup:
                    orphaned_cids += 1
                    self.mismatches.append({
                        'retailer': retailer,
                        'cid': cid,
                        'issue_type': 'orphaned_cid',
                        'field': 'cigar_id',
                        'retailer_value': cid,
                        'master_value': 'NOT_FOUND'
                    })
                    continue
                
                master_data = self.master_lookup[cid]
                
                # Check each metadata field
                for field in metadata_fields:
                    retailer_value = str(row.get(field, '')).strip()
                    master_value = str(master_data.get(field, '')).strip()
                    
                    # Handle empty/null values
                    if retailer_value in ['', 'nan', 'None']:
                        retailer_value = ''
                    if master_value in ['', 'nan', 'None']:
                        master_value = ''
                    
                    if retailer_value != master_value:
                        retailer_mismatches += 1
                        retailer_stats[retailer]['mismatches_by_field'][field] += 1
                        
                        self.mismatches.append({
                            'retailer': retailer,
                            'cid': cid,
                            'issue_type': 'metadata_mismatch',
                            'field': field,
                            'retailer_value': retailer_value,
                            'master_value': master_value
                        })
            
            retailer_stats[retailer]['missing_cids'] = missing_cids
            retailer_stats[retailer]['orphaned_cids'] = orphaned_cids
            
            # Print retailer summary
            total_issues = retailer_mismatches + missing_cids + orphaned_cids
            if total_issues == 0:
                print(f"  [OK] Perfect consistency - {len(df)} products")
            else:
                print(f"  [ISSUES] {total_issues} total problems:")
                if retailer_mismatches > 0:
                    print(f"    Metadata mismatches: {retailer_mismatches}")
                    for field, count in retailer_stats[retailer]['mismatches_by_field'].items():
                        print(f"      {field}: {count}")
                if missing_cids > 0:
                    print(f"    Missing CIDs: {missing_cids}")
                if orphaned_cids > 0:
                    print(f"    Orphaned CIDs: {orphaned_cids}")
        
        self.summary_stats = retailer_stats
    
    def generate_detailed_mismatch_report(self):
        """Generate detailed report of all mismatches"""
        print(f"\n" + "="*70)
        print("DETAILED MISMATCH REPORT")
        print("="*70)
        
        if len(self.mismatches) == 0:
            print("No mismatches found! All retailer metadata is consistent with master database.")
            return
        
        # Group mismatches by type
        by_type = defaultdict(list)
        for mismatch in self.mismatches:
            by_type[mismatch['issue_type']].append(mismatch)
        
        print(f"\nTOTAL MISMATCHES: {len(self.mismatches)}")
        
        # Show metadata mismatches
        if 'metadata_mismatch' in by_type:
            metadata_mismatches = by_type['metadata_mismatch']
            print(f"\nMETADATA MISMATCHES: {len(metadata_mismatches)}")
            
            # Group by field
            by_field = defaultdict(list)
            for m in metadata_mismatches:
                by_field[m['field']].append(m)
            
            for field, mismatches in by_field.items():
                print(f"\n  {field.upper()} MISMATCHES ({len(mismatches)}):")
                
                # Show first 5 examples
                for mismatch in mismatches[:5]:
                    print(f"    {mismatch['retailer']}: {mismatch['cid']}")
                    print(f"      Retailer: '{mismatch['retailer_value']}'")
                    print(f"      Master:   '{mismatch['master_value']}'")
                
                if len(mismatches) > 5:
                    print(f"    ... and {len(mismatches) - 5} more")
        
        # Show orphaned CIDs
        if 'orphaned_cid' in by_type:
            orphaned = by_type['orphaned_cid']
            print(f"\nORPHANED CIDs: {len(orphaned)}")
            
            # Group by retailer
            by_retailer = defaultdict(list)
            for m in orphaned:
                by_retailer[m['retailer']].append(m)
            
            for retailer, orphans in by_retailer.items():
                print(f"  {retailer}: {len(orphans)} orphaned CIDs")
                for orphan in orphans[:3]:
                    print(f"    {orphan['cid']}")
                if len(orphans) > 3:
                    print(f"    ... and {len(orphans) - 3} more")
    
    def generate_priority_fix_list(self):
        """Generate prioritized list of retailers to fix"""
        print(f"\n" + "="*70)
        print("PRIORITY FIX LIST")
        print("="*70)
        
        if not self.summary_stats:
            print("No retailers loaded for analysis.")
            return []
        
        # Calculate priority scores
        retailer_priorities = []
        
        for retailer, stats in self.summary_stats.items():
            if stats['total_products'] == 0:
                continue
            
            total_issues = (sum(stats['mismatches_by_field'].values()) + 
                          stats['missing_cids'] + stats['orphaned_cids'])
            
            issue_rate = total_issues / stats['total_products']
            
            # Priority score: issue rate weighted by product count
            priority_score = issue_rate * stats['total_products']
            
            retailer_priorities.append({
                'retailer': retailer,
                'total_products': stats['total_products'],
                'total_issues': total_issues,
                'issue_rate': issue_rate,
                'priority_score': priority_score
            })
        
        # Sort by priority score (descending)
        retailer_priorities.sort(key=lambda x: x['priority_score'], reverse=True)
        
        print(f"RECOMMENDED FIX ORDER:")
        print(f"Rank | Retailer           | Products | Issues | Rate   | Priority")
        print(f"-----|--------------------|---------:|-------:|-------:|---------:")
        
        for i, retailer_info in enumerate(retailer_priorities, 1):
            print(f"{i:4} | {retailer_info['retailer']:18} | "
                  f"{retailer_info['total_products']:7} | "
                  f"{retailer_info['total_issues']:6} | "
                  f"{retailer_info['issue_rate']:5.1%} | "
                  f"{retailer_info['priority_score']:7.1f}")
        
        return retailer_priorities
    
    def save_audit_results(self):
        """Save detailed audit results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save mismatches to CSV
        if self.mismatches:
            mismatches_df = pd.DataFrame(self.mismatches)
            mismatches_file = f"cid_mismatches_{timestamp}.csv"
            mismatches_df.to_csv(mismatches_file, index=False)
            print(f"\n[SAVED] Detailed mismatches: {mismatches_file}")
        else:
            print(f"\n[INFO] No mismatches to save - perfect consistency!")
        
        # Save summary statistics
        summary_file = f"audit_summary_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write(f"CID Metadata Consistency Audit - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"OVERVIEW:\n")
            f.write(f"Master database: {len(self.master_df) if self.master_df is not None else 0} products\n")
            f.write(f"Retailers analyzed: {len(self.retailer_data)}\n")
            f.write(f"Total mismatches: {len(self.mismatches)}\n\n")
            
            for retailer, stats in self.summary_stats.items():
                total_issues = (sum(stats['mismatches_by_field'].values()) + 
                              stats['missing_cids'] + stats['orphaned_cids'])
                f.write(f"{retailer}: {total_issues} issues out of {stats['total_products']} products\n")
        
        print(f"[SAVED] Summary report: {summary_file}")
        
        return summary_file
    
    def run_complete_audit(self):
        """Run complete Monday audit process"""
        print("MONDAY TASK: CID METADATA CONSISTENCY AUDIT")
        print("="*70)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Step 1: Load master database
        if not self.load_master_database():
            print("\n[FAILED] Could not load master database")
            return False
        
        # Step 2: Load retailer CSVs
        if not self.load_retailer_csvs():
            print("\n[FAILED] Could not load retailer CSVs")
            return False
        
        # Step 3: Audit metadata consistency
        self.audit_metadata_consistency()
        
        # Step 4: Generate detailed reports
        self.generate_detailed_mismatch_report()
        
        # Step 5: Generate priority fix list
        priority_list = self.generate_priority_fix_list()
        
        # Step 6: Save results
        self.save_audit_results()
        
        print(f"\n" + "="*70)
        print("MONDAY AUDIT COMPLETE")
        print("="*70)
        if priority_list:
            print(f"Next: Tuesday - Build master sync framework")
            print(f"Start with: {priority_list[0]['retailer']}")
        else:
            print("Perfect consistency found! Ready for Tuesday framework development.")
        
        return True

def main():
    """Monday execution"""
    auditor = CIDMetadataAuditor()
    
    success = auditor.run_complete_audit()
    
    if not success:
        print("\n[HELP] Make sure you're running this from your project root directory")
        print("       where master_cigars.csv and retailer CSV files are located.")
        sys.exit(1)
    
    print(f"\n[SUCCESS] Monday audit complete!")
    print(f"[NEXT] Tuesday: Build master sync framework")

if __name__ == "__main__":
    main()
