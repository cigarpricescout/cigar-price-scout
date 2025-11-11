"""
Analyze gaps between CJ feeds and master database
Shows what brands/lines exist in feeds but not in master database
"""

import requests
import pandas as pd
from pathlib import Path
import re
from io import StringIO
import zipfile
import io
import os
from collections import defaultdict

# CJ HTTP credentials
CJ_USERNAME = '7711335'
CJ_PASSWORD = os.environ.get('CJ_HTTP_PASSWORD', '~quskK6y')

FEEDS = {
    'thompson': os.environ.get('CJ_THOMPSON_URL', ''),
    'cigora': os.environ.get('CJ_CIGORA_URL', '')
}

def normalize_brand(brand):
    """Normalize brand names"""
    brand = brand.lower().strip()
    replacements = {
        'a. fuente': 'arturo fuente',
        'fuente': 'arturo fuente',
        'padrón': 'padron',
        'romeo': 'romeo y julieta',
        'ryj': 'romeo y julieta',
        'hoyo': 'hoyo de monterrey',
        'myfather': 'my father',
        'monte cristo': 'montecristo',
    }
    for pattern, replacement in replacements.items():
        if pattern in brand:
            return replacement
    return brand

def extract_box_qty(title):
    """Extract box quantity"""
    patterns = [
        r'BOX\s*\((\d+)\)',
        r'BOX\s*OF\s*(\d+)',
        r'PACK\s*\((\d+)\)',
        r'PACK\s*OF\s*(\d+)',
        r'Box\s*of\s*(\d+)',
        r'Pack\s*of\s*(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            qty = int(match.group(1))
            if qty >= 20:
                return qty
    return None

def analyze_feeds():
    """Analyze feed products against master database"""
    
    # Load master database
    master_path = Path(__file__).parent.parent / 'master_cigars.tsv'
    master_df = pd.read_csv(master_path, sep='\t')
    
    # Create brand/line sets from master
    master_brands = set(master_df['Brand'].str.lower().str.strip())
    master_lines = defaultdict(set)
    for _, row in master_df.iterrows():
        brand_lower = row['Brand'].lower().strip()
        line_lower = row['Line'].lower().strip()
        master_lines[brand_lower].add(line_lower)
    
    print(f"\n{'='*80}")
    print(f"MASTER DATABASE SUMMARY")
    print(f"{'='*80}")
    print(f"Total brands in master: {len(master_brands)}")
    print(f"Total cigars in master: {len(master_df)}")
    
    for retailer_name, feed_url in FEEDS.items():
        if not feed_url or feed_url.strip() == '':
            continue
        
        print(f"\n{'='*80}")
        print(f"ANALYZING {retailer_name.upper()} FEED")
        print(f"{'='*80}")
        
        try:
            # Download feed
            response = requests.get(feed_url, auth=(CJ_USERNAME, CJ_PASSWORD), timeout=60)
            response.raise_for_status()
            
            # Extract
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                txt_files = [name for name in z.namelist() if name.endswith('.txt')]
                feed_content = z.read(txt_files[0]).decode('utf-8')
            
            # Parse
            df = pd.read_csv(StringIO(feed_content), sep='\t', dtype=str)
            
            # Analyze
            feed_brands = defaultdict(int)
            feed_lines = defaultdict(lambda: defaultdict(int))
            missing_brands = defaultdict(int)
            missing_lines = defaultdict(lambda: defaultdict(int))
            box_products = 0
            
            for _, row in df.iterrows():
                brand = row.get('BRAND', '').strip()
                title = row.get('TITLE', '').strip()
                box_qty = extract_box_qty(title)
                
                if not brand or not box_qty or box_qty < 20:
                    continue
                
                box_products += 1
                brand_normalized = normalize_brand(brand)
                
                # Extract basic line (first few words after brand)
                title_lower = title.lower()
                brand_pattern = re.escape(brand.lower())
                after_brand = re.sub(f'^{brand_pattern}\\s+', '', title_lower).strip()
                line_guess = ' '.join(after_brand.split()[:3])  # First 3 words
                
                feed_brands[brand_normalized] += 1
                feed_lines[brand_normalized][line_guess] += 1
                
                # Check if in master
                if brand_normalized not in master_brands:
                    missing_brands[brand_normalized] += 1
                else:
                    # Brand exists, check line
                    line_found = False
                    for master_line in master_lines[brand_normalized]:
                        if master_line in line_guess or line_guess in master_line:
                            line_found = True
                            break
                    if not line_found:
                        missing_lines[brand_normalized][line_guess] += 1
            
            print(f"\nTotal products in feed: {len(df)}")
            print(f"Box products (20+): {box_products}")
            print(f"Unique brands in feed: {len(feed_brands)}")
            
            print(f"\n{'='*80}")
            print(f"BRANDS IN FEED (Top 20 by product count)")
            print(f"{'='*80}")
            sorted_brands = sorted(feed_brands.items(), key=lambda x: x[1], reverse=True)
            for brand, count in sorted_brands[:20]:
                in_master = "[IN MASTER]" if brand in master_brands else "[MISSING]"
                print(f"{brand:30} {count:4} products  {in_master}")
            
            if missing_brands:
                print(f"\n{'='*80}")
                print(f"BRANDS MISSING FROM MASTER DATABASE")
                print(f"{'='*80}")
                sorted_missing = sorted(missing_brands.items(), key=lambda x: x[1], reverse=True)
                for brand, count in sorted_missing:
                    print(f"{brand:30} {count:4} products")
            
            if missing_lines:
                print(f"\n{'='*80}")
                print(f"LINES MISSING FROM MASTER DATABASE (Top 30)")
                print(f"{'='*80}")
                all_missing_lines = []
                for brand, lines in missing_lines.items():
                    for line, count in lines.items():
                        all_missing_lines.append((brand, line, count))
                
                sorted_lines = sorted(all_missing_lines, key=lambda x: x[2], reverse=True)
                for brand, line, count in sorted_lines[:30]:
                    print(f"{brand:25} - {line:35} ({count} products)")
            
            # Export unmatched products to CSV
            unmatched_products = []
            for _, row in df.iterrows():
                brand = row.get('BRAND', '').strip()
                title = row.get('TITLE', '').strip()
                box_qty = extract_box_qty(title)
                
                if not brand or not box_qty or box_qty < 20:
                    continue
                
                brand_normalized = normalize_brand(brand)
                if brand_normalized not in master_brands:
                    unmatched_products.append({
                        'brand': brand,
                        'title': title,
                        'box_qty': box_qty,
                        'price': row.get('PRICE', ''),
                        'url': row.get('LINK', '')
                    })
            
            if unmatched_products:
                output_path = Path(__file__).parent.parent / f'{retailer_name}_unmatched.csv'
                pd.DataFrame(unmatched_products).to_csv(output_path, index=False)
                print(f"\n✓ Exported {len(unmatched_products)} unmatched products to: {output_path}")
        
        except Exception as e:
            print(f"Error analyzing {retailer_name}: {e}")
    
    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    analyze_feeds()
