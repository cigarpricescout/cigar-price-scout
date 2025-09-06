import requests
import json
import csv
import time
from datetime import datetime
import re
from pathlib import Path

class CigarRetailerCollector:
    def __init__(self, personal_access_token, company_id="7711335"):
        self.token = personal_access_token
        self.company_id = company_id
        self.base_url = "https://ads.api.cj.com/query"
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        # Known cigar retailers from your CJ applications
        self.cigar_retailers = {
            '5359174': {'name': 'Cigars International', 'key': 'ci'},
            '5815943': {'name': 'Cigora', 'key': 'cigora'},
            '6240744': {'name': 'Famous Smoke Shop', 'key': 'famous'},
            '7547384': {'name': 'FyreLux', 'key': 'fyrelux'},
            '3982297': {'name': 'Gotham Cigars', 'key': 'gothamcigars'},
            '2965991': {'name': 'Thompson Cigar', 'key': 'thompson'}
        }
    
    def check_partnership_status(self):
        """Check which cigar retailer partnerships are active"""
        print("Checking partnership status for cigar retailers...")
        
        query = f"""
        {{
            productFeeds(companyId: "{self.company_id}", limit: 100) {{
                resultList {{
                    advertiserId
                    advertiserName
                    productCount
                    adId
                }}
            }}
        }}
        """
        
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json={"query": query},
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"API Error: {response.status_code} - {response.text}")
                return {}
            
            data = response.json()
            if 'errors' in data:
                print(f"GraphQL errors: {data['errors']}")
                return {}
            
            feeds = data.get('data', {}).get('productFeeds', {}).get('resultList', [])
            
            active_retailers = {}
            
            print("\nPartnership Status:")
            print("-" * 50)
            
            for advertiser_id, info in self.cigar_retailers.items():
                found = False
                for feed in feeds:
                    if feed.get('advertiserId') == advertiser_id:
                        active_retailers[advertiser_id] = {
                            'name': info['name'],
                            'key': info['key'],
                            'ad_id': feed.get('adId'),
                            'product_count': feed.get('productCount', 0)
                        }
                        print(f"ACTIVE: {info['name']} - {feed.get('productCount', 0)} products")
                        found = True
                        break
                
                if not found:
                    print(f"PENDING: {info['name']} - Application pending approval")
            
            print(f"\nActive partnerships: {len(active_retailers)}")
            return active_retailers
            
        except Exception as e:
            print(f"Error checking partnerships: {e}")
            return {}
    
    def get_products_from_retailer(self, advertiser_id, retailer_name):
        """Get products from a specific retailer"""
        print(f"\nFetching products from {retailer_name}...")
        
        query = f"""
        {{
            products(companyId: "{self.company_id}", partnerIds: [{advertiser_id}], limit: 1000) {{
                totalCount
                count
                resultList {{
                    id
                    title
                    description
                    brand
                    price {{
                        amount
                        currency
                    }}
                    salePrice {{
                        amount
                        currency
                    }}
                    availability
                    linkCode(pid: "101532120") {{
                        clickUrl
                    }}
                }}
            }}
        }}
        """
        
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json={"query": query},
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"API Error: {response.status_code}")
                print(f"Response: {response.text}")
                return []
            
            data = response.json()
            
            if 'errors' in data:
                print(f"GraphQL errors: {data['errors']}")
                return []
            
            products_data = data.get('data', {}).get('products', {})
            products = products_data.get('resultList', [])
            total_count = products_data.get('totalCount', 0)
            
            print(f"Retrieved {len(products)} products (Total available: {total_count})")
            return products
            
        except Exception as e:
            print(f"Error fetching products: {e}")
            return []
    
    def process_cigar_products(self, raw_products, retailer_name):
        """Process products into cigar format"""
        processed_products = []
        
        for product in raw_products:
            try:
                title = product.get('title', '')
                description = product.get('description', '')
                
                # Basic cigar filtering
                if not self._is_cigar_product(title, description):
                    continue
                
                # Parse cigar attributes
                brand, line, wrapper, vitola, size = self._parse_cigar_attributes(title)
                
                # Get pricing
                price_obj = product.get('price', {})
                sale_price_obj = product.get('salePrice')
                
                price = float(price_obj.get('amount', 0)) if price_obj else 0.0
                sale_price = float(sale_price_obj.get('amount', 0)) if sale_price_obj else None
                
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
                    'box_qty': self._extract_box_qty(title),
                    'price': final_price,
                    'in_stock': in_stock
                }
                
                processed_products.append(processed_product)
                
            except Exception as e:
                print(f"Error processing product: {e}")
                continue
        
        print(f"Processed {len(processed_products)} cigar products")
        return processed_products
    
    def _is_cigar_product(self, title, description):
        """Check if product is a cigar"""
        text = f"{title} {description}".lower()
        
        cigar_indicators = [
            'cigar', 'cigars', 'robusto', 'churchill', 'toro', 'corona',
            'maduro', 'connecticut', 'habano', 'torpedo', 'belicoso'
        ]
        
        exclusions = ['cigarette', 'pipe tobacco', 'vape', 'e-cig', 'lighter', 'cutter', 'humidor']
        
        has_cigar = any(indicator in text for indicator in cigar_indicators)
        has_exclusion = any(exclusion in text for exclusion in exclusions)
        
        return has_cigar and not has_exclusion
    
    def _parse_cigar_attributes(self, title):
        """Parse cigar attributes from title"""
        # Extract size
        size_match = re.search(r'(\d+\.?\d*\s*x\s*\d+)', title, re.IGNORECASE)
        size = size_match.group(1).strip() if size_match else ""
        
        # Extract wrapper
        wrapper_patterns = ['Connecticut', 'Maduro', 'Habano', 'Natural', 'Cameroon', 'Corojo', 'Sumatra']
        wrapper = ""
        for pattern in wrapper_patterns:
            if pattern.lower() in title.lower():
                wrapper = pattern
                break
        
        # Extract vitola
        vitola_patterns = ['Robusto', 'Churchill', 'Toro', 'Corona', 'Torpedo', 'Belicoso', 'Gordo']
        vitola = ""
        for pattern in vitola_patterns:
            if pattern.lower() in title.lower():
                vitola = pattern
                break
        
        # Extract brand and line (first two words, refined)
        words = title.split()
        brand = words[0] if words else ""
        line = words[1] if len(words) > 1 else ""
        
        return brand, line, wrapper, vitola, size
    
    def _extract_box_qty(self, title):
        """Extract box quantity"""
        text = title.lower()
        
        box_patterns = [r'box of (\d+)', r'(\d+) count', r'(\d+)ct']
        for pattern in box_patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
        
        return 25  # Default
    
    def save_to_csv(self, products, retailer_key):
        """Save products to CSV"""
        if not products:
            print(f"No products to save for {retailer_key}")
            return
        
        data_dir = Path("static/data")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        filename = data_dir / f"{retailer_key}.csv"
        
        fieldnames = ['title', 'url', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty', 'price', 'in_stock']
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(products)
        
        print(f"Saved {len(products)} products to {filename}")
    
    def collect_all_data(self):
        """Main method to collect data from all active retailers"""
        print("Starting targeted cigar retailer data collection...")
        print(f"Timestamp: {datetime.now()}")
        
        # Check which partnerships are active
        active_retailers = self.check_partnership_status()
        
        if not active_retailers:
            print("\nNo active cigar retailer partnerships found.")
            print("Wait for your applications to be approved, then run this script again.")
            return
        
        # Collect data from each active retailer
        total_products = 0
        for advertiser_id, retailer_info in active_retailers.items():
            try:
                raw_products = self.get_products_from_retailer(advertiser_id, retailer_info['name'])
                
                if raw_products:
                    processed_products = self.process_cigar_products(raw_products, retailer_info['name'])
                    self.save_to_csv(processed_products, retailer_info['key'])
                    total_products += len(processed_products)
                
                time.sleep(2)  # Rate limiting
                
            except Exception as e:
                print(f"Error processing {retailer_info['name']}: {e}")
        
        print(f"\nData collection complete!")
        print(f"Total products collected: {total_products}")
        print(f"Active retailers processed: {len(active_retailers)}")

def main():
    # Replace with your actual token
    PERSONAL_ACCESS_TOKEN = "s64Z7FGpWmmCDbdHlfcweg-MZA"
    
    if PERSONAL_ACCESS_TOKEN == "YOUR_TOKEN_HERE":
        print("Please replace YOUR_TOKEN_HERE with your actual CJ Personal Access Token")
        return
    
    collector = CigarRetailerCollector(PERSONAL_ACCESS_TOKEN)
    collector.collect_all_data()

if __name__ == "__main__":
    main()
