#!/usr/bin/env python3
"""
CCCrafter.com Price Extractor
Extracts sale price, box quantity, and stock status from product pages
Rate limited to 1 request/second with 10 second timeout
"""

import requests
import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import csv
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CCCrafterExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.base_url = 'https://cccrafter.com'
        self.last_request_time = 0
        self.rate_limit_delay = 1.0  # 1 second between requests
        self.timeout = 10
        
    def _rate_limit(self):
        """Enforce 1 request per second rate limit"""
        time_since_last = time.time() - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def fetch_page(self, url):
        """Fetch a page with rate limiting and error handling"""
        self._rate_limit()
        
        try:
            logger.info(f"Fetching: {url}")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def extract_product_data(self, url):
        """Extract price, quantity, and stock data from a product page"""
        html = self.fetch_page(url)
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Debug: Save HTML to inspect structure
        debug_filename = f"debug_html_{url.split('/')[-2]}.html"
        with open(debug_filename, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.debug(f"Saved raw HTML to {debug_filename}")
        
        try:
            # Extract product title for context
            title_elem = soup.find('h1') or soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
            
            # Extract pricing information
            price_data = self._extract_price(soup)
            
            # Extract box quantity
            box_qty = self._extract_box_quantity(soup, title)
            
            # Extract stock status
            in_stock = self._extract_stock_status(soup)
            
            result = {
                'url': url,
                'title': title,
                'sale_price': price_data['sale_price'],
                'msrp_price': price_data['msrp_price'],
                'box_qty': box_qty,
                'in_stock': in_stock,
                'raw_price_text': price_data['raw_text']
            }
            
            logger.info(f"Extracted: {title} - ${price_data['sale_price']} (Box of {box_qty}) - {'In Stock' if in_stock else 'Out of Stock'}")
            return result
            
        except Exception as e:
            logger.error(f"Error extracting data from {url}: {e}")
            return None
    
    def _extract_price(self, soup):
        """Extract sale price and MSRP from WooCommerce pricing elements"""
        price_data = {
            'sale_price': None,
            'msrp_price': None,
            'raw_text': ''
        }
        
        # Method 1: Parse BCData JavaScript object (BigCommerce specific)
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'BCData' in script.string:
                script_text = script.string
                logger.debug("Found BCData script")
                
                # Extract the BCData JSON object
                bcdata_match = re.search(r'var BCData\s*=\s*({.*?});', script_text, re.DOTALL)
                if bcdata_match:
                    try:
                        import json
                        bcdata_json = bcdata_match.group(1)
                        bcdata = json.loads(bcdata_json)
                        
                        product_attrs = bcdata.get('product_attributes', {})
                        price_info = product_attrs.get('price', {})
                        
                        # Get MSRP from rrp_without_tax
                        rrp_info = price_info.get('rrp_without_tax', {})
                        if rrp_info.get('value'):
                            price_data['msrp_price'] = float(rrp_info['value'])
                            logger.debug(f"Found MSRP from BCData: ${price_data['msrp_price']}")
                        
                        # Get sale price from price_range.max (box price)
                        price_range = price_info.get('price_range', {})
                        max_price = price_range.get('max', {}).get('without_tax', {})
                        if max_price.get('value'):
                            price_data['sale_price'] = float(max_price['value'])
                            logger.debug(f"Found sale price from BCData: ${price_data['sale_price']}")
                        
                        # If no max price, try the base price
                        if not price_data['sale_price']:
                            base_price = price_info.get('without_tax', {})
                            if base_price.get('value'):
                                price_data['sale_price'] = float(base_price['value'])
                                logger.debug(f"Found base price from BCData: ${price_data['sale_price']}")
                        
                        price_data['raw_text'] = f"BCData: MSRP ${price_data['msrp_price']}, Sale ${price_data['sale_price']}"
                        
                        # If we found prices in BCData, return early
                        if price_data['sale_price']:
                            logger.debug(f"BCData extraction successful: Sale=${price_data['sale_price']}, MSRP=${price_data['msrp_price']}")
                            return price_data
                            
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.debug(f"Error parsing BCData: {e}")
                        continue
        
        # Method 2: Look for JavaScript/data attributes with pricing info
        # WooCommerce often stores variation pricing in data attributes
        variation_data = soup.find_all(['input', 'select', 'div'], attrs={'data-price': True})
        for elem in variation_data:
            data_price = elem.get('data-price')
            if data_price:
                try:
                    price = float(data_price)
                    if not price_data['sale_price'] or price < price_data['sale_price']:
                        price_data['sale_price'] = price
                    logger.debug(f"Found data-price: ${price}")
                except (ValueError, TypeError):
                    pass
        
        # Method 3: Look for variation pricing in script tags
        for script in scripts:
            if script.string:
                script_text = script.string
                # Look for WooCommerce variation data
                if 'variation_data' in script_text or 'product_variations' in script_text:
                    # Extract prices from JavaScript objects
                    price_matches = re.findall(r'"price":\s*"?(\d+(?:\.\d{2})?)"?', script_text)
                    if price_matches:
                        for price_str in price_matches:
                            try:
                                price = float(price_str)
                                if not price_data['sale_price'] or price < price_data['sale_price']:
                                    price_data['sale_price'] = price
                                logger.debug(f"Found script price: ${price}")
                            except ValueError:
                                pass
        
        # Method 4: Look for form variation options
        variation_forms = soup.find_all('form', class_='variations_form')
        for form in variation_forms:
            # Look for price display elements within variation forms
            price_elems = form.find_all(['span', 'div'], class_=lambda x: x and 'price' in x.lower())
            for elem in price_elems:
                price_text = elem.get_text(strip=True)
                if '$' in price_text:
                    prices = re.findall(r'\$\s*(\d+(?:\.\d{2})?)', price_text)
                    for price_str in prices:
                        try:
                            price = float(price_str)
                            if not price_data['sale_price'] or price < price_data['sale_price']:
                                price_data['sale_price'] = price
                            logger.debug(f"Found variation price: ${price}")
                        except ValueError:
                            pass
        
        # Method 5: Original price container logic (fallback)
        if not price_data['sale_price']:
            price_container = soup.find('p', class_='price') or soup.find('span', class_='price')
            
            if price_container:
                container_text = price_container.get_text(strip=True)
                price_data['raw_text'] = container_text
                logger.debug(f"Found price container with text: {container_text}")
                
                # Extract all price values from the container
                price_pattern = r'\$\s*(\d+(?:\.\d{2})?)'
                all_prices = re.findall(price_pattern, container_text)
                logger.debug(f"Found prices in container: {all_prices}")
                
                if len(all_prices) == 2:
                    # Two prices usually means MSRP and Sale price
                    price1, price2 = float(all_prices[0]), float(all_prices[1])
                    if price1 > price2:
                        price_data['msrp_price'] = price1
                        if not price_data['sale_price']:  # Don't override if we found a better one
                            price_data['sale_price'] = price2
                    else:
                        price_data['msrp_price'] = price2
                        if not price_data['sale_price']:
                            price_data['sale_price'] = price1
                elif len(all_prices) == 1:
                    single_price = float(all_prices[0])
                    
                    # Check if this looks like an MSRP (higher price) or sale price
                    container_html = str(price_container).lower()
                    
                    # If we already found a sale price and this is higher, it's probably MSRP
                    if price_data['sale_price'] and single_price > price_data['sale_price']:
                        price_data['msrp_price'] = single_price
                    elif 'del' in container_html or 'line-through' in container_html:
                        price_data['msrp_price'] = single_price
                    else:
                        # Default to sale price if we haven't found one yet
                        if not price_data['sale_price']:
                            price_data['sale_price'] = single_price
        
        logger.debug(f"Final price data: Sale=${price_data['sale_price']}, MSRP=${price_data['msrp_price']}")
        return price_data
    
    def _parse_price(self, price_text):
        """Parse price from text string"""
        if not price_text:
            return None
            
        # Remove common currency symbols and whitespace
        clean_text = re.sub(r'[^\d\.,]', '', price_text)
        
        # Extract price using regex
        price_match = re.search(r'(\d+(?:\.\d{2})?)', clean_text)
        if price_match:
            try:
                return float(price_match.group(1))
            except ValueError:
                return None
        return None
    
    def _extract_box_quantity(self, soup, title):
        """Extract box quantity from various sources"""
        # Method 1: Look for radio button options (like "Box of 25")
        radio_labels = soup.find_all('label')
        for label in radio_labels:
            text = label.get_text(strip=True)
            box_match = re.search(r'Box of (\d+)', text, re.IGNORECASE)
            if box_match:
                return int(box_match.group(1))
        
        # Method 2: Extract from title
        title_box_match = re.search(r'Box of (\d+)', title, re.IGNORECASE)
        if title_box_match:
            return int(title_box_match.group(1))
        
        # Method 3: Look in product specifications or description
        spec_areas = soup.find_all(['div', 'p', 'span'], class_=lambda x: x and ('spec' in x.lower() or 'detail' in x.lower()))
        for area in spec_areas:
            text = area.get_text(strip=True)
            box_match = re.search(r'(\d+)\s*(?:count|pc|piece|cigar)', text, re.IGNORECASE)
            if box_match:
                return int(box_match.group(1))
        
        # Method 4: Look for quantity in product meta
        quantity_selectors = [
            '[data-quantity]',
            '.quantity input[type="number"]',
            '.qty'
        ]
        
        for selector in quantity_selectors:
            elem = soup.select_one(selector)
            if elem:
                qty_value = elem.get('data-quantity') or elem.get('value') or elem.get('max')
                if qty_value and qty_value.isdigit():
                    qty = int(qty_value)
                    if qty > 1:  # Likely a box quantity
                        return qty
        
        # Default fallback
        logger.warning(f"Could not determine box quantity, defaulting to 25")
        return 25
    
    def _extract_stock_status(self, soup):
        """Determine if product is in stock"""
        
        # Method 1: Check BCData JavaScript object first (most reliable)
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'BCData' in script.string:
                script_text = script.string
                logger.debug("Found BCData script for stock check")
                
                # Extract the BCData JSON object
                bcdata_match = re.search(r'var BCData\s*=\s*({.*?});', script_text, re.DOTALL)
                if bcdata_match:
                    try:
                        import json
                        bcdata_json = bcdata_match.group(1)
                        bcdata = json.loads(bcdata_json)
                        
                        product_attrs = bcdata.get('product_attributes', {})
                        
                        # Check instock flag
                        instock = product_attrs.get('instock')
                        if instock is not None:
                            logger.debug(f"Found stock status in BCData: {instock}")
                            return bool(instock)
                        
                        # Check purchasable flag as backup
                        purchasable = product_attrs.get('purchasable')
                        if purchasable is not None:
                            logger.debug(f"Found purchasable status in BCData: {purchasable}")
                            return bool(purchasable)
                            
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.debug(f"Error parsing BCData for stock: {e}")
                        continue
        
        # Method 2: Check for meta property og:availability
        availability_meta = soup.find('meta', property='og:availability')
        if availability_meta:
            content = availability_meta.get('content', '').lower()
            logger.debug(f"Found og:availability meta: {content}")
            if content == 'instock':
                return True
            elif content in ['outofstock', 'out of stock']:
                return False
        
        # Method 3: Look for explicit "OUT OF STOCK" text in main product area only
        # Avoid false positives from related products
        product_main = soup.find('div', class_='productView') or soup.find('main') or soup.find('div', {'id': 'product'})
        
        out_of_stock_indicators = [
            'out of stock',
            'sold out',
            'unavailable',
            'not available'
        ]
        
        if product_main:
            main_text = product_main.get_text().lower()
            # Only check the main product area, not related products
            for indicator in out_of_stock_indicators:
                if indicator in main_text:
                    # Make sure it's not from related products by checking context
                    if 'related' not in main_text.split(indicator)[0][-100:]:
                        logger.debug(f"Found out of stock indicator in main product: {indicator}")
                        return False
        
        # Method 4: Check for "Add to Cart" button presence in main product area
        add_to_cart_selectors = [
            'button[name="add-to-cart"]',
            '.single_add_to_cart_button', 
            'button.add_to_cart_button',
            'input[type="submit"][value*="cart"]',
            '.btn-addtocart',
            'form[action*="cart"]'
        ]
        
        has_cart_button = False
        for selector in add_to_cart_selectors:
            elements = soup.select(selector)
            for elem in elements:
                # Make sure the button is in the main product area, not related products
                if not any(parent.get('class') and 'related' in ' '.join(parent.get('class', [])).lower() 
                          for parent in elem.find_parents()):
                    has_cart_button = True
                    logger.debug(f"Found add to cart button with selector: {selector}")
                    break
            if has_cart_button:
                break
        
        # Also look for button text directly in main product area
        if not has_cart_button and product_main:
            buttons = product_main.find_all('button')
            for button in buttons:
                button_text = button.get_text(strip=True).upper()
                if any(phrase in button_text for phrase in ['ADD TO CART', 'BUY NOW', 'PURCHASE']):
                    has_cart_button = True
                    logger.debug(f"Found add to cart button with text: {button_text}")
                    break
        
        # Method 5: Check availability field specifically in main product
        if product_main:
            availability_elem = product_main.find(string=re.compile(r'Availability:', re.IGNORECASE))
            if availability_elem:
                parent = availability_elem.parent
                if parent:
                    avail_text = parent.get_text().lower()
                    logger.debug(f"Found availability text: {avail_text}")
                    if any(indicator in avail_text for indicator in out_of_stock_indicators):
                        return False
                    elif 'in stock' in avail_text:
                        return True
        
        # Decision logic: if we have an add to cart button and no explicit out-of-stock indicators, assume in stock
        if has_cart_button:
            logger.debug("Has add to cart button, assuming in stock")
            return True
        else:
            logger.debug("No add to cart button found and no BCData, assuming out of stock")
            return False
    
    def extract_multiple_products(self, urls):
        """Extract data from multiple product URLs"""
        results = []
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Processing product {i}/{len(urls)}: {url}")
            
            product_data = self.extract_product_data(url)
            if product_data:
                results.append(product_data)
            else:
                logger.error(f"Failed to extract data from {url}")
        
        return results
    
    def save_to_csv(self, results, filename):
        """Save extracted data to CSV file"""
        if not results:
            logger.warning("No results to save")
            return
        
        fieldnames = ['url', 'title', 'sale_price', 'msrp_price', 'box_qty', 'in_stock', 'raw_price_text']
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                writer.writerow(result)
        
        logger.info(f"Saved {len(results)} results to {filename}")

def main():
    """Example usage"""
    extractor = CCCrafterExtractor()
    
    # Test URLs based on the screenshots
    test_urls = [
        'https://cccrafter.com/padron-1964-anniversary-diplomat-maduro-50-x-7-cigars/',
        'https://cccrafter.com/romeo-y-julieta-1875-lovers-sampler-box-of-6/'
    ]
    
    # Extract data
    results = extractor.extract_multiple_products(test_urls)
    
    # Print results
    for result in results:
        print(f"\nProduct: {result['title']}")
        print(f"URL: {result['url']}")
        print(f"Sale Price: ${result['sale_price']}")
        print(f"MSRP Price: ${result['msrp_price']}")
        print(f"Box Quantity: {result['box_qty']}")
        print(f"In Stock: {result['in_stock']}")
        print(f"Raw Price Text: {result['raw_price_text']}")
        print("-" * 50)
    
    # Save to CSV
    if results:
        extractor.save_to_csv(results, 'cccrafter_products.csv')

if __name__ == "__main__":
    main()
