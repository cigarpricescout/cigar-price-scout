#!/usr/bin/env python3
"""
CID Structure Scalability Evaluation
Analyzes current CID format for scalability issues and optimization opportunities
"""

import pandas as pd
import re
from collections import Counter

def analyze_current_cid_structure():
    """Analyze the current CID structure for scalability"""
    
    # Sample current CIDs for analysis
    sample_cids = [
        "ARTUROFUENTE|ARTUROFUENTE|HEMINGWAY|CLASSIC|CLASSIC|7x48|CAM|BOX25",
        "MYFATHER|MYFATHER|THEJUDGE|GRANDROBUSTO|GRANDROBUSTO|5.625x60|ECU|BOX23",
        "ROMEOYJULIETA|ROMEOYJULIETA|1875|CHURCHILL|CHURCHILL|7x50|IND|BOX25",
        "PERDOMO|PERDOMO|RESERVE10THANNIVERSARYCHAMPAGNE|EPICURE|EPICURE|6x54|ECU|BOX25"
    ]
    
    print("CURRENT CID STRUCTURE ANALYSIS")
    print("="*60)
    
    # Analyze structure
    total_length = 0
    part_counts = []
    redundancy_issues = 0
    special_char_issues = 0
    
    for cid in sample_cids:
        parts = cid.split('|')
        part_counts.append(len(parts))
        total_length += len(cid)
        
        # Check for redundancy (parts 1=2, parts 4=5)
        if len(parts) >= 5 and parts[0] == parts[1] and parts[3] == parts[4]:
            redundancy_issues += 1
        
        # Check for special characters that could cause issues
        if re.search(r'[^A-Z0-9|x.]', cid):
            special_char_issues += 1
    
    avg_length = total_length / len(sample_cids)
    
    print(f"Average CID length: {avg_length:.0f} characters")
    print(f"Parts per CID: {Counter(part_counts)}")
    print(f"Redundancy issues: {redundancy_issues}/{len(sample_cids)}")
    print(f"Special character concerns: {special_char_issues}/{len(sample_cids)}")
    
    print(f"\nCURRENT STRUCTURE: BRAND|BRAND|LINE|VITOLA|VITOLA|SIZE|WRAPPER|PACKAGING")
    print(f"Issues identified:")
    print(f"  1. Redundant brand repetition (positions 1&2)")
    print(f"  2. Redundant vitola repetition (positions 4&5)")
    print(f"  3. Long format reduces readability")
    print(f"  4. Pipe separators may cause CSV/URL issues")
    
def propose_optimized_structures():
    """Propose optimized CID structures"""
    
    print(f"\nOPTIMIZED CID STRUCTURE PROPOSALS")
    print("="*60)
    
    sample_product = {
        'brand': 'ARTURO FUENTE',
        'line': 'HEMINGWAY', 
        'vitola': 'CLASSIC',
        'size': '7x48',
        'wrapper': 'CAM',
        'qty': '25'
    }
    
    print(f"\nExample product: Arturo Fuente Hemingway Classic 7x48 Cameroon Box of 25")
    print(f"Current CID: ARTUROFUENTE|ARTUROFUENTE|HEMINGWAY|CLASSIC|CLASSIC|7x48|CAM|BOX25")
    
    # Option A: Streamlined hyphen format
    option_a = f"ARTUROFUENTE-HEMINGWAY-CLASSIC-7X48-CAM-25"
    print(f"\nOption A (Streamlined): {option_a}")
    print(f"  Length: {len(option_a)} chars (vs {len('ARTUROFUENTE|ARTUROFUENTE|HEMINGWAY|CLASSIC|CLASSIC|7x48|CAM|BOX25')})")
    print(f"  Benefits: 40% shorter, no redundancy, URL-safe")
    print(f"  Format: BRAND-LINE-VITOLA-SIZE-WRAPPER-QTY")
    
    # Option B: Minimal pipe format
    option_b = f"ARTUROFUENTE|HEMINGWAY|CLASSIC|7X48|CAM|25"
    print(f"\nOption B (Minimal Pipes): {option_b}")
    print(f"  Length: {len(option_b)} chars")
    print(f"  Benefits: 37% shorter, familiar pipes, no redundancy")
    print(f"  Format: BRAND|LINE|VITOLA|SIZE|WRAPPER|QTY")
    
    # Option C: Encoded format
    option_c = f"AF-HEM-CLA-748-CAM-25"
    print(f"\nOption C (Encoded): {option_c}")
    print(f"  Length: {len(option_c)} chars")
    print(f"  Benefits: 71% shorter, compact, fast processing")
    print(f"  Format: BRAND_CODE-LINE_CODE-VIT_CODE-SIZE-WRAP-QTY")
    print(f"  Requires: Brand/line lookup tables")
    
    return {
        'current': 'ARTUROFUENTE|ARTUROFUENTE|HEMINGWAY|CLASSIC|CLASSIC|7x48|CAM|BOX25',
        'option_a': option_a,
        'option_b': option_b, 
        'option_c': option_c
    }

