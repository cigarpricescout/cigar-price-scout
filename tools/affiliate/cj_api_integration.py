import requests
import json
import csv
import time
from datetime import datetime
import re
from pathlib import Path

class CJProductFeedAPI:
    def __init__(self, personal_access_token, company_id="7711335"):
        self.token = personal_access_token
        self.company_id = company_id
        self.base_url = "https://ads.api.cj.com/query"
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        # Known cigar retailer advertiser IDs (you'll need to find these)
        self.cigar_retailers = {
            # These are examples - you'll need to find the actual IDs
            'famous': None,  # Famous Smoke Shop
            'ci': None,      # Cigars International  
            'thompson': None, # Thompson Cigar
            'jr': None,      # JR Cigar
            # Add more as you discover them
        }
    
    def find_cigar_retailers(self):
        """Find advertiser IDs for cigar retailers"""
        print("Searching for cigar retailer partners...")
        
        # First, get all available product feeds
        query = """
        {
            productFeeds(companyId: "%s", limit: 1000) {
                totalCount
                resultList {
                    adId
                    feedName
                    advertiserId
                    advertiserName
                    productCount
                    lastUpdated
                }
            }
        }
        """ % self.company_id
        
        response = self._make_request(query)
        if not response:
            return {}
        
        feeds = response.get('data', {}).get('productFeeds', {}).get('resultList', [])
        
        # Look for cigar-related retailers
        cigar_keywords = ['cigar', 'smoke', 'tobacco', 'famous', 'thompson', 'jr', 'international']
        found_retailers = {}
        
        for feed in feeds:
            advertiser_name = feed.get('advertiserName') or ''
            feed_name = feed.get('feedName') or ''
            
            advertiser_name = advertiser_name.lower()
            feed_name = feed_name.lower()
            
            for keyword in cigar_keywords:
                if keyword in advertiser_name or keyword in feed_name:
                    retailer_key = self._generate_retailer_key(advertiser_name)
                    found_retailers[retailer_key] = {
                        'advertiser_id': feed.get('advertiserId'),
                        'ad_id': feed.get('adId'), 
                        'name': feed.get('advertiserName'),
                        'feed_name': feed.get('feedName'),
                        'product_count': feed.get('productCount', 0),
                        'last_updated': feed.get('lastUpdated')
                    }
                    print(f"Found: {feed.get('advertiserName')} (ID: {feed.get('advertiserId')}, Products: {feed.get('productCount')})")
                    break
        
        return found_retailers
    
    def _generate_retailer_key(self, name):
        """Generate a retailer key from name"""
        # Remove common words and make lowercase
        name = re.sub(r'\b(inc|llc|company|corp|limited|ltd)\b', '', name.lower())
        name = re.sub(r'[^a-z0-9]', '', name)
        return name[:15]  # Limit length
    
    def get_products_from_retailer(self, advertiser_id, limit=10000):
        """Get all products from a specific retailer"""
        print(f"Fetching products from advertiser ID: {advertiser_id}")
        
        query = """
        {
            products(companyId: "%s", partnerIds: [%s], limit: %d, keywords: ["cigar"]) {
                totalCount
                count
                resultList {
                    id
                    title
                    description
                    brand
                    price {
                        amount
                        currency
                    }
                    salePrice {
                        amount
                        currency
                    }
                    availability
                    linkCode(pid: "%s") {
                        clickUrl
                    }
                    advertiserId
                    advertiserName
                    lastUpdated
                }
            }
        }
        """ % (self.company_id, advertiser_id, limit, "101532120")  # Using your Property ID as PID
        
        response = self._make_request(query)
        if not response:
            return []
        
        products_data = response.get('data', {}).get('products', {})
        products = products_data.get('resultList', [])
        
        print(f"Found {len(products)} products (Total available: {products_data.get('totalCount', 0)})")
        return products
    
    def process_cigar_products(self, raw_products, retailer_key, retailer_name):
        """Process raw CJ products into cigar-specific format"""
        processed_products = []
        
        for product in raw_products:
            try:
                # Extract basic info
                title = product.get('title', '')
                description = product.get('description', '')
                
                # Skip if not clearly a cigar product
                if not self._is_cigar_product(title, description):
                    continue
                
                # Parse cigar-specific attributes
                brand, line, wrapper, vitola, size = self._parse_cigar_attributes(title, description)
                
                # Get pricing
                price_obj = product.get('price', {})
                sale_price_obj = product.get('salePrice')
                
                price = float(price_obj.get('amount', 0)) if price_obj else 0.0
                sale_price = float(sale_price_obj.get('amount', 0)) if sale_price_obj else None
                
                # Use sale price if available and lower
                final_price = sale_price if sale_price and sale_price < price else price
                
                # Get affiliate URL
                link_code = product.get('linkCode', {})
                url = link_code.get('clickUrl', '') if link_code else ''
                
                # Check availability
                availability = product.get('availability', 'IN_STOCK')
                in_stock = availability == 'IN_STOCK'
                
                processed_product = {
                    'title': title,
                    'url': url,
                    'brand': brand,
                    'line': line,
                    'wrapper': wrapper,
                    'vitola': vitola,
                    'size': size,
                    'box_qty': self._extract_box_qty(title, description),
                    'price': final_price,
                    'in_stock': in_stock
                }
                
                processed_products.append(processed_product)
                
            except Exception as e:
                print(f"Error processing product: {e}")
                continue
        
        print(f"Processed {len(processed_products)} cigar products from {retailer_name}")
        return processed_products
    
    def _is_cigar_product(self, title, description):
        """Check if product is actually a cigar"""
        cigar_indicators = [
            'cigar', 'cigars', 'robusto', 'churchill', 'toro', 'corona',
            'maduro', 'connecticut', 'habano', 'torpedo', 'belicoso',
            'montecristo', 'cohiba', 'romeo', 'davidoff', 'arturo',
            'x 50', 'x 52', 'x 54', 'ring gauge'
        ]
        
        text = f"{title} {description}".lower()
        
        # Must contain at least one cigar indicator
        has_cigar_indicator = any(indicator in text for indicator in cigar_indicators)
        
        # Exclude non-cigar tobacco products
        exclusions = ['cigarette', 'pipe tobacco', 'chewing tobacco', 'snuff', 'vape', 'e-cig']
        has_exclusion = any(exclusion in text for exclusion in exclusions)
        
        return has_cigar_indicator and not has_exclusion
    
    def _parse_cigar_attributes(self, title, description):
        """Parse brand, line, wrapper, vitola, and size from product info"""
        text = f"{title} {description}"
        
        # Extract size (pattern like "6x50" or "6 x 50")
        size_match = re.search(r'(\d+\.?\d*\s*x\s*\d+)', text, re.IGNORECASE)
        size = size_match.group(1).strip() if size_match else ""
        
        # Extract wrapper types
        wrapper_patterns = [
            'Connecticut Shade', 'Connecticut Broadleaf', 'Connecticut',
            'Maduro', 'Habano', 'Natural', 'Oscuro', 'Cameroon', 
            'Corojo', 'Sumatra', 'Broadleaf', 'Claro', 'San Andres'
        ]
        wrapper = ""
        for pattern in wrapper_patterns:
            if pattern.lower() in text.lower():
                wrapper = pattern
                break
        
        # Extract vitola names
        vitola_patterns = [
            'Robusto', 'Churchill', 'Toro', 'Corona Extra', 'Corona',
            'Torpedo', 'Belicoso', 'Gordo', 'Presidente', 'Petit Corona',
            'Lancero', 'Perfecto', 'Petit Robusto', 'Double Corona',
            'Gran Toro', 'Short Robusto'
        ]
        vitola = ""
        for pattern in vitola_patterns:
            if pattern.lower() in text.lower():
                vitola = pattern
                break
        
        # Extract brand and line (first few words, refined)
        words = title.split()
        brand = words[0] if words else ""
        line = words[1] if len(words) > 1 else ""
        
        # Clean up brand/line if they contain size info
        if re.search(r'\d+x\d+', brand):
            brand = ""
        if re.search(r'\d+x\d+', line):
            line = ""
        
        return brand, line, wrapper, vitola, size
    
    def _extract_box_qty(self, title, description):
        """Extract box quantity from product info"""
        text = f"{title} {description}".lower()
        
        # Look for box quantities
        box_patterns = [
            r'box of (\d+)', r'(\d+) count', r'(\d+)ct', 
            r'(\d+)-pack', r'pack of (\d+)'
        ]
        
        for pattern in box_patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
        
        # Default quantities for common vitolas
        if 'single' in text or '1 cigar' in text:
            return 1
        elif 'sampler' in text:
            return 5
        else:
            return 25  # Standard box
    
    def save_to_csv(self, products, retailer_key):
        """Save products to CSV file in your existing format"""
        if not products:
            print(f"No products to save for {retailer_key}")
            return
        
        # Create data directory if it doesn't exist
        data_dir = Path("../static/data")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        filename = data_dir / f"{retailer_key}.csv"
        
        fieldnames = ['title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(products)
        
        print(f"Saved {len(products)} products to {filename}")
    
    def _make_request(self, query):
        """Make GraphQL request to CJ API"""
        try:
            payload = {"query": query}
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return None
    
    def update_all_retailer_data(self):
        """Main method to update all cigar retailer data"""
        print("Starting CJ API data collection...")
        print(f"Timestamp: {datetime.now()}")
        
        # Step 1: Find cigar retailers
        retailers = self.find_cigar_retailers()
        
        if not retailers:
            print("No cigar retailers found. Check your CJ partnerships.")
            return
        
        # Step 2: Process each retailer
        total_products = 0
        for retailer_key, retailer_info in retailers.items():
            try:
                print(f"\nProcessing {retailer_info['name']}...")
                
                # Get products from this retailer
                raw_products = self.get_products_from_retailer(
                    retailer_info['advertiser_id']
                )
                
                # Process into cigar-specific format
                processed_products = self.process_cigar_products(
                    raw_products, 
                    retailer_key, 
                    retailer_info['name']
                )
                
                # Save to CSV
                self.save_to_csv(processed_products, retailer_key)
                
                total_products += len(processed_products)
                
                # Rate limiting - be respectful
                time.sleep(2)
                
            except Exception as e:
                print(f"Error processing {retailer_info['name']}: {e}")
        
        print(f"\nData collection complete!")
        print(f"Total products collected: {total_products}")
        print(f"Retailers processed: {len(retailers)}")

def main():
    """Run the CJ API data collection"""
    # YOU NEED TO REPLACE THIS WITH YOUR ACTUAL TOKENYOUR_PERSONAL_ACCESS_TOKEN_HERE
    PERSONAL_ACCESS_TOKEN = "s64Z7FGpWmmCDbdHlfcweg-MZA"
    
    if PERSONAL_ACCESS_TOKEN == "YOUR_PERSONAL_ACCESS_TOKEN_HERE":
        print("Please set your Personal Access Token first!")
        print("1. Go to https://developers.cj.com/")
        print("2. Create a Personal Access Token")
        print("3. Replace 'YOUR_PERSONAL_ACCESS_TOKEN_HERE' in this script")
        return
    
    # Initialize CJ API client
    cj_client = CJProductFeedAPI(PERSONAL_ACCESS_TOKEN)
    
    # Run the data collection
    cj_client.update_all_retailer_data()

if __name__ == "__main__":
    main()
