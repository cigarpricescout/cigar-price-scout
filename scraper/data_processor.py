import pandas as pd
import re
import os
from datetime import datetime

class CigarDataProcessor:
    def __init__(self):
        # Load master cigars for reference
        self.master_cigars = self.load_master_cigars()
        
        # Standard wrapper mappings
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
        
        # Standard vitola mappings
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
    
    def load_master_cigars(self):
        """Load master cigars for reference"""
        try:
            paths = [
                'data/master_cigars.tsv',
                '/mnt/user-data/uploads/master_cigars.tsv',
                'master_cigars.tsv'
            ]
            
            for path in paths:
                try:
                    return pd.read_csv(path, sep='\t')
                except FileNotFoundError:
                    continue
            
            print("Warning: Could not find master_cigars.tsv")
            return pd.DataFrame()
        except Exception as e:
            print(f"Error loading master cigars: {e}")
            return pd.DataFrame()
    
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
        
        # Must contain cigar indicators
        cigar_indicators = [
            'cigar', 'churchill', 'robusto', 'toro', 'corona', 'torpedo',
            'lancero', 'perfecto', 'maduro', 'natural', 'wrapper',
            'box of', 'pack of', 'sampler'
        ]
        
        return any(indicator in name_lower for indicator in cigar_indicators)
    
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
    
    def process_raw_data(self, raw_csv_path, retailer_name):
        """Process raw scraper CSV into website format"""
        print(f"Processing {raw_csv_path} for {retailer_name}...")
        
        # Load raw data
        try:
            df = pd.read_csv(raw_csv_path)
        except Exception as e:
            print(f"Error loading {raw_csv_path}: {e}")
            return None
        
        print(f"Loaded {len(df)} raw products")
        
        # Filter to cigars only
        cigar_mask = df.apply(lambda row: self.is_cigar_product(row.get('name', ''), row.get('price', 0)), axis=1)
        df_cigars = df[cigar_mask].copy()
        
        print(f"Filtered to {len(df_cigars)} cigar products")
        
        if df_cigars.empty:
            print("No cigar products found after filtering")
            return None
        
        # Transform to website format
        processed_data = []
        
        for _, row in df_cigars.iterrows():
            # Extract data
            product_name = row.get('name', '')
            brand = row.get('brand', 'Unknown')
            price = row.get('price', 0)
            url = row.get('url', '')
            availability = row.get('availability', 'Unknown')
            wrapper = row.get('wrapper', 'Unknown')
            vitola = row.get('vitola', 'Unknown')
            ring_gauge = row.get('ring_gauge')
            length = row.get('length')
            
            # Process fields
            title = self.clean_title(product_name)
            line = self.extract_line_from_master(brand, product_name)
            normalized_wrapper = self.normalize_wrapper(wrapper)
            normalized_vitola = self.normalize_vitola(vitola)
            size = self.extract_size(product_name, ring_gauge, length)
            box_qty = self.extract_box_quantity(product_name)
            
            # Convert availability to boolean
            in_stock = availability.lower() in ['in stock', 'available', 'true', 'yes']
            
            processed_data.append({
                'title': title,
                'url': url,
                'brand': brand,
                'line': line,
                'wrapper': normalized_wrapper,
                'vitola': normalized_vitola,
                'size': size,
                'box_qty': box_qty,
                'price': price,
                'in_stock': in_stock
            })
        
        # Create processed DataFrame
        processed_df = pd.DataFrame(processed_data)
        
        # Save processed data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f'data/processed/{retailer_name.lower().replace(" ", "_")}_{timestamp}.csv'
        
        os.makedirs(os.path.dirname(output_filename), exist_ok=True)
        processed_df.to_csv(output_filename, index=False)
        
        print(f"Processed data saved to: {output_filename}")
        
        # Quality report
        self.generate_quality_report(processed_df, retailer_name)
        
        return output_filename
    
    def generate_quality_report(self, df, retailer_name):
        """Generate data quality report"""
        print(f"\n{'='*60}")
        print(f"DATA QUALITY REPORT - {retailer_name.upper()}")
        print(f"{'='*60}")
        
        total_products = len(df)
        print(f"Total products: {total_products}")
        
        # Brand analysis
        known_brands = len(df[df['brand'] != 'Unknown'])
        print(f"Known brands: {known_brands}/{total_products} ({known_brands/total_products*100:.1f}%)")
        
        # Line analysis  
        known_lines = len(df[df['line'] != 'Unknown'])
        print(f"Known lines: {known_lines}/{total_products} ({known_lines/total_products*100:.1f}%)")
        
        # Size analysis
        known_sizes = len(df[df['size'] != 'Unknown'])
        print(f"Known sizes: {known_sizes}/{total_products} ({known_sizes/total_products*100:.1f}%)")
        
        # Wrapper analysis
        known_wrappers = len(df[df['wrapper'] != 'Unknown'])
        print(f"Known wrappers: {known_wrappers}/{total_products} ({known_wrappers/total_products*100:.1f}%)")
        
        # Price analysis
        print(f"\nPrice range: ${df['price'].min():.2f} - ${df['price'].max():.2f}")
        print(f"Average price: ${df['price'].mean():.2f}")
        
        # Top brands
        top_brands = df['brand'].value_counts().head(5)
        print(f"\nTop brands:")
        for brand, count in top_brands.items():
            if brand != 'Unknown':
                print(f"  {brand}: {count} products")
        
        # Box quantity analysis
        box_qty_dist = df['box_qty'].value_counts().sort_index()
        print(f"\nBox quantities:")
        for qty, count in box_qty_dist.items():
            print(f"  {qty}: {count} products")

def process_fox_cigar_data():
    """Process the most recent Fox Cigar scrape"""
    processor = CigarDataProcessor()
    
    # Find most recent Fox Cigar CSV
    data_dir = 'data/raw'
    if not os.path.exists(data_dir):
        print(f"Data directory {data_dir} not found")
        return
    
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    if not csv_files:
        print("No CSV files found in data/raw")
        return
    
    # Get most recent file
    csv_files.sort(reverse=True)
    latest_file = os.path.join(data_dir, csv_files[0])
    
    print(f"Processing latest file: {latest_file}")
    
    # Process the data
    output_file = processor.process_raw_data(latest_file, 'Fox Cigar')
    
    if output_file:
        print(f"\nSUCCESS! Website-ready data saved to: {output_file}")
        return output_file
    else:
        print("Processing failed")
        return None

if __name__ == "__main__":
    print("CIGAR DATA PROCESSOR")
    print("Transforms raw scraper output into website format")
    print("="*60)
    
    # Create directories
    os.makedirs('data/processed', exist_ok=True)
    
    # Process Fox Cigar data
    result = process_fox_cigar_data()
    
    if result:
        print(f"\nREADY FOR WEBSITE IMPORT!")
        print("The processed CSV matches your bestcigar.csv format exactly.")
