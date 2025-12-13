from fastapi import FastAPI, Query, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response, RedirectResponse
from pathlib import Path
import csv
from typing import Optional
from pydantic import BaseModel
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import sqlite3
import hashlib
import psycopg2
from urllib.parse import quote_plus

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    scheduler_available = True
except ImportError:
    BackgroundScheduler = None
    CronTrigger = None
    scheduler_available = False
import subprocess
import logging

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
        elif retailer_key == 'bnbtobacco' and base_dollars >= 199:
            return 0  # Adjust threshold as needed
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
        elif retailer_key == 'cigora':
            return 0
        elif retailer_key == 'corona' and base_dollars >= 125:
            return 0
        elif retailer_key == 'cubancrafters' and base_dollars >= 100:
            return 0
        elif retailer_key == 'cuencacigars' and base_dollars >= 99:
            return 0
        elif retailer_key == 'foxcigar' and base_dollars >= 25:
            return 0
        elif retailer_key == 'holts' and base_dollars >= 150:
            return 0
        elif retailer_key == 'iheartcigars' and base_dollars >= 99:
            return 0  # Free shipping over $99
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
        elif retailer_key == 'tampasweethearts':
            if base_dollars >= 200.01:
                return 0  # Free shipping
            elif base_dollars >= 100.01:
                return 1295  # $12.95 in cents
            elif base_dollars >= 50.01:
                return 1195  # $11.95 in cents  
            else:
                return 1500  # $15.00 in cents
        elif retailer_key == 'thecigarshop' and base_dollars >= 100:
            return 0
        elif retailer_key == 'twoguys' and base_dollars >= 199:
            return 0
        elif retailer_key == 'thecigarstore' and base_dollars >= 75:
            return 0
        elif retailer_key == 'thompson' and base_dollars >= 125:
            return 0
        elif retailer_key == 'watchcity' and base_dollars >= 99.99:
            return 0
        elif retailer_key == 'hilands' and base_dollars >= 99.99:
            return 0
        elif retailer_key == 'absolutecigars':    # ADD THIS LINE
            return 800  # $8.00 in cents                    # AND THIS LINE
        
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
            'bnbtobacco': ['VA'],  # Update with BnB's actual tax states
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
            'cigora': ['PA'],
            'corona': ['FL'],
            'cubancrafters': ['FL'],
            'cuencacigars': ['FL'],
            'famous': ['PA'],
            'foxcigar': ['AZ'],
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
            'baysidecigars': ['FL'],  # Sounds like Florida-based
            'cigarboxinc': ['PA'],  # Many cigar retailers are PA-based
            'cigarprimestore': ['FL'],  # Estimated
            'karmacigar': ['CA'],  # Many cigar bars are CA-based
            'mailcubancigars': [],  # Swiss company - likely no US tax nexus
            'pyramidcigars': ['FL'],  # Estimated Florida
            'thecigarshouse': ['FL'],  # Estimated Florida  
            'tobacconistofgreenwich': ['CT'],  # Greenwich is in Connecticut
            'iheartcigars': ['FL'],
        }
        
        # Load tax rates
        rates = {
            'PA': 0.08, 'FL': 0.07, 'TX': 0.082, 'AZ': 0.084, 'NC': 0.07, 'NJ': 0.066, 
            'SC': 0.073, 'NY': 0.086, 'WA': 0.092, 'IL': 0.089, 'NV': 0.0825, 'TN': 0.07,
            'DC': 0.06, 'VA': 0.057, 'DE': 0.0, 'OH': 0.0725, 'MI': 0.06, 'MA': 0.0625,
            'CA': 0.0825, 'NH': 0.0, 'CT': 0.0635
        }
        
        # Only charge tax if customer is in a state where retailer has nexus
        if retailer_key in retailer_nexus and state in retailer_nexus[retailer_key]:
            return int(taxable_amount_cents * rates.get(state, 0))
        
        return 0

 # Configure logging  â† NO INDENTATION
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Box Pricing Request Model
class BoxPricingRequest(BaseModel):
    brand: str
    line: str
    wrapper: str = ""
    vitola: str = ""
    boxSize: str = ""
    name: str
    email: str
    zip: str
    notes: str = ""

# Data Issue Report Model
class DataIssueReport(BaseModel):
    search_context: str = ""
    retailer: str = ""
    issue_type: str
    problem_description: str
    recommended_solution: str
    name: str
    email: str
    current_url: str = ""
    timestamp: str = ""

