#!/usr/bin/env python3
"""
Quick CID Validation Script - Windows Compatible
Verify all retailer CIDs now have matches in master database after fixes
"""

import os
import pandas as pd

def validate_cid_matches():
    """Check if all retailer CIDs exist in master database"""
    
    # Load master database
    master_path = None
    for path in ['data/master_cigars.csv', 'master_cigars.csv', 'static/data/master_cigars.csv']:
        if os.path.exists(path):
            master_path = path
            break
    
    if not master_path:
        print("[ERROR] Master cigars file not found")
        return
    
    master_df = pd.read_csv(master_path)
    master_cids = set(master_df['cigar_id'].dropna())
    print(f"[INFO] Master database: {len(master_cids)} CIDs loaded")
    
    # Check retailer CSVs
    retailer_files = [
        'smokeinn.csv', 'holts.csv', 'atlantic.csv', 'foxcigar.csv',
        'nickscigarworld.csv', 'hilands.csv', 'gothamcigars.csv',
        'bnbtobacco.csv', 'neptune.csv', 'tampasweethearts.csv',
        'tobaccolocker.csv', 'watchcity.csv', 'cigarsdirect.csv',
        'absolutecigars.csv'
    ]
    
    print("\nCID VALIDATION RESULTS:")
    print("="*50)
    
    total_orphans = 0
    all_valid = True
    
    for file in retailer_files:
        # Try multiple data directories
        file_path = None
        for data_dir in ['static/data', 'data', '.']:
            test_path = os.path.join(data_dir, file)
            if os.path.exists(test_path):
                file_path = test_path
                break
        
        if not file_path:
            continue
            
        try:
            df = pd.read_csv(file_path)
            retailer = file.replace('.csv', '')
            
            orphaned_cids = []
            valid_cids = 0
            
            for _, row in df.iterrows():
                cid = row.get('cigar_id', '')
                if pd.notna(cid) and cid:
                    if cid in master_cids:
                        valid_cids += 1
                    else:
                        orphaned_cids.append(cid)
                        all_valid = False
            
            if orphaned_cids:
                print(f"{retailer:18} | {valid_cids:2} valid | {len(orphaned_cids):2} ORPHANED")
                for cid in orphaned_cids:
                    print(f"  MISSING: {cid}")
                total_orphans += len(orphaned_cids)
            else:
                print(f"{retailer:18} | {valid_cids:2} valid | ALL MATCH")
                
        except Exception as e:
            print(f"{retailer:18} | ERROR: {e}")
    
    print("="*50)
    if all_valid:
        print("SUCCESS: All retailer CIDs match master database!")
        print("Ready to proceed with master sync framework.")
    else:
        print(f"ISSUES: {total_orphans} orphaned CIDs still need fixing")
        print("Fix these before implementing master sync.")

    # Show specific fix needed
    if total_orphans > 0:
        print("\nFIX NEEDED:")
        print("Nick's Cigar World has incomplete CID:")
        print("  CURRENT: PADRON|PADRON|1964ANNIVERSARY|DIPLOMATICO|DIPLOMATICO|7x50|CAM")
        print("  NEEDS:   PADRON|PADRON|1964ANNIVERSARY|DIPLOMATICO|DIPLOMATICO|7x50|CAM|BOX10")
        print("  OR:      PADRON|PADRON|1964ANNIVERSARY|DIPLOMATICO|DIPLOMATICO|7x50|CAM|BOX25")

if __name__ == "__main__":
    validate_cid_matches()
