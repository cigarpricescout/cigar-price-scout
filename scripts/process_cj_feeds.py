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

class CigarMatcher:
    """Match feed products to master cigar database"""
    
    def __init__(self, master_file='master_cigars.tsv'):
        """Load master cigar database"""
        master_path = Path(__file__).parent.parent / master_file
        self.master_df = pd.read_csv(master_path, sep='\t')
        
        # Create lookup index for faster matching
        self.master_df['brand_lower'] = self.master_df['Brand'].str.lower().str.strip()
        self.master_df['line_lower'] = self.master_df['Line'].str.lower().str.strip()
        
        logger.info(f"Loaded {len(self.master_df)} cigars from master database")
    
    def normalize_brand(self, brand):
        """Normalize brand names for matching"""
        brand = brand.lower().strip()
        
        # Common brand variations
        replacements = {
            'arturo fuente': 'arturo fuente',
            'a. fuente': 'arturo fuente',
            'fuente': 'arturo fuente',
            'padron': 'padron',
            'padrón': 'padron',
            'romeo y julieta': 'romeo y julieta',
            'romeo': 'romeo y julieta',
            'ryj': 'romeo y julieta',
            'hoyo de monterrey': 'hoyo de monterrey',
            'hoyo': 'hoyo de monterrey',
            'drew estate': 'drew estate',
            'my father': 'my father',
            'myfather': 'my father',
            'oliva': 'oliva',
            'rocky patel': 'rocky patel',
            'perdomo': 'perdomo',
            'alec bradley': 'alec bradley',
            'cao': 'cao',
            'montecristo': 'montecristo',
            'monte cristo': 'montecristo',
            'ashton': 'ashton',
            'macanudo': 'macanudo',
            'davidoff': 'davidoff',
            'undercrown': 'drew estate',
            'liga privada': 'drew estate',
            'acid': 'drew estate',
        }
        
        for pattern, replacement in replacements.items():
            if pattern in brand:
                return replacement
        
        return brand
    
    def extract_size_from_title(self, title):
        """Extract size like '5 x 50' or '5.0" x 50' from title"""
        # Pattern 1: (5.0" x 50)
        match = re.search(r'\((\d+\.?\d*)"?\s*x\s*(\d+)\)', title, re.IGNORECASE)
        if match:
            return f"{match.group(1)} x {match.group(2)}"
        
        # Pattern 2: 5x50 or 5 x 50
        match = re.search(r'(\d+\.?\d*)\s*x\s*(\d+)', title, re.IGNORECASE)
        if match:
            return f"{match.group(1)} x {match.group(2)}"
        
        return None
    
    def similarity(self, str1, str2):
        """Calculate string similarity ratio"""
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
    
    def match_product(self, brand, title, price):
        """Match a product to the master database"""
        
        # Normalize brand
        brand_normalized = self.normalize_brand(brand)
        
        # Filter master database by brand
        brand_matches = self.master_df[
            self.master_df['brand_lower'] == brand_normalized
        ]
        
        if len(brand_matches) == 0:
            logger.debug(f"No brand match for: {brand}")
            return None
        
        # Extract size from title
        size = self.extract_size_from_title(title)
        
        # Try to match by size if available
        if size:
            # Normalize size format (remove spaces, quotes)
            size_normalized = size.replace(' ', '').replace('"', '').lower()
            
            size_matches = brand_matches[
                brand_matches.apply(
                    lambda row: (
                        f"{row['Length']}x{row['Ring Gauge']}".lower() == size_normalized or
                        f"{row['Length']} x {row['Ring Gauge']}".lower() == size_normalized.replace('x', ' x ')
                    ),
                    axis=1
                )
            ]
            
            if len(size_matches) > 0:
                # Find best line match within size matches
                best_match = None
                best_score = 0
                
                for _, row in size_matches.iterrows():
                    line_score = self.similarity(title, row['Line'])
                    if line_score > best_score:
                        best_score = line_score
                        best_match = row
                
                if best_score > 0.3:  # Minimum similarity threshold
                    return best_match
        
        # Fallback: Try to match by line name in title
        best_match = None
        best_score = 0
        
        for _, row in brand_matches.iterrows():
            # Check if line name appears in title
            line_lower = row['line_lower']
            title_lower = title.lower()
            
            if line_lower in title_lower:
                score = len(line_lower) / len(title_lower)  # Prefer longer matches
                if score > best_score:
                    best_score = score
                    best_match = row
        
        if best_score > 0.1:  # Very low threshold for fallback
            return best_match
        
        return None

