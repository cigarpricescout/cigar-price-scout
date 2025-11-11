import requests
import gzip
import csv
import io
from pathlib import Path
import logging
import re
from cigar_matcher import CigarMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AWIN_FEED_URL = "https://productdata.awin.com/datafeed/download/apikey/3543fc5e82a1ca4122a1c5e74de3ac38/language/en/fid/104528/rid/0/hasEnhancedFeeds/0/columns/aw_deep_link,product_name,aw_product_id,merchant_product_id,merchant_image_url,description,merchant_category,search_price,merchant_name,merchant_id,category_name,category_id,aw_image_url,currency,store_price,delivery_cost,merchant_deep_link,language,last_updated,display_price,data_feed_id,brand_name,brand_id,colour,product_short_description,specifications,condition,product_model,model_number,dimensions,keywords,promotional_text,product_type,commission_group,merchant_product_category_path,merchant_product_second_category,merchant_product_third_category,rrp_price,saving,savings_percent,base_price,base_price_amount,base_price_text,product_price_old,in_stock,stock_quantity,valid_from,valid_to,is_for_sale,web_offer,pre_order,stock_status,size_stock_status,size_stock_amount/format/csv/delimiter/%2C/compression/gzip/adultcontent/1/"

# Path to your master cigar file
MASTER_FILE = Path(__file__).parent.parent / 'master_cigars.tsv'

def is_actual_cigar_product(title):
    """Filter for actual cigar products"""
    title_lower = title.lower()
    
    if 'cigar' not in title_lower:
        return False
    
    exclude_terms = [
        'hat', 'shirt', 'cap', 'apparel', 'clothing',
        'mug', 'cup', 'glass', 'set', 'kit', 'essentials',
        'pouch', 'bag', 'case', 'sampler', 'press', 'cutter', 
        'lighter', 'humidor', 'ashtray', 'punch', 'flask', 'torch',
        'book', 'magazine', 'guide', 'wood',
        'little cigars', 'cigarillos', 'damaged', 'tubes', 'cigarette'
    ]
    
    for term in exclude_terms:
        if term in title_lower:
            return False
    
    # Accept if has premium brand OR vitola
    premium_indicators = [
        'arturo fuente', 'padron', 'ashton', 'davidoff', 'opus x',
        'hemingway', 'don carlos', 'anejo', 'opus', 'fuente fuente',
        'aged', 'reserve', 'vintage', 'anniversary'
    ]
    
    is_premium = any(ind in title_lower for ind in premium_indicators)
    
    vitolas = ['corona', 'robusto', 'toro', 'churchill', 'torpedo', 
               'belicoso', 'perfecto', 'lancero', 'gordo']
    has_vitola = any(v in title_lower for v in vitolas)
    
    return is_premium or has_vitola

def parse_brand_and_line(title):
    """Extract brand and line from title"""
    title_lower = title.lower()
    
    brand_patterns = [
        ('arturo fuente', 'Arturo Fuente'),
        ('antonio y cleopatra', 'Antonio Y Cleopatra'),
        ('garcia y vega', 'Garcia Y Vega'),
        ('hoyo de monterrey', 'Hoyo De Monterrey'),
        ('hoyo de honduras', 'Hoyo De Honduras'),
        ('romeo y julieta', 'Romeo Y Julieta'),
        ('h upmann', 'H Upmann'),
        ('don pepin garcia', 'Don Pepin Garcia'),
        ('rocky patel', 'Rocky Patel'),
        ('alec bradley', 'Alec Bradley'),
        ('my father', 'My Father'),
        ('drew estate', 'Drew Estate'),
        ('la fabuloso', 'La Fabuloso'),
        ('dutch masters', 'Dutch Masters'),
        ('danlys', 'Danlys'),
        ('acid', 'Acid'),
        ('macanudo', 'Macanudo'),
        ('cohiba', 'Cohiba'),
        ('montecristo', 'Montecristo'),
        ('padron', 'Padron'),
        ('ashton', 'Ashton'),
        ('oliva', 'Oliva'),
        ('perdomo', 'Perdomo'),
        ('cao', 'CAO'),
        ('davidoff', 'Davidoff'),
    ]
    
    for pattern, full_name in brand_patterns:
        if title_lower.startswith(pattern):
            remaining = title[len(pattern):].strip()
            
            # Extract line
            vitolas = ['corona', 'robusto', 'toro', 'churchill', 'torpedo', 'belicoso', 'perfecto', 'lancero']
            line = ""
            
            for vitola in vitolas:
                if vitola in remaining.lower():
                    vitola_pos = remaining.lower().find(vitola)
                    line = remaining[:vitola_pos].strip()
                    break
            
            line = line.replace('Cigars', '').replace('Cigar', '').strip()
            return full_name, line
    
    words = title.split()
    return words[0] if words else "", ""

