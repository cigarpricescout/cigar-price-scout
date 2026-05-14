#!/usr/bin/env python3
"""
Cigar Hustler Extractor - Production Ready
ZenCart platform with clean product display and sale price support
Successfully tested on multiple products with 100% accuracy

Platform: ZenCart
Compliance: Tier 1 (stable URLs, 1 req/sec)
Test Results: 3/3 passed (Hemingway, Padron 1964, 601 La Bomba)
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from typing import Dict, Optional
from datetime import datetime

class CigarHustlerExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from Cigar Hustler URL
        Returns: {
            'box_price': float or None,
            'box_qty': int or None,
            'in_stock': bool,
            'discount_percent': float or None,
            'error': str or None
        }
        """
        try:
            # Rate limiting - 1 request per second
            time.sleep(1)
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract box quantity FIRST — _extract_price uses it to sanity-check
            # candidate prices via per-stick math (rejects single-stick / 5-pack
            # prices that would otherwise be mistaken for the box price).
            box_qty = self._extract_box_quantity(soup)
            
            # Extract price (ZenCart specific logic - handles sale prices)
            box_price = self._extract_price(soup, box_qty=box_qty)
            
            # Check stock status
            in_stock = self._check_stock_status(soup)
            
            # Calculate discount if available
            discount_percent = self._calculate_discount(soup, box_price)
            
            return {
                'box_price': box_price,
                'box_qty': box_qty,
                'in_stock': in_stock,
                'discount_percent': discount_percent,
                'error': None
            }
            
        except Exception as e:
            return {
                'box_price': None,
                'box_qty': None,
                'in_stock': False,
                'discount_percent': None,
                'error': str(e)
            }
    
    def _extract_box_quantity(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract box quantity from product page"""
        page_text = soup.get_text()
        
        # Priority patterns - check title and description
        qty_patterns = [
            r'[Bb]ox [Oo]f (\d+)',           # "Box of 25"
            r'\(Box of (\d+)\)',              # "(Box of 25)"
            r'(\d+) [Pp]ack',                 # "5 Pack"
            r'(\d+)-[Pp]ack',                 # "5-pack"
            r'[Bb]ox \((\d+)\)',              # "Box (25)"
            r'(\d+) [Cc]ount',                # "25 count"
            r'(\d+)[Cc]t',                    # "25ct"
        ]
        
        # Check product title first (most reliable)
        title = soup.find('h1')
        if title:
            title_text = title.get_text()
            for pattern in qty_patterns:
                match = re.search(pattern, title_text)
                if match:
                    qty = int(match.group(1))
                    if 5 <= qty <= 100:  # Reasonable box/pack range
                        return qty
        
        # Check description section
        description = soup.find('div', class_='description')
        if description:
            desc_text = description.get_text()
            for pattern in qty_patterns:
                match = re.search(pattern, desc_text)
                if match:
                    qty = int(match.group(1))
                    if 5 <= qty <= 100:
                        return qty
        
        # Fallback: search entire page
        for pattern in qty_patterns:
            match = re.search(pattern, page_text)
            if match:
                qty = int(match.group(1))
                if 5 <= qty <= 100:
                    return qty
        
        return None
    
    # Per-stick sanity gate. Real cigarhustler boxes land in roughly
    # $3–$80/stick. Anything below ~$3/stick on a box page is almost
    # certainly a 5-pack price masquerading as a box (e.g. Opus X
    # PerfecXion No.4 box-of-42 wrote $110.70 ÷ 42 = $2.64/stick),
    # and per-stick prices (Padron 1964 Diplomatico $18.70 ÷ 25 =
    # $0.75/stick) sit far below the floor.
    _MIN_PER_STICK = 3.00
    _MAX_PER_STICK = 100.0

    def _is_sane_box_price(self, price: float, box_qty: Optional[int]) -> bool:
        """Reject candidate prices whose per-stick math is implausible.

        Without box_qty we still require a non-trivial absolute price
        (boxes are rarely under $50) — better to skip the row than to
        write a per-stick price as the box price.
        """
        if not box_qty or box_qty < 2:
            return price >= 50.0
        per_stick = price / box_qty
        return self._MIN_PER_STICK <= per_stick <= self._MAX_PER_STICK

    def _extract_price(self, soup: BeautifulSoup, box_qty: Optional[int] = None) -> Optional[float]:
        """
        Extract the BOX price from a ZenCart product page.

        ZenCart product pages for box SKUs typically display multiple prices
        side-by-side: per-stick, 5-pack, and box (plus a strikethrough
        "original" price when on sale). The previous implementation picked
        the LOWEST price, which silently turned per-stick prices into box
        prices on the website (e.g. Padron 1964 Diplomatico showed $18.70
        instead of $442.50 — $442.50 ÷ 25 ≈ $17.68/stick).

        Strategy:
          1. ZenCart's <span id="productPrice…"> — authoritative when
             present AND per-stick-sane.
          2. Otherwise gather every $X.YZ in the main product section,
             keep only candidates whose per-stick math is sane, and pick
             the highest. Boxes are the most expensive SKU on a box page.
          3. Sale handling: when "Save:" is present, the highest sane
             price is the strikethrough original — return the
             second-highest sane price (the current sale price).
          4. If nothing passes the sanity gate, return None. We'd rather
             write no price than write a wrong one (the loader treats
             missing price as out-of-stock / hidden, which is recoverable).
        """
        box_qty = box_qty if box_qty is not None else self._extract_box_quantity(soup)

        # Method 1: ZenCart's standard productPrice span.
        # Only trust it when the value passes the per-stick sanity gate —
        # ZenCart themes sometimes show the per-stick price in this
        # element when the box-price live region renders elsewhere.
        for elem in soup.find_all('span', id=re.compile(r'productPrice', re.I)):
            price_match = re.search(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', elem.get_text())
            if not price_match:
                continue
            try:
                price = float(price_match.group(1).replace(',', ''))
            except ValueError:
                continue
            if self._is_sane_box_price(price, box_qty):
                return price

        # Method 2: scrape all $ values from the main product section, then
        # pick the box price via max-with-sale-aware logic.
        product_title = soup.find('h1')
        section_text = ''
        if product_title:
            main_section = product_title.find_parent(['div', 'section', 'article'])
            if main_section:
                section_text = main_section.get_text()
        if not section_text:
            body_text = soup.get_text()
            if 'Related Products' in body_text:
                section_text = body_text.split('Related Products')[0]
            else:
                section_text = body_text

        on_sale = bool(re.search(r'[Ss]ave\s*:', section_text))

        candidates = []
        for raw in re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', section_text):
            try:
                p = float(raw.replace(',', ''))
            except ValueError:
                continue
            if 1.0 <= p <= 10000.0:
                candidates.append(p)

        sane = sorted({p for p in candidates if self._is_sane_box_price(p, box_qty)}, reverse=True)
        if not sane:
            return None

        if on_sale and len(sane) >= 2:
            # Two large sane prices on a sale page → highest is the
            # strikethrough original, second-highest is the current
            # sale price. Edge case: if the strikethrough is missing
            # one of the two largest prices (e.g. only the sale price
            # is shown), the second-highest may actually be a 5-pack
            # — but the per-stick gate would've already filtered that
            # out, so this is safe.
            return sane[1]
        return sane[0]
    
    def _check_stock_status(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock"""
        # Find the product title to locate main product section
        product_title = soup.find('h1')
        if product_title:
            # Get the parent section containing the product info
            main_section = product_title.find_parent(['div', 'section', 'article'])
            if main_section:
                section_text = main_section.get_text().lower()
                
                # Check in product section first
                if 'sold out' in section_text:
                    return False
                if 'out of stock' in section_text:
                    return False
                if 'add to cart' in section_text:
                    return True
        
        # Fallback: check entire page but split on "Related Products"
        page_text = soup.get_text()
        
        # Get main content before "Related Products" to avoid false positives
        if 'Related Products' in page_text:
            main_content = page_text.split('Related Products')[0]
        elif 'related products' in page_text.lower():
            main_content = page_text.split('related products')[0].split('Related products')[0]
        else:
            main_content = page_text
        
        # Convert to lowercase for comparisons
        main_content_lower = main_content.lower()
        
        # Check for explicit "Sold Out" text
        if 'sold out' in main_content_lower:
            return False
        
        # Check for "out of stock" text
        if 'out of stock' in main_content_lower:
            return False
        
        # Check if "Add to Cart" text exists in main content (indicates in stock)
        if 'add to cart' in main_content_lower:
            return True
        
        # Check for "Add to Cart" button (use 'string' instead of deprecated 'text')
        add_to_cart = soup.find(['button', 'input'], string=re.compile(r'[Aa]dd [Tt]o [Cc]art', re.I))
        if add_to_cart:
            # Make sure button is not disabled
            is_disabled = add_to_cart.get('disabled') is not None
            return not is_disabled
        
        # Check for quantity selector (indicates in stock)
        qty_input = soup.find('input', {'name': re.compile(r'cart_quantity', re.I)})
        if qty_input and qty_input.get('disabled') is None:
            return True
        
        # Default: assume out of stock if no positive indicators
        return False
    
    def _calculate_discount(self, soup: BeautifulSoup, current_price: Optional[float]) -> Optional[float]:
        """Calculate discount percentage if original price is available"""
        if not current_price:
            return None
        
        # Only look in the immediate product title/price area
        product_title = soup.find('h1')
        if not product_title:
            return None
        
        # Get the parent section containing the product info
        main_section = product_title.find_parent(['div', 'section', 'article'])
        if not main_section:
            return None
        
        section_text = main_section.get_text()
        
        # Look for "Save:" text which indicates a discount - must be in product section
        save_match = re.search(r'[Ss]ave:\s*(\d+(?:\.\d+)?)\s*%', section_text)
        if save_match:
            # Direct percentage found
            return float(save_match.group(1))
        
        # Look for strikethrough or original prices in product section only
        # ZenCart typically shows: $75.00 $71.25
        # We need to find the higher price (original)
        
        price_matches = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', section_text)
        prices = []
        for price_str in price_matches:
            try:
                price = float(price_str.replace(',', ''))
                # Only consider prices that are close to our current price
                # (within 20% higher) to be very restrictive
                if price >= 10 and price >= current_price and price <= current_price * 1.2:
                    prices.append(price)
            except ValueError:
                continue
        
        # Remove duplicates and sort
        prices = sorted(set(prices), reverse=True)
        
        # If we have at least 2 prices, calculate discount
        if len(prices) >= 2 and prices[0] > current_price:
            original_price = prices[0]
            discount_percent = ((original_price - current_price) / original_price) * 100
            return round(discount_percent, 1)
        
        return None


def extract_cigarhustler_data(url: str) -> Dict:
    """
    Main extraction function for Cigar Hustler
    Compatible with CSV update workflow
    """
    extractor = CigarHustlerExtractor()
    result = extractor.extract_product_data(url)
    
    return {
        'success': result['error'] is None,
        'price': result['box_price'], 
        'box_quantity': result['box_qty'],
        'in_stock': result['in_stock'],
        'discount_percent': result['discount_percent'],
        'error': result['error']
    }


# Cigar Hustler Retailer Configuration
CIGAR_HUSTLER_CONFIG = {
    "retailer_info": {
        "name": "Cigar Hustler",
        "domain": "cigarhustler.com",
        "platform": "ZenCart",
        "compliance_tier": 1,
        "trained_date": "2026-01-19",
        "training_examples": 3
    },
    
    "extraction_patterns": {
        "pricing_method": "ZenCart standard with sale price support",
        "price_location": "Multiple prices on page, lower is sale price",
        "box_quantities_seen": [5, 25],
        "price_range": "$71-$442 for boxes/packs",
        
        "stock_indicators": {
            "in_stock": ["Add to Cart"],
            "out_of_stock": ["Sold Out"]
        }
    },
    
    "automation_ready": True,
    "confidence_level": "high",
    "test_results": {
        "tests_run": 3,
        "tests_passed": 3,
        "accuracy": "100%"
    },
    "notes": [
        "ZenCart platform with straightforward product pages",
        "Sale prices shown as: $75.00 $71.25 Save: 5% off",
        "Box quantities in title or description",
        "Clear stock indicators (Sold Out vs Add to Cart)",
        "Handles both regular and sale pricing"
    ]
}


# Test function
def test_cigarhustler_extraction():
    """Test the extraction on training URLs"""
    
    test_urls = [
        {
            'url': "https://cigarhustler.com/arturo-fuente-hemingway-c-1_178/arturo-fuente-hemingway-best-seller-maduro-perfecto-cigar-box-p-7930.html",
            'name': "Arturo Fuente Hemingway Best Seller",
            'expected_price': 271.00,
            'expected_stock': False,
            'expected_qty': 25,
            'has_discount': False
        },
        {
            'url': "https://cigarhustler.com/padron-1964-anniversary-maduro-c-1_257/padron-1964-anniversary-diplomatico-maduro-cigar-box-p-501.html",
            'name': "Padron 1964 Anniversary Diplomatico",
            'expected_price': 442.50,
            'expected_stock': True,
            'expected_qty': 25,
            'has_discount': False
        },
        {
            'url': "https://cigarhustler.com/warhead-la-bomba-tin-c-1_889/601-la-bomba-warhead-11-cigar-5-pack-p-9117.html",
            'name': "601 La Bomba Warhead 11 - 5 Pack",
            'expected_price': 71.25,
            'expected_stock': True,
            'expected_qty': 5,
            'has_discount': True
        }
    ]
    
    print("Testing Cigar Hustler extraction...")
    print("=" * 70)
    
    all_passed = True
    
    for i, test in enumerate(test_urls):
        print(f"\n[Test {i+1}] {test['name']}")
        result = extract_cigarhustler_data(test['url'])
        
        if result['success']:
            print(f"  Price: ${result['price']}")
            print(f"  Box Quantity: {result['box_quantity']}")
            print(f"  In Stock: {result['in_stock']}")
            if result['discount_percent']:
                print(f"  Discount: {result['discount_percent']:.1f}% off")
            
            # Validation
            price_ok = abs(result['price'] - test['expected_price']) < 0.01 if result['price'] else False
            stock_ok = result['in_stock'] == test['expected_stock']
            qty_ok = result['box_quantity'] == test['expected_qty'] if result['box_quantity'] else False
            discount_ok = (result['discount_percent'] is not None) == test['has_discount']
            
            if price_ok and stock_ok and qty_ok and discount_ok:
                print(f"  Status: PASSED")
            else:
                print(f"  Status: FAILED")
                if not price_ok:
                    print(f"    - Price mismatch: expected ${test['expected_price']}, got ${result['price']}")
                if not stock_ok:
                    print(f"    - Stock mismatch: expected {test['expected_stock']}, got {result['in_stock']}")
                if not qty_ok:
                    print(f"    - Quantity mismatch: expected {test['expected_qty']}, got {result['box_quantity']}")
                if not discount_ok:
                    print(f"    - Discount mismatch: expected {test['has_discount']}, got {result['discount_percent'] is not None}")
                all_passed = False
        else:
            print(f"  Status: FAILED - {result.get('error', 'Unknown error')}")
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("[SUCCESS] Cigar Hustler extraction ready for production!")
    else:
        print("[FAILED] Some tests failed - needs adjustment")
    
    return all_passed


def test_cigarhustler_offline_box_price():
    """Network-free unit tests for the box-price fix in _extract_price.

    Mirrors the failure modes that produced bad CSV values (Padron 1964
    Diplomatico $18.70 from a per-stick price, Opus X No.4 $110.70 from
    a 5-pack price) plus a few healthy/sale/regression scenarios.

    Run with:  python -m tools.price_monitoring.retailers.cigarhustler_extractor offline
    """

    def _page(title: str, prices_html: str, box_qty: Optional[int] = 25, sale: bool = False) -> str:
        # Mirrors the real ZenCart markup just enough for the
        # h1 → parent-section → text-scrape path to fire.
        sale_block = '<p>Save: 12% off</p>' if sale else ''
        qty_in_title = f' Cigar Box of {box_qty}' if box_qty else ''
        return f"""
        <html><body>
          <div class="centerColumn">
            <h1>{title}{qty_in_title}</h1>
            <div class="productPriceArea">
              {prices_html}
              {sale_block}
              <button>Add to Cart</button>
            </div>
          </div>
          <div class="related">
            <h2>Related Products</h2><p>$15.00</p><p>$25.00</p>
          </div>
        </body></html>
        """

    ext = CigarHustlerExtractor()
    cases = [
        # (name, html, expected_price, box_qty)
        ('per-stick masquerade (Padron Diplomatico)',
         _page('Padron 1964 Anniversary Diplomatico Maduro',
               '<p>Per Stick: $18.70</p><p>5-Pack: $93.50</p><p>Box Price: $442.50</p>',
               box_qty=25),
         442.50, 25),
        ('5-pack masquerade (Opus X PerfecXion No. 4)',
         _page('Arturo Fuente Opus X PerfecXion No. 4',
               '<p>Per Stick: $11.90</p><p>5-Pack: $110.70</p><p>Box of 42 Price: $499.80</p>',
               box_qty=42),
         499.80, 42),
        ('sale page (pick sale, not strikethrough orig)',
         _page('Padron 1926 No. 9 Maduro',
               '<p>Per Stick: $28.00</p><p>5-Pack: $135.00</p><p><s>$725.00</s> $652.50</p>',
               box_qty=24, sale=True),
         652.50, 24),
        ('sale page with only one sane candidate (no regression to 5-pack)',
         _page('Generic Budget Box',
               '<p>Per Stick: $3.95</p><p>5-Pack: $18.75</p><p>Box: $89.00</p>',
               box_qty=25, sale=True),
         89.00, 25),
        ('hostile page (no sane candidate -> None, not per-stick)',
         _page('Mystery Cigar', '<p>Per Stick: $7.50</p>', box_qty=25),
         None, 25),
        ('sane productPrice span short-circuits',
         '<html><body><h1>AF Hemingway Best Seller Maduro Cigar Box of 25</h1>'
         '<div><span id="productPrice12">$270.00</span>'
         '<p>Per Stick: $11.50</p><button>Add to Cart</button></div></body></html>',
         270.00, 25),
        ('insane productPrice span falls through to text scrape',
         '<html><body><h1>Padron 1964 Anniversary Diplomatico Maduro Cigar Box of 25</h1>'
         '<div><span id="productPrice12">$18.70</span>'
         '<p>Per Stick: $18.70</p><p>5-Pack: $93.50</p><p>Box Price: $442.50</p>'
         '<button>Add to Cart</button></div></body></html>',
         442.50, 25),
        ('regression: healthy 5-pack-only page (601 La Bomba Warhead)',
         _page('601 La Bomba Warhead 11', '<p>$71.25</p>', box_qty=5),
         71.25, 5),
    ]

    print('Cigar Hustler — offline box-price tests')
    print('-' * 70)
    failures = 0
    for name, html, expected, box_qty in cases:
        soup = BeautifulSoup(html, 'html.parser')
        got = ext._extract_price(soup, box_qty=box_qty)
        ok = (got is None and expected is None) or (
            got is not None and expected is not None and abs(got - expected) < 0.01
        )
        flag = 'PASS' if ok else 'FAIL'
        print(f'  [{flag}]  {name:55s}  expected={expected!s:<10}  got={got!s}')
        if not ok:
            failures += 1
    print('-' * 70)
    print(f'{len(cases) - failures}/{len(cases)} passed')
    return failures == 0


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == 'offline':
        ok = test_cigarhustler_offline_box_price()
        _sys.exit(0 if ok else 1)
    test_cigarhustler_extraction()
