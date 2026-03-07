#!/usr/bin/env python3
"""
Find CIDs from master_cigars.csv that don't appear in ANY retailer CSV.
Then prioritize them based on search demand data.
"""

import pandas as pd
import os
from pathlib import Path

def main():
    # Load master cigars
    master_df = pd.read_csv('data/master_cigars.csv')
    print(f"Total CIDs in master file: {len(master_df)}")
    
    # Get all CIDs from master
    master_cids = set(master_df['cigar_id'].dropna().unique())
    print(f"Unique CIDs in master: {len(master_cids)}")
    
    # Get all retailer CSVs (exclude DORMANT and backups)
    retailer_dir = Path('static/data')
    retailer_csvs = [
        f for f in retailer_dir.glob('*.csv')
        if 'DORMANT' not in f.name and 'backup' not in f.name and 'BROKEN' not in f.name
    ]
    
    print(f"\nActive retailer CSVs: {len(retailer_csvs)}")
    
    # Collect all CIDs that appear in at least one retailer CSV
    monitored_cids = set()
    for csv_file in retailer_csvs:
        try:
            df = pd.read_csv(csv_file)
            if 'cigar_id' in df.columns:
                cids = df['cigar_id'].dropna().unique()
                monitored_cids.update(cids)
        except Exception as e:
            print(f"  Error reading {csv_file.name}: {e}")
    
    print(f"\nUnique CIDs being monitored across all retailers: {len(monitored_cids)}")
    
    # Find CIDs not being monitored
    unmonitored_cids = master_cids - monitored_cids
    print(f"CIDs NOT being monitored: {len(unmonitored_cids)}")
    
    # Get the full records for unmonitored CIDs
    unmonitored_df = master_df[master_df['cigar_id'].isin(unmonitored_cids)].copy()
    
    # Sort by Brand, Line, Wrapper, Vitola for readability
    unmonitored_df = unmonitored_df.sort_values(['Brand', 'Line', 'Wrapper', 'Vitola'])
    
    # ACTUAL SEARCH QUERIES FROM GOOGLE SEARCH CONSOLE
    # Format: {search_term: impressions}
    search_queries = {
        'cohiba red dot': 82,  # 10+ related queries
        'perdomo reserve champagne': 58,  # 26+ related queries combined
        'perdomo champagne': 58,
        'norteno cigar': 12,  # "norteno cigars", "herrera esteli norteno", "drew estate norteno"
        'padron 1964 anniversary': 8,  # "for sale", "series", etc
        'fuente opus x': 13,  # "price", "for sale", "in stock"
        'hemingway cigars': 2,  # "price"
        'ashton vsg': 2,  # "price"
        'hoyo de monterrey': 4,  # "price", "excalibur price"
        'romeo y julieta 1875': 8,  # Multiple vitola queries
        'arturo fuente': 1,  # "cigars price"
    }
    
    # Create scoring based on ACTUAL search terms
    def get_search_score(row):
        """Match CID against actual search queries and return impression-based score"""
        score = 0
        brand_lower = str(row['Brand']).lower()
        line_lower = str(row['Line']).lower()
        
        # Direct brand+line matches (highest value)
        if 'cohiba' in brand_lower and 'red dot' in line_lower:
            score += 82  # Highest impressions
        elif 'perdomo' in brand_lower and 'champagne' in line_lower:
            score += 58
        elif 'herrera esteli' in line_lower and 'norteno' in line_lower:
            score += 12
        elif 'padron' in brand_lower and '1964' in line_lower:
            score += 8
        elif 'opus x' in line_lower or 'opusx' in line_lower:
            score += 13
        elif 'hemingway' in line_lower:
            score += 2
        elif 'ashton' in brand_lower and 'vsg' in line_lower:
            score += 2
        elif 'hoyo de monterrey' in brand_lower:
            score += 4
        elif 'romeo y julieta' in brand_lower or 'romeo and julieta' in brand_lower:
            score += 8
        elif 'arturo fuente' in brand_lower:
            score += 1
        
        return score
    
    # Additional factors for SEO value
    priority_brands = {
        'Cohiba': 5,
        'Perdomo': 5,
        'Drew Estate': 4,
        'Arturo Fuente': 4,
        'Padron': 4,
        'Ashton': 3,
        'Hoyo de Monterrey': 3,
        'Romeo y Julieta': 3,
    }
    
    def calculate_priority(row):
        """Calculate priority based on search impressions and SEO factors"""
        # Start with search impression score (most important)
        score = get_search_score(row)
        
        # Add brand bonus
        score += priority_brands.get(row['Brand'], 0)
        
        # Popular sizes that people search for (Robusto, Toro, Churchill)
        popular_sizes = ['Robusto', 'Toro', 'Churchill', 'Epicure', 'Corona']
        if row['Vitola'] in popular_sizes:
            score += 3
        
        # Box quantity bonus (25+ boxes = deal hunters)
        box_qty = row.get('Box Quantity', 0)
        if pd.notna(box_qty):
            try:
                box_qty_int = int(box_qty)
                if box_qty_int >= 25:
                    score += 2
                elif box_qty_int >= 20:
                    score += 1
            except (ValueError, TypeError):
                pass  # Skip if box_qty is not convertible to int
            
        return score
    
    unmonitored_df['Priority_Score'] = unmonitored_df.apply(calculate_priority, axis=1)
    unmonitored_df = unmonitored_df.sort_values('Priority_Score', ascending=False)
    
    # Save full report
    output_file = 'unmonitored_cids_full_report.csv'
    unmonitored_df.to_csv(output_file, index=False)
    print(f"\nFull report saved to: {output_file}")
    
    # Show top 20 priorities
    print("\n" + "="*80)
    print("TOP 10 UNMONITORED CIDs (Based on Google Search Console Traffic)")
    print("="*80)
    print("These cigars are driving actual search impressions but you're NOT monitoring them")
    print("="*80)
    
    top_10 = unmonitored_df.head(10)
    for idx, row in top_10.iterrows():
        search_score = get_search_score(row)
        box_qty = row.get('Box Quantity', 'N/A')
        print(f"\n{int(row['Priority_Score']):3d} pts (Search: {int(search_score)}) | {row['Brand']} - {row['Line']}")
        print(f"     Wrapper: {row['Wrapper']} | {row['Vitola']} ({row['Length']}x{row['Ring Gauge']}) | Box of {box_qty}")
        print(f"     CID: {row['cigar_id']}")
    
    print("\n" + "="*80)
    print("NEXT 10 UNMONITORED CIDs (Ranked 11-20)")
    print("="*80)
    
    next_10 = unmonitored_df.iloc[10:20]
    for idx, row in next_10.iterrows():
        search_score = get_search_score(row)
        box_qty = row.get('Box Quantity', 'N/A')
        print(f"\n{int(row['Priority_Score']):3d} pts (Search: {int(search_score)}) | {row['Brand']} - {row['Line']}")
        print(f"     {row['Wrapper']} | {row['Vitola']} | Box of {box_qty}")
        print(f"     CID: {row['cigar_id']}")
    
    # Summary by brand
    print("\n" + "="*80)
    print("UNMONITORED CIDs BY BRAND")
    print("="*80)
    brand_summary = unmonitored_df['Brand'].value_counts().head(15)
    for brand, count in brand_summary.items():
        print(f"{brand:30s}: {count:3d} unmonitored CIDs")
    
    # Create a "Top 10 to Add" file
    top_10 = unmonitored_df.head(10)
    top_10_simple = top_10[['Brand', 'Line', 'Wrapper', 'Vitola', 'Length', 'Ring Gauge', 'Box Quantity', 'cigar_id', 'Priority_Score']]
    top_10_file = 'top_10_cids_to_add.csv'
    top_10_simple.to_csv(top_10_file, index=False)
    print(f"\nTop 10 CIDs saved to: {top_10_file}")

if __name__ == '__main__':
    main()
