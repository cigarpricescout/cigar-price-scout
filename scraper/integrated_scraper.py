import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import csv
from datetime import datetime
import os
import re
import random
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

class IntegratedCigarScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'CigarPriceScoutBot/1.0 (+https://cigar-price-scout.com)'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Load master cigars and build brand mappings
        self.master_cigars = self.load_master_cigars()
        self.brand_resolver = self.build_brand_resolver()
        
        # Priority brand set for mass-market traffic
        self.priority_brands = [
            'Arturo Fuente', 'Padron', 'Oliva', 'Drew Estate', 'My Father',
            'Ashton', 'Perdomo', 'Romeo y Julieta', 'Montecristo', 'AJ Fernandez',
            'CAO', 'Punch', 'San Cristobal', 'Liga Privada', 'Undercrown',
            'Hemingway', 'Don Carlos', 'Serie V', 'Melanio', 'Le Bijou',
            'Flor de Las Antillas', 'New World', 'San Lotano'
        ]
        
        # Standard wrapper/vitola mappings for processing
        self.wrapper_mappings = {
            'natural': 'Connecticut Shade',
            'connecticut': 'Connecticut Shade', 
            'connecticut shade': 'Connecticut Shade',
            'cameroon': 'Cameroon',
            'maduro': 'Maduro',
            'habano': 'Habano',
            'corojo': 'Corojo',
            'candela': 'Candela',
            'oscuro': 'Oscuro',
            'mexican san andres': 'Mexican San Andres Maduro',
            'ecuadorian': 'Ecuadorian',
            'indonesian': 'Indonesian Shade Grown TBN'
        }
        
        self.vitola_mappings = {
            'churchill': 'Churchill',
            'robusto': 'Robusto', 
            'toro': 'Toro',
            'corona': 'Corona',
            'torpedo': 'Torpedo',
            'belicoso': 'Belicoso',
            'lancero': 'Lancero',
            'lonsdale': 'Lonsdale',
            'perfecto': 'Perfecto',
            'petit corona': 'Petit Corona',
            'grand corona': 'Grand Corona',
            'presidente': 'Presidente',
            'double corona': 'Double Corona',
            'gordo': 'Gordo',
            'gigante': 'Gigante',
            'rothschild': 'Rothschild'
        }
        
        # Retailer configurations
        self.retailers = {
            'Fox Cigar': {
                'base_url': 'https://www.foxcigar.com',
                'tier': 1,
                'platform': 'WooCommerce',
                'sitemap_urls': [
                    'https://www.foxcigar.com/sitemap.xml',
                    'https://www.foxcigar.com/product-sitemap.xml'
                ],
                'archive_pages': [
                    'https://www.foxcigar.com/product-category/cigars/',
                    'https://www.foxcigar.com/product-category/cigars/arturo-fuente/',
                    'https://www.foxcigar.com/product-category/cigars/romeo-y-julieta/',
                    'https://www.foxcigar.com/product-category/cigars/padron/'
                ],
                'limits': {'delay_min': 800, 'delay_max': 1500, 'max_products': 100, 'max_pages': 8}
            }
        }
    
    def load_master_cigars(self):
        """Load master cigar list"""
        try:
            paths = [
                'data/master_cigars.tsv',
                '/mnt/user-data/uploads/master_cigars.tsv',
                'master_cigars.tsv'
            ]
            
            for path in paths:
                try:
                    master_df = pd.read_csv(path, sep='\t')
                    print(f"Loaded {len(master_df)} cigars from master list")
                    return master_df
                except FileNotFoundError:
                    continue
            
            print("Warning: Could not find master_cigars.tsv file")
            return pd.DataFrame()
            
        except Exception as e:
            print(f"Error loading master cigars: {e}")
            return pd.DataFrame()
    
    def build_brand_resolver(self):
        """Build comprehensive brand resolver from master data"""
        resolver = {}
        
        if not self.master_cigars.empty:
            # Exact brand matches
            for _, row in self.master_cigars.iterrows():
                brand = str(row.get('Brand', '')).strip()
                line = str(row.get('Line', '')).strip()
                
                if brand and brand != 'nan':
                    resolver[brand.lower()] = {
                        'brand': brand,
                        'line': line if line != 'nan' else '',
                        'source': 'master_exact'
                    }
                    
                    # Add brand + line combinations
                    if line and line != 'nan':
                        combined = f"{brand} {line}".lower()
                        resolver[combined] = {
                            'brand': brand,
                            'line': line,
                            'source': 'master_combined'
                        }
        
        print(f"Built brand resolver with {len(resolver)} entries")
        return resolver
    
    def get_sitemap_product_urls(self, retailer_name):
        """Extract product URLs from sitemaps with brand filtering"""
        retailer = self.retailers[retailer_name]
        product_urls = []
        
        print(f"Checking sitemaps for {retailer_name}...")
        
        for sitemap_url in retailer['sitemap_urls']:
            try:
                response = self.session.get(sitemap_url, timeout=10)
                if response.status_code == 404:
                    continue
                    
                response.raise_for_status()
                root = ET.fromstring(response.content)
                
                # Handle sitemap index or direct sitemap
                if root.tag.endswith('sitemapindex'):
                    for sitemap in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
                        loc = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                        if loc is not None and 'product' in loc.text:
                            sub_urls = self.parse_product_sitemap(loc.text)
                            product_urls.extend(sub_urls)
                elif root.tag.endswith('urlset'):
                    product_urls.extend(self.parse_product_sitemap(sitemap_url, root))
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"  Error with {sitemap_url}: {e}")
                continue
        
        # Filter to priority brands only
        filtered_urls = self.filter_urls_by_brand(product_urls)
        print(f"Sitemap discovery: {len(product_urls)} total -> {len(filtered_urls)} brand-filtered URLs")
        
        return filtered_urls
    
    def parse_product_sitemap(self, sitemap_url, root=None):
        """Parse individual product sitemap"""
        product_urls = []
        
        if root is None:
            try:
                response = self.session.get(sitemap_url, timeout=10)
                response.raise_for_status()
                root = ET.fromstring(response.content)
            except Exception as e:
                return product_urls
        
        # Extract URLs
        for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
            loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
            if loc is not None:
                url_text = loc.text
                if self.is_product_url_from_sitemap(url_text):
                    product_urls.append(url_text)
        
        return product_urls
    
    def is_product_url_from_sitemap(self, url):
        """Check if sitemap URL is a product page"""
        path = urlparse(url).path.lower()
        
        # Must look like a product
        product_indicators = ['/shop/', '/product/', '/cigars/']
        if not any(indicator in path for indicator in product_indicators):
            return False
        
        # Skip category/archive pages
        skip_patterns = ['/category/', '/tag/', '/page/', '/brand/$', '/cigars/$']
        if any(pattern in path for pattern in skip_patterns):
            return False
        
        # Should be specific product (deep path)
        path_parts = [p for p in path.split('/') if p]
        return len(path_parts) >= 3
    
    def filter_urls_by_brand(self, urls):
        """Filter URLs to only priority brands"""
        filtered = []
        
        for url in urls:
            url_lower = url.lower()
            
            # Check if URL contains any priority brand
            for brand in self.priority_brands:
                brand_variations = brand.lower().split()
                
                # Check for brand name in URL
                if any(variation in url_lower for variation in brand_variations):
                    filtered.append(url)
                    break
        
        return filtered
    
    def scrape_product(self, product_url, retailer_name):
        """Enhanced product scraping with brand resolution"""
        retailer = self.retailers[retailer_name]
        
        try:
            # Smart delay
            min_delay = retailer['limits']['delay_min'] / 1000.0
            max_delay = retailer['limits']['delay_max'] / 1000.0
            delay = random.uniform(min_delay, max_delay)
            time.sleep(delay)
            
            response = self.session.get(product_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract basic data
            name = self.extract_name(soup)
            price = self.extract_price(soup)
            
            if not name or name == "Product name not found" or price == 0.0:
                return None
            
            # Resolve brand using comprehensive resolver
            brand_info = self.resolve_brand(name)
            
            # Extract additional details
            vitola = self.extract_vitola(name)
            wrapper = self.extract_wrapper(name)
            ring_gauge = self.extract_ring_gauge(name)
            length = self.extract_length(name)
            
            product_data = {
                'retailer': retailer_name,
                'url': product_url,
                'name': name,
                'price': price,
                'brand': brand_info['brand'],
                'line': brand_info['line'],
                'vitola': vitola,
                'wrapper': wrapper,
                'ring_gauge': ring_gauge,
                'length': length,
                'availability': self.extract_availability(soup),
                'platform': retailer['platform'],
                'tier': retailer['tier'],
                'brand_source': brand_info['source'],
                'scraped_at': datetime.now().isoformat()
            }
            
            return product_data
            
        except Exception as e:
            return None
    
    def resolve_brand(self, product_name):
        """Resolve brand using comprehensive brand resolver"""
        if not product_name:
            return {'brand': 'Unknown', 'line': '', 'source': 'none'}
        
        name_lower = product_name.lower()
        
        # Try exact matches first (longest to shortest)
        for brand_key in sorted(self.brand_resolver.keys(), key=len, reverse=True):
            if brand_key in name_lower:
                return self.brand_resolver[brand_key]
        
        # Fallback to priority brand fuzzy matching
        for brand in self.priority_brands:
            brand_words = brand.lower().split()
            if any(word in name_lower for word in brand_words if len(word) > 3):
                return {'brand': brand, 'line': '', 'source': 'fuzzy_priority'}
        
        return {'brand': 'Unknown', 'line': '', 'source': 'none'}
    
    def extract_name(self, soup):
        """Extract product name"""
        selectors = [
            'h1.product_title',
            'h1.entry-title', 
            '.product-title h1',
            '.product-title',
            'h1[class*="title"]',
            'h1'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                name = element.get_text().strip()
                if name and len(name) > 5:
                    return name
        
        return "Product name not found"
    
    def extract_price(self, soup):
        """Extract price with better handling"""
        selectors = [
            '.woocommerce-Price-amount bdi',
            '.price .woocommerce-Price-amount bdi',
            '.price .woocommerce-Price-amount',
            '.price .amount',
            '.price',
            '[class*="price"]:not([class*="strike"])'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                price_text = element.get_text().strip()
                
                # Skip sale/strike prices context
                parent_text = element.parent.get_text() if element.parent else ""
                if any(word in parent_text.lower() for word in ['was:', 'msrp', 'retail']):
                    continue
                
                # Extract price
                price_match = re.search(r'\$(\d{1,4}(?:,\d{3})*\.?\d{0,2})', price_text)
                if price_match:
                    try:
                        price = float(price_match.group(1).replace(',', ''))
                        if 1.0 <= price <= 5000.0:
                            return price
                    except ValueError:
                        continue
        
        return 0.0
    
    def extract_vitola(self, name):
        """Extract vitola from name"""
        if not name:
            return "Unknown"
        
        name_lower = name.lower()
        
        # Common vitolas (longest first for better matching)
        vitolas = [
            'double corona', 'petit corona', 'grand corona', 'corona extra',
            'churchill', 'robusto', 'torpedo', 'perfecto', 'lancero',
            'lonsdale', 'panetela', 'rothschild', 'presidente', 'gigante',
            'gordito', 'corona', 'toro'
        ]
        
        for vitola in vitolas:
            if vitola in name_lower:
                return vitola.title()
        
        return "Unknown"
    
    def extract_wrapper(self, name):
        """Extract wrapper from name"""
        name_lower = name.lower()
        
        wrapper_map = {
            'maduro': 'Maduro',
            'natural': 'Natural',
            'connecticut': 'Connecticut',
            'cameroon': 'Cameroon', 
            'habano': 'Habano',
            'corojo': 'Corojo',
            'candela': 'Candela',
            'oscuro': 'Oscuro',
            'claro': 'Claro'
        }
        
        for term, wrapper in wrapper_map.items():
            if term in name_lower:
                return wrapper
        
        return "Unknown"
    
    def extract_ring_gauge(self, name):
        """Extract ring gauge from name"""
        patterns = [
            r'(\d{2,3})rg',
            r'x\s*(\d{2,3})',
            r'ring\s*(\d{2,3})',
            r'(\d+\.?\d*)\s*x\s*(\d{2,3})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, name.lower())
            if match:
                if len(match.groups()) == 2:  # Length x Ring format
                    return int(match.group(2))
                else:
                    ring = int(match.group(1))
                    if 20 <= ring <= 80:  # Reasonable ring gauge range
                        return ring
        
        return None
    
    def extract_length(self, name):
        """Extract length from name"""
        patterns = [
            r'(\d+\.?\d*)\s*x\s*\d{2,3}',
            r'(\d+)\s*(\d+/\d+)',  # 5 1/2 format
            r'(\d+\.?\d*)\s*inch'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, name.lower())
            if match:
                try:
                    if len(match.groups()) == 2 and '/' in match.group(2):
                        # Handle fraction format like "5 1/2"
                        whole = float(match.group(1))
                        frac_parts = match.group(2).split('/')
                        fraction = float(frac_parts[0]) / float(frac_parts[1])
                        length = whole + fraction
                    else:
                        length = float(match.group(1))
                    
                    if 3.0 <= length <= 10.0:  # Reasonable cigar length
                        return length
                except ValueError:
                    continue
        
        return None
    
    def extract_availability(self, soup):
        """Extract availability"""
        page_text = soup.get_text().lower()
        
        if 'out of stock' in page_text or 'sold out' in page_text:
            return 'Out of Stock'
        elif 'in stock' in page_text or 'add to cart' in page_text:
            return 'In Stock'
        else:
            return 'Unknown'
    
    def scrape_retailer(self, retailer_name, max_products=None):
        """Scrape retailer and get raw data"""
        retailer = self.retailers[retailer_name]
        if max_products is None:
            max_products = retailer['limits']['max_products']
        
        print(f"\n{'='*80}")
        print(f"SCRAPING: {retailer_name.upper()}")
        print(f"Target: {max_products} products from priority brands")
        print(f"{'='*80}")
        
        # Get URLs from sitemap
        sitemap_urls = self.get_sitemap_product_urls(retailer_name)
        
        print(f"Will scrape {min(len(sitemap_urls), max_products)} products")
        
        # Scrape products
        products = []
        target_urls = sitemap_urls[:max_products]
        
        for i, url in enumerate(target_urls, 1):
            print(f"[{i}/{len(target_urls)}] ", end="", flush=True)
            product = self.scrape_product(url, retailer_name)
            if product:
                products.append(product)
                print(f"SUCCESS: {product['brand']} - {product['name'][:30]}...")
            else:
                print("SKIP")
        
        print(f"\n{retailer_name}: {len(products)} products scraped")
        return products
    
    def process_to_website_format(self, raw_products, retailer_name):
        """Process raw scraped data into website-ready format"""
        print(f"\nProcessing {len(raw_products)} products for website...")
        
        processed_data = []
        
        for product in raw_products:
            # Filter out non-cigars
            if not self.is_cigar_product(product['name'], product['price']):
                continue
            
            # Process fields for website
            title = self.clean_title(product['name'])
            line = self.extract_line_from_master(product['brand'], product['name'])
            normalized_wrapper = self.normalize_wrapper(product['wrapper'])
            normalized_vitola = self.normalize_vitola(product['vitola'])
            size = self.extract_size(product['name'], product['ring_gauge'], product['length'])
            box_qty = self.extract_box_quantity(product['name'])
            
            # Convert availability to boolean
            in_stock = product['availability'].lower() in ['in stock', 'available', 'true', 'yes']
            
            processed_data.append({
                'title': title,
                'url': product['url'],
                'brand': product['brand'],
                'line': line,
                'wrapper': normalized_wrapper,
                'vitola': normalized_vitola,
                'size': size,
                'box_qty': box_qty,
                'price': product['price'],
                'in_stock': in_stock
            })
        
        print(f"Processed to {len(processed_data)} website-ready products")
        return processed_data
    
    def is_cigar_product(self, product_name, price):
        """Filter out non-cigar products"""
        if not product_name or price < 3.0:
            return False
        
        name_lower = product_name.lower()
        
        # Skip accessories and non-cigars
        non_cigar_terms = [
            'lighter', 'cutter', 'ashtray', 'humidor', 'kit', 'hat',
            'case', 'flame', 'torch', 'tool', 'accessory', 'punch',
            'stand', 'rest', 'holder', 'box only', 'empty box',
            'gift card', 'shipping'
        ]
        
        if any(term in name_lower for term in non_cigar_terms):
            return False
        
        return True
    
    def extract_box_quantity(self, title):
        """Extract box quantity from title"""
        if not title:
            return 1
        
        # Look for "Box of X", "Pack of X", "(X)"
        patterns = [
            r'box\s+of\s+(\d+)',
            r'pack\s+of\s+(\d+)', 
            r'\((\d+)\)',
            r'(\d+)\s*count',
            r'(\d+)\s*ct'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title.lower())
            if match:
                qty = int(match.group(1))
                if 1 <= qty <= 100:  # Reasonable range
                    return qty
        
        return 1  # Default to single cigar
    
    def extract_size(self, product_name, ring_gauge=None, length=None):
        """Extract size in 7x48 format"""
        if ring_gauge and length:
            return f"{length}x{ring_gauge}"
        
        if not product_name:
            return "Unknown"
        
        # Look for size patterns in product name
        size_patterns = [
            r'(\d+\.?\d*)\s*x\s*(\d{2,3})',
            r'(\d+)\s+(\d+/\d+)\s*x\s*(\d{2,3})',  # 5 1/2 x 50
            r'(\d+\.?\d*)"?\s*x\s*(\d{2,3})'
        ]
        
        for pattern in size_patterns:
            match = re.search(pattern, product_name.lower())
            if match:
                if len(match.groups()) == 3:  # Fraction format
                    whole = int(match.group(1))
                    frac_parts = match.group(2).split('/')
                    fraction = float(frac_parts[0]) / float(frac_parts[1])
                    length = whole + fraction
                    ring = match.group(3)
                else:
                    length = match.group(1)
                    ring = match.group(2)
                
                return f"{length}x{ring}"
        
        return "Unknown"
    
    def normalize_wrapper(self, wrapper_text):
        """Normalize wrapper to standard names"""
        if not wrapper_text or wrapper_text == "Unknown":
            return "Unknown"
        
        wrapper_lower = wrapper_text.lower().strip()
        
        # Direct mapping
        if wrapper_lower in self.wrapper_mappings:
            return self.wrapper_mappings[wrapper_lower]
        
        # Partial matching
        for key, value in self.wrapper_mappings.items():
            if key in wrapper_lower:
                return value
        
        return wrapper_text.title()  # Return original if no match
    
    def normalize_vitola(self, vitola_text):
        """Normalize vitola to standard names"""
        if not vitola_text or vitola_text == "Unknown":
            return "Unknown"
        
        vitola_lower = vitola_text.lower().strip()
        
        # Direct mapping
        if vitola_lower in self.vitola_mappings:
            return self.vitola_mappings[vitola_lower]
        
        return vitola_text.title()  # Return original if no match
    
    def extract_line_from_master(self, brand, product_name):
        """Extract line using master cigars data"""
        if self.master_cigars.empty or not brand or brand == "Unknown":
            return self.extract_line_fallback(product_name)
        
        # Find matching lines for this brand
        brand_cigars = self.master_cigars[self.master_cigars['Brand'].str.lower() == brand.lower()]
        
        if brand_cigars.empty:
            return self.extract_line_fallback(product_name)
        
        product_lower = product_name.lower()
        
        # Check each line for matches (longest first)
        lines = brand_cigars['Line'].dropna().unique()
        for line in sorted(lines, key=len, reverse=True):
            if line.lower() in product_lower:
                return line
        
        return self.extract_line_fallback(product_name)
    
    def extract_line_fallback(self, product_name):
        """Fallback line extraction for common patterns"""
        if not product_name:
            return "Unknown"
        
        name_lower = product_name.lower()
        
        # Common line patterns
        line_patterns = {
            'hemingway': 'Hemingway',
            '1875': '1875',
            '1964': '1964 Anniversary',
            '1926': '1926 Anniversary', 
            'liga privada': 'Liga Privada',
            'undercrown': 'Undercrown',
            'herrera esteli': 'Herrera Esteli',
            'norteno': 'Herrera Esteli Norteno',
            'excalibur': 'Excalibur',
            'don carlos': 'Don Carlos',
            'opus x': 'Opus X',
            'gran reserva': 'Gran Reserva',
            'serie v': 'Serie V',
            'flor de las antillas': 'Flor de Las Antillas'
        }
        
        for pattern, line in line_patterns.items():
            if pattern in name_lower:
                return line
        
        return "Unknown"
    
    def clean_title(self, product_name):
        """Clean and format title for website"""
        if not product_name:
            return "Unknown Product"
        
        # Remove extra whitespace and special characters
        title = re.sub(r'\s+', ' ', product_name.strip())
        title = re.sub(r'[^\w\s\-\.\(\)\/]', '', title)
        
        # Capitalize properly
        title = title.title()
        
        return title
    
    def save_website_csv(self, processed_data, retailer_name):
        """Save processed data in website format to static/data directory"""
        if not processed_data:
            print("No processed data to save")
            return None
        
        # Create website-ready CSV filename in static/data directory
        retailer_filename = retailer_name.lower().replace(' ', '_')
        filename = f'static/data/{retailer_filename}.csv'
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Create DataFrame with exact website columns
        df = pd.DataFrame(processed_data)
        
        # Ensure column order matches your website format
        column_order = ['title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
        df = df[column_order]
        
        # Save to CSV
        df.to_csv(filename, index=False)
        
        print(f"\nWebsite-ready CSV saved: {filename}")
        print(f"Products: {len(df)}")
        print(f"Location: cigar-price-scout/static/data/{retailer_filename}.csv")
        print(f"Format matches your bestcigar.csv exactly")
        
        return filename

def run_integrated_fox_cigar():
    """Run complete pipeline: scrape -> process -> save website CSV"""
    scraper = IntegratedCigarScraper()
    
    print("INTEGRATED CIGAR SCRAPER PIPELINE")
    print("Scrape -> Process -> Website-Ready CSV")
    print("="*80)
    
    # Step 1: Scrape raw data
    raw_products = scraper.scrape_retailer('Fox Cigar', max_products=100)
    
    if not raw_products:
        print("No products scraped")
        return False
    
    # Step 2: Process to website format
    processed_products = scraper.process_to_website_format(raw_products, 'Fox Cigar')
    
    if not processed_products:
        print("No products after processing")
        return False
    
    # Step 3: Save website-ready CSV
    csv_file = scraper.save_website_csv(processed_products, 'Fox Cigar')
    
    if csv_file:
        print(f"\nPIPELINE COMPLETE!")
        print(f"Your website can now import: {csv_file}")
        return True
    else:
        print("Failed to save website CSV")
        return False

if __name__ == "__main__":
    # Create directories
    os.makedirs('static/data', exist_ok=True)
    
    # Run integrated pipeline
    success = run_integrated_fox_cigar()
    
    if success:
        print("\nREADY FOR WEBSITE INTEGRATION!")
        print("The CSV file is in your static/data directory for automatic import.")