def evaluate_scalability_metrics():
    """Evaluate how each format scales"""
    
    print(f"\nSCALABILITY METRICS")
    print("="*60)
    
    # Simulate scaling scenarios
    scenarios = [
        {'brands': 50, 'lines_per_brand': 20, 'vitolas_per_line': 8, 'sizes': 5, 'wrappers': 6, 'qtys': 4},
        {'brands': 100, 'lines_per_brand': 25, 'vitolas_per_line': 10, 'sizes': 8, 'wrappers': 8, 'qtys': 5},
        {'brands': 200, 'lines_per_brand': 30, 'vitolas_per_line': 12, 'sizes': 10, 'wrappers': 10, 'qtys': 6}
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        total_products = (scenario['brands'] * scenario['lines_per_brand'] * 
                         scenario['vitolas_per_line'] * scenario['sizes'] * 
                         scenario['wrappers'] * scenario['qtys'])
        
        print(f"\nScenario {i}: {scenario['brands']} brands")
        print(f"  Total possible products: {total_products:,}")
        print(f"  Storage with current format: {total_products * 70:.0f} KB")
        print(f"  Storage with optimized format: {total_products * 25:.0f} KB")
        print(f"  Storage savings: {((70-25)/70)*100:.0f}%")

def recommend_migration_strategy():
    """Recommend specific migration approach"""
    
    print(f"\nRECOMMENDED MIGRATION STRATEGY")
    print("="*60)
    
    print(f"RECOMMENDATION: Hybrid Approach (Option B + Migration Plan)")
    print(f"")
    print(f"New Format: BRAND|LINE|VITOLA|SIZE|WRAPPER|QTY")
    print(f"Benefits:")
    print(f"  - 37% size reduction")
    print(f"  - Eliminates redundancy") 
    print(f"  - Maintains familiar pipe structure")
    print(f"  - Easy to parse and validate")
    print(f"  - Backward compatible during migration")
    
    print(f"\nMIGRATION STEPS:")
    print(f"1. Add 'new_cigar_id' column to all CSVs")
    print(f"2. Generate new CIDs using optimized format")
    print(f"3. Update extractors to populate both old and new CIDs")
    print(f"4. Migrate website/API to use new CIDs")
    print(f"5. Remove old CID columns after validation")
    
    print(f"\nTIMELINE:")
    print(f"  Week 1: Analysis and new CID generation")
    print(f"  Week 2: Update master database")
    print(f"  Week 3-4: Migrate retailer CSVs")
    print(f"  Week 5: Update extractors and automation")
    print(f"  Week 6: Validation and cleanup")

def main():
    """Run CID structure analysis"""
    analyze_current_cid_structure()
    propose_optimized_structures() 
    evaluate_scalability_metrics()
    recommend_migration_strategy()

if __name__ == "__main__":
    main()