def fetch_and_parse_awin_feed():
    """Download and parse the Awin feed"""
    try:
        logger.info("Fetching Awin BnB Tobacco feed...")
        response = requests.get(AWIN_FEED_URL, timeout=300)
        response.raise_for_status()
        
        logger.info("Decompressing feed...")
        decompressed = gzip.decompress(response.content)
        csv_data = io.StringIO(decompressed.decode('utf-8'))
        
        reader = csv.DictReader(csv_data)
        products = []
        skipped = 0
        
        for row in reader:
            title = row.get('product_name', '').strip()
            
            if not title or not is_actual_cigar_product(title):
                skipped += 1
                continue
            
            products.append({
                'title': title,
                'url': row.get('aw_deep_link', ''),
                'price': row.get('search_price', '0'),
                'in_stock': row.get('in_stock', '1')
            })
        
        logger.info(f"Found {len(products)} cigar products (skipped {skipped})")
        return products
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return []

def save_to_csv(products, matcher):
    """Save products to CSV using master list for metadata"""
    output_dir = Path(__file__).parent.parent / 'static' / 'data'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / 'bnbtobacco.csv'
    
    valid = 0
    skipped_no_match = 0
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock'
        ])
        writer.writeheader()
        
        for product in products:
            brand, line = parse_brand_and_line(product['title'])
            
            if not brand or len(brand) < 3:
                continue
            
            # Get all vitolas for this brand+line from master
            vitolas = matcher.get_all_vitolas_for_line(brand, line)
            
            if not vitolas:
                # No match in master - skip
                skipped_no_match += 1
                logger.warning(f"No master match: {brand} {line}")
                continue
            
            # Create one CSV entry for EACH vitola in the master list
            for master_cigar in vitolas:
                size = f"{master_cigar['length']}x{master_cigar['ring_gauge']}" if master_cigar['length'] and master_cigar['ring_gauge'] else "5x50"
                
                writer.writerow({
                    'title': f"{brand} {line} {master_cigar['vitola']}",
                    'url': product['url'],
                    'brand': brand,
                    'line': line,
                    'wrapper': master_cigar['wrapper'],
                    'vitola': master_cigar['vitola'],
                    'size': size,
                    'box_qty': master_cigar['box_qty'] or 25,
                    'price': product['price'],
                    'in_stock': product['in_stock']
                })
                valid += 1
    
    logger.info(f"✓ Saved {valid} products ({skipped_no_match} skipped - no master match)")

def main():
    logger.info("Starting Awin BnB Tobacco feed processor with master matching...")
    
    # Load master cigar list
    matcher = CigarMatcher(MASTER_FILE)
    
    if not matcher.master_cigars:
        logger.error("❌ Master file not loaded - cannot proceed")
        return
    
    products = fetch_and_parse_awin_feed()
    
    if not products:
        logger.error("❌ No products found")
        return
    
    save_to_csv(products, matcher)
    logger.info("✓ Feed processing complete!")

if __name__ == "__main__":
    main()