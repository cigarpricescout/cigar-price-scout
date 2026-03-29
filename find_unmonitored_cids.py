#!/usr/bin/env python3
"""
Find CIDs from master_cigars.csv that don't appear in ANY retailer CSV.
Then prioritize them based on search demand data.

Priority scoring matches tools/ai/url_discoverer.py so the daily discovery
agent researches the same high-demand cigars surfaced here.
"""

import pandas as pd
import os
from pathlib import Path

# ── Shared priority tables (keep in sync with url_discoverer.py) ──────

PRIORITY_LINES = {
    "opus x": 100,
    "opus x angel's share": 95,
    "opus x lost city": 95,
    "opus x forbidden x": 95,
    "opus x oro oscuro": 90,
    "opus x 20th anniversary": 85,
    "opus x 25th anniversary": 85,
    "padron 1964 anniversary": 90,
    "padron 1926 anniversary": 85,
    "padron family reserve": 80,
    "padron damaso": 70,
    "cohiba red dot": 80,
    "cohiba riviera": 70,
    "perdomo reserve 10th anniversary champagne": 75,
    "ashton vsg": 70,
    "ashton esg": 65,
    "hemingway": 60,
    "liga privada no. 9": 60,
    "liga privada t52": 60,
    "undercrown": 55,
    "my father the judge": 55,
    "le bijou 1922": 55,
    "oliva serie v": 55,
    "herrera esteli": 50,
}

PRIORITY_BRANDS = {
    "Arturo Fuente": 15,
    "Padron": 12,
    "Cohiba": 10,
    "Perdomo": 8,
    "Ashton": 7,
    "My Father": 6,
    "Drew Estate": 6,
    "Oliva": 5,
    "Romeo y Julieta": 4,
    "Hoyo de Monterrey": 3,
    "Montecristo": 3,
    "Foundation": 3,
    "Alec Bradley": 2,
    "CAO": 2,
}

POPULAR_VITOLAS = {"Robusto", "Toro", "Churchill", "Gordo", "Corona", "Belicoso"}


def calculate_priority(row):
    """Score a CID by line-level search demand, brand value, and popular sizing."""
    score = 0
    brand = str(row.get("Brand", "")).strip()
    line = str(row.get("Line", "")).strip().lower()

    for pattern, pts in PRIORITY_LINES.items():
        if pattern in line or (brand.lower() + " " + line).startswith(pattern):
            score += pts
            break

    score += PRIORITY_BRANDS.get(brand, 0)

    vitola = str(row.get("Vitola", ""))
    if vitola in POPULAR_VITOLAS:
        score += 3

    box_qty = row.get("Box Quantity", 0)
    if pd.notna(box_qty):
        try:
            if int(box_qty) >= 20:
                score += 2
        except (ValueError, TypeError):
            pass

    return score


def main():
    master_df = pd.read_csv('data/master_cigars.csv')
    print(f"Total CIDs in master file: {len(master_df)}")
    
    master_cids = set(master_df['cigar_id'].dropna().unique())
    print(f"Unique CIDs in master: {len(master_cids)}")
    
    retailer_dir = Path('static/data')
    retailer_csvs = [
        f for f in retailer_dir.glob('*.csv')
        if 'DORMANT' not in f.name and 'backup' not in f.name and 'BROKEN' not in f.name
    ]
    
    print(f"\nActive retailer CSVs: {len(retailer_csvs)}")
    
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
    
    unmonitored_cids = master_cids - monitored_cids
    print(f"CIDs NOT being monitored: {len(unmonitored_cids)}")
    
    unmonitored_df = master_df[master_df['cigar_id'].isin(unmonitored_cids)].copy()
    
    unmonitored_df['Priority_Score'] = unmonitored_df.apply(calculate_priority, axis=1)
    unmonitored_df = unmonitored_df.sort_values('Priority_Score', ascending=False)
    
    # Save full report
    output_file = 'unmonitored_cids_full_report.csv'
    unmonitored_df.to_csv(output_file, index=False)
    print(f"\nFull report saved to: {output_file}")
    
    print("\n" + "="*80)
    print("TOP 10 UNMONITORED CIDs (Prioritized by Search Demand)")
    print("="*80)
    print("These cigars are driving actual search traffic but you're NOT monitoring them")
    print("="*80)
    
    top_10 = unmonitored_df.head(10)
    for idx, row in top_10.iterrows():
        box_qty = row.get('Box Quantity', 'N/A')
        print(f"\n{int(row['Priority_Score']):3d} pts | {row['Brand']} - {row['Line']}")
        print(f"     Wrapper: {row['Wrapper']} | {row['Vitola']} ({row['Length']}x{row['Ring Gauge']}) | Box of {box_qty}")
        print(f"     CID: {row['cigar_id']}")
    
    print("\n" + "="*80)
    print("NEXT 10 UNMONITORED CIDs (Ranked 11-20)")
    print("="*80)
    
    next_10 = unmonitored_df.iloc[10:20]
    for idx, row in next_10.iterrows():
        box_qty = row.get('Box Quantity', 'N/A')
        print(f"\n{int(row['Priority_Score']):3d} pts | {row['Brand']} - {row['Line']}")
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
