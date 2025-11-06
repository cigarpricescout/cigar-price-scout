import requests
import pandas as pd
from pathlib import Path
import re
import logging
from io import StringIO
import zipfile
import io
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CJ HTTP credentials
CJ_USERNAME = '7711335'
CJ_PASSWORD = os.environ.get('CJ_HTTP_PASSWORD', '~quskK6y')

# Feed URLs from environment variables (set these in Railway)
FEEDS = {
    'thompson': os.environ.get('CJ_THOMPSON_URL', ''),
    'cigora': os.environ.get('CJ_CIGORA_URL', '')
}

def extract_size_from_title(title):
    """Extract size like '5.0" x 50' from title"""
    clean = title.replace('"""', '"').replace('\\"', '"')
    size_match = re.search(r'\((\d+\.?\d*)"*\s*x\s*(\d+)\)', clean)
    if size_match:
        return f'{size_match.group(1)}" x {size_match.group(2)}'
    return None

def extract_vitola_from_title(title):
    """Extract vitola/shape from title"""
    clean = title.replace('"""', '"').replace('\\"', '"')
    vitola_pattern = r'\b(Robusto|Toro|Corona|Churchill|Torpedo|Gordo|Belicoso|Lancero|Lonsdale|Perfecto|Figurado|Double Corona|Gran Toro|Double Toro|Short Robusto|Petit Corona|Petit|Nub|Tubo)\b'
    vitola_match = re.search(vitola_pattern, clean, re.IGNORECASE)
    return vitola_match.group(1) if vitola_match else None

def extract_box_qty_from_title(title):
    """Extract box quantity from title"""
    box_match = re.search(r'(?:BOX|Box)\s*(?:of\s*)?(\d+)', title, re.IGNORECASE)
    if box_match:
        return int(box_match.group(1))
    
    pack_match = re.search(r'(?:PACK|Pack)\s*(?:of\s*)?(\d+)', title, re.IGNORECASE)
    if pack_match:
        return int(pack_match.group(1))
    
    return None

def extract_line_from_title(title, brand):
    """Extract product line (between brand and vitola/size)"""
    clean = title.replace('"""', '"').replace('\\"', '"').strip('"')
    
    # Remove brand from beginning (case insensitive)
    brand_pattern = re.escape(brand)
    after_brand = re.sub(f'^{brand_pattern}\\s+', '', clean, flags=re.IGNORECASE).strip()
    
    # Split at first vitola word
    vitola_pattern = r'\s+(Robusto|Toro|Corona|Churchill|Torpedo|Gordo|Belicoso|Lancero|Lonsdale|Perfecto|Figurado|Double Corona|Gran Toro|Double Toro|Short Robusto|Petit Corona|Petit|Nub|Tubo|Belicoso|Emperor|No\.\s*4)\s'
    parts = re.split(vitola_pattern, after_brand, maxsplit=1, flags=re.IGNORECASE)
    line = parts[0].strip()
    
    # Remove size pattern from end
    line = re.sub(r'\s*\([0-9.]+.*?\).*$', '', line).strip()
    
    # Remove "BOX" or "PACK" suffix
    line = re.sub(r'\s*-?\s*(?:BOX|PACK|Box|Pack).*$', '', line, flags=re.IGNORECASE).strip()
    
    return line if line else 'Unknown'

def infer_box_qty_from_price(price):
    """Infer box quantity from price for Cigora products"""
    if price >= 80:
        return 20  # Box
    elif price >= 25:
        return 5   # 5-pack
    else:
        return 1   # Single

def process_feed():
    """Download and process separate Thompson and Cigora feeds"""
    
    if not FEEDS['thompson'] and not FEEDS['cigora']:
        logger.error("No feed URLs configured. Set CJ_THOMPSON_URL and CJ_CIGORA_URL environment variables.")
        return
    
    for retailer_name, feed_url in FEEDS.items():
        try:
            # Skip if no URL configured
            if not feed_url or feed_url.strip() == '':
                logger.warning(f"Skipping {retailer_name} - no URL configured")
                continue
            
            logger.info(f"Processing {retailer_name}...")
            logger.info(f"Downloading from {feed_url}")
            
            # Download ZIP file with authentication
            response = requests.get(
                feed_url,
                auth=(CJ_USERNAME, CJ_PASSWORD),
                timeout=60
            )
            response.raise_for_status()
            
            logger.info(f"Downloaded {len(response.content)} bytes")
            
            # Extract ZIP file
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                # Find the .txt file inside
                txt_files = [name for name in z.namelist() if name.endswith('.txt')]
                if not txt_files:
                    logger.error(f"No .txt file found in {retailer_name} ZIP")
                    continue
                
                feed_content = z.read(txt_files[0]).decode('utf-8')
                logger.info(f"Extracted {txt_files[0]}")
            
            # Parse TSV
            df = pd.read_csv(StringIO(feed_content), sep='\t', dtype=str)
            logger.info(f"Parsed {len(df)} products from {retailer_name}")
            
            # Process products
            products = []
            
            for _, row in df.iterrows():
                try:
                    brand = row.get('BRAND', '').strip()
                    title = row.get('TITLE', '').strip()
                    
                    if not brand or not title:
                        continue
                    
                    # Extract data
                    size = extract_size_from_title(title)
                    vitola = extract_vitola_from_title(title)
                    # Skip products without a vitola
                    if not vitola:
                        continue
                    line = extract_line_from_title(title, brand)
                    box_qty = extract_box_qty_from_title(title)
                    
                    price_str = row.get('PRICE', '0').replace(' USD', '').strip()
                    try:
                        price = float(price_str)
                    except:
                        continue
                    
                    # For Cigora: infer box_qty from price if not explicit
                    if retailer_name == 'cigora' and box_qty is None:
                        box_qty = infer_box_qty_from_price(price)
                    
                    # Only keep boxes (20+)
                    if box_qty is None or box_qty < 20:
                        continue
                    
                    in_stock = row.get('AVAILABILITY', '').lower() == 'in stock'
                    
                    products.append({
                        'title': re.sub(r'"{2,}', '"', title).strip('"'),
                        'url': row.get('LINK', ''),
                        'brand': brand,
                        'line': line,
                        'wrapper': '',  # Leave blank - add manually later
                        'vitola': vitola or '',  # Extract from title
                        'size': size or '',
                        'box_qty': box_qty,
                        'price': price,
                        'in_stock': in_stock
                    })
                        
                except Exception as e:
                    logger.warning(f"Error processing row: {e}")
                    continue
            
            # Create DataFrame and deduplicate
            if not products:
                logger.warning(f"No products found for {retailer_name}")
                continue
            
            products_df = pd.DataFrame(products)
            products_df = products_df.sort_values('price').drop_duplicates(
                subset=['brand', 'line', 'size', 'box_qty'],
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