def run_feed_processor():
    """Run the CJ feed processing script"""
    try:
        logger.info("Starting CJ feed processor...")
        result = subprocess.run(
            ['python', 'scripts/process_cj_feeds.py'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        logger.info(f"Feed processor output: {result.stdout}")
        if result.stderr:
            logger.error(f"Feed processor errors: {result.stderr}")
        if result.returncode == 0:
            logger.info("Feed processor completed successfully")
        else:
            logger.error(f"Feed processor failed with code {result.returncode}")
    except Exception as e:
        logger.error(f"Failed to run feed processor: {e}")

def run_awin_processor():
    """Run the Awin BnB Tobacco feed processing script"""
    try:
        logger.info("Starting Awin BnB Tobacco feed processor...")
        result = subprocess.run(
            ['python', 'scripts/process_awin_feed.py'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        logger.info(f"Awin processor output: {result.stdout}")
        if result.stderr:
            logger.error(f"Awin processor errors: {result.stderr}")
        if result.returncode == 0:
            logger.info("Awin BnB Tobacco processor completed successfully")
        else:
            logger.error(f"Awin processor failed with code {result.returncode}")
    except Exception as e:
        logger.error(f"Failed to run Awin processor: {e}")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

def get_analytics_conn():
    """Connect to Postgres using ANALYTICS_DB_URL from Railway."""
    db_url = os.getenv("ANALYTICS_DB_URL")
    if not db_url:
        raise RuntimeError("ANALYTICS_DB_URL is not set")
    return psycopg2.connect(db_url)  

def load_promotions():
    """Load active promotions from promotions.json"""
    try:
        promo_file = Path("promotions.json")
        if not promo_file.exists():
            return {}
        
        with open(promo_file, 'r') as f:
            promotions = json.load(f)
        
        # Filter to only active promotions
        active_promos = {}
        for retailer, promos in promotions.items():
            active_promos[retailer] = [p for p in promos if p.get('active', False)]
        
        return active_promos
    except Exception as e:
        logger.error(f"Failed to load promotions: {e}")
        return {}

def apply_promotion(base_price_cents, retailer_key):
    """Apply applicable promotion to base price"""
    promotions = load_promotions()
    
    if retailer_key not in promotions or not promotions[retailer_key]:
        return base_price_cents, None, None
    
    # Get the first active promotion (you can enhance this logic)
    promo = promotions[retailer_key][0]
    discount_percent = promo['discount']
    promo_code = promo['code']
    
    # Calculate discounted price
    discount_amount = int(base_price_cents * (discount_percent / 100))
    promo_price_cents = base_price_cents - discount_amount
    
    return promo_price_cents, promo_code, discount_percent

# Dynamic path resolution for local vs Railway deployment
import os
if os.path.exists("../static"):
    STATIC_PATH = "../static"
    CSV_PATH_PREFIX = f"{STATIC_PATH}/data"
else:
    STATIC_PATH = "static"  
    CSV_PATH_PREFIX = "static/data"

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

import json
import urllib.request
import urllib.error

def send_notification_email(subject: str, body: str, to_email: str = None, reply_to: str = None):
    """
    Sends an email via SendGrid Web API (HTTPS). Works reliably on Railway.
    Required env vars:
      - SENDGRID_API_KEY
      - SENDGRID_FROM
    Optional env var:
      - EMAIL_TO (default recipient)
    """
    try:
        api_key = os.getenv("SENDGRID_API_KEY")
        from_email = os.getenv("SENDGRID_FROM")
        default_to = os.getenv("EMAIL_TO", "info@cigarpricescout.com")
        to_email = to_email or default_to

        if not api_key or not from_email:
            raise RuntimeError("Missing env vars SENDGRID_API_KEY and/or SENDGRID_FROM")

        payload = {
            "personalizations": [
                {
                    "to": [{"email": to_email}],
                }
            ],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }

        if reply_to:
            payload["reply_to"] = {"email": reply_to}

        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            # SendGrid returns 202 Accepted on success
            if resp.status not in (200, 202):
                raise RuntimeError(f"SendGrid error status: {resp.status}")

        logger.info(f"✅ SendGrid email accepted for delivery to {to_email}: {subject}")
        return True

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        logger.error(f"❌ SendGrid HTTPError {e.code}: {err_body}")
        return False
    except Exception as e:
        logger.error(f"❌ SendGrid send failed: {e}")
        return False

def init_analytics_tables():
    """Create analytics tables in Postgres if they don't exist."""
    conn = get_analytics_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_events (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            brand TEXT,
            line TEXT,
            wrapper TEXT,
            vitola TEXT,
            size TEXT,
            zip_prefix TEXT,
            cid TEXT,
            ip_hash TEXT,
            user_agent TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS click_events (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            retailer TEXT,
            cid TEXT,
            target_url TEXT,
            ip_hash TEXT,
            user_agent TEXT
        )
    """)

    conn.commit()
    conn.close()

@app.on_event("startup")
def startup_event():
    """Initialize analytics tables on app startup."""
    init_analytics_tables()
    # Later, if you re-enable the scheduler, you can also call start_scheduler() here.

#@app.on_event("startup")
#async def startup_event():
#    """Initialize scheduler when app starts"""
#    start_scheduler()
#    logger.info("✓ Application started with scheduled feed processing")

RETAILERS = [
    {"key": "abcfws", "name": "ABC Fine Wine & Spirits", "csv": f"{CSV_PATH_PREFIX}/abcfws.csv", "authorized": False},
    {"key": "absolutecigars", "name": "Absolute Cigars", "csv": f"{CSV_PATH_PREFIX}/absolutecigars.csv", "authorized": False},
    {"key": "atlantic", "name": "Atlantic Cigar", "csv": f"{CSV_PATH_PREFIX}/atlantic.csv", "authorized": False},
    {"key": "bestcigar", "name": "Best Cigar Prices", "csv": f"{CSV_PATH_PREFIX}/bestcigar.csv", "authorized": False},
    {"key": "bighumidor", "name": "Big Humidor", "csv": f"{CSV_PATH_PREFIX}/bighumidor.csv", "authorized": False},
    {"key": "bnbtobacco", "name": "BnB Tobacco", "csv": f"{CSV_PATH_PREFIX}/bnbtobacco.csv", "authorized": True},
    {"key": "bonitasmokeshop", "name": "Bonita Smoke Shop", "csv": f"{CSV_PATH_PREFIX}/bonitasmokeshop.csv", "authorized": False},
    {"key": "buitragocigars", "name": "Buitrago Cigars", "csv": f"{CSV_PATH_PREFIX}/buitragocigars.csv", "authorized": False},
    {"key": "casademontecristo", "name": "Casa de Montecristo", "csv": f"{CSV_PATH_PREFIX}/casademontecristo.csv", "authorized": False},
    {"key": "cccrafter", "name": "CC Crafter", "csv": f"{CSV_PATH_PREFIX}/cccrafter.csv", "authorized": False},
    {"key": "cdmcigars", "name": "CDM Cigars", "csv": f"{CSV_PATH_PREFIX}/cdmcigars.csv", "authorized": False},
    {"key": "cheaplittlecigars", "name": "Cheap Little Cigars", "csv": f"{CSV_PATH_PREFIX}/cheaplittlecigars.csv", "authorized": False},
    {"key": "ci", "name": "Cigars International", "csv": f"{CSV_PATH_PREFIX}/ci.csv", "authorized": True},
    {"key": "cigar", "name": "Cigar.com", "csv": f"{CSV_PATH_PREFIX}/cigar.csv", "authorized": False},
    {"key": "cigarboxpa", "name": "Cigar Box PA", "csv": f"{CSV_PATH_PREFIX}/cigarboxpa.csv", "authorized": False},
    {"key": "cigarcellarofmiami", "name": "Cigar Cellar of Miami", "csv": f"{CSV_PATH_PREFIX}/cigarcellarofmiami.csv", "authorized": False},
    {"key": "cigarcountry", "name": "Cigar Country", "csv": f"{CSV_PATH_PREFIX}/cigarcountry.csv", "authorized": False},
    {"key": "cigarhustler", "name": "Cigar Hustler", "csv": f"{CSV_PATH_PREFIX}/cigarhustler.csv", "authorized": False},
    {"key": "cigarking", "name": "Cigar King", "csv": f"{CSV_PATH_PREFIX}/cigarking.csv", "authorized": False},    
    {"key": "cigaroasis", "name": "Cigar Oasis", "csv": f"{CSV_PATH_PREFIX}/cigaroasis.csv", "authorized": False},
    {"key": "cigarpage", "name": "Cigar Page", "csv": f"{CSV_PATH_PREFIX}/cigarpage.csv", "authorized": False},
    {"key": "cigarpairingparlor", "name": "The Cigar Pairing Parlor LLC", "csv": f"{CSV_PATH_PREFIX}/cigarpairingparlor.csv", "authorized": False},
    {"key": "cigarplace", "name": "Cigar Place", "csv": f"{CSV_PATH_PREFIX}/cigarplace.csv", "authorized": False},
    {"key": "cigarsdirect", "name": "Cigars Direct", "csv": f"{CSV_PATH_PREFIX}/cigarsdirect.csv", "authorized": False},
    {"key": "cigora", "name": "Cigora", "csv": f"{CSV_PATH_PREFIX}/cigora.csv", "authorized": True},
    {"key": "corona", "name": "Corona Cigar", "csv": f"{CSV_PATH_PREFIX}/corona.csv", "authorized": False},
    {"key": "cubancrafters", "name": "Cuban Crafters", "csv": f"{CSV_PATH_PREFIX}/cubancrafters.csv", "authorized": False},
    {"key": "cuencacigars", "name": "Cuenca Cigars", "csv": f"{CSV_PATH_PREFIX}/cuencacigars.csv", "authorized": False},
    {"key": "escobarcigars", "name": "Escobar Cigars", "csv": f"{CSV_PATH_PREFIX}/escobarcigars.csv", "authorized": False},
    {"key": "famous", "name": "Famous Smoke Shop", "csv": f"{CSV_PATH_PREFIX}/famous.csv", "authorized": True},
    {"key": "foxcigar", "name": "Fox Cigar", "csv": f"{CSV_PATH_PREFIX}/foxcigar.csv", "authorized": False},
    {"key": "gothamcigars", "name": "Gotham Cigars", "csv": f"{CSV_PATH_PREFIX}/gothamcigars.csv", "authorized": True},
    {"key": "hilands", "name": "Hiland's Cigars", "csv": f"{CSV_PATH_PREFIX}/hilands.csv", "authorized": False},
    {"key": "holts", "name": "Holt's Cigar Company", "csv": f"{CSV_PATH_PREFIX}/holts.csv", "authorized": False},
    {"key": "jr", "name": "JR Cigar", "csv": f"{CSV_PATH_PREFIX}/jr.csv", "authorized": False},
    {"key": "lmcigars", "name": "LM Cigars", "csv": f"{CSV_PATH_PREFIX}/lmcigars.csv", "authorized": False},
    {"key": "mikescigars", "name": "Mike's Cigars", "csv": f"{CSV_PATH_PREFIX}/mikescigars.csv", "authorized": False},
    {"key": "momscigars", "name": "Mom's Cigars", "csv": f"{CSV_PATH_PREFIX}/momscigars.csv", "authorized": False},
    {"key": "neptune", "name": "Neptune Cigar", "csv": f"{CSV_PATH_PREFIX}/neptune.csv", "authorized": False},
    {"key": "niceashcigars", "name": "Nice Ash Cigars", "csv": f"{CSV_PATH_PREFIX}/niceashcigars.csv", "authorized": False},
    {"key": "nickscigarworld", "name": "Nick's Cigar World", "csv": f"{CSV_PATH_PREFIX}/nickscigarworld.csv", "authorized": False},
    {"key": "oldhavana", "name": "Old Havana Cigar Co.", "csv": f"{CSV_PATH_PREFIX}/oldhavana.csv", "authorized": False},
    {"key": "pipesandcigars", "name": "Pipes and Cigars", "csv": f"{CSV_PATH_PREFIX}/pipesandcigars.csv", "authorized": False},
    {"key": "planetcigars", "name": "Planet Cigars", "csv": f"{CSV_PATH_PREFIX}/planetcigars.csv", "authorized": False},
    {"key": "santamonicacigars", "name": "Santa Monica Cigars", "csv": f"{CSV_PATH_PREFIX}/santamonicacigars.csv", "authorized": False},
    {"key": "secretocigarbar", "name": "Secreto Cigar Bar", "csv": f"{CSV_PATH_PREFIX}/secretocigarbar.csv", "authorized": False},
    {"key": "smallbatchcigar", "name": "Small Batch Cigar", "csv": f"{CSV_PATH_PREFIX}/smallbatchcigar.csv", "authorized": False},
    {"key": "smokeinn", "name": "Smoke Inn", "csv": f"{CSV_PATH_PREFIX}/smokeinn.csv", "authorized": False},
    {"key": "tampasweethearts", "name": "Tampa Sweethearts", "csv": f"{CSV_PATH_PREFIX}/tampasweethearts.csv", "authorized": False},
    {"key": "thecigarshop", "name": "The Cigar Shop", "csv": f"{CSV_PATH_PREFIX}/thecigarshop.csv", "authorized": False},
    {"key": "thecigarstore", "name": "The Cigar Store", "csv": f"{CSV_PATH_PREFIX}/thecigarstore.csv", "authorized": False},
    {"key": "thompson", "name": "Thompson Cigar", "csv": f"{CSV_PATH_PREFIX}/thompson.csv", "authorized": True},
    {"key": "tobaccolocker", "name": "Tobacco Locker", "csv": f"{CSV_PATH_PREFIX}/tobaccolocker.csv", "authorized": False},
    {"key": "twoguys", "name": "Two Guys Smoke Shop", "csv": f"{CSV_PATH_PREFIX}/twoguys.csv", "authorized": False},
    {"key": "watchcity", "name": "Watch City Cigar", "csv": f"{CSV_PATH_PREFIX}/watchcity.csv", "authorized": False},
    {"key": "windycitycigars", "name": "Windy City Cigars", "csv": f"{CSV_PATH_PREFIX}/windycitycigars.csv", "authorized": False},
    {"key": "baysidecigars", "name": "Bayside Cigars", "csv": f"{CSV_PATH_PREFIX}/baysidecigars.csv", "authorized": False},
    {"key": "cigarboxinc", "name": "Cigar Box Inc", "csv": f"{CSV_PATH_PREFIX}/cigarboxinc.csv", "authorized": False},
    {"key": "cigarprimestore", "name": "Cigar Prime Store", "csv": f"{CSV_PATH_PREFIX}/cigarprimestore.csv", "authorized": False},
    {"key": "karmacigar", "name": "Karma Cigar Bar", "csv": f"{CSV_PATH_PREFIX}/karmacigar.csv", "authorized": False},
    {"key": "mailcubancigars", "name": "Mail Cuban Cigars", "csv": f"{CSV_PATH_PREFIX}/mailcubancigars.csv", "authorized": False},
    {"key": "pyramidcigars", "name": "Pyramid Cigars", "csv": f"{CSV_PATH_PREFIX}/pyramidcigars.csv", "authorized": False},
    {"key": "thecigarshouse", "name": "The Cigars House", "csv": f"{CSV_PATH_PREFIX}/thecigarshouse.csv", "authorized": False},
    {"key": "tobacconistofgreenwich", "name": "Tobacconist of Greenwich", "csv": f"{CSV_PATH_PREFIX}/tobacconistofgreenwich.csv", "authorized": False},
    {"key": "iheartcigars", "name": "iHeart Cigars", "csv": f"{CSV_PATH_PREFIX}/iheartcigars.csv", "authorized": False},
]

# Enhanced CSV loader with wrapper and vitola support
class Product:
    def __init__(self, retailer_key, retailer_name, title, url, brand, line, wrapper, vitola, size, box_qty, price, in_stock=True, current_promotions_applied=''):
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
        self.current_promotions_applied = current_promotions_applied

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
                        in_stock=row.get('in_stock', True),
                        current_promotions_applied=row.get('current_promotions_applied', '')
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

def load_master_wrapper_aliases():
    """Load wrapper aliases from master_cigars.csv for lookup"""
    # Try multiple possible paths for the master file using dynamic path resolution
    possible_paths = [
        Path("data/master_cigars.csv"),
        Path("../data/master_cigars.csv") if os.path.exists("../data") else Path("data/master_cigars.csv"),
        Path("./master_cigars.csv"),
        Path(f"{STATIC_PATH}/data/master_cigars.csv")
    ]
    
    master_file = None
    for path in possible_paths:
        if path.exists():
            master_file = path
            break
    
    if not master_file:
        print(f"Warning: Master file not found in any of these locations: {[str(p) for p in possible_paths]}")
        return {}
    
    print(f"Loading wrapper aliases from: {master_file}")
    wrapper_aliases = {}
    
    try:
        with open(master_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows_processed = 0
            aliases_found = 0
            
            for row in reader:
                rows_processed += 1
                wrapper = row.get('Wrapper', '').strip()
                wrapper_alias = row.get('Wrapper_Alias', '').strip()
                brand = row.get('Brand', '').strip()
                line = row.get('Line', '').strip()
                
                if wrapper and wrapper_alias and wrapper_alias != wrapper:
                    aliases_found += 1
                    # Create a composite key for more precise matching
                    key = f"{brand}|{line}|{wrapper}"
                    wrapper_aliases[key] = wrapper_alias
                    
                    # Also create a simple wrapper-only key as fallback
                    if wrapper not in wrapper_aliases:
                        wrapper_aliases[wrapper] = wrapper_alias
                    
                    # Debug first few entries
                    if aliases_found <= 5:
                        print(f"  Added alias: {wrapper} -> {wrapper_alias} (Brand: {brand}, Line: {line})")
            
            print(f"Processed {rows_processed} rows, found {aliases_found} wrapper aliases")
            
    except Exception as e:
        print(f"Error loading master wrapper aliases: {e}")
        import traceback
        traceback.print_exc()
    
    return wrapper_aliases

def get_wrapper_alias(wrapper, brand=None, line=None, wrapper_aliases=None):
    """Get wrapper alias for a given wrapper, with context-aware lookup"""
    if not wrapper_aliases:
        return None
    
    # Try context-aware lookup first
    if brand and line:
        key = f"{brand}|{line}|{wrapper}"
        if key in wrapper_aliases:
            alias = wrapper_aliases[key]
            # Uncomment for debugging: print(f"  Found alias via context key '{key}': {wrapper} -> {alias}")
            return alias
    
    # Fall back to simple wrapper lookup
    alias = wrapper_aliases.get(wrapper, None)
    if alias:
        # Uncomment for debugging: print(f"  Found alias via simple lookup: {wrapper} -> {alias}")
        pass
    return alias

def build_options_tree():
    """Build the brand -> line -> wrapper -> vitola/size tree for dropdowns with wrapper alias support"""
    products = load_all_products()
    wrapper_aliases = load_master_wrapper_aliases()  # Load wrapper aliases
    
    print(f"Building options tree with {len(products)} products and {len(wrapper_aliases)} wrapper aliases")
    
    tree = {}
    aliases_used = 0
    
    for product in products:
        if not product.brand:
            continue
        
        # Initialize brand if not exists
        if product.brand not in tree:
            tree[product.brand] = {}
        
        # Initialize line if not exists
        if product.line not in tree[product.brand]:
            tree[product.brand][product.line] = {}
        
        # Get wrapper alias for this wrapper
        wrapper_alias = get_wrapper_alias(product.wrapper, product.brand, product.line, wrapper_aliases)
        if wrapper_alias:
            aliases_used += 1
        
        # Initialize wrapper if not exists (allow empty wrapper)
        wrapper_key = product.wrapper or "No Wrapper Specified"
        if wrapper_key not in tree[product.brand][product.line]:
            tree[product.brand][product.line][wrapper_key] = {
                'vitolas': set(),
                'sizes': set(),
                'box_qtys': set(),
                'wrapper_alias': wrapper_alias  # Store wrapper alias
            }
        
        # Add vitola, size, and box_qty
        if product.vitola:
            tree[product.brand][product.line][wrapper_key]['vitolas'].add(product.vitola)
        tree[product.brand][product.line][wrapper_key]['sizes'].add(product.size)
        tree[product.brand][product.line][wrapper_key]['box_qtys'].add(product.box_qty)  # Add this line
    
    print(f"Aliases used during tree building: {aliases_used}")
    
    # Convert to the format expected by frontend
    brands = []
    wrappers_with_aliases = 0
    for brand_name in sorted(tree.keys()):
        lines = []
        for line_name in sorted(tree[brand_name].keys()):
            wrappers = []
            for wrapper_name in sorted(tree[brand_name][line_name].keys()):
                wrapper_data = tree[brand_name][line_name][wrapper_name]
                vitolas = sorted(list(wrapper_data['vitolas']))
                sizes = sorted(list(wrapper_data['sizes']))
                
                wrapper_alias_value = wrapper_data.get('wrapper_alias')
                if wrapper_alias_value:
                    wrappers_with_aliases += 1
                
                wrappers.append({
                    "wrapper": wrapper_name if wrapper_name != "No Wrapper Specified" else "",
                    "wrapper_alias": wrapper_alias_value,  # Include wrapper alias
                    "vitolas": vitolas,
                    "sizes": sizes,
                    "box_qtys": sorted(list(wrapper_data['box_qtys']))  # Add this line

                })
            
            lines.append({
                "line": line_name,
                "wrappers": wrappers
            })
        
        brands.append({
            "brand": brand_name,
            "lines": lines
        })
    
    print(f"Final summary: {len(brands)} brands, {wrappers_with_aliases} wrappers have aliases")
    
    return brands

# Routes
@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(f"{STATIC_PATH}/index.html")

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
    authorized_only: bool = Query(False, description="Show only authorized dealers"),
    request: Request = None,
):
    """Compare prices for a specific cigar across all retailers with wrapper/vitola support"""
    
    # --- Analytics: log search event ---
    try:
        ua = request.headers.get("user-agent", "") if request else ""
        ip = request.client.host if (request and request.client) else ""
        ip_hash = hashlib.sha256(ip.encode()).hexdigest() if ip else None
        zip_prefix = zip[:3] if zip else None

        conn = get_analytics_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO search_events
            (brand, line, wrapper, vitola, size, zip_prefix, cid, ip_hash, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                brand,
                line,
                wrapper,
                vitola,
                size,
                zip_prefix,
                None,       # cid placeholder for now
                ip_hash,
                ua,
            ),
        )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[analytics] Search log failed: {e}")

    
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
        
        # Size matching is handled by the compare endpoint naturally
        # Wrapper and vitola are optional filters
        pass
        
        matching_products.append(p)

    # Filter by authorized dealers if requested
    if authorized_only:
        authorized_retailer_keys = {r["key"] for r in RETAILERS if r["authorized"]}
        matching_products = [p for p in matching_products if p.retailer_key in authorized_retailer_keys]

    # Calculate price context (median comparison) - AFTER filtering
    if len(matching_products) >= 3:  # Need at least 3 prices for meaningful comparison
        delivered_prices = []
        for product in matching_products:
            base_cents = product.price_cents
            shipping_cents = estimate_shipping_cents(base_cents, product.retailer_key, state) or 0
            tax_cents = estimate_tax_cents(base_cents + shipping_cents, product.retailer_key, state) or 0
            delivered_prices.append(base_cents + shipping_cents + tax_cents)
        
        # Calculate median
        delivered_prices.sort()
        n = len(delivered_prices)
        median_price = delivered_prices[n//2] if n % 2 == 1 else (delivered_prices[n//2-1] + delivered_prices[n//2]) / 2
    else:
        median_price = None

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
        
        # Apply promotions
        # Apply promotions
        promo_price_cents, promo_code, promo_discount = apply_promotion(base_cents, product.retailer_key)
        print(f"DEBUG: {product.retailer_key} - Base: {base_cents}, Promo: {promo_price_cents}, Code: {promo_code}, Discount: {promo_discount}")
        if promo_price_cents and promo_price_cents != base_cents:
            promo_shipping_cents = estimate_shipping_cents(promo_price_cents, product.retailer_key, state) or 0
            promo_tax_cents = estimate_tax_cents(promo_price_cents + promo_shipping_cents, product.retailer_key, state) or 0
            final_delivered_cents = promo_price_cents + promo_shipping_cents + promo_tax_cents
        else:
            final_delivered_cents = delivered_cents

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

        # Calculate final delivered price with promos (BEFORE the result dictionary)
        if product.current_promotions_applied:
            promo_parts = product.current_promotions_applied.split('|')
            promo_price_text = promo_parts[0]  # "$139.80 [25% off]"
            promo_code = promo_parts[1] if len(promo_parts) > 1 else None
            
            # Extract the discounted price
            promo_price_match = promo_price_text.split(' [')[0].replace('$', '')
            try:
                promo_price_cents = int(float(promo_price_match) * 100)
                final_delivered_cents = promo_price_cents + shipping_cents + tax_cents
            except:
                final_delivered_cents = delivered_cents
        else:
            final_delivered_cents = delivered_cents
            promo_code = None

          # Calculate price context vs median (10% thresholds)
        price_context = None
        if median_price:
            diff_percent = ((final_delivered_cents - median_price) / median_price) * 100
            if diff_percent <= -10:
                price_context = "Value"
            elif diff_percent >= 10:
                price_context = "Premium"
            else:
                price_context = "Market"

        result = {
            "retailer": product.retailer_name,
            "product": product_name,
            "wrapper": product.wrapper,
            "vitola": product.vitola,
            "size": product.size,
            "box_qty": product.box_qty,
            "base": f"${base_cents/100:.2f}",
            "shipping": f"${shipping_cents/100:.2f}",
            "tax": f"${tax_cents/100:.2f}",
            "delivered": f"${delivered_cents/100:.2f}",
            "promo": f"{promo_discount:.0f}% off" if promo_discount else None,
            "promo_code": promo_code,
            "delivered_after_promo": f"${final_delivered_cents/100:.2f}",
            "url": product.url,
            "oos": not product.in_stock,
            "cheapest": False,
            "authorized": is_authorized,
            "price_context": price_context,
            "current_promotions_applied": product.current_promotions_applied,
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

@app.get("/compare-all")
def compare_all(
    brand: str = Query(...),
    line: str = Query(...),
    zip: str = Query("", description="ZIP code for shipping/tax estimates"),
    authorized_only: bool = Query(False, description="Show only authorized dealers"),
):
    """
    Compare prices for ALL variations of a brand/line (for landing pages)
    Shows all wrappers, vitolas, and box quantities
    """
    
    # Get state from ZIP for shipping/tax calculations
    state = zip_to_state(zip) if zip else 'OR'
    
    # Load all products and filter by brand/line only
    all_products = load_all_products()
    matching_products = []
    
    for p in all_products:
        # Brand and line must match
        if p.brand.lower() != brand.lower() or p.line.lower() != line.lower():
            continue
        
        matching_products.append(p)

    # Filter by authorized dealers if requested
    if authorized_only:
        authorized_retailer_keys = {r["key"] for r in RETAILERS if r["authorized"]}
        matching_products = [p for p in matching_products if p.retailer_key in authorized_retailer_keys]

    # Calculate price context (median comparison)
    if len(matching_products) >= 3:
        delivered_prices = []
        for product in matching_products:
            base_cents = product.price_cents
            shipping_cents = estimate_shipping_cents(base_cents, product.retailer_key, state) or 0
            tax_cents = estimate_tax_cents(base_cents + shipping_cents, product.retailer_key, state) or 0
            delivered_prices.append(base_cents + shipping_cents + tax_cents)
        
        delivered_prices.sort()
        n = len(delivered_prices)
        median_price = delivered_prices[n//2] if n % 2 == 1 else (delivered_prices[n//2-1] + delivered_prices[n//2]) / 2
    else:
        median_price = None

    if not matching_products:
        return {
            "brand": brand,
            "line": line,
            "state": state,
            "results": []
        }

    # Calculate delivered prices and build results
    results = []
    in_stock_prices = []

    for product in matching_products:
        base_cents = product.price_cents
        shipping_cents = estimate_shipping_cents(base_cents, product.retailer_key, state) or 0
        tax_cents = estimate_tax_cents(base_cents + shipping_cents, product.retailer_key, state) or 0
        delivered_cents = base_cents + shipping_cents + tax_cents

        price_context = None
        if median_price:
            diff_percent = ((delivered_cents - median_price) / median_price) * 100
            if diff_percent <= -10:
                price_context = "Value"
            elif diff_percent >= 10:
                price_context = "Premium"
            else:
                price_context = "Market"
        
        if product.in_stock:
            in_stock_prices.append(delivered_cents)
        
        wrapper_text = f" {product.wrapper}" if product.wrapper else ""
        vitola_text = f" {product.vitola}" if product.vitola else ""
        product_name = f"{product.brand} {product.line}{wrapper_text}{vitola_text} ({product.size})"
        
        retailer_info = next((r for r in RETAILERS if r["key"] == product.retailer_key), None)
        is_authorized = retailer_info.get("authorized", False) if retailer_info else False

        # Calculate final delivered price with promos (BEFORE the result dictionary)
        if product.current_promotions_applied:
            promo_parts = product.current_promotions_applied.split('|')
            promo_price_text = promo_parts[0]  # "$139.80 [25% off]"
            promo_code = promo_parts[1] if len(promo_parts) > 1 else None
            
            # Extract the discounted price
            promo_price_match = promo_price_text.split(' [')[0].replace('$', '')
            try:
                promo_price_cents = int(float(promo_price_match) * 100)
                final_delivered_cents = promo_price_cents + shipping_cents + tax_cents
            except:
                final_delivered_cents = delivered_cents
        else:
            final_delivered_cents = delivered_cents
            promo_code = None

        tracking_url = f"/go?retailer={product.retailer_key}&cid={product.cid}&url={quote_plus(product.url)}"

        result = {
            "retailer": product.retailer_name,
            "product": product_name,
            "wrapper": product.wrapper,
            "vitola": product.vitola,
            "size": product.size,
            "box_qty": product.box_qty,
            "base": f"${base_cents/100:.2f}",
            "shipping": f"${shipping_cents/100:.2f}",
            "tax": f"${tax_cents/100:.2f}",
            "delivered": f"${delivered_cents/100:.2f}",
            "promo": f"{promo_discount:.0f}% off" if promo_discount else None,
            "promo_code": promo_code,
            "delivered_after_promo": f"${final_delivered_cents/100:.2f}",
            "url": product.url,
            "oos": not product.in_stock,
            "cheapest": False,
            "authorized": is_authorized,
            "price_context": price_context,
            "current_promotions_applied": product.current_promotions_applied,
        }
        results.append(result)

    if in_stock_prices:
        cheapest_price = min(in_stock_prices)
        for result in results:
            if not result["oos"]:
                delivered_price = float(result["delivered_after_promo"].replace("$", ""))
                if abs(delivered_price - cheapest_price/100) < 0.01:
                    result["cheapest"] = True
                    break

    results.sort(key=lambda r: (r["oos"], float(r["delivered_after_promo"].replace("$", ""))))

    return {
        "brand": brand,
        "line": line,
        "state": state,
        "results": results
    }

# Legal page routes

# Legal page routes
@app.get("/about.html")
async def about():
    return FileResponse(f"{STATIC_PATH}/about.html")

@app.get("/privacy-policy.html") 
async def privacy_policy():
    return FileResponse(f"{STATIC_PATH}/privacy-policy.html")

@app.get("/terms-of-service.html")
async def terms_of_service():
    return FileResponse(f"{STATIC_PATH}/terms-of-service.html")

@app.get("/contact.html")
async def contact():
    return FileResponse(f"{STATIC_PATH}/contact.html")

@app.get("/request-box-pricing.html")
async def request_box_pricing():
    return FileResponse(f"{STATIC_PATH}/request-box-pricing.html")

@app.get("/report-data-issue.html")
async def report_data_issue():
    return FileResponse(f"{STATIC_PATH}/report-data-issue.html")

@app.post("/api/box-pricing-request")
async def submit_box_pricing_request(request: BoxPricingRequest):
    try:
        # Format the email content
        subject = f"Box Pricing Request: {request.brand} {request.line}"
        
        # Log the complete request details
        submission_time = datetime.now().strftime('%Y-%m-%d at %H:%M:%S')
        full_request = f"""
========== NEW BOX PRICING REQUEST ==========
CIGAR DETAILS:
- Brand: {request.brand}
- Line: {request.line}
- Wrapper: {request.wrapper or 'Any wrapper'}
- Vitola: {request.vitola or 'Any vitola'}
- Preferred Box Size: {request.boxSize or 'Any size'}

CUSTOMER INFO:
- Name: {request.name}
- Email: {request.email}
- ZIP Code: {request.zip}

ADDITIONAL NOTES:
{request.notes or 'None'}

Submitted: {submission_time}
============================================
"""
        logger.info(full_request)
        send_notification_email(subject, full_request, "info@cigarpricescout.com")
        return {"status": "success", "message": "Your box pricing request has been submitted successfully!"}
        
    except Exception as e:
        logger.error(f"Error processing box pricing request: {e}")
        return {"status": "error", "message": "There was an error submitting your request. Please try again."}

@app.post("/api/contact")
async def submit_contact_form(request: Request):
    try:
        data = await request.json()
        
        subject = f"Contact Form: {data.get('subject', 'General Inquiry')}"
        
        full_message = f"""
========== NEW CONTACT FORM SUBMISSION ==========
SUBJECT: {data.get('subject', 'Not specified')}

FROM:
- Name: {data.get('name', 'Not provided')}
- Email: {data.get('email', 'Not provided')}

MESSAGE:
{data.get('message', 'No message provided')}

Submitted: {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}
================================================
"""
        
        logger.info(full_message)
        send_notification_email(subject, full_message, "info@cigarpricescout.com")
        return {"status": "success", "message": "Your message has been sent successfully!"}
        
    except Exception as e:
        logger.error(f"Error processing contact form: {e}")
        return {"status": "error", "message": "There was an error sending your message. Please try again."}

@app.post("/api/data-issue-report")
async def submit_data_issue_report(request: Request):
    try:
        # LOAD THE JSON DATA FIRST
        data = await request.json()
        
        # DEFINE SUBJECT VARIABLE
        subject = f"Data Issue Report: {data.get('issue_type', 'General Issue')}"
        
        full_report = f"""
========== NEW DATA ISSUE REPORT ==========
SEARCH CONTEXT: {data.get('search_context', 'Not specified')}
RETAILER: {data.get('retailer', 'Not specified')}
ISSUE TYPE: {data.get('issue_type', 'Not specified')}

PROBLEM DESCRIPTION:
{data.get('problem_description', 'No description provided')}

RECOMMENDED SOLUTION:
{data.get('recommended_solution', 'No solution provided')}

REPORTER INFO:
- Name: {data.get('name', 'Not provided')}
- Email: {data.get('email', 'Not provided')}

TECHNICAL INFO:
- URL: {data.get('current_url', 'Not provided')}
- Timestamp: {data.get('timestamp', 'Not provided')}

Submitted: {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}
==========================================
"""
        
        logger.info(full_report)
        
        # SEND EMAIL NOTIFICATION
        send_notification_email(subject, full_report, "info@cigarpricescout.com")
        
        return {"status": "success", "message": "Your data issue report has been submitted successfully!"}
        
    except Exception as e:
        logger.error(f"Error processing data issue report: {e}")
        return {"status": "error", "message": "There was an error submitting your report. Please try again."}

@app.get("/cigars/{brand}/{line}", response_class=HTMLResponse)
async def cigar_landing_page(brand: str, line: str):
    """
    SEO-friendly landing page for specific cigar brands/lines
    URL format: /cigars/padron/1964-anniversary-series
    """
    # Read the template
    template_path = Path(f"{STATIC_PATH}/cigar-template.html")
    
    if not template_path.exists():
        # Fallback if template doesn't exist yet
        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    
    # Replace placeholders with actual values
    # Convert URL-friendly format back to display format
    brand_display = brand.replace('-', ' ').title()
    line_display = line.replace('-', ' ').title()
    
    html = template.replace('{{BRAND}}', brand_display)
    html = html.replace('{{LINE}}', line_display)
    
    return HTMLResponse(content=html)


# Helper function to generate URL-friendly slugs
def create_slug(text: str) -> str:
    """Convert 'Padron 1964' to 'padron-1964'"""
    return text.lower().replace(' ', '-').replace('/', '-')


@app.get("/generate-landing-pages")
async def generate_landing_page_list():
    """
    Utility endpoint to see what landing pages you should create
    Visit this in your browser to get a list
    """
    brands = build_options_tree()
    
    pages = []
    for brand in brands[:20]:  # Start with top 20 brands
        for line in brand['lines'][:3]:  # Top 3 lines per brand
            brand_slug = create_slug(brand['brand'])
            line_slug = create_slug(line['line'])
            url = f"/cigars/{brand_slug}/{line_slug}"
            pages.append({
                'url': url,
                'brand': brand['brand'],
                'line': line['line'],
                'full_url': f"https://cigarpricescout.com{url}"
            })
    
    return {"pages": pages, "count": len(pages)}

@app.get("/sitemap.xml", response_class=Response)
async def sitemap():
    base_url = "https://cigarpricescout.com"
    
    # Static pages
    urls = [
        {"url": base_url, "priority": "1.0", "changefreq": "daily"},
        {"url": f"{base_url}/about.html", "priority": "0.8", "changefreq": "monthly"},
        {"url": f"{base_url}/privacy-policy.html", "priority": "0.5", "changefreq": "yearly"},
        {"url": f"{base_url}/terms-of-service.html", "priority": "0.5", "changefreq": "yearly"},
        {"url": f"{base_url}/contact.html", "priority": "0.5", "changefreq": "yearly"},
    ]
    
    # Add dynamic cigar landing pages
    brands = build_options_tree()
    for brand in brands[:50]:  # Increase from 20 to 50 brands
        for line in brand['lines'][:5]:  # Increase from 3 to 5 lines per brand
            brand_slug = create_slug(brand['brand'])
            line_slug = create_slug(line['line'])
            urls.append({
                "url": f"{base_url}/cigars/{brand_slug}/{line_slug}",
                "priority": "0.9",
                "changefreq": "weekly"
            })
    
    # Generate XML
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    for url_data in urls:
        xml_content += f'  <url>\n'
        xml_content += f'    <loc>{url_data["url"]}</loc>\n'
        xml_content += f'    <priority>{url_data["priority"]}</priority>\n'
        xml_content += f'    <changefreq>{url_data["changefreq"]}</changefreq>\n'
        xml_content += f'  </url>\n'
    
    xml_content += '</urlset>'
    
    return Response(content=xml_content, media_type="application/xml")

# Add this endpoint to your main.py after your other routes (around line 1200)

@app.get("/debug/init_analytics")
def debug_init_analytics():
    """
    One-time helper: create analytics tables (search_events, click_events) in Postgres.
    You can hit this endpoint once after deploy to ensure tables exist.
    """
    conn = get_analytics_conn()
    cur = conn.cursor()

    # Create search_events table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_events (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMPTZ DEFAULT NOW(),
            brand TEXT,
            line TEXT,
            wrapper TEXT,
            vitola TEXT,
            size TEXT,
            zip_prefix TEXT,
            cid TEXT,
            ip_hash TEXT,
            user_agent TEXT
        )
    """)

    # Create click_events table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS click_events (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMPTZ DEFAULT NOW(),
            retailer TEXT,
            cid TEXT,
            target_url TEXT,
            ip_hash TEXT,
            user_agent TEXT
        )
    """)

    conn.commit()
    conn.close()

    return {"status": "ok", "message": "Analytics tables ensured in Postgres"}

@app.get("/go")
def track_click(
    retailer: str,
    cid: str,
    url: str,
    request: Request
):
    """Track retailer click-outs and redirect to target URL."""
    try:
        ua = request.headers.get("user-agent", "") or ""
        ip = request.client.host if request and request.client else ""
        ip_hash = hashlib.sha256(ip.encode()).hexdigest() if ip else None

        conn = get_analytics_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO click_events (retailer, cid, target_url, ip_hash, user_agent)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (retailer, cid, url, ip_hash, ua),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[analytics] Click log failed: {e}")

    return RedirectResponse(url, status_code=302)

@app.get("/click")
def log_click(retailer: str, cid: str, request: Request):
    """
    Logs when a user clicks out to a retailer's website.
    """
    try:
        # Get IP without storing the real address
        client_ip = request.client.host
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()

        # Get user agent
        user_agent = request.headers.get("User-Agent", "unknown")

        # Connect to analytics DB
        conn = get_analytics_conn()
        cur = conn.cursor()

        # Insert record
        cur.execute("""
            INSERT INTO click_events (retailer, cid, ip_hash, user_agent)
            VALUES (%s, %s, %s, %s);
        """, (retailer, cid, ip_hash, user_agent))

        conn.commit()
        cur.close()
        conn.close()

        return {"status": "ok"}

    except Exception as e:
        print("CLICK ERROR:", e)
        return {"status": "error", "detail": str(e)}

@app.post("/admin/trigger-feed-update")
async def trigger_feed_update():
    """Manual trigger for testing (remove in production or add auth)"""
    run_feed_processor()
    return {"status": "Feed processor triggered"}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)