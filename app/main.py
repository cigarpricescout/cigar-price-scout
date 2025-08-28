from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import csv
import json
import time
from datetime import date

# Import your working shipping/tax functions
try:
    from app.shipping_tax import zip_to_state, estimate_shipping_cents, estimate_tax_cents
except Exception:
    # Fallback functions if shipping_tax.py is missing
    def zip_to_state(zip_code):
        if not zip_code:
            return 'OR'
        first_digit = str(zip_code)[0] if zip_code else '9'
        states = {'0': 'MA', '1': 'NY', '2': 'VA', '3': 'FL', '4': 'OH', '5': 'MN', '6': 'IL', '7': 'TX', '8': 'CO', '9': 'CA'}
        return states.get(first_digit, 'OR')

    def estimate_shipping_cents(base_cents, retailer_key, state=None):
        if retailer_key == 'famous':
            return 999
        elif retailer_key == 'ci':
            return 895
        else:
            return 999

    def estimate_tax_cents(base_cents, state):
        if not state:
            return 0
        rates = {'CA': 0.08, 'NY': 0.08, 'TX': 0.06, 'FL': 0.06, 'OR': 0.0}
        return int(base_cents * rates.get(state, 0.05))

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Your working retailer list
RETAILERS = [
    {"key": "famous", "name": "Famous Smoke Shop", "csv": "static/data/famous.csv"},
    {"key": "ci", "name": "Cigars International", "csv": "static/data/ci.csv"},
    {"key": "jr", "name": "JR Cigar", "csv": "static/data/jr.csv"},
    {"key": "thompson", "name": "Thompson Cigar", "csv": "static/data/thompson.csv"},
    {"key": "atlantic", "name": "Atlantic Cigar", "csv": "static/data/atlantic.csv"},
    {"key": "neptune", "name": "Neptune Cigar", "csv": "static/data/neptune.csv"},
    {"key": "bestcigar", "name": "Best Cigar Prices", "csv": "static/data/bestcigar.csv"},
    {"key": "corona", "name": "Corona Cigar", "csv": "static/data/corona.csv"},
    {"key": "cigarcountry", "name": "Cigar Country", "csv": "static/data/cigarcountry.csv"},
    {"key": "oldhavana", "name": "Old Havana Cigar Co.", "csv": "static/data/oldhavana.csv"},
    {"key": "nickscigarworld", "name": "Nick's Cigar World", "csv": "static/data/nickscigarworld.csv"},
    {"key": "cigarboxpa", "name": "Cigar Box PA", "csv": "static/data/cigarboxpa.csv"},
    {"key": "tampasweethearts", "name": "Tampa Sweethearts", "csv": "static/data/tampasweethearts.csv"},
    {"key": "cdmcigars", "name": "CDM Cigars", "csv": "static/data/cdmcigars.csv"},
    {"key": "smokeinn", "name": "Smoke Inn", "csv": "static/data/smokeinn.csv"},
    {"key": "holts", "name": "Holt's Cigar Company", "csv": "static/data/holts.csv"},
    {"key": "cuencacigars", "name": "Cuenca Cigars", "csv": "static/data/cuencacigars.csv"},
    {"key": "thecigarshop", "name": "The Cigar Shop", "csv": "static/data/thecigarshop.csv"},
    {"key": "cigarhustler", "name": "Cigar Hustler", "csv": "static/data/cigarhustler.csv"},
    {"key": "cigarplace", "name": "Cigar Place", "csv": "static/data/cigarplace.csv"},
    {"key": "tobaccolocker", "name": "Tobacco Locker", "csv": "static/data/tobaccolocker.csv"},
    {"key": "thecigarstore", "name": "The Cigar Store", "csv": "static/data/thecigarstore.csv"},
    {"key": "mikescigars", "name": "Mike's Cigars", "csv": "static/data/mikescigars.csv"},
    {"key": "bonitasmokeshop", "name": "Bonita Smoke Shop", "csv": "static/data/bonitasmokeshop.csv"},
    {"key": "windycitycigars", "name": "Windy City Cigars", "csv": "static/data/windycitycigars.csv"},
    {"key": "absolutecigars", "name": "Absolute Cigars", "csv": "static/data/absolutecigars.csv"},
    {"key": "cubancrafters", "name": "Cuban Crafters", "csv": "static/data/cubancrafters.csv"},
    {"key": "cigar", "name": "Cigar.com", "csv": "static/data/cigar.csv"},
    {"key": "pipesandcigars", "name": "Pipes and Cigars", "csv": "static/data/pipesandcigars.csv"},
    {"key": "planetcigars", "name": "Planet Cigars", "csv": "static/data/planetcigars.csv"},
    {"key": "smallbatchcigar", "name": "Small Batch Cigar", "csv": "static/data/smallbatchcigar.csv"},
    {"key": "niceashcigars", "name": "Nice Ash Cigars", "csv": "static/data/niceashcigars.csv"},
    {"key": "cigarsdirect", "name": "Cigars Direct", "csv": "static/data/cigarsdirect.csv"},
    {"key": "secretocigarbar", "name": "Secreto Cigar Bar", "csv": "static/data/secretocigarbar.csv"},
    {"key": "momscigars", "name": "Mom's Cigars", "csv": "static/data/momscigars.csv"},
    {"key": "bighumidor", "name": "Big Humidor", "csv": "static/data/bighumidor.csv"},
]