def extract_box_qty_from_title(title):
    """Extract box quantity from title"""
    # BOX (20), BOX OF 20, Pack of 20
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
            if qty >= 20:  # Only return if it's a box (20+)
                return qty
    
    return None

def process_feed():
    """Download and process CJ feeds with master database matching"""
    
    if not FEEDS['thompson'] and not FEEDS['cigora']:
        logger.error("No feed URLs configured. Set CJ_THOMPSON_URL and CJ_CIGORA_URL environment variables.")
        return
    
    # Initialize matcher
    matcher = CigarMatcher()
    
    for retailer_name, feed_url in FEEDS.items():
        try:
            if not feed_url or feed_url.strip() == '':
                logger.warning(f"Skipping {retailer_name} - no URL configured")
                continue
            
            logger.info(f"Processing {retailer_name}...")
            logger.info(f"Downloading from {feed_url}")
            
            # Download ZIP file
            response = requests.get(
                feed_url,
                auth=(CJ_USERNAME, CJ_PASSWORD),
                timeout=60
            )
            response.raise_for_status()
            logger.info(f"Downloaded {len(response.content)} bytes")
            
            # Extract ZIP file
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                txt_files = [name for name in z.namelist() if name.endswith('.txt')]
                if not txt_files:
                    logger.error(f"No .txt file found in {retailer_name} ZIP")
                    continue
                
                feed_content = z.read(txt_files[0]).decode('utf-8')
                logger.info(f"Extracted {txt_files[0]}")
            
            # Parse TSV
            df = pd.read_csv(StringIO(feed_content), sep='\t', dtype=str)
            logger.info(f"Parsed {len(df)} products from {retailer_name}")
            
            # Process products with matching
            products = []
            matched_count = 0
            unmatched_count = 0
            
            for _, row in df.iterrows():
                try:
                    brand = row.get('BRAND', '').strip()
                    title = row.get('TITLE', '').strip()
                    
                    if not brand or not title:
                        continue
                    
                    # Extract box quantity from title
                    box_qty = extract_box_qty_from_title(title)
                    
                    # Only process boxes (20+)
                    if not box_qty or box_qty < 20:
                        continue
                    
                    # Get price
                    price_str = row.get('PRICE', '0').replace(' USD', '').strip()
                    try:
                        price = float(price_str)
                    except:
                        continue
                    
                    # Check availability
                    in_stock = row.get('AVAILABILITY', '').lower() == 'in stock'
                    
                    # Match to master database
                    match = matcher.match_product(brand, title, price)
                    
                    if match is not None:
                        matched_count += 1
                        
                        # Build size string
                        size = f"{match['Length']} x {match['Ring Gauge']}"
                        
                        products.append({
                            'title': title,
                            'url': row.get('LINK', ''),
                            'brand': match['Brand'],
                            'line': match['Line'],
                            'wrapper': match['Wrapper'],
                            'vitola': match['Vitola'],
                            'size': size,
                            'box_qty': box_qty,
                            'price': price,
                            'in_stock': in_stock
                        })
                    else:
                        unmatched_count += 1
                        logger.debug(f"No match for: {brand} - {title}")
                
                except Exception as e:
                    logger.warning(f"Error processing row: {e}")
                    continue
            
            logger.info(f"Matched: {matched_count}, Unmatched: {unmatched_count}")
            
            # Create DataFrame and deduplicate
            if not products:
                logger.warning(f"No products found for {retailer_name}")
                continue
            
            products_df = pd.DataFrame(products)
            
            # Deduplicate: keep cheapest price for each unique cigar
            products_df = products_df.sort_values('price').drop_duplicates(
                subset=['brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty'],
                keep='first'
            )
            
            # Save to CSV
            output_dir = Path(__file__).parent.parent / 'static' / 'data'
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / f'{retailer_name}.csv'
            products_df.to_csv(output_path, index=False)
            logger.info(f"✓ Saved {len(products_df)} {retailer_name} products to {output_path}")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading {retailer_name} feed: {e}")
        except Exception as e:
            logger.error(f"Error processing {retailer_name} feed: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    logger.info("All feeds processed!")

if __name__ == "__main__":
    process_feed()