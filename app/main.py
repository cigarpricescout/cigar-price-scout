from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import csv
from typing import Optional

# Import your working shipping/tax functions
try:
    from shipping_tax import zip_to_state, estimate_shipping_cents, estimate_tax_cents
except Exception:
    # Fallback functions if shipping_tax.py is missing
    def zip_to_state(zip_code):
        if not zip_code:
            return 'OR'
        zip_str = str(zip_code)
        if zip_str.startswith('19'):
            return 'PA'
        elif zip_str.startswith('90'):
            return 'CA'
        else:
            first_digit = zip_str[0]
            states = {'0': 'MA', '1': 'NY', '2': 'VA', '3': 'FL', '4': 'OH', '5': 'MN', '6': 'IL', '7': 'TX', '8': 'CO', '9': 'CA'}
            return states.get(first_digit, 'OR')
    
    def estimate_shipping_cents(base_cents, retailer_key, state=None):
        base_dollars = base_cents / 100
    
        # Free shipping thresholds
        if retailer_key == 'smallbatchcigar':
            return 0  # Always free
        elif retailer_key == 'atlantic' and base_dollars >= 99:
            return 0
        elif retailer_key == 'bestcigar' and base_dollars >= 99:
            return 0
        elif retailer_key == 'bonitasmokeshop' and base_dollars >= 150:
            return 0
        elif retailer_key == 'casademontecristo' and base_dollars >= 200:
            return 0
        elif retailer_key == 'cccrafter' and base_dollars >= 100:
            return 0
        elif retailer_key == 'cdmcigars' and base_dollars >= 100:
            return 0
        elif retailer_key == 'cigar' and base_dollars >= 150:
            return 0
        elif retailer_key == 'cigarboxpa' and base_dollars >= 175:
            return 0
        elif retailer_key == 'cigarcountry' and base_dollars >= 150:
            return 0
        elif retailer_key == 'cigarking' and base_dollars >= 150:
            return 0
        elif retailer_key == 'cigarsdirect' and base_dollars >= 99:
            return 0
        elif retailer_key == 'corona' and base_dollars >= 125:
            return 0
        elif retailer_key == 'cubancrafters' and base_dollars >= 100:
            return 0
        elif retailer_key == 'cuencacigars' and base_dollars >= 99:
            return 0
        elif retailer_key == 'holts' and base_dollars >= 150:
            return 0
        elif retailer_key == 'lmcigars' and base_dollars >= 100:
            return 0
        elif retailer_key == 'neptune' and base_dollars >= 99:
            return 0
        elif retailer_key == 'niceashcigars':
            return 0
        elif retailer_key == 'pipesandcigars' and base_dollars >= 99:
            return 0
        elif retailer_key == 'planetcigars' and base_dollars >= 200:
            return 0
        elif retailer_key == 'tampasweethearts' and base_dollars >= 200:
            return 0
        elif retailer_key == 'thecigarshop' and base_dollars >= 100:
            return 0
        elif retailer_key == 'thecigarstore' and base_dollars >= 75:
            return 0
        elif retailer_key == 'thompson' and base_dollars >= 125:
            return 0
        elif retailer_key == 'watchcity' and base_dollars >= 99.99:
            return 0
        
        # Flat rate shipping
        elif retailer_key == 'cigarpairingparlor':
            return 995  # $9.95
        elif retailer_key == 'smokeinn':
            return 995  # $9.95
        
        # Standard rates
        elif retailer_key == 'famous':
            return 999
        elif retailer_key == 'ci':
            return 895
        else:
            return 999
    
    def estimate_tax_cents(taxable_amount_cents, retailer_key, state):
        # Retailer nexus - states where they charge tax
        retailer_nexus = {
            'abcfws': ['FL'],
            'absolutecigars': ['VA'],
            'atlantic': ['PA'],
            'bestcigar': ['PA'],
            'bighumidor': ['DE'],
            'bonitasmokeshop': ['FL'],
            'casademontecristo': ['FL','IL','NV','TN','TX','DC','NJ','NC'],
            'cccrafter': ['FL'],
            'cdmcigars': ['CA'],
            'ci': ['PA','TX','FL','AZ'],
            'cigar': ['PA'],
            'cigarboxpa': ['PA'],
            'cigarcellarofmiami': ['FL'],
            'cigarhustler': ['FL'],
            'cigarking': ['AZ'],
            'cigarplace': ['FL'],
            'cigarsdirect': ['FL'],
            'corona': ['FL'],
            'cubancrafters': ['FL'],
            'cuencacigars': ['FL'],
            'famous': ['PA'],
            'hilands': ['AZ'],
            'holts': ['PA'],
            'jr': ['NC','NJ'],
            'lmcigars': ['FL'],
            'mikescigars': ['FL'],
            'momscigars': ['VA'],
            'neptune': ['FL'],
            'niceashcigars': ['NY','PA'],
            'nickscigarworld': ['SC'],
            'oldhavana': ['OH'],
            'pipesandcigars': ['PA'],
            'planetcigars': ['FL'],
            'santamonicacigars': ['CA'],
            'secretocigarbar': ['MI'],
            'smallbatchcigar': ['CA'],
            'smokeinn': ['FL'],
            'tampasweethearts': ['FL'],
            'thecigarshop': ['SC','NC'],
            'thecigarstore': ['CA'],
            'thompson': ['PA'],
            'tobaccolocker': ['FL'],
            'twoguys': ['NH'],
            'watchcity': ['MA'],
            'windycitycigars': ['IL'],
            'buitragocigars': ['FL'],
            'cheaplittlecigars': ['SC'],
            'cigaroasis': ['NY'],
            'cigarpage': ['PA'],
            'escobarcigars': ['FL'],
            'gothamcigars': ['FL'],
            'cigarpairingparlor': ['WA'],
        }
        
        # Load tax rates
        rates = {
            'PA': 0.08, 'FL': 0.07, 'TX': 0.082, 'AZ': 0.084, 'NC': 0.07, 'NJ': 0.066, 
            'SC': 0.073, 'NY': 0.086, 'WA': 0.092, 'IL': 0.089, 'NV': 0.0825, 'TN': 0.07,
            'DC': 0.06, 'VA': 0.057, 'DE': 0.0, 'OH': 0.0725, 'MI': 0.06, 'MA': 0.0625,
            'CA': 0.0825, 'NH': 0.0
    }
        
        # Only charge tax if customer is in a state where retailer has nexus
        if  retailer_key in retailer_nexus and state in retailer_nexus[retailer_key]:
            return int(taxable_amount_cents * rates.get(state, 0))
    
            return 0

app = FastAPI()
app.mount("/static", StaticFiles(directory="../static"), name="static")

RETAILERS = [
    {"key": "abcfws", "name": "ABC Fine Wine & Spirits", "csv": "../static/data/abcfws.csv", "authorized": False},
    {"key": "absolutecigars", "name": "Absolute Cigars", "csv": "../static/data/absolutecigars.csv", "authorized": False},
    {"key": "atlantic", "name": "Atlantic Cigar", "csv": "../static/data/atlantic.csv", "authorized": False},
    {"key": "bestcigar", "name": "Best Cigar Prices", "csv": "../static/data/bestcigar.csv", "authorized": True},
    {"key": "bighumidor", "name": "Big Humidor", "csv": "../static/data/bighumidor.csv", "authorized": False},
    {"key": "bonitasmokeshop", "name": "Bonita Smoke Shop", "csv": "../static/data/bonitasmokeshop.csv", "authorized": False},
    {"key": "buitragocigars", "name": "Buitrago Cigars", "csv": "../static/data/buitragocigars.csv", "authorized": True},
    {"key": "casademontecristo", "name": "Casa de Montecristo", "csv": "../static/data/casademontecristo.csv", "authorized": False},
    {"key": "cccrafter", "name": "CC Crafter", "csv": "../static/data/cccrafter.csv", "authorized": False},
    {"key": "cdmcigars", "name": "CDM Cigars", "csv": "../static/data/cdmcigars.csv", "authorized": False},
    {"key": "cheaplittlecigars", "name": "Cheap Little Cigars", "csv": "../static/data/cheaplittlecigars.csv", "authorized": True},
    {"key": "ci", "name": "Cigars International", "csv": "../static/data/ci.csv", "authorized": True},
    {"key": "cigar", "name": "Cigar.com", "csv": "../static/data/cigar.csv", "authorized": True},
    {"key": "cigarboxpa", "name": "Cigar Box PA", "csv": "../static/data/cigarboxpa.csv", "authorized": False},
    {"key": "cigarcellarofmiami", "name": "Cigar Cellar of Miami", "csv": "../static/data/cigarcellarofmiami.csv", "authorized": False},
    {"key": "cigarcountry", "name": "Cigar Country", "csv": "../static/data/cigarcountry.csv", "authorized": False},
    {"key": "cigarhustler", "name": "Cigar Hustler", "csv": "../static/data/cigarhustler.csv", "authorized": False},
    {"key": "cigarking", "name": "Cigar King", "csv": "../static/data/cigarking.csv", "authorized": False},    
    {"key": "cigaroasis", "name": "Cigar Oasis", "csv": "../static/data/cigaroasis.csv", "authorized": True},
    {"key": "cigarpage", "name": "Cigar Page", "csv": "../static/data/cigarpage.csv", "authorized": True},
    {"key": "cigarpairingparlor", "name": "The Cigar Pairing Parlor LLC", "csv": "../static/data/cigarpairingparlor.csv", "authorized": True},
    {"key": "cigarplace", "name": "Cigar Place", "csv": "../static/data/cigarplace.csv", "authorized": False},
    {"key": "cigarsdirect", "name": "Cigars Direct", "csv": "../static/data/cigarsdirect.csv", "authorized": False},
    {"key": "corona", "name": "Corona Cigar", "csv": "../static/data/corona.csv", "authorized": False},
    {"key": "cubancrafters", "name": "Cuban Crafters", "csv": "../static/data/cubancrafters.csv", "authorized": False},
    {"key": "cuencacigars", "name": "Cuenca Cigars", "csv": "../static/data/cuencacigars.csv", "authorized": False},
    {"key": "escobarcigars", "name": "Escobar Cigars", "csv": "../static/data/escobarcigars.csv", "authorized": True},
    {"key": "famous", "name": "Famous Smoke Shop", "csv": "../static/data/famous.csv", "authorized": True},
    {"key": "gothamcigars", "name": "Gotham Cigars", "csv": "../static/data/gothamcigars.csv", "authorized": True},
    {"key": "hilands", "name": "Hiland's Cigars", "csv": "../static/data/hilands.csv", "authorized": False},
    {"key": "holts", "name": "Holt's Cigar Company", "csv": "../static/data/holts.csv", "authorized": False},
    {"key": "jr", "name": "JR Cigar", "csv": "../static/data/jr.csv", "authorized": True},
    {"key": "lmcigars", "name": "LM Cigars", "csv": "../static/data/lmcigars.csv", "authorized": False},
    {"key": "mikescigars", "name": "Mike's Cigars", "csv": "../static/data/mikescigars.csv", "authorized": True},
    {"key": "momscigars", "name": "Mom's Cigars", "csv": "../static/data/momscigars.csv", "authorized": False},
    {"key": "neptune", "name": "Neptune Cigar", "csv": "../static/data/neptune.csv", "authorized": False},
    {"key": "niceashcigars", "name": "Nice Ash Cigars", "csv": "../static/data/niceashcigars.csv", "authorized": False},
    {"key": "nickscigarworld", "name": "Nick's Cigar World", "csv": "../static/data/nickscigarworld.csv", "authorized": False},
    {"key": "oldhavana", "name": "Old Havana Cigar Co.", "csv": "../static/data/oldhavana.csv", "authorized": False},
    {"key": "pipesandcigars", "name": "Pipes and Cigars", "csv": "../static/data/pipesandcigars.csv", "authorized": False},
    {"key": "planetcigars", "name": "Planet Cigars", "csv": "../static/data/planetcigars.csv", "authorized": False},
    {"key": "santamonicacigars", "name": "Santa Monica Cigars", "csv": "../static/data/santamonicacigars.csv", "authorized": False},
    {"key": "secretocigarbar", "name": "Secreto Cigar Bar", "csv": "../static/data/secretocigarbar.csv", "authorized": False},
    {"key": "smallbatchcigar", "name": "Small Batch Cigar", "csv": "../static/data/smallbatchcigar.csv", "authorized": False},
    {"key": "smokeinn", "name": "Smoke Inn", "csv": "../static/data/smokeinn.csv", "authorized": False},
    {"key": "tampasweethearts", "name": "Tampa Sweethearts", "csv": "../static/data/tampasweethearts.csv", "authorized": False},
    {"key": "thecigarshop", "name": "The Cigar Shop", "csv": "../static/data/thecigarshop.csv", "authorized": False},
    {"key": "thecigarstore", "name": "The Cigar Store", "csv": "../static/data/thecigarstore.csv", "authorized": False},
    {"key": "thompson", "name": "Thompson Cigar", "csv": "../static/data/thompson.csv", "authorized": True},
    {"key": "tobaccolocker", "name": "Tobacco Locker", "csv": "../static/data/tobaccolocker.csv", "authorized": False},
    {"key": "twoguys", "name": "Two Guys Smoke Shop", "csv": "../static/data/twoguys.csv", "authorized": False},
    {"key": "watchcity", "name": "Watch City Cigar", "csv": "../static/data/watchcity.csv", "authorized": False},
    {"key": "windycitycigars", "name": "Windy City Cigars", "csv": "../static/data/windycitycigars.csv", "authorized": False},
]

# Enhanced CSV loader with wrapper and vitola support
class Product:
    def __init__(self, retailer_key, retailer_name, title, url, brand, line, wrapper, vitola, size, box_qty, price, in_stock=True):
        self.retailer_key = retailer_key
        self.retailer_name = retailer_name
        self.title = title
        self.url = url
        self.brand = brand
        self.line = line
        self.wrapper = wrapper
        self.vitola = vitola
        self.size = size
        self.box_qty = int(box_qty) if box_qty else 25
        self.price_cents = int(float(price) * 100) if price else 0
        self.in_stock = str(in_stock).lower() not in ('false', '0', 'no', '')

def load_csv(csv_path, retailer_key, retailer_name):
    """Load products from a CSV file with enhanced format"""
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
                        wrapper=row.get('wrapper', ''),
                        vitola=row.get('vitola', ''),
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
    """Build the brand -> line -> wrapper -> vitola/size tree for dropdowns"""
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
            tree[product.brand][product.line] = {}
        
        # Initialize wrapper if not exists (allow empty wrapper)
        wrapper_key = product.wrapper or "No Wrapper Specified"
        if wrapper_key not in tree[product.brand][product.line]:
            tree[product.brand][product.line][wrapper_key] = {
                'vitolas': set(),
                'sizes': set()
            }
        
        # Add vitola and size
        if product.vitola:
            tree[product.brand][product.line][wrapper_key]['vitolas'].add(product.vitola)
        tree[product.brand][product.line][wrapper_key]['sizes'].add(product.size)
    
    # Convert to the format expected by frontend
    brands = []
    for brand_name in sorted(tree.keys()):
        lines = []
        for line_name in sorted(tree[brand_name].keys()):
            wrappers = []
            for wrapper_name in sorted(tree[brand_name][line_name].keys()):
                wrapper_data = tree[brand_name][line_name][wrapper_name]
                vitolas = sorted(list(wrapper_data['vitolas']))
                sizes = sorted(list(wrapper_data['sizes']))
                
                wrappers.append({
                    "wrapper": wrapper_name if wrapper_name != "No Wrapper Specified" else "",
                    "vitolas": vitolas,
                    "sizes": sizes
                })
            
            lines.append({
                "line": line_name,
                "wrappers": wrappers
            })
        
        brands.append({
            "brand": brand_name,
            "lines": lines
        })
    
    return brands

# Routes
@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse("../static/index.html")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/options")
def options():
    """Return brand -> line -> wrapper -> vitola/size tree for dropdowns"""
    return {"brands": build_options_tree()}

@app.get("/compare")
def compare(
    brand: str = Query(...),
    line: str = Query(...),
    wrapper: Optional[str] = Query(None),
    vitola: Optional[str] = Query(None),
    size: Optional[str] = Query(None),
    zip: str = Query("", description="ZIP code for shipping/tax estimates"),
):
    """Compare prices for a specific cigar across all retailers with wrapper/vitola support"""
    
    # Get state from ZIP for shipping/tax calculations
    state = zip_to_state(zip) if zip else 'OR'
    
    # Load all products and filter by criteria
    all_products = load_all_products()
    matching_products = []
    
    for p in all_products:
        # Brand and line must match
        if p.brand.lower() != brand.lower() or p.line.lower() != line.lower():
            continue
        
        # Wrapper filter (optional)
        if wrapper and wrapper.strip():
            if p.wrapper.lower() != wrapper.lower():
                continue
        
        # Vitola filter (optional)
        if vitola and vitola.strip():
            if p.vitola.lower() != vitola.lower():
                continue
        
        # Size filter (optional, but at least one selection criteria needed)
        if size and size.strip():
            if p.size.lower() != size.lower():
                continue
        
        # Need at least wrapper, vitola, OR size to match
        if not wrapper and not vitola and not size:
            continue
        
        matching_products.append(p)
    
    if not matching_products:
        return {
            "brand": brand,
            "line": line,
            "wrapper": wrapper,
            "vitola": vitola,
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
        tax_cents = estimate_tax_cents(base_cents + shipping_cents, product.retailer_key, state)        
        # Ensure all values are integers, not None
        shipping_cents = shipping_cents or 0
        tax_cents = tax_cents or 0
        delivered_cents = base_cents + shipping_cents + tax_cents
        
        # Track in-stock prices for determining cheapest
        if product.in_stock:
            in_stock_prices.append(delivered_cents)
        
        # Build descriptive product name
        wrapper_text = f" {product.wrapper}" if product.wrapper else ""
        vitola_text = f" {product.vitola}" if product.vitola else ""
        product_name = f"{product.brand} {product.line}{wrapper_text}{vitola_text} ({product.size})"
        
        # Build result entry
        retailer_info = next((r for r in RETAILERS if r["key"] == product.retailer_key), None)
        is_authorized = retailer_info.get("authorized", False) if retailer_info else False

        # Build result entry
        result = {
            "retailer": product.retailer_name,
            "product": product_name,
            "wrapper": product.wrapper,
            "vitola": product.vitola,
            "size": product.size,
            "base": f"${base_cents/100:.2f}",
            "shipping": f"${shipping_cents/100:.2f}",
            "tax": f"${tax_cents/100:.2f}",
            "delivered": f"${delivered_cents/100:.2f}",
            "promo": None,
            "promo_code": None,
            "delivered_after_promo": f"${delivered_cents/100:.2f}",
            "url": product.url,
            "oos": not product.in_stock,
            "cheapest": False,  # Will be set below
            "authorized": is_authorized
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
        "wrapper": wrapper,
        "vitola": vitola, 
        "size": size,
        "state": state,
        "results": results
    }

# Legal page routes
@app.get("/about.html")
async def about():
    return FileResponse("../static/about.html")

@app.get("/privacy-policy.html") 
async def privacy_policy():
    return FileResponse("../static/privacy-policy.html")

@app.get("/terms-of-service.html")
async def terms_of_service():
    return FileResponse("../static/terms-of-service.html")

@app.get("/contact.html")
async def contact():
    return FileResponse("../static/contact.html")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)