# Simple CSV loader
class Product:
    def __init__(self, retailer_key, retailer_name, title, url, brand, line, size, box_qty, price, in_stock=True):
        self.retailer_key = retailer_key
        self.retailer_name = retailer_name
        self.title = title
        self.url = url
        self.brand = brand
        self.line = line
        self.size = size
        self.box_qty = int(box_qty) if box_qty else 25
        self.price_cents = int(float(price) * 100) if price else 0
        self.in_stock = str(in_stock).lower() not in ('false', '0', 'no', '')

def load_csv(csv_path, retailer_key, retailer_name):
    """Load products from a CSV file"""
    items = []
    csv_file = Path(csv_path)

    if not csv_file.exists():
        return items

    try:
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    product = Product(
                        retailer_key=retailer_key,
                        retailer_name=retailer_name,
                        title=row.get('title', ''),
                        url=row.get('url', ''),
                        brand=row.get('brand', ''),
                        line=row.get('line', ''),
                        size=row.get('size', ''),
                        box_qty=row.get('box_qty', 25),
                        price=row.get('price', 0),
                        in_stock=row.get('in_stock', True)
                    )
                    if product.brand and product.line and product.size:
                        items.append(product)
                except Exception as e:
                    continue
    except Exception as e:
        print(f"Error loading {csv_path}: {e}")

    return items

def load_all_products():
    """Load all products from all retailer CSV files"""
    all_products = []
    for retailer in RETAILERS:
        products = load_csv(retailer["csv"], retailer["key"], retailer["name"])
        all_products.extend(products)
    return all_products

def build_options_tree():
    """Build the brand -> line -> sizes tree for dropdowns"""
    products = load_all_products()
    tree = {}

    for product in products:
        if not product.brand:
            continue

        # Initialize brand if not exists
        if product.brand not in tree:
            tree[product.brand] = {}

        # Initialize line if not exists
        if product.line not in tree[product.brand]:
            tree[product.brand][product.line] = set()

        # Add size
        tree[product.brand][product.line].add(product.size)

    # Convert to the format expected by frontend
    brands = []
    for brand_name in sorted(tree.keys()):
        lines = []
        for line_name in sorted(tree[brand_name].keys()):
            sizes = sorted(list(tree[brand_name][line_name]))
            lines.append({
                "line": line_name,
                "sizes": sizes
            })
        brands.append({
            "brand": brand_name,
            "lines": lines
        })

    return brands

# Routes
@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/options")
def options():
    """Return brand -> line -> sizes tree for dropdowns"""
    return {"brands": build_options_tree()}

@app.get("/compare")
def compare(
    brand: str = Query(...),
    line: str = Query(...),
    size: str = Query(...),
    zip: str = Query("", description="ZIP code for shipping/tax estimates"),
):
    """Compare prices for a specific cigar across all retailers"""

    # Get state from ZIP for shipping/tax calculations
    state = zip_to_state(zip) if zip else 'OR'

    # Load all products and filter by criteria
    all_products = load_all_products()
    matching_products = [
        p for p in all_products 
        if (p.brand.lower() == brand.lower() and 
            p.line.lower() == line.lower() and 
            p.size.lower() == size.lower())
    ]

    if not matching_products:
        return {
            "brand": brand,
            "line": line,
            "size": size,
            "state": state,
            "results": []
        }

    # Calculate delivered prices and build results
    results = []
    in_stock_prices = []

    for product in matching_products:
        # Calculate costs
        base_cents = product.price_cents
        shipping_cents = estimate_shipping_cents(base_cents, product.retailer_key, state)
        tax_cents = estimate_tax_cents(base_cents, state)
        delivered_cents = base_cents + shipping_cents + tax_cents

        # Track in-stock prices for determining cheapest
        if product.in_stock:
            in_stock_prices.append(delivered_cents)

        # Build result entry
        result = {
            "retailer": product.retailer_name,
            "base": f"${base_cents/100:.2f}",
            "shipping": f"${shipping_cents/100:.2f}",
            "tax": f"${tax_cents/100:.2f}",
            "delivered": f"${delivered_cents/100:.2f}",
            "promo": None,
            "promo_code": None,
            "delivered_after_promo": f"${delivered_cents/100:.2f}",
            "url": product.url,
            "oos": not product.in_stock,
            "cheapest": False  # Will be set below
        }
        results.append(result)

    # Mark the cheapest in-stock option
    if in_stock_prices:
        cheapest_price = min(in_stock_prices)
        for result in results:
            if not result["oos"]:
                delivered_price = float(result["delivered_after_promo"].replace("$", ""))
                if abs(delivered_price - cheapest_price/100) < 0.01:
                    result["cheapest"] = True
                    break

    # Sort results: in-stock first, then by price
    results.sort(key=lambda r: (r["oos"], float(r["delivered_after_promo"].replace("$", ""))))

    return {
        "brand": brand,
        "line": line,
        "size": size,
        "state": state,
        "results": results
    }

# Legal page routes
@app.get("/about.html")
async def about():
    return FileResponse("static/about.html")

@app.get("/privacy-policy.html") 
async def privacy_policy():
    return FileResponse("static/privacy-policy.html")

@app.get("/terms-of-service.html")
async def terms_of_service():
    return FileResponse("static/terms-of-service.html")

@app.get("/contact.html")
async def contact():
    return FileResponse("static/contact.html")