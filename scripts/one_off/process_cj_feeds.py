import requests
import pandas as pd
from pathlib import Path
import re
import logging
from io import StringIO
import zipfile
import io
import os
from difflib import SequenceMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CJ HTTP credentials
CJ_USERNAME = '7711335'
CJ_PASSWORD = os.environ.get('CJ_HTTP_PASSWORD', '~quskK6y')

# Feed URLs
FEEDS = {
    'thompson': os.environ.get('CJ_THOMPSON_URL', ''),
    'cigora': os.environ.get('CJ_CIGORA_URL', '')
}

# Vitola patterns
VITOLA_PATTERNS = [
    ('Double Corona', r'\bDouble\s+Corona\b'),
    ('Gran Toro', r'\bGran\s+Toro\b'),
    ('Double Toro', r'\bDouble\s+Toro\b'),
    ('Short Robusto', r'\bShort\s+Robusto\b'),
    ('Petit Corona', r'\bPetit\s+Corona\b'),
    ('Corona Gorda', r'\bCorona\s+Gorda\b'),
    ('Churchill', r'\bChurchill\b'),
    ('Torpedo', r'\bTorpedo\b'),
    ('Belicoso', r'\bBelicoso\b'),
    ('Perfecto', r'\bPerfecto\b'),
    ('Lancero', r'\bLancero\b'),
    ('Lonsdale', r'\bLonsdale\b'),
    ('Robusto', r'\bRobusto\b'),
    ('Corona', r'\bCorona\b'),
    ('Toro', r'\bToro\b'),
    ('Gordo', r'\bGordo\b'),
]

class CigarMatcher:
    """Match feed products to master cigar database"""
    
    def __init__(self, master_file='master_cigars.tsv'):
        """Load master cigar database"""
        master_path = Path(__file__).parent.parent / master_file
        self.master_df = pd.read_csv(master_path, sep='\t')
        
        # Convert numeric columns
        self.master_df['Box Quantity'] = pd.to_numeric(self.master_df['Box Quantity'], errors='coerce')
        self.master_df['Length'] = pd.to_numeric(self.master_df['Length'], errors='coerce')
        self.master_df['Ring Gauge'] = pd.to_numeric(self.master_df['Ring Gauge'], errors='coerce')
        
        # Normalize for matching
        self.master_df['brand_lower'] = self.master_df['Brand'].str.lower().str.strip()
        self.master_df['line_lower'] = self.master_df['Line'].str.lower().str.strip()
        self.master_df['vitola_lower'] = self.master_df['Vitola'].str.lower().str.strip()
        
        logger.info(f"Loaded {len(self.master_df)} cigars from master database")
    
    def normalize_brand(self, brand):
        """Normalize brand names"""
        brand = brand.lower().strip()
        replacements = {
            'a. fuente': 'arturo fuente',
            'padrón': 'padron',
            'romeo': 'romeo y julieta',
            'hoyo': 'hoyo de monterrey',
            'myfather': 'my father',
            'monte cristo': 'montecristo',
        }
        for pattern, replacement in replacements.items():
            if pattern in brand:
                return replacement
        return brand
    
    def extract_line_from_title(self, title, brand):
        """Extract product line from title"""
        title_lower = title.lower()
        brand_lower = brand.lower()
        
        # Remove brand from start
        if title_lower.startswith(brand_lower):
            after_brand = title[len(brand):].strip()
        else:
            after_brand = title
        
        # Remove common suffixes
        after_brand = re.sub(r'\s*-?\s*(BOX|PACK|Box|Pack).*$', '', after_brand, flags=re.IGNORECASE)
        
        # Extract line (words before vitola or box info)
        words = after_brand.split()
        line_words = []
        
        for word in words:
            # Stop at vitola words
            if any(word.lower() in vitola_name.lower() for vitola_name, _ in VITOLA_PATTERNS):
                break
            # Stop at size patterns
            if re.match(r'\d+\.?\d*', word):
                break
            line_words.append(word)
        
        return ' '.join(line_words).strip()
    
    def extract_vitola_from_title(self, title):
        """Extract vitola from title"""
        for vitola_name, pattern in VITOLA_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                return vitola_name
        return None
    
    def extract_size_from_title(self, title):
        """Extract size from title"""
        patterns = [
            r'\((\d+\.?\d*)"?\s*x\s*(\d+)\)',
            r'(\d+\.?\d*)"?\s*x\s*(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return f"{match.group(1)} x {match.group(2)}"
        return None
    
    def match_product(self, brand, title, price, box_qty):
        """Match product with flexible strategy"""
        
        brand_normalized = self.normalize_brand(brand)
        
        # Filter by brand
        brand_matches = self.master_df[
            self.master_df['brand_lower'] == brand_normalized
        ]
        
        if len(brand_matches) == 0:
            logger.debug(f"No brand match: '{brand}' -> '{brand_normalized}'")
            return None
        
        logger.debug(f"Found {len(brand_matches)} products for brand '{brand_normalized}'")
        
        # Extract line from title
        line_from_title = self.extract_line_from_title(title, brand)
        
        if not line_from_title:
            logger.debug(f"Could not extract line from: {title}")
            return None
        
        logger.debug(f"Extracted line: '{line_from_title}' from title: {title}")
        
        # Find best line match
        best_line_match = None
        best_score = 0
        
        for line_value in brand_matches['line_lower'].unique():
            score = SequenceMatcher(None, line_from_title.lower(), line_value).ratio()
            if score > best_score:
                best_score = score
                best_line_match = line_value
        
        # Require at least 90% similarity on line name (very strict - near exact match)
        if best_score < 0.9:
            logger.debug(f"No line match for: {brand} - {line_from_title} (best score: {best_score:.2f})")
            return None
        
        # Filter by matched line
        line_matches = brand_matches[brand_matches['line_lower'] == best_line_match]
        
        # STRICT: Require vitola in title - reject if missing
        vitola_from_title = self.extract_vitola_from_title(title)
        if not vitola_from_title:
            logger.debug(f"No vitola found in title: {title}")
            return None
        
        # STRICT: Require vitola match
        vitola_matches = line_matches[
            line_matches['vitola_lower'] == vitola_from_title.lower()
        ]
        if len(vitola_matches) > 0:
            line_matches = vitola_matches
        else:
            # No vitola match - reject this product
            logger.debug(f"Vitola mismatch: '{vitola_from_title}' not found for {brand} {line_from_title}")
            return None
        
        # Try to match by size if present
        size_from_title = self.extract_size_from_title(title)
        if size_from_title:
            size_norm = size_from_title.replace(' ', '').replace('"', '').lower()
            size_matches = line_matches[
                line_matches.apply(
                    lambda row: f"{row['Length']}x{row['Ring Gauge']}".replace(' ', '').lower() == size_norm,
                    axis=1
                )
            ]
            if len(size_matches) > 0:
                line_matches = size_matches
        
        # Try to match by box quantity (with tolerance)
        if box_qty:
            # Accept +/- 5 cigars difference
            qty_matches = line_matches[
                (line_matches['Box Quantity'] >= box_qty - 5) &
                (line_matches['Box Quantity'] <= box_qty + 5)
            ]
            if len(qty_matches) > 0:
                line_matches = qty_matches
        
        # Return best match (prefer first if multiple)
        if len(line_matches) > 0:
            return line_matches.iloc[0]
        
        return None

def extract_box_qty_from_title(title):
    """Extract box quantity from title"""
    patterns = [
        r'BOX\s*(?:OF\s*)?(\d+)',
        r'PACK\s*(?:OF\s*)?(\d+)',
        r'Box\s*of\s*(\d+)',
        r'Pack\s*of\s*(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return None

def process_feed():
    """Process CJ feeds with smart matching"""
    
    if not FEEDS['thompson'] and not FEEDS['cigora']:
        logger.error("No feed URLs configured.")
        return
    
    matcher = CigarMatcher()
    
    for retailer_name, feed_url in FEEDS.items():
        try:
            if not feed_url or feed_url.strip() == '':
                logger.warning(f"Skipping {retailer_name}")
                continue
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing {retailer_name.upper()}")
            logger.info(f"{'='*60}")
            
            # Download
            response = requests.get(feed_url, auth=(CJ_USERNAME, CJ_PASSWORD), timeout=60)
            response.raise_for_status()
            logger.info(f"Downloaded {len(response.content)} bytes")
            
            # Extract
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                txt_files = [name for name in z.namelist() if name.endswith('.txt')]
                if not txt_files:
                    continue
                feed_content = z.read(txt_files[0]).decode('utf-8')
            
            # Parse
            df = pd.read_csv(StringIO(feed_content), sep='\t', dtype=str)
            logger.info(f"Parsed {len(df)} total products")
            
            # Process
            products = []
            matched = 0
            unmatched = 0
            skipped = 0
            
            for _, row in df.iterrows():
                try:
                    brand = row.get('BRAND', '').strip()
                    title = row.get('TITLE', '').strip()
                    
                    if not brand or not title:
                        continue
                    
                    box_qty = extract_box_qty_from_title(title)
                    
                    # Skip singles/5-packs
                    if not box_qty or box_qty < 10:
                        skipped += 1
                        continue
                    
                    price_str = row.get('PRICE', '0').replace(' USD', '').strip()
                    try:
                        price = float(price_str)
                    except:
                        continue
                    
                    in_stock = row.get('AVAILABILITY', '').lower() == 'in stock'
                    
                    # Match
                    match = matcher.match_product(brand, title, price, box_qty)
                    
                    if match is not None:
                        matched += 1
                        
                        size = f"{match['Length']} x {match['Ring Gauge']}"
                        
                        products.append({
                            'title': title,
                            'url': row.get('LINK', ''),
                            'brand': match['Brand'],
                            'line': match['Line'],
                            'wrapper': match['Wrapper'],
                            'vitola': match['Vitola'],
                            'size': size,
                            'box_qty': int(match['Box Quantity']),
                            'price': price,
                            'in_stock': in_stock
                        })
                    else:
                        unmatched += 1
                
                except Exception as e:
                    continue
            
            logger.info(f"\nResults:")
            logger.info(f"  Matched: {matched}")
            logger.info(f"  Unmatched: {unmatched}")
            logger.info(f"  Skipped (< 10): {skipped}")
            
            if not products:
                logger.warning(f"No products for {retailer_name}")
                continue
            
            # DataFrame and deduplicate
            products_df = pd.DataFrame(products)
            logger.info(f"  Before dedup: {len(products_df)}")
            
            products_df = products_df.sort_values('price').drop_duplicates(
                subset=['brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty'],
                keep='first'
            )
            
            logger.info(f"  After dedup: {len(products_df)}")
            
            # Save
            output_dir = Path(__file__).parent.parent / 'static' / 'data'
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f'{retailer_name}.csv'
            products_df.to_csv(output_path, index=False)
            logger.info(f"\n✓ Saved {len(products_df)} products to {output_path}")
        
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    logger.info(f"\n{'='*60}")
    logger.info("Complete!")
    logger.info(f"{'='*60}\n")

if __name__ == "__main__":
    process_feed()