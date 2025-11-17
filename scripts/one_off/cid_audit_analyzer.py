#!/usr/bin/env python3
"""
Comprehensive CID Audit and Scalability Analysis
Analyzes cigar_id consistency across retailers and evaluates scalability
"""

import os
import sys
import pandas as pd
import numpy as np
from collections import defaultdict, Counter
from pathlib import Path
import re

class CIDAnalyzer:
    def __init__(self, data_path='data'):
        self.data_path = Path(data_path)
        self.master_df = None
        self.retailer_data = {}
        self.issues = defaultdict(list)
        
    def load_all_data(self):
        """Load master database and all retailer CSVs"""
        try:
            # Load master database
            master_path = self.data_path / 'master_cigars.csv'
            if master_path.exists():
                self.master_df = pd.read_csv(master_path)
                print(f"[INFO] Loaded master database: {len(self.master_df)} products")
            else:
                print("[ERROR] Master cigars file not found")
                return False
            
            # Load retailer CSVs
            retailer_files = [
                'smokeinn.csv', 'holts.csv', 'atlantic.csv', 'foxcigar.csv',
                'nickscigarworld.csv', 'hilands.csv', 'gothamcigars.csv',
                'bnbtobacco.csv', 'neptune.csv', 'tampasweethearts.csv',
                'tobaccolocker.csv', 'watchcity.csv', 'cigarsdirect.csv',
                'absolutecigars.csv', 'smallbatch_cigar.csv', 'planet_cigars.csv'
            ]
            
            for file in retailer_files:
                file_path = self.data_path / file
                if file_path.exists():
                    try:
                        df = pd.read_csv(file_path)
                        retailer = file.replace('.csv', '')
                        self.retailer_data[retailer] = df
                        print(f"[INFO] Loaded {retailer}: {len(df)} products")
                    except Exception as e:
                        print(f"[WARNING] Could not load {file}: {e}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to load data: {e}")
            return False
    
    def analyze_cid_structure(self):
        """Analyze the current CID structure for scalability issues"""
        print("\n" + "="*70)
        print("CID STRUCTURE ANALYSIS")
        print("="*70)
        
        if self.master_df is None:
            return
        
        # Analyze CID format
        sample_cids = self.master_df['cigar_id'].dropna().head(10)
        print(f"Sample CIDs:")
        for cid in sample_cids:
            print(f"  {cid}")
        
        # Parse CID structure
        cid_parts_analysis = []
        for cid in self.master_df['cigar_id'].dropna():
            parts = cid.split('|')
            cid_parts_analysis.append({
                'total_parts': len(parts),
                'brand': parts[0] if len(parts) > 0 else '',
                'brand_repeat': parts[1] if len(parts) > 1 else '',
                'line': parts[2] if len(parts) > 2 else '',
                'vitola': parts[3] if len(parts) > 3 else '',
                'vitola_repeat': parts[4] if len(parts) > 4 else '',
                'size': parts[5] if len(parts) > 5 else '',
                'wrapper': parts[6] if len(parts) > 6 else '',
                'packaging': parts[7] if len(parts) > 7 else ''
            })
        
        parts_df = pd.DataFrame(cid_parts_analysis)
        
        print(f"\nCID STRUCTURE ANALYSIS:")
        print(f"Total parts distribution: {parts_df['total_parts'].value_counts().to_dict()}")
        print(f"Unique brands: {parts_df['brand'].nunique()}")
        print(f"Unique lines: {parts_df['line'].nunique()}")
        print(f"Unique vitolas: {parts_df['vitola'].nunique()}")
        print(f"Unique wrappers: {parts_df['wrapper'].nunique()}")
        
        # Identify scalability issues
        print(f"\nSCALABILITY CONCERNS:")
        
        # Check for brand repetition
        brand_mismatches = sum(1 for _, row in parts_df.iterrows() 
                              if row['brand'] != row['brand_repeat'])
        if brand_mismatches > 0:
            print(f"  [WARNING] {brand_mismatches} CIDs have mismatched brand repetition")
        
        # Check for vitola repetition  
        vitola_mismatches = sum(1 for _, row in parts_df.iterrows() 
                               if row['vitola'] != row['vitola_repeat'])
        if vitola_mismatches > 0:
            print(f"  [WARNING] {vitola_mismatches} CIDs have mismatched vitola repetition")
        
        # Check wrapper code consistency
        wrapper_codes = parts_df['wrapper'].unique()
        print(f"  Wrapper codes used: {sorted([w for w in wrapper_codes if w])}")
        
        # Check for problematic characters in CIDs
        special_char_issues = []
        for cid in self.master_df['cigar_id'].dropna():
            if any(char in cid for char in [' ', '.', '(', ')', '&', '#']):
                special_char_issues.append(cid)
        
        if special_char_issues:
            print(f"  [WARNING] {len(special_char_issues)} CIDs contain special characters")
            for cid in special_char_issues[:5]:
                print(f"    Example: {cid}")
    
    def find_cid_inconsistencies(self):
        """Find products that should have same CID but don't"""
        print("\n" + "="*70)
        print("CID CONSISTENCY ANALYSIS")
        print("="*70)
        
        # Collect all CIDs across all retailers
        all_products = []
        
        # Add master products
        for _, row in self.master_df.iterrows():
            all_products.append({
                'source': 'master',
                'cigar_id': row['cigar_id'],
                'brand': row.get('Brand', ''),
                'line': row.get('Line', ''), 
                'vitola': row.get('Vitola', ''),
                'size': f"{row.get('Length', '')}x{row.get('Ring Gauge', '')}",
                'wrapper': row.get('Wrapper', ''),
                'box_qty': row.get('Box Quantity', '')
            })
        
        # Add retailer products
        for retailer, df in self.retailer_data.items():
            for _, row in df.iterrows():
                if pd.notna(row.get('cigar_id')):
                    all_products.append({
                        'source': retailer,
                        'cigar_id': row.get('cigar_id', ''),
                        'brand': row.get('brand', ''),
                        'line': row.get('line', ''),
                        'vitola': row.get('vitola', ''),
                        'size': row.get('size', ''),
                        'wrapper': row.get('wrapper', ''),
                        'box_qty': row.get('box_qty', '')
                    })
        
        products_df = pd.DataFrame(all_products)
        
        # Group by product characteristics to find duplicates
        product_groups = products_df.groupby(['brand', 'line', 'vitola', 'size', 'wrapper'])
        
        print(f"INCONSISTENCY ANALYSIS:")
        inconsistent_groups = 0
        total_inconsistencies = 0
        
        for (brand, line, vitola, size, wrapper), group in product_groups:
            unique_cids = group['cigar_id'].unique()
            if len(unique_cids) > 1:
                inconsistent_groups += 1
                total_inconsistencies += len(group) - 1
                
                print(f"\n  [INCONSISTENCY] {brand} {line} {vitola} ({size})")
                print(f"    Wrapper: {wrapper}")
                print(f"    Different CIDs found:")
                for cid in unique_cids:
                    sources = group[group['cigar_id'] == cid]['source'].tolist()
                    print(f"      {cid} (in: {', '.join(sources)})")
        
        print(f"\nSUMMARY:")
        print(f"  Product groups with inconsistent CIDs: {inconsistent_groups}")
        print(f"  Total products affected: {total_inconsistencies}")
        print(f"  Consistency rate: {((len(product_groups) - inconsistent_groups) / len(product_groups) * 100):.1f}%")
    
    def analyze_missing_metadata(self):
        """Analyze missing metadata across retailers"""
        print("\n" + "="*70)
        print("METADATA COMPLETENESS ANALYSIS")
        print("="*70)
        
        for retailer, df in self.retailer_data.items():
            print(f"\n{retailer.upper()}:")
            
            if df.empty:
                print("  [WARNING] No data")
                continue
            
            metadata_fields = ['brand', 'line', 'wrapper', 'vitola', 'size']
            missing_counts = {}
            
            for field in metadata_fields:
                if field in df.columns:
                    missing = df[field].isna().sum() + (df[field] == '').sum()
                    missing_counts[field] = missing
                else:
                    missing_counts[field] = len(df)
            
            for field, missing in missing_counts.items():
                if missing > 0:
                    pct = (missing / len(df)) * 100
                    print(f"    {field}: {missing}/{len(df)} missing ({pct:.1f}%)")
    
    def recommend_cid_improvements(self):
        """Recommend improvements to CID structure"""
        print("\n" + "="*70)
        print("CID STRUCTURE RECOMMENDATIONS")
        print("="*70)
        
        print("CURRENT STRUCTURE ISSUES:")
        print("1. Brand/Vitola repetition adds unnecessary length")
        print("2. Special characters may cause URL/database issues") 
        print("3. Inconsistent wrapper code standards")
        print("4. No version control for CID changes")
        
        print("\nRECOMMENDED IMPROVEMENTS:")
        print("\nOption A: Streamlined CID (Recommended)")
        print("  Format: BRAND-LINE-VITOLA-SIZE-WRAPPER-QTY")
        print("  Example: ARTUROFUENTE-HEMINGWAY-CLASSIC-7X48-CAM-25")
        print("  Benefits: Shorter, cleaner, no repetition")
        
        print("\nOption B: Enhanced Current Format")
        print("  Format: BRAND|LINE|VITOLA|SIZE|WRAPPER|QTY")  
        print("  Example: ARTUROFUENTE|HEMINGWAY|CLASSIC|7X48|CAM|BOX25")
        print("  Benefits: Familiar, removes repetition")
        
        print("\nOption C: Hybrid Approach")
        print("  Keep existing CIDs, add new standardized field")
        print("  Add 'standard_id' column for new consistent format")
        print("  Gradually migrate over time")
        
        print("\nRECOMMENDATION:")
        print("  Implement Option C (Hybrid) for minimal disruption")
        print("  Create migration plan over 2-3 months")
        print("  Maintain backward compatibility during transition")
    
    def generate_migration_plan(self):
        """Generate specific migration recommendations"""
        print("\n" + "="*70)
        print("MIGRATION PLAN")
        print("="*70)
        
        print("PHASE 1: Assessment & Standards (Week 1)")
        print("  1. Audit all CID inconsistencies (completed)")
        print("  2. Define new CID standard format")
        print("  3. Create wrapper code standardization")
        print("  4. Build CID translation mapping")
        
        print("\nPHASE 2: Master Database Update (Week 2)")
        print("  1. Add 'standard_cid' column to master database")
        print("  2. Generate new standardized CIDs for all products")
        print("  3. Create lookup table: old_cid -> new_cid")
        print("  4. Validate no data loss")
        
        print("\nPHASE 3: Retailer CSV Updates (Week 3-4)")
        print("  1. Update all retailer CSVs with standardized CIDs")
        print("  2. Modify price updaters to use new CID format")
        print("  3. Update automation scripts")
        print("  4. Test all retailer integrations")
        
        print("\nPHASE 4: Validation & Cleanup (Week 5)")
        print("  1. Run consistency checks across all data")
        print("  2. Fix any remaining inconsistencies") 
        print("  3. Remove old CID columns")
        print("  4. Document new CID standards")
    
    def run_full_analysis(self):
        """Run complete CID analysis"""
        print("CID COMPREHENSIVE ANALYSIS")
        print("="*70)
        
        if not self.load_all_data():
            return False
        
        self.analyze_cid_structure()
        self.find_cid_inconsistencies() 
        self.analyze_missing_metadata()
        self.recommend_cid_improvements()
        self.generate_migration_plan()
        
        return True

def main():
    """Main execution"""
    analyzer = CIDAnalyzer()
    
    if len(sys.argv) > 1:
        data_path = sys.argv[1]
        analyzer = CIDAnalyzer(data_path)
    
    analyzer.run_full_analysis()

if __name__ == "__main__":
    main()
