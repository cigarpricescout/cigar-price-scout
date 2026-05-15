from fastapi import FastAPI, Query, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response, RedirectResponse, PlainTextResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from pathlib import Path
import csv
import re
import time
import uuid
from typing import Dict, Optional
from pydantic import BaseModel
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import sqlite3
import hashlib
import psycopg2
from urllib.parse import quote_plus, urlparse, urlunparse, parse_qsl, urlencode

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

        if retailer_key.startswith("community_free_"):
            return 0
    
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
        elif retailer_key == 'cigardepot' and base_dollars >= 200:
            return 0
        elif retailer_key == 'cigarcountry' and base_dollars >= 150:
            return 0
        elif retailer_key == 'cigarking' and base_dollars >= 150:
            return 0
        elif retailer_key == 'cigarpage':
            return 0  # Free shipping advertised on every page (banner: "FREE Shipping")
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
        elif retailer_key == 'tobaccolocker':
            return 0  # Free shipping on all orders
        elif retailer_key == 'watchcity' and base_dollars >= 99.99:
            return 0
        elif retailer_key == 'hilands' and base_dollars >= 99.99:
            return 0
        elif retailer_key == 'absolutecigars':    # ADD THIS LINE
            return 800  # $8.00 in cents                    # AND THIS LINE
        
        # Flat rate shipping
        elif retailer_key == 'cigarpairingparlor':
            return 995  # $9.95
        elif retailer_key == 'pyramidcigars':
            return 895  # $8.95
        elif retailer_key == 'smokeinn':
            return 995  # $9.95
        elif retailer_key == 'stogies' and base_dollars >= 100:
            return 0  # Free shipping on $100+
        elif retailer_key == 'stogies':
            return 999  # $9.99 flat rate
        elif retailer_key == 'cigarhustler':
            return 999  # $9.99 flat rate (research exact policy)
        elif retailer_key == 'cigarprimestore':
            return 999  # $9.99 flat rate (research exact policy)
        elif retailer_key == 'coronacigar' and base_dollars >= 100:
            return 0  # Free shipping on $100+
        elif retailer_key == 'coronacigar':
            return 999  # $9.99 under $100
        
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
            'cigardepot': ['FL'],  # Tampa, FL
            'cigarcellarofmiami': ['FL'],
            'cigarhustler': ['FL'],
            'cigarking': ['AZ'],
            'cigora': ['PA'],
            'corona': ['FL'],
            'coronacigar': ['FL'],  # Corona Cigar Co. - Florida based,
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
            'pyramidcigars': ['TN'],  # Memphis, TN
            'santamonicacigars': ['CA'],
            'secretocigarbar': ['MI'],
            'smallbatchcigar': ['CA'],
            'smokeinn': ['FL'],
            'stogies': ['TX'],  # Stogies World Class Cigars
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

    current_url: str = ""
    timestamp: str = ""

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

def get_analytics_conn():
    """Connect to Postgres using ANALYTICS_DB_URL from Railway."""
    db_url = os.getenv("ANALYTICS_DB_URL")
    if not db_url:
        raise RuntimeError("ANALYTICS_DB_URL is not set")
    return psycopg2.connect(db_url)  

def load_promotions():
    """Load active, non-expired promotions from promotions.json"""
    try:
        promo_file = PROJECT_ROOT / "tools" / "promotions" / "promotions.json"
        if not promo_file.exists():
            logger.warning(f"Promotions file not found at {promo_file}")
            return {}
        
        with open(promo_file, 'r') as f:
            promotions = json.load(f)
        
        today = datetime.now().strftime('%Y-%m-%d')
        active_promos = {}
        for retailer, promos in promotions.items():
            active_promos[retailer] = [
                p for p in promos
                if p.get('active', False) and p.get('end_date', '9999-12-31') >= today
            ]
        
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
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_PATH = str(PROJECT_ROOT / "static")
CSV_PATH_PREFIX = str(PROJECT_ROOT / "static" / "data")

app = FastAPI()

# SEO Fix: WWW to non-WWW redirect middleware
# Forces all www.cigarpricescout.com traffic to cigarpricescout.com
class WWWRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        if host.startswith("www."):
            # Build the new URL without www
            url = str(request.url).replace("://www.", "://", 1)
            return RedirectResponse(url, status_code=301)
        return await call_next(request)

app.add_middleware(WWWRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)

# Cache-Control middleware for static assets (browsers cache for 24 hours)
class StaticCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response

app.add_middleware(StaticCacheMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

# Custom 404 handler
@app.exception_handler(404)
async def custom_404_handler(request, exc):
    return FileResponse(f"{STATIC_PATH}/404.html", status_code=404)

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS url_staged_matches (
            id SERIAL PRIMARY KEY,
            match_token TEXT UNIQUE NOT NULL,
            cid TEXT NOT NULL,
            retailer_key TEXT NOT NULL,
            url TEXT NOT NULL,
            confidence TEXT,
            reason TEXT,
            brand TEXT,
            line TEXT,
            vitola TEXT,
            wrapper TEXT,
            size TEXT,
            box_qty INTEGER,
            price NUMERIC(10,2),
            in_stock BOOLEAN,
            status TEXT DEFAULT 'staged',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ,
            UNIQUE(cid, retailer_key, url)
        )
    """)

    conn.commit()
    conn.close()

@app.on_event("startup")
def startup_event():
    """Initialize analytics and community tables on app startup."""
    try:
        init_analytics_tables()
        _ensure_community_tables_pg()
        logger.info("✓ Analytics and community tables initialized")
    except Exception as e:
        logger.warning(f"⚠ Analytics DB not available (local dev mode): {e}")
    # Initialize the Chrome-extension staging tables (idempotent). Failure here
    # must not block app boot — the extension is opt-in and the rest of the
    # site is unaffected if these tables can't be created.
    try:
        from app.extension_endpoints import init_extension_tables
        init_extension_tables()
        logger.info("✓ Extension staging tables initialized")
    except Exception as e:
        logger.warning(f"⚠ Extension tables init skipped: {e}")
    try:
        from app.community_endpoints import init_community_tables
        init_community_tables()
        logger.info("✓ Community staging tables initialized")
    except Exception as e:
        logger.warning(f"⚠ Community tables init skipped: {e}")


# Mount the Chrome-extension router. All routes are admin-gated and additive;
# no existing route paths or behaviors change.
try:
    from app.extension_endpoints import router as _extension_router
    app.include_router(_extension_router)
except Exception as _ext_err:
    logger.warning(f"⚠ Extension router not mounted: {_ext_err}")

# Mount the public community router (consumer extension's passive observe
# + metadata-proposal endpoints). These routes are anonymous + rate-limited,
# and never write to retailer CSVs or master_cigars — only to Postgres.
try:
    from app.community_endpoints import router as _community_router
    from app.community_endpoints import public_router as _public_router
    app.include_router(_community_router)
    app.include_router(_public_router)
except Exception as _comm_err:
    logger.warning(f"⚠ Community/public router not mounted: {_comm_err}")


# Retailer config.
#
# Per-entry fields:
#   key                — internal id; matches static/data/{key}.csv stem.
#   name               — display name.
#   csv                — CSV path (may be empty file for blocked retailers).
#   authorized         — affiliate / authorized-dealer flag.
#   extractor_status   — 'active'  (default; we run a scraper, CSV is source of truth)
#                       'blocked' (anti-bot or no extractor; consumer
#                                  observations are the source of truth — they
#                                  overlay into load_all_products at query time)
#                       'dormant' (was active, now skipped entirely)
#   hostname           — optional explicit primary hostname. Required for
#                       blocked retailers whose CSVs are empty; otherwise
#                       inferred from the first URL row in the CSV.
#
# When adding a new anti-bot retailer:
#   1. Add the row here with extractor_status='blocked' and a hostname.
#   2. Create an empty `static/data/{key}.csv` (header-only is fine).
#   3. Deploy. The registry picks up the hostname and the consumer
#      extension will let users contribute observations + propose CIDs.
RETAILERS = [
    {"key": "abcfws", "name": "ABC Fine Wine & Spirits", "csv": f"{CSV_PATH_PREFIX}/abcfws.csv", "authorized": False},
    {"key": "absolutecigars", "name": "Absolute Cigars", "csv": f"{CSV_PATH_PREFIX}/absolutecigars.csv", "authorized": False},
    {"key": "atlantic", "name": "Atlantic Cigar", "csv": f"{CSV_PATH_PREFIX}/atlantic.csv", "authorized": False},
    {"key": "bestcigar", "name": "Best Cigar Prices", "csv": f"{CSV_PATH_PREFIX}/bestcigar.csv", "authorized": False, "extractor_status": "blocked", "hostname": "bestcigarprices.com"},
    {"key": "bighumidor", "name": "Big Humidor", "csv": f"{CSV_PATH_PREFIX}/bighumidor.csv", "authorized": False},
    {"key": "bnbtobacco", "name": "BnB Tobacco", "csv": f"{CSV_PATH_PREFIX}/bnbtobacco.csv", "authorized": True},
    {"key": "bonitasmokeshop", "name": "Bonita Smoke Shop", "csv": f"{CSV_PATH_PREFIX}/bonitasmokeshop.csv", "authorized": False},
    {"key": "boutiquecigar", "name": "The Boutique Cigar", "csv": f"{CSV_PATH_PREFIX}/boutiquecigar.csv", "authorized": False, "extractor_status": "blocked", "hostname": "theboutiquecigar.com"},
    {"key": "buitragocigars", "name": "Buitrago Cigars", "csv": f"{CSV_PATH_PREFIX}/buitragocigars.csv", "authorized": False},
    {"key": "casademontecristo", "name": "Casa de Montecristo", "csv": f"{CSV_PATH_PREFIX}/casademontecristo.csv", "authorized": False},
    {"key": "cccrafter", "name": "CC Crafter", "csv": f"{CSV_PATH_PREFIX}/cccrafter.csv", "authorized": False},
    {"key": "cdmcigars", "name": "CDM Cigars", "csv": f"{CSV_PATH_PREFIX}/cdmcigars.csv", "authorized": False},
    {"key": "cheaplittlecigars", "name": "Cheap Little Cigars", "csv": f"{CSV_PATH_PREFIX}/cheaplittlecigars.csv", "authorized": False},
    {"key": "ci", "name": "Cigars International", "csv": f"{CSV_PATH_PREFIX}/ci.csv", "authorized": True, "extractor_status": "blocked", "hostname": "cigarsinternational.com"},
    {"key": "cigar", "name": "Cigar.com", "csv": f"{CSV_PATH_PREFIX}/cigar.csv", "authorized": False},
    {"key": "cigarboxpa", "name": "Cigar Box PA", "csv": f"{CSV_PATH_PREFIX}/cigarboxpa.csv", "authorized": False},
    {"key": "cigardepot", "name": "Cigar Depot", "csv": f"{CSV_PATH_PREFIX}/cigardepot.csv", "authorized": False},
    {"key": "cigarcellarofmiami", "name": "Cigar Cellar of Miami", "csv": f"{CSV_PATH_PREFIX}/cigarcellarofmiami.csv", "authorized": False, "extractor_status": "blocked", "hostname": "cigarcellarofmiami.com"},
    {"key": "cigarcountry", "name": "Cigar Country", "csv": f"{CSV_PATH_PREFIX}/cigarcountry.csv", "authorized": False, "extractor_status": "blocked", "hostname": "cigarcountry.com"},
    {"key": "cigarhustler", "name": "Cigar Hustler", "csv": f"{CSV_PATH_PREFIX}/cigarhustler.csv", "authorized": False},
    {"key": "cigarking", "name": "Cigar King", "csv": f"{CSV_PATH_PREFIX}/cigarking.csv", "authorized": False},    
    {"key": "cigaroasis", "name": "Cigar Oasis", "csv": f"{CSV_PATH_PREFIX}/cigaroasis.csv", "authorized": False},
    {"key": "cigarpage", "name": "Cigar Page", "csv": f"{CSV_PATH_PREFIX}/cigarpage.csv", "authorized": False, "extractor_status": "blocked", "hostname": "cigarpage.com"},
    {"key": "cigarpairingparlor", "name": "The Cigar Pairing Parlor LLC", "csv": f"{CSV_PATH_PREFIX}/cigarpairingparlor.csv", "authorized": False},
    {"key": "cigarplace", "name": "Cigar Place", "csv": f"{CSV_PATH_PREFIX}/cigarplace.csv", "authorized": False},
    {"key": "cigarprimestore", "name": "Cigar Prime Store", "csv": f"{CSV_PATH_PREFIX}/cigarprimestore.csv", "authorized": False},
    {"key": "cigarsdirect", "name": "Cigars Direct", "csv": f"{CSV_PATH_PREFIX}/cigarsdirect.csv", "authorized": False},
    {"key": "cigarwarehouseusa", "name": "Cigar Warehouse USA", "csv": f"{CSV_PATH_PREFIX}/cigarwarehouseusa.csv", "authorized": False, "extractor_status": "blocked", "hostname": "cigarwarehouseusa.com"},
    {"key": "cigora", "name": "Cigora", "csv": f"{CSV_PATH_PREFIX}/cigora.csv", "authorized": True, "extractor_status": "blocked", "hostname": "cigora.com"},
    {"key": "corona", "name": "Corona Cigar", "csv": f"{CSV_PATH_PREFIX}/corona.csv", "authorized": False},
    {"key": "coronacigar", "name": "Corona Cigar Co.", "csv": f"{CSV_PATH_PREFIX}/coronacigar.csv", "authorized": False},
    {"key": "cubancrafters", "name": "Cuban Crafters", "csv": f"{CSV_PATH_PREFIX}/cubancrafters.csv", "authorized": False},
    {"key": "cuencacigars", "name": "Cuenca Cigars", "csv": f"{CSV_PATH_PREFIX}/cuencacigars.csv", "authorized": False},
    {"key": "escobarcigars", "name": "Escobar Cigars", "csv": f"{CSV_PATH_PREFIX}/escobarcigars.csv", "authorized": False},
    {"key": "famous", "name": "Famous Smoke Shop", "csv": f"{CSV_PATH_PREFIX}/famous.csv", "authorized": True, "extractor_status": "blocked", "hostname": "famous-smoke.com"},
    {"key": "foxcigar", "name": "Fox Cigar", "csv": f"{CSV_PATH_PREFIX}/foxcigar.csv", "authorized": False},
    {"key": "gothamcigars", "name": "Gotham Cigars", "csv": f"{CSV_PATH_PREFIX}/gothamcigars.csv", "authorized": True},
    {"key": "hilands", "name": "Hiland's Cigars", "csv": f"{CSV_PATH_PREFIX}/hilands.csv", "authorized": False},
    {"key": "holts", "name": "Holt's Cigar Company", "csv": f"{CSV_PATH_PREFIX}/holts.csv", "authorized": False},
    {"key": "jr", "name": "JR Cigar", "csv": f"{CSV_PATH_PREFIX}/jr.csv", "authorized": False, "extractor_status": "blocked", "hostname": "jrcigars.com"},
    {"key": "lmcigars", "name": "LM Cigars", "csv": f"{CSV_PATH_PREFIX}/lmcigars.csv", "authorized": False},
    {"key": "mikescigars", "name": "Mike's Cigars", "csv": f"{CSV_PATH_PREFIX}/mikescigars.csv", "authorized": False, "extractor_status": "blocked", "hostname": "mikescigars.com"},
    {"key": "momscigars", "name": "Mom's Cigars", "csv": f"{CSV_PATH_PREFIX}/momscigars.csv", "authorized": False},
    {"key": "neptune", "name": "Neptune Cigar", "csv": f"{CSV_PATH_PREFIX}/neptune.csv", "authorized": False, "extractor_status": "blocked", "hostname": "neptunecigar.com"},
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
    {"key": "thompson", "name": "Thompson Cigar", "csv": f"{CSV_PATH_PREFIX}/thompson.csv", "authorized": True, "extractor_status": "blocked", "hostname": "thompsoncigar.com"},
    {"key": "tobaccolocker", "name": "Tobacco Locker", "csv": f"{CSV_PATH_PREFIX}/tobaccolocker.csv", "authorized": False},
    {"key": "tobaccostock", "name": "Tobacco Stock", "csv": f"{CSV_PATH_PREFIX}/tobaccostock.csv", "authorized": False},
    {"key": "twoguys", "name": "Two Guys Smoke Shop", "csv": f"{CSV_PATH_PREFIX}/twoguys.csv", "authorized": False},
    {"key": "watchcity", "name": "Watch City Cigar", "csv": f"{CSV_PATH_PREFIX}/watchcity.csv", "authorized": False},
    {"key": "windycitycigars", "name": "Windy City Cigars", "csv": f"{CSV_PATH_PREFIX}/windycitycigars.csv", "authorized": False},
    {"key": "baysidecigars", "name": "Bayside Cigars", "csv": f"{CSV_PATH_PREFIX}/baysidecigars.csv", "authorized": False, "extractor_status": "blocked", "hostname": "baysidecigars.com"},
    {"key": "cigarboxinc", "name": "Cigar Box Inc", "csv": f"{CSV_PATH_PREFIX}/cigarboxinc.csv", "authorized": False},
    {"key": "karmacigar", "name": "Karma Cigar Bar", "csv": f"{CSV_PATH_PREFIX}/karmacigar.csv", "authorized": False},
    {"key": "mailcubancigars", "name": "Mail Cuban Cigars", "csv": f"{CSV_PATH_PREFIX}/mailcubancigars.csv", "authorized": False},
    {"key": "pyramidcigars", "name": "Pyramid Cigars", "csv": f"{CSV_PATH_PREFIX}/pyramidcigars.csv", "authorized": False},
    {"key": "thecigarshouse", "name": "The Cigars House", "csv": f"{CSV_PATH_PREFIX}/thecigarshouse.csv", "authorized": False},
    {"key": "tobacconistofgreenwich", "name": "Tobacconist of Greenwich", "csv": f"{CSV_PATH_PREFIX}/tobacconistofgreenwich.csv", "authorized": False},
    {"key": "iheartcigars", "name": "iHeart Cigars", "csv": f"{CSV_PATH_PREFIX}/iheartcigars.csv", "authorized": False},
    {"key": "stogies", "name": "Stogies World Class Cigars", "csv": f"{CSV_PATH_PREFIX}/stogies.csv", "authorized": False},
]


def get_extractor_status(retailer_key: str) -> str:
    """Return the extractor status for a retailer_key.

    Defaults to 'active' for retailers without an explicit value, since the
    historical contract for any entry in RETAILERS is "we scrape this".
    """
    for r in RETAILERS:
        if r["key"] == retailer_key:
            return r.get("extractor_status", "active")
    return "active"


def get_blocked_retailer_hosts() -> Dict[str, str]:
    """{hostname: retailer_key} for every blocked retailer with a known hostname.

    Used by the retailer registry to surface anti-bot retailers in the
    consumer extension even when their CSV is empty.
    """
    out: Dict[str, str] = {}
    for r in RETAILERS:
        if r.get("extractor_status") != "blocked":
            continue
        host = (r.get("hostname") or "").strip().lower()
        if host:
            out[host] = r["key"]
    return out


def get_blocked_retailer_keys() -> set:
    return {r["key"] for r in RETAILERS if r.get("extractor_status") == "blocked"}

# Enhanced CSV loader with wrapper and vitola support
class Product:
    def __init__(self, retailer_key, retailer_name, title, url, brand, line, wrapper, vitola, size, box_qty, price, in_stock=True, current_promotions_applied='', cigar_id='', community_id=None, price_source='csv', observed_at=None, observation_count=0, strength='', country=''):
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
        self.cigar_id = cigar_id
        self.community_id = community_id
        # Provenance for the consumer extension's "Last observed …" badge
        # and the operator's data-quality view:
        #   'csv'      — sourced from a per-retailer CSV; no per-row timestamp.
        #   'observed' — aggregate of recent /api/community/observe rows.
        #   'community'— legacy community_prices fallback.
        self.price_source = price_source
        # ISO 8601 string, only set when price_source='observed'. Used by the
        # popup to render an absolute "Last observed YYYY-MM-DD" stamp.
        self.observed_at = observed_at
        self.observation_count = observation_count
        # Master-only fields surfaced via Gap 3 master-first JOIN. Populated
        # from master_cigars.csv (canonical) when the row's cigar_id resolves
        # there; empty when no master entry exists yet (e.g. a brand-new CID
        # in flight before master propagation).
        self.strength = strength
        self.country = country


# ── Gap 3: master-first metadata index ────────────────────────────────
#
# Per-retailer CSVs duplicate metadata (brand/line/wrapper/vitola/size/
# box_qty) that master_cigars already owns. Until Sprint 4 the loader
# read those columns verbatim from each CSV — which meant (a) operator-
# extension "bare rows" (cigar_id+url only) were invisible until the
# next daily extractor filled them in, and (b) master corrections never
# propagated to /compare until every retailer's scraper rewrote the row.
#
# load_master_index() builds a dict keyed by cigar_id with the canonical
# metadata that load_csv() prefers over CSV columns. CSV values stay as
# a fallback for in-flight new CIDs not yet in master.
#
# Also exposes strength + country_of_origin — fields master has had all
# along but were never read by the loader.

_master_index_cache = {"data": None, "timestamp": 0}


def _format_wrapper_display(alias: str, canon: str) -> str:
    """Combine the canonical wrapper category and its specific varietal alias.

    The cigar landing page (/cigars/<brand>/<line>) historically showed the
    industry-friendly wrapper category first, with the specific botanical
    varietal in parentheses — e.g. "Maduro (Connecticut Broadleaf)" or
    "Sun Grown (Ecuadorian Sungrown)" — so a shopper who knows the cigar
    by either term can find it. This helper preserves that ordering.

    Examples:
      _format_wrapper_display("Connecticut Broadleaf", "Maduro") -> "Maduro (Connecticut Broadleaf)"
      _format_wrapper_display("Ecuadorian Sungrown", "Sun Grown") -> "Sun Grown (Ecuadorian Sungrown)"
      _format_wrapper_display("Natural", "Cameroon")            -> "Cameroon (Natural)"
      _format_wrapper_display("Maduro", "Maduro")               -> "Maduro"
      _format_wrapper_display("", "Habano")                     -> "Habano"
      _format_wrapper_display("Natural", "")                    -> "Natural"
      _format_wrapper_display("", "")                           -> ""
    """
    a = (alias or "").strip()
    c = (canon or "").strip()
    if a and c and a.lower() != c.lower():
        return f"{c} ({a})"
    return c or a


def _master_csv_path() -> Path:
    """Locate master_cigars.csv with fallbacks for dev / static-served deploys."""
    candidates = [
        Path("data/master_cigars.csv"),
        Path(__file__).resolve().parents[1] / "data" / "master_cigars.csv",
        Path(f"{STATIC_PATH}/data/master_cigars.csv"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # nonexistent path; loader returns {}

def load_master_index() -> Dict[str, Dict[str, str]]:
    """Load master_cigars.csv keyed by cigar_id for metadata enrichment.

    Returns dict: cigar_id -> {brand, line, wrapper, vitola, size, box_qty,
                               strength, country}.
    Cached for 5 minutes alongside the product cache.
    """
    now = time.time()
    if (_master_index_cache["data"] is not None
            and (now - _master_index_cache["timestamp"]) < CACHE_TTL_SECONDS):
        return _master_index_cache["data"]

    index: Dict[str, Dict[str, str]] = {}
    csv_path = _master_csv_path()
    if not csv_path.exists():
        logger.warning("master_cigars.csv not found at %s; load_master_index returning empty", csv_path)
        _master_index_cache.update({"data": index, "timestamp": now})
        return index

    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cid = (row.get('cigar_id') or '').strip()
                if not cid:
                    continue
                # Size is split across Length + Ring Gauge in master CSV.
                length = (row.get('Length') or '').strip()
                ring = (row.get('Ring Gauge') or '').strip()
                size = f"{length}x{ring}" if (length and ring) else ''
                box_qty_raw = (row.get('Box Quantity') or '').strip()
                try:
                    box_qty = int(float(box_qty_raw)) if box_qty_raw else 0
                except (TypeError, ValueError):
                    box_qty = 0
                # Prefer wrapper_alias for display ("Connecticut Shade")
                # over the technical wrapper column ("Connecticut"). The
                # canonical wrapper_code lives in the CID itself.
                # Both fields are also exposed separately so endpoints
                # that want the formal+colloquial combined display
                # (e.g. /compare-all → cigar landing page dropdown) can
                # build "alias (canon)" without re-reading the master CSV.
                wrapper_alias = (row.get('Wrapper_Alias') or '').strip()
                wrapper_canon = (row.get('Wrapper') or '').strip()
                index[cid] = {
                    'brand':    (row.get('Brand') or '').strip(),
                    'line':     (row.get('Line') or '').strip(),
                    'wrapper':  wrapper_alias or wrapper_canon,
                    'wrapper_alias': wrapper_alias,
                    'wrapper_canon': wrapper_canon,
                    'vitola':   (row.get('Vitola') or '').strip(),
                    'size':     size,
                    'box_qty':  box_qty,
                    'strength': (row.get('Strength') or '').strip(),
                    'country':  (row.get('country_of_origin') or '').strip(),
                }
    except Exception as e:
        logger.warning("load_master_index failed: %s", e)
    _master_index_cache.update({"data": index, "timestamp": now})
    return index


def _enrich_from_master(field: str, csv_value: str, master_row: Optional[Dict[str, str]]) -> str:
    """master-first preference. master wins when populated; CSV fallback."""
    if master_row:
        m = master_row.get(field)
        if m not in (None, '', 0):
            return m
    return csv_value if csv_value not in (None, '') else ''


def load_csv(csv_path, retailer_key, retailer_name, master_index: Optional[Dict[str, Dict[str, str]]] = None):
    """Load products from a per-retailer CSV with master-first metadata enrichment.

    For every row, the cigar_id is looked up in master_index. When master
    has the row, its brand/line/wrapper/vitola/size/box_qty/strength/
    country win over the CSV columns — which makes operator-extension
    bare rows (cigar_id + url + price + in_stock only) render correctly
    on /compare immediately, and master corrections propagate without
    every retailer needing to re-run their scraper.

    CSV cells remain the fallback so brand-new CIDs not yet in master
    (e.g. just-approved via the operator extension on Friday evening,
    master append still pending) still surface with the operator's
    typed-in metadata.
    """
    items = []
    csv_file = Path(csv_path)

    if not csv_file.exists():
        return items

    if master_index is None:
        master_index = load_master_index()

    try:
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    cid = (row.get('cigar_id') or '').strip()
                    master_row = master_index.get(cid) if cid else None

                    brand    = _enrich_from_master('brand',    row.get('brand', ''),    master_row)
                    line     = _enrich_from_master('line',     row.get('line', ''),     master_row)
                    wrapper  = _enrich_from_master('wrapper',  row.get('wrapper', ''),  master_row)
                    vitola   = _enrich_from_master('vitola',   row.get('vitola', ''),   master_row)
                    size     = _enrich_from_master('size',     row.get('size', ''),     master_row)
                    box_qty  = _enrich_from_master('box_qty',  row.get('box_qty', 25),  master_row)
                    # Master-only fields (no CSV equivalent today)
                    strength = (master_row or {}).get('strength', '') or ''
                    country  = (master_row or {}).get('country',  '') or ''

                    product = Product(
                        retailer_key=retailer_key,
                        retailer_name=retailer_name,
                        title=row.get('title', ''),
                        url=row.get('url', ''),
                        brand=brand,
                        line=line,
                        wrapper=wrapper,
                        vitola=vitola,
                        size=size,
                        box_qty=box_qty,
                        price=row.get('price', 0),
                        in_stock=row.get('in_stock', True),
                        current_promotions_applied=row.get('current_promotions_applied', ''),
                        cigar_id=cid,
                        strength=strength,
                        country=country,
                    )
                    # Only include products with valid URLs and prices (exclude empty/zero)
                    if product.brand and product.line and product.size and product.url and product.price_cents > 0:
                        items.append(product)
                except Exception as e:
                    continue
    except Exception as e:
        print(f"Error loading {csv_path}: {e}")

    return items

# In-memory product cache (refreshes every 5 minutes instead of reading 35+ CSVs per request)
_product_cache = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 300  # 5 minutes

# Last-run dedup stats. Surfaces in the smoke-test dashboard so the
# operator can see whether a fresh website-form submission was caught
# by the dedup logic in load_all_products(). Updated on every cache
# refresh (i.e. every CACHE_TTL_SECONDS at most).
_dedup_stats: Dict[str, object] = {
    "last_dropped": 0,
    "last_total_community": 0,
    "last_run_at": None,
}

COMMUNITY_DOWNVOTE_THRESHOLD = 3

def _ensure_community_tables_pg():
    """Create community tables in PostgreSQL analytics DB (persists across deploys)."""
    try:
        conn = get_analytics_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS community_prices (
                id SERIAL PRIMARY KEY,
                cid TEXT NOT NULL,
                url TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                retailer_name TEXT NOT NULL,
                submitted_at TIMESTAMP NOT NULL DEFAULT NOW(),
                active INTEGER NOT NULL DEFAULT 1,
                downvotes INTEGER NOT NULL DEFAULT 0,
                voter_hash TEXT DEFAULT '',
                brand TEXT DEFAULT '',
                line TEXT DEFAULT '',
                wrapper TEXT DEFAULT '',
                vitola TEXT DEFAULT '',
                size TEXT DEFAULT '',
                box_qty INTEGER DEFAULT 20,
                free_shipping INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS community_votes (
                id SERIAL PRIMARY KEY,
                community_price_id INTEGER NOT NULL REFERENCES community_prices(id),
                reason TEXT NOT NULL,
                voter_hash TEXT NOT NULL,
                voted_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error ensuring community tables in PG: {e}")

def _load_community_products():
    """Load active community-submitted prices from PostgreSQL as Product objects."""
    products = []
    try:
        conn = get_analytics_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, cid, url, price_cents, retailer_name,
                   brand, line, wrapper, vitola, size, box_qty, free_shipping
            FROM community_prices
            WHERE active = 1
        """)
        for row in cur.fetchall():
            cp_id, cid, url, price_cents, retailer_name, brand, line, wrapper, vitola, size, box_qty, free_ship = row
            key_prefix = "community_free_" if free_ship else "community_"
            products.append(Product(
                retailer_key=f"{key_prefix}{cp_id}",
                retailer_name=retailer_name or "Community",
                title=f"{brand} {line} {wrapper} {vitola}".strip(),
                url=url,
                brand=brand or "",
                line=line or "",
                wrapper=wrapper or "",
                vitola=vitola or "",
                size=size or "",
                box_qty=box_qty or 20,
                price=price_cents / 100 if price_cents else 0,
                in_stock=True,
                cigar_id=cid,
                community_id=cp_id,
            ))
        conn.close()
    except Exception as e:
        logger.error(f"Error loading community prices from PG: {e}")
    return products

def _load_observed_overlay(window_days: int = 14) -> list:
    """Aggregate recent consumer observations into Product objects.

    Only emits rows for retailers with extractor_status='blocked' (anti-bot
    sites we can't scrape — observations are the source of truth) AND only
    where the URL has been mapped to a CID by the operator. Without a CID
    we can't slot the observation into any /compare row.

    Aggregation strategy (matches the user's stated preference in the
    Sprint 3 brief):
      * window: last ``window_days`` days of quantity_type='box' rows
      * one row per (retailer_key, cigar_id) — newest observation wins
        for price + in_stock + observed_at
      * skips rows where the operator hasn't approved the URL yet
        (cigar_id IS NULL)
      * skips rows where the latest observation is older than the window
    """
    blocked_keys = get_blocked_retailer_keys()
    if not blocked_keys:
        return []
    try:
        conn = get_analytics_conn()
    except Exception as e:
        print(f"_load_observed_overlay: analytics conn failed: {e}")
        return []
    rows = []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT ON (retailer_key, cigar_id)
                   retailer_key, cigar_id, price_cents, in_stock,
                   box_qty, scraped_title, url, observed_at
            FROM observed_prices
            WHERE retailer_key = ANY(%s)
              AND cigar_id IS NOT NULL
              AND quantity_type = 'box'
              AND price_cents IS NOT NULL
              AND observed_at > NOW() - (%s || ' days')::interval
            ORDER BY retailer_key, cigar_id, observed_at DESC
            """,
            (list(blocked_keys), str(window_days)),
        )
        rows = cur.fetchall()
        # Pull per-pair observation counts so the popup can show "based on
        # N reports". Cheap secondary query keyed by the same window.
        cur.execute(
            """
            SELECT retailer_key, cigar_id, COUNT(*)
            FROM observed_prices
            WHERE retailer_key = ANY(%s)
              AND cigar_id IS NOT NULL
              AND quantity_type = 'box'
              AND price_cents IS NOT NULL
              AND observed_at > NOW() - (%s || ' days')::interval
            GROUP BY retailer_key, cigar_id
            """,
            (list(blocked_keys), str(window_days)),
        )
        counts = {(r[0], r[1]): int(r[2]) for r in cur.fetchall()}
    except Exception as e:
        print(f"_load_observed_overlay: query failed: {e}")
        counts = {}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    retailer_name_by_key = {r["key"]: r["name"] for r in RETAILERS}
    master_index = load_master_index()
    products = []
    for r in rows:
        (retailer_key, cigar_id, price_cents, in_stock,
         box_qty, scraped_title, url, observed_at) = r
        try:
            # Master-first metadata (Gap 3). For observed rows, master is
            # the ONLY source of human-readable metadata — the previous
            # CID-string-split heuristic produced ALL-CAPS slugs
            # ("ARTUROFUENTE", "HEMINGWAY") that looked broken in
            # /compare. Master returns the natural-case canonical values.
            master_row = master_index.get(cigar_id or "")
            if master_row:
                brand   = master_row.get("brand", "")
                line    = master_row.get("line", "")
                vitola  = master_row.get("vitola", "")
                size    = master_row.get("size", "")
                wrapper = master_row.get("wrapper", "")
                strength = master_row.get("strength", "")
                country  = master_row.get("country", "")
                master_box_qty = master_row.get("box_qty") or 0
                if master_box_qty:
                    box_qty = master_box_qty
            else:
                # Fallback: parse the CID string. Ugly capitalization but
                # better than empty rows for CIDs not yet in master.
                cid_parts = (cigar_id or "").split("|")
                brand = cid_parts[0] if cid_parts else ""
                line = cid_parts[2] if len(cid_parts) > 2 else ""
                vitola = cid_parts[3] if len(cid_parts) > 3 else ""
                size = cid_parts[5] if len(cid_parts) > 5 else ""
                wrapper = cid_parts[6] if len(cid_parts) > 6 else ""
                strength = ""
                country = ""
            products.append(Product(
                retailer_key=retailer_key,
                retailer_name=retailer_name_by_key.get(retailer_key, retailer_key),
                title=scraped_title or "",
                url=url,
                brand=brand,
                line=line,
                wrapper=wrapper,
                vitola=vitola,
                size=size,
                box_qty=box_qty or 25,
                price=(price_cents or 0) / 100.0,
                in_stock=bool(in_stock) if in_stock is not None else True,
                cigar_id=cigar_id or "",
                price_source="observed",
                observed_at=observed_at.isoformat() if observed_at else None,
                observation_count=counts.get((retailer_key, cigar_id), 1),
                strength=strength,
                country=country,
            ))
        except Exception as e:
            print(f"_load_observed_overlay: skipping row: {e}")
            continue
    return products


def _load_staged_approval_overlay() -> list:
    """Live-overlay pending operator approvals onto /compare for blocked retailers.

    Mirrors _load_observed_overlay but reads from extension_staged_approvals
    (status='pending') instead of observed_prices. Only emits Products for
    BLOCKED retailers — these are the ones where the staging row carries a
    price the operator entered manually. For active retailers the staging
    row has price=NULL (the extractor will fill it in next scrape) so
    there's nothing useful to render until then.

    Why this exists: when the operator approves a URL→CID mapping via the
    extension popup, we want it to show up on cigarpricescout.com
    immediately — no waiting for the local publisher script, git push, or
    Railway redeploy. Pairs with extension_endpoints._load_staged_approval_url_overlay
    which handles the popup-side url_index.
    """
    blocked_keys = get_blocked_retailer_keys()
    if not blocked_keys:
        return []
    try:
        conn = get_analytics_conn()
    except Exception as e:
        print(f"_load_staged_approval_overlay: analytics conn failed: {e}")
        return []
    rows: list = []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT ON (retailer_key, cid)
                   retailer_key, cid, url, title, price, in_stock,
                   box_qty, created_at
            FROM extension_staged_approvals
            WHERE status = 'pending'
              AND retailer_key = ANY(%s)
              AND price IS NOT NULL
            ORDER BY retailer_key, cid, created_at DESC
            """,
            (list(blocked_keys),),
        )
        rows = cur.fetchall()
    except Exception as e:
        print(f"_load_staged_approval_overlay: query failed: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    retailer_name_by_key = {r["key"]: r["name"] for r in RETAILERS}
    master_index = load_master_index()
    products = []
    for r in rows:
        (retailer_key, cigar_id, url, title, price, in_stock,
         box_qty, created_at) = r
        try:
            master_row = master_index.get(cigar_id or "")
            if master_row:
                brand   = master_row.get("brand", "")
                line    = master_row.get("line", "")
                vitola  = master_row.get("vitola", "")
                size    = master_row.get("size", "")
                wrapper = master_row.get("wrapper", "")
                strength = master_row.get("strength", "")
                country  = master_row.get("country", "")
                master_box_qty = master_row.get("box_qty") or 0
                if master_box_qty:
                    box_qty = master_box_qty
            else:
                cid_parts = (cigar_id or "").split("|")
                brand = cid_parts[0] if cid_parts else ""
                line = cid_parts[2] if len(cid_parts) > 2 else ""
                vitola = cid_parts[3] if len(cid_parts) > 3 else ""
                size = cid_parts[5] if len(cid_parts) > 5 else ""
                wrapper = cid_parts[6] if len(cid_parts) > 6 else ""
                strength = ""
                country = ""
            products.append(Product(
                retailer_key=retailer_key,
                retailer_name=retailer_name_by_key.get(retailer_key, retailer_key),
                title=title or "",
                url=url,
                brand=brand,
                line=line,
                wrapper=wrapper,
                vitola=vitola,
                size=size,
                box_qty=box_qty or 25,
                price=float(price) if price is not None else 0.0,
                in_stock=bool(in_stock) if in_stock is not None else True,
                cigar_id=cigar_id or "",
                price_source="operator_approved",
                observed_at=created_at.isoformat() if created_at else None,
                observation_count=1,
                strength=strength,
                country=country,
            ))
        except Exception as e:
            print(f"_load_staged_approval_overlay: skipping row: {e}")
            continue
    return products


def _merge_blocked_overlay_onto_csv_products(
    all_products: list,
    overlay_products: list,
    *,
    price_source: str,
) -> set:
    """Apply overlay price/stock onto existing CSV rows for blocked retailers.

    Historically ``load_all_products`` only *appended* overlay rows when no
    CSV row existed for ``(retailer_key, cigar_id)``. Blocked retailers almost
    always already have a published CSV row, so consumer observations and
    correction snapshots never changed ``in_stock`` / price on /compare.

    Returns a set of ``(retailer_key, canonical_cigar_id)`` keys for overlay
    rows that were merged into at least one CSV product (so the caller can
    avoid appending duplicates).
    """
    if not overlay_products:
        return set()
    blocked = get_blocked_retailer_keys()
    if not blocked:
        return set()
    try:
        from app.cid_matcher import (  # type: ignore
            canonicalize_url,
            canonical_cigar_id_for_comparison,
        )
    except Exception:
        return set()

    merged_keys = set()
    for op in overlay_products:
        rk = getattr(op, "retailer_key", None) or ""
        if rk not in blocked:
            continue
        ocid = canonical_cigar_id_for_comparison(getattr(op, "cigar_id", None) or "")
        if not ocid:
            continue
        ou = canonicalize_url(getattr(op, "url", "") or "") if getattr(op, "url", None) else ""
        candidates = [
            p for p in all_products
            if getattr(p, "retailer_key", None) == rk
            and canonical_cigar_id_for_comparison(getattr(p, "cigar_id", None) or "") == ocid
        ]
        if not candidates:
            continue
        targets = []
        if ou:
            targets = [
                p for p in candidates
                if canonicalize_url(getattr(p, "url", "") or "") == ou
            ]
        if not targets and len(candidates) == 1:
            targets = candidates
        if not targets:
            continue
        opc = int(getattr(op, "price_cents", 0) or 0)
        for p in targets:
            if opc > 0:
                p.price_cents = opc
            p.in_stock = bool(getattr(op, "in_stock", True))
            p.price_source = price_source
            oat = getattr(op, "observed_at", None)
            if oat:
                p.observed_at = oat
            ocnt = getattr(op, "observation_count", None)
            if ocnt is not None:
                p.observation_count = int(ocnt) or p.observation_count
            ot = getattr(op, "title", None)
            if ot:
                p.title = ot
        merged_keys.add((rk, ocid))
    return merged_keys


_RETAILER_LOOKUP_CACHE: Dict[str, Dict[str, str]] = {"by_name": {}, "by_host": {}}


def _norm_retailer_name(name: str) -> str:
    """Lowercase, strip non-alphanumerics. Used to fuzzy-match the
    website form's free-text retailer_name against the canonical RETAILERS
    catalog. 'JR Cigars' / 'jr-cigar' / 'JR  Cigar' all collapse to 'jrcigar'."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _build_retailer_lookups() -> Dict[str, Dict[str, str]]:
    """Cache-once: build {normalized_name -> key} and {hostname -> key} for
    every entry in RETAILERS. Hostname is taken from the explicit
    `hostname` field (for blocked retailers) or inferred from the cached
    extension registry (for retailers with sample URLs in their CSV)."""
    if _RETAILER_LOOKUP_CACHE["by_name"] and _RETAILER_LOOKUP_CACHE["by_host"]:
        return _RETAILER_LOOKUP_CACHE
    by_name: Dict[str, str] = {}
    by_host: Dict[str, str] = {}
    for r in RETAILERS:
        key = r["key"]
        normalized = _norm_retailer_name(r["name"])
        if normalized:
            by_name.setdefault(normalized, key)
        host = (r.get("hostname") or "").strip().lower()
        if host:
            by_host[host] = key
            by_host["www." + host if not host.startswith("www.") else host[4:]] = key
    # Pull the extension's full registry too (covers retailers whose
    # hostname is only present in their CSV's sample URL).
    try:
        from app.extension_endpoints import _cache_state, _refresh_cache  # type: ignore
        _refresh_cache()
        for h, k in (_cache_state.get("retailers") or {}).items():
            by_host.setdefault(h.lower(), k)
    except Exception:
        pass
    _RETAILER_LOOKUP_CACHE["by_name"] = by_name
    _RETAILER_LOOKUP_CACHE["by_host"] = by_host
    return _RETAILER_LOOKUP_CACHE


def _community_canonical_url(url: str) -> Optional[str]:
    """Best-effort URL canonicalization for dedup. Strips trailing slash
    and lowercases the host; falls back to the extension's full canonical
    form when available (handles ?variant=, utm_*, etc.)."""
    if not url:
        return None
    try:
        from app.cid_matcher import canonicalize_url  # type: ignore
        return canonicalize_url(url)
    except Exception:
        try:
            from urllib.parse import urlparse, urlunparse
            u = urlparse(url.strip())
            host = (u.netloc or "").lower()
            path = (u.path or "").rstrip("/")
            return urlunparse((u.scheme.lower() or "https", host, path, "", "", ""))
        except Exception:
            return url.strip().lower()


def _resolve_community_retailer_key(retailer_name: str, url: str) -> Optional[str]:
    """Map a website-form community submission to a canonical retailer_key.

    Prefers URL hostname (authoritative — the submitter pasted a real
    retailer URL) and falls back to normalized retailer_name (for cases
    where the URL is malformed or pointing to a redirect).
    """
    lookups = _build_retailer_lookups()
    if url:
        try:
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        if host:
            if host in lookups["by_host"]:
                return lookups["by_host"][host]
            if host.startswith("www.") and host[4:] in lookups["by_host"]:
                return lookups["by_host"][host[4:]]
    if retailer_name:
        norm = _norm_retailer_name(retailer_name)
        if norm:
            # Exact match first.
            if norm in lookups["by_name"]:
                return lookups["by_name"][norm]
            # Singular/plural variance: 'jrcigars' (form) vs 'jrcigar' (catalog).
            # Cheap, catches 90% of the divergence we actually see.
            stripped = norm.rstrip("s")
            for cand_norm, key in lookups["by_name"].items():
                if cand_norm.rstrip("s") == stripped:
                    return key
    return None


def load_all_products():
    """Load all products from all retailer CSV files + community submissions, with in-memory caching"""
    now = time.time()
    if _product_cache["data"] is not None and (now - _product_cache["timestamp"]) < CACHE_TTL_SECONDS:
        return _product_cache["data"]

    # Build the master metadata index ONCE per cache refresh and pass it
    # into every per-retailer load_csv call. This avoids re-parsing
    # master_cigars.csv 35+ times (once per retailer) on a cold cache.
    master_index = load_master_index()

    all_products = []
    for retailer in RETAILERS:
        products = load_csv(retailer["csv"], retailer["key"], retailer["name"], master_index=master_index)
        all_products.extend(products)

    # Overlay consumer observations on top of CSV data for blocked retailers.
    # Rows in ``observed_prices`` must *merge into* existing CSV Products when
    # the same (retailer_key, cigar_id) already exists — otherwise stale CSV
    # in_stock/price would never reflect extension observations or corrections.
    observed_products = _load_observed_overlay()
    if observed_products:
        merged_obs = _merge_blocked_overlay_onto_csv_products(
            all_products, observed_products, price_source="observed",
        )
        try:
            from app.cid_matcher import canonical_cigar_id_for_comparison  # type: ignore
        except Exception:
            canonical_cigar_id_for_comparison = lambda x: x or ""  # type: ignore
        for op in observed_products:
            key = (
                op.retailer_key,
                canonical_cigar_id_for_comparison(op.cigar_id or ""),
            )
            if key not in merged_obs:
                all_products.append(op)

    # Pending operator approvals: merge over CSV (and over observed fields)
    # for blocked retailers so manual approvals and community resolutions
    # refresh price/stock immediately on /compare.
    staged_approval_products = _load_staged_approval_overlay()
    if staged_approval_products:
        merged_staged = _merge_blocked_overlay_onto_csv_products(
            all_products, staged_approval_products, price_source="operator_approved",
        )
        try:
            from app.cid_matcher import canonical_cigar_id_for_comparison  # type: ignore
        except Exception:
            canonical_cigar_id_for_comparison = lambda x: x or ""  # type: ignore
        for sp in staged_approval_products:
            key = (
                sp.retailer_key,
                canonical_cigar_id_for_comparison(sp.cigar_id or ""),
            )
            if key not in merged_staged:
                all_products.append(sp)

    community_products = _load_community_products()

    # Backfill missing size/CID on community products from CSV data
    if community_products:
        csv_lookup = {}
        for p in all_products:
            if p.brand and p.line and p.wrapper and p.vitola and p.size:
                key = (p.brand.lower(), p.line.lower(), p.wrapper.lower(), p.vitola.lower(), p.box_qty)
                if key not in csv_lookup:
                    csv_lookup[key] = p
        for cp in community_products:
            key = (cp.brand.lower(), cp.line.lower(), cp.wrapper.lower(), cp.vitola.lower(), cp.box_qty)
            match = csv_lookup.get(key)
            if match:
                if not cp.size:
                    cp.size = match.size
                if not cp.cigar_id:
                    cp.cigar_id = match.cigar_id

    # Dedup website-form community submissions against CSV + observed.
    # The website form has been around longer than the extension and uses
    # its own per-submission retailer_key ('community_42'), so naive
    # extension.extend(community_products) used to show "JR Cigar" twice
    # on /compare — once from the extension's observed overlay, once as
    # "community_42 — JR Cigar". We drop the community row when EITHER
    # of two signals matches an existing CSV/observed row:
    #   1. Same canonical URL (strongest — exact same product page)
    #   2. Same (retailer_key, cigar_id) — the community submission
    #      maps to a known retailer (via URL hostname or fuzzy name
    #      match) and we already have data for that retailer + cigar.
    # CSV/observed wins on collision: CSV is operator-curated, observed
    # has a timestamp the user can judge for freshness; legacy community
    # rows have no surfaced provenance.
    existing_urls = set()
    existing_pairs = set()
    for p in all_products:
        canon = _community_canonical_url(p.url)
        if canon:
            existing_urls.add(canon)
        if p.cigar_id:
            existing_pairs.add((p.retailer_key, p.cigar_id))

    deduped_community = []
    dropped = 0
    for cp in community_products:
        canon = _community_canonical_url(cp.url)
        if canon and canon in existing_urls:
            dropped += 1
            continue
        if cp.cigar_id:
            mapped_key = _resolve_community_retailer_key(cp.retailer_name, cp.url)
            if mapped_key and (mapped_key, cp.cigar_id) in existing_pairs:
                dropped += 1
                continue
        deduped_community.append(cp)
    if dropped:
        logger.info(
            "load_all_products: dropped %d community submission(s) that duplicated CSV/observed rows",
            dropped,
        )
    all_products.extend(deduped_community)

    _dedup_stats["last_dropped"] = dropped
    _dedup_stats["last_total_community"] = len(community_products)
    _dedup_stats["last_run_at"] = datetime.now().isoformat()
    
    _product_cache["data"] = all_products
    _product_cache["timestamp"] = now
    return all_products


_sitemap_cigar_pairs_cache = {"pairs": None, "_prod_ts": None}


def _get_sorted_cigar_sitemap_pairs():
    """Unique (brand_slug, line_slug) pairs; invalidated whenever load_all_products() refreshes."""
    pts = _product_cache["timestamp"]
    c = _sitemap_cigar_pairs_cache
    if c["pairs"] is not None and c.get("_prod_ts") == pts:
        return c["pairs"]

    all_products = load_all_products()
    cigar_pages = set()
    for p in all_products:
        if not p.brand or not p.line:
            continue
        brand_slug = p.brand.lower().replace(' ', '-').replace('&', 'and')
        line_slug = normalize_line_slug(p.line)
        cigar_pages.add((brand_slug, line_slug))
    pairs = sorted(cigar_pages, key=lambda x: (x[0], x[1]))
    c["pairs"] = pairs
    c["_prod_ts"] = pts
    return pairs


def load_master_wrapper_aliases():
    """Load wrapper aliases from master_cigars.db (SQLite) for lookup"""
    # Try multiple possible paths for the master database
    possible_paths = [
        Path("data/master_cigars.db"),
        Path("../data/master_cigars.db") if os.path.exists("../data") else Path("data/master_cigars.db"),
        Path(f"{STATIC_PATH}/data/master_cigars.db")
    ]
    
    master_db = None
    for path in possible_paths:
        if path.exists():
            master_db = path
            break
    
    if not master_db:
        print(f"Warning: Master database not found in any of these locations: {[str(p) for p in possible_paths]}")
        return {}
    
    print(f"Loading wrapper aliases from: {master_db}")
    wrapper_aliases = {}
    
    try:
        conn = sqlite3.connect(master_db)
        cursor = conn.execute("SELECT brand, line, wrapper, wrapper_alias FROM cigars WHERE wrapper_alias IS NOT NULL AND wrapper_alias != ''")
        rows_processed = 0
        aliases_found = 0
        
        for row in cursor:
            rows_processed += 1
            brand, line, wrapper, wrapper_alias = row
            wrapper = (wrapper or '').strip()
            wrapper_alias = (wrapper_alias or '').strip()
            brand = (brand or '').strip()
            line = (line or '').strip()
            
            if wrapper and wrapper_alias and wrapper_alias != wrapper:
                aliases_found += 1
                # Brand-line scoped, BOTH directions. load_master_index
                # picks `wrapper_alias or wrapper_canon` for product.wrapper,
                # so the lookup might arrive with either the canon ("Maduro")
                # or the alias ("Connecticut Broadleaf") in hand. Indexing
                # both ways guarantees the right pair is found within the
                # brand-line context.
                canon_key = f"{brand}|{line}|{wrapper}"
                alias_key = f"{brand}|{line}|{wrapper_alias}"
                wrapper_aliases[canon_key] = wrapper_alias
                wrapper_aliases[alias_key] = wrapper

                # NOTE: deliberately NO global (unscoped) fallback. A generic
                # canon like "Natural" maps to different specific aliases for
                # different brands (Padron "Natural"->"Sun Grown" vs Punch
                # Knuckle Buster "Natural"->"Nicaraguan Habano"), so an
                # unscoped dict inevitably leaks one brand's mapping into
                # another. Brand-line scoping is what makes the alias
                # system honest.

                if aliases_found <= 5:
                    print(f"  Added alias: {wrapper} <-> {wrapper_alias} (Brand: {brand}, Line: {line})")
        
        conn.close()
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

def load_seo_content():
    """Load SEO content from CSV file"""
    seo_data = {}
    seo_file = Path(PROJECT_ROOT / "data" / "seo_content_top_cigars.csv")
    
    if not seo_file.exists():
        print(f"SEO content file not found: {seo_file}")
        return seo_data
    
    try:
        with open(seo_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                brand = row.get('Brand', '').strip()
                line = row.get('Line', '').strip()
                if brand and line:
                    key = f"{brand.lower()}|{line.lower()}"
                    seo_data[key] = {
                        'description': row.get('description', ''),
                        'tasting_notes': row.get('tasting_notes', ''),
                        'best_for': row.get('best_for', ''),
                        'rating_average': row.get('rating_average', ''),
                        'review_count': row.get('review_count', '')
                    }
        print(f"Loaded SEO content for {len(seo_data)} cigars")
    except Exception as e:
        print(f"Error loading SEO content: {e}")
    
    return seo_data

def has_quality_seo_data(brand, line, seo_data):
    """Check if cigar has quality SEO data (not generic fallback)"""
    key = f"{brand.lower()}|{line.lower()}"
    data = seo_data.get(key, {})
    
    # Check if description exists and is substantial (>50 characters)
    description = data.get('description', '').strip()
    if len(description) > 50:
        return True
    
    return False

def generate_faq_answers(brand, line, seo_data):
    """Generate cigar-specific FAQ answers from SEO data"""
    key = f"{brand.lower()}|{line.lower()}"
    data = seo_data.get(key, {})
    
    # FAQ 1: What makes this cigar special?
    faq_1 = data.get('description', f"The {brand} {line} is a premium handmade cigar known for its quality construction and consistent performance.")
    
    # FAQ 2: What wrappers are available?
    # Try to extract wrapper info from products database
    all_products = load_all_products()
    wrappers = set()
    vitolas = set()
    for p in all_products:
        if p.brand.lower() == brand.lower() and p.line.lower() == line.lower():
            if p.wrapper:
                wrappers.add(p.wrapper)
            if p.vitola:
                vitolas.add(p.vitola)
    
    if wrappers:
        wrapper_list = sorted(list(wrappers))
        if len(wrapper_list) == 1:
            faq_2 = f"The {brand} {line} is available in {wrapper_list[0]} wrapper."
        else:
            faq_2 = f"The {brand} {line} is available in multiple wrappers including {', '.join(wrapper_list[:-1])}, and {wrapper_list[-1]}."
    else:
        faq_2 = f"The {brand} {line} is available in various wrapper options. Check our comparison table above for specific wrapper availability."
    
    # FAQ 3: What vitolas are available?
    if vitolas:
        vitola_list = sorted(list(vitolas))[:5]  # Limit to 5 to avoid super long text
        if len(vitola_list) == 1:
            faq_3 = f"Available vitola: {vitola_list[0]}."
        else:
            faq_3 = f"Popular vitolas include {', '.join(vitola_list[:-1])}, and {vitola_list[-1]}."
            if len(vitolas) > 5:
                faq_3 += " See the comparison table above for all available sizes."
    else:
        faq_3 = f"The {brand} {line} is available in multiple vitola sizes to suit different smoking preferences."
    
    # Add tasting notes and best_for info if available
    tasting_notes = data.get('tasting_notes', '')
    if tasting_notes:
        faq_1 += f" Flavor profile includes notes of {tasting_notes}."
    
    best_for = data.get('best_for', '')
    if best_for:
        faq_1 += f" Best for {best_for}."
    
    return faq_1, faq_2, faq_3

MIN_RETAILERS_FOR_COMPARISON = 3

def build_options_tree():
    """Build the brand -> line -> wrapper -> vitola/size tree for dropdowns with wrapper alias support.
    
    Only includes brand/line combinations carried by at least MIN_RETAILERS_FOR_COMPARISON
    distinct retailers so every dropdown selection leads to a meaningful comparison.
    Variation-level filtering ensures individual wrapper/vitola/box_qty combos also
    meet the retailer threshold before appearing in dropdowns.
    """
    products = load_all_products()
    wrapper_aliases = load_master_wrapper_aliases()
    
    print(f"Building options tree with {len(products)} products and {len(wrapper_aliases)} wrapper aliases")
    
    # Pre-compute retailer counts per brand/line
    line_retailers: dict[tuple, set] = {}
    # Pre-compute retailer counts per specific variation
    variation_retailers: dict[tuple, set] = {}
    for p in products:
        if p.brand:
            key = (p.brand, p.line)
            line_retailers.setdefault(key, set()).add(p.retailer_key)
            vkey = (p.brand, p.line, p.wrapper or "", p.vitola or "", p.box_qty)
            variation_retailers.setdefault(vkey, set()).add(p.retailer_key)
    
    tree = {}
    aliases_used = 0
    skipped_lines = 0
    skipped_variations = 0
    
    for product in products:
        if not product.brand:
            continue
        
        if len(line_retailers.get((product.brand, product.line), set())) < MIN_RETAILERS_FOR_COMPARISON:
            skipped_lines += 1
            continue
        
        vkey = (product.brand, product.line, product.wrapper or "", product.vitola or "", product.box_qty)
        if len(variation_retailers.get(vkey, set())) < MIN_RETAILERS_FOR_COMPARISON:
            skipped_variations += 1
            continue
        
        if product.brand not in tree:
            tree[product.brand] = {}
        
        if product.line not in tree[product.brand]:
            tree[product.brand][product.line] = {}
        
        wrapper_alias = get_wrapper_alias(product.wrapper, product.brand, product.line, wrapper_aliases)
        if wrapper_alias:
            aliases_used += 1
        
        wrapper_key = product.wrapper or "No Wrapper Specified"
        if wrapper_key not in tree[product.brand][product.line]:
            tree[product.brand][product.line][wrapper_key] = {
                'vitolas': set(),
                'sizes': set(),
                'box_qtys': set(),
                'vitola_box_qtys': {},
                'wrapper_alias': wrapper_alias
            }
        
        if product.vitola:
            tree[product.brand][product.line][wrapper_key]['vitolas'].add(product.vitola)
            if product.vitola not in tree[product.brand][product.line][wrapper_key]['vitola_box_qtys']:
                tree[product.brand][product.line][wrapper_key]['vitola_box_qtys'][product.vitola] = set()
            tree[product.brand][product.line][wrapper_key]['vitola_box_qtys'][product.vitola].add(product.box_qty)
        tree[product.brand][product.line][wrapper_key]['sizes'].add(product.size)
        tree[product.brand][product.line][wrapper_key]['box_qtys'].add(product.box_qty)
    
    # Prune empty branches: remove wrappers with no vitolas, lines with no wrappers
    for brand_name in list(tree.keys()):
        for line_name in list(tree[brand_name].keys()):
            for wrapper_name in list(tree[brand_name][line_name].keys()):
                if not tree[brand_name][line_name][wrapper_name]['vitolas']:
                    del tree[brand_name][line_name][wrapper_name]
            if not tree[brand_name][line_name]:
                del tree[brand_name][line_name]
        if not tree[brand_name]:
            del tree[brand_name]
    
    print(f"Aliases used during tree building: {aliases_used}, products skipped (< {MIN_RETAILERS_FOR_COMPARISON} retailers): {skipped_lines}, variations skipped: {skipped_variations}")
    
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
                
                vitola_box_qtys = {}
                for v, qtys in wrapper_data.get('vitola_box_qtys', {}).items():
                    vitola_box_qtys[v] = sorted(list(qtys))

                wrappers.append({
                    "wrapper": wrapper_name if wrapper_name != "No Wrapper Specified" else "",
                    "wrapper_alias": wrapper_alias_value,
                    "vitolas": vitolas,
                    "sizes": sizes,
                    "box_qtys": sorted(list(wrapper_data['box_qtys'])),
                    "vitola_box_qtys": vitola_box_qtys
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
    box_qty: Optional[int] = Query(None, description="Box quantity filter"),
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
        
        # Size filter (optional)
        if size and size.strip():
            if p.size.lower() != size.lower():
                continue
        
        # Box quantity filter
        if box_qty is not None:
            if p.box_qty != box_qty:
                continue
        
        matching_products.append(p)

    # Filter by authorized dealers if requested
    if authorized_only:
        authorized_retailer_keys = {r["key"] for r in RETAILERS if r["authorized"]}
        matching_products = [p for p in matching_products if p.retailer_key in authorized_retailer_keys]

    # Require minimum distinct retailers for a meaningful comparison
    distinct_retailers = {p.retailer_key for p in matching_products}
    if len(distinct_retailers) < MIN_RETAILERS_FOR_COMPARISON:
        return {
            "brand": brand,
            "line": line,
            "wrapper": wrapper,
            "vitola": vitola,
            "size": size,
            "state": state,
            "results": [],
            "reason": f"Only {len(distinct_retailers)} retailer(s) carry this cigar. At least {MIN_RETAILERS_FOR_COMPARISON} are needed for a comparison."
        }

    # Calculate price context (median comparison) - AFTER filtering
    if len(matching_products) >= 3:
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
            "retailer_key": product.retailer_key,
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
            "url": add_tracking_params(product.url, brand=brand, line=line, retailer_key=product.retailer_key),
            "oos": not product.in_stock,
            "cheapest": False,
            "authorized": is_authorized,
            "community": product.community_id is not None,
            "community_id": product.community_id,
            "price_context": price_context,
            "current_promotions_applied": product.current_promotions_applied,
            # Sprint 3 provenance: when this row was sourced from consumer
            # observations (anti-bot retailer), expose the latest-seen date
            # so the UI can render an absolute "Last observed YYYY-MM-DD"
            # stamp. Rows sourced from a per-retailer CSV are 'csv' with
            # no per-row timestamp (CSVs roll over together).
            "price_source": getattr(product, "price_source", "csv"),
            "observed_at": getattr(product, "observed_at", None),
            "observation_count": getattr(product, "observation_count", 0),
            # Gap 3: master-only fields surfaced for the first time.
            # Empty strings when a CID isn't in master yet (in-flight new
            # CID). Consumed by /compare and the public comparison API;
            # template surfaces these where shopper-relevant.
            "strength": getattr(product, "strength", "") or "",
            "country": getattr(product, "country", "") or "",
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

    from collections import defaultdict
    variation_retailers = defaultdict(set)
    for p in matching_products:
        key = (p.wrapper, p.vitola, p.size, p.box_qty)
        variation_retailers[key].add(p.retailer_key)
    comparable_variations = {k for k, v in variation_retailers.items() if len(v) >= MIN_RETAILERS_FOR_COMPARISON}
    matching_products = [
        p for p in matching_products
        if (p.wrapper, p.vitola, p.size, p.box_qty) in comparable_variations
    ]

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

    # Require at least 3 unique retailers with prices for a meaningful comparison
    unique_retailers_with_prices = {p.retailer_key for p in matching_products if p.price_cents}
    
    if not matching_products or len(unique_retailers_with_prices) < 3:
        return {
            "brand": brand,
            "line": line,
            "state": state,
            "results": []
        }

    # Calculate delivered prices and build results
    results = []
    in_stock_prices = []

    # Pull the master index once for wrapper-display lookups below. The
    # cigar landing page (this endpoint's only consumer) wants the
    # combined "alias (canon)" form — e.g. "Maduro (Connecticut Broadleaf)"
    # — so a shopper who knows the cigar by either term still finds it.
    # /compare (used by the main page search) stays on the single-value
    # wrapper for filter-equality compatibility.
    master_index_for_display = load_master_index()

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
        promo_discount = None
        promo_code = None
        if product.current_promotions_applied:
            promo_parts = product.current_promotions_applied.split('|')
            promo_price_text = promo_parts[0]  # "$139.80 [25% off]"
            promo_code = promo_parts[1] if len(promo_parts) > 1 else None
            
            # Extract the discount percentage if present
            pct_match = re.search(r'\[(\d+)%', promo_price_text)
            if pct_match:
                promo_discount = int(pct_match.group(1))
            
            # Extract the discounted price
            promo_price_match = promo_price_text.split(' [')[0].replace('$', '')
            try:
                promo_price_cents = int(float(promo_price_match) * 100)
                final_delivered_cents = promo_price_cents + shipping_cents + tax_cents
            except:
                final_delivered_cents = delivered_cents
        else:
            final_delivered_cents = delivered_cents

        # Combined "alias (canon)" wrapper display for the cigar landing
        # page. Falls back to product.wrapper when the master row is
        # missing (in-flight CIDs not yet promoted to master) or when
        # one of the two fields is empty.
        master_row_for_display = master_index_for_display.get(product.cigar_id or "")
        if master_row_for_display:
            wrapper_display = _format_wrapper_display(
                master_row_for_display.get("wrapper_alias", ""),
                master_row_for_display.get("wrapper_canon", ""),
            ) or product.wrapper
        else:
            wrapper_display = product.wrapper

        result = {
            "retailer": product.retailer_name,
            "retailer_key": product.retailer_key,
            "product": product_name,
            "wrapper": wrapper_display,
            "vitola": product.vitola,
            "size": product.size,
            "box_qty": product.box_qty,
            "base": f"${base_cents/100:.2f}",
            "shipping": f"${shipping_cents/100:.2f}",
            "tax": f"${tax_cents/100:.2f}",
            "delivered": f"${delivered_cents/100:.2f}",
            "promo": f"{promo_discount}% off" if promo_discount else None,
            "promo_code": promo_code,
            "delivered_after_promo": f"${final_delivered_cents/100:.2f}",
            "url": add_tracking_params(product.url, brand=brand, line=line, retailer_key=product.retailer_key),
            "oos": not product.in_stock,
            "cheapest": False,
            "authorized": is_authorized,
            "community": product.community_id is not None,
            "community_id": product.community_id,
            "price_context": price_context,
            "current_promotions_applied": product.current_promotions_applied,
            "strength": getattr(product, "strength", "") or "",
            "country": getattr(product, "country", "") or "",
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

RETAILER_KEY_TO_NAME = {r["key"]: r["name"] for r in RETAILERS}

@app.get("/api/price-history")
def price_history(
    brand: str = Query(...),
    line: str = Query(...),
    wrapper: str = Query(""),
    vitola: str = Query(""),
):
    """Return historical price data for a specific cigar variation, grouped by retailer."""
    all_products = load_all_products()
    matching_cids = set()

    for p in all_products:
        if p.brand.lower() != brand.lower() or p.line.lower() != line.lower():
            continue
        if wrapper and p.wrapper.lower() != wrapper.lower():
            continue
        if vitola and p.vitola.lower() != vitola.lower():
            continue
        matching_cids.add(p.cigar_id)

    if not matching_cids:
        return {"days": 0, "retailers": {}}

    hist_db_path = Path("data/historical_prices.db")
    if not hist_db_path.exists():
        return {"days": 0, "retailers": {}}

    conn = sqlite3.connect(str(hist_db_path))
    cur = conn.cursor()

    placeholders = ",".join("?" for _ in matching_cids)
    cur.execute(f"""
        SELECT retailer, date, price
        FROM price_history
        WHERE cigar_id IN ({placeholders}) AND price > 0
        ORDER BY date ASC
    """, list(matching_cids))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"days": 0, "retailers": {}}

    retailers_data = {}
    all_dates = set()

    for retailer_key, date_str, price in rows:
        name = RETAILER_KEY_TO_NAME.get(retailer_key, retailer_key)
        if name not in retailers_data:
            retailers_data[name] = {}
        retailers_data[name][date_str] = price
        all_dates.add(date_str)

    sorted_dates = sorted(all_dates)
    num_days = max(1, (datetime.strptime(sorted_dates[-1], "%Y-%m-%d") - datetime.strptime(sorted_dates[0], "%Y-%m-%d")).days)

    all_prices = [p for r in retailers_data.values() for p in r.values()]
    avg_price = round(sum(all_prices) / len(all_prices), 2) if all_prices else 0

    low_price = min(all_prices) if all_prices else 0
    high_price = max(all_prices) if all_prices else 0
    low_date = None
    low_retailer = None
    high_retailer = None
    for name, dates in retailers_data.items():
        for d, p in dates.items():
            if p == low_price and low_date is None:
                low_date = d
                low_retailer = name
            if p == high_price and high_retailer is None:
                high_retailer = name

    retailer_series = {}
    for name, date_prices in retailers_data.items():
        points = [{"date": d, "price": date_prices[d]} for d in sorted_dates if d in date_prices]
        if len(points) >= 7:
            retailer_series[name] = points

    top_retailers = sorted(retailer_series.keys(), key=lambda n: min(p["price"] for p in retailer_series[n]))[:5]
    filtered_series = {n: retailer_series[n] for n in top_retailers}

    # Buying recommendation thresholds (25th / 75th percentile)
    recommendation = None
    if len(all_prices) >= 20:
        sorted_prices = sorted(all_prices)
        n = len(sorted_prices)
        p25 = sorted_prices[int(n * 0.25)]
        p75 = sorted_prices[int(n * 0.75)]
        recommendation = {
            "buy_below": round(p25, 2),
            "fair_up_to": round(p75, 2),
            "data_points": n,
        }

    return {
        "days": num_days,
        "dates": sorted_dates,
        "avg_price": avg_price,
        "low_price": low_price,
        "low_date": low_date,
        "low_retailer": low_retailer,
        "high_price": high_price,
        "high_retailer": high_retailer,
        "retailers": filtered_series,
        "recommendation": recommendation,
    }


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

@app.get("/deals.html")
async def deals_page():
    return FileResponse(f"{STATIC_PATH}/deals.html")

@app.get("/submit-deal.html")
async def submit_deal_page():
    return FileResponse(f"{STATIC_PATH}/submit-deal.html")

# SEO: Sitemap index (/sitemap.xml) + child maps — avoids truncating cigar URLs at an arbitrary cap
STATIC_SITEMAP_PAGES = [
    {"url": "/", "priority": "1.0", "changefreq": "daily"},
    {"url": "/about.html", "priority": "0.8", "changefreq": "monthly"},
    {"url": "/contact.html", "priority": "0.7", "changefreq": "monthly"},
    {"url": "/privacy-policy.html", "priority": "0.5", "changefreq": "yearly"},
    {"url": "/terms-of-service.html", "priority": "0.5", "changefreq": "yearly"},
    {"url": "/request-box-pricing.html", "priority": "0.7", "changefreq": "monthly"},
    {"url": "/deals.html", "priority": "0.9", "changefreq": "daily"},
    {"url": "/submit-deal.html", "priority": "0.6", "changefreq": "monthly"},
]


@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap_index():
    base_url = "https://cigarpricescout.com"
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <sitemap><loc>{base_url}/sitemap-static.xml</loc><lastmod>{today}</lastmod></sitemap>',
    ]
    try:
        if _get_sorted_cigar_sitemap_pairs():
            lines.append(f'  <sitemap><loc>{base_url}/sitemap-cigars.xml</loc><lastmod>{today}</lastmod></sitemap>')
    except Exception as e:
        print(f"[sitemap] Error listing cigar pages for index: {e}")
    lines.append("</sitemapindex>")
    return "\n".join(lines) + "\n"


@app.get("/sitemap-static.xml", response_class=PlainTextResponse)
async def sitemap_static():
    base_url = "https://cigarpricescout.com"
    today = datetime.now().strftime("%Y-%m-%d")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for page in STATIC_SITEMAP_PAGES:
        parts.extend([
            "  <url>",
            f'    <loc>{base_url}{page["url"]}</loc>',
            f'    <lastmod>{today}</lastmod>',
            f'    <changefreq>{page["changefreq"]}</changefreq>',
            f'    <priority>{page["priority"]}</priority>',
            "  </url>",
        ])
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


@app.get("/sitemap-cigars.xml", response_class=PlainTextResponse)
async def sitemap_cigars():
    base_url = "https://cigarpricescout.com"
    today = datetime.now().strftime("%Y-%m-%d")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    try:
        for brand_slug, line_slug in _get_sorted_cigar_sitemap_pairs():
            parts.extend([
                "  <url>",
                f"    <loc>{base_url}/cigars/{brand_slug}/{line_slug}</loc>",
                f"    <lastmod>{today}</lastmod>",
                "    <changefreq>weekly</changefreq>",
                "    <priority>0.8</priority>",
                "  </url>",
            ])
    except Exception as e:
        print(f"[sitemap] Error building cigar sitemap: {e}")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"

# SEO: robots.txt (serve from file, but ensure it exists)
@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return FileResponse(f"{STATIC_PATH}/robots.txt")

@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt():
    return FileResponse(f"{STATIC_PATH}/llms.txt", media_type="text/plain")

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

def _build_related_releases_html(
    all_products,
    canonical_brand: str,
    current_line_slug: str,
    brand_slug: str,
) -> tuple[str, str]:
    """Build the Related Releases button + collapsible panel HTML for a cigar page.

    Returns ("", "") when there aren't at least 2 qualifying sibling lines, so both
    template placeholders collapse to nothing and the page looks identical to before.

    A sibling line qualifies when:
      - same brand (case-insensitive match against the canonical brand)
      - different line slug from the current page
      - has at least one (wrapper, vitola, box_qty) variation with
        >= MIN_RETAILERS_FOR_COMPARISON distinct retailers (mirrors the 404 check in
        the route, guaranteeing every sibling link lands on a valid comparison page)
    """
    from collections import defaultdict

    canonical_brand_lower = canonical_brand.lower()
    variation_retailers: dict[tuple, set] = defaultdict(set)
    line_info: dict[str, dict] = defaultdict(
        lambda: {
            "line_display": None,
            "retailers": set(),
            "vitolas": set(),
            "prices": [],
            "wrapper_counts": defaultdict(int),
        }
    )

    for p in all_products:
        if p.brand.lower() != canonical_brand_lower:
            continue
        p_line_slug = normalize_line_slug(p.line)
        if p_line_slug == current_line_slug:
            continue

        variation_retailers[(p.line, p.wrapper, p.vitola, p.box_qty)].add(p.retailer_key)

        info = line_info[p.line]
        if info["line_display"] is None:
            info["line_display"] = p.line
        info["retailers"].add(p.retailer_key)
        info["vitolas"].add((p.wrapper, p.vitola, p.box_qty))
        if p.price_cents:
            info["prices"].append(p.price_cents / 100)
        if p.wrapper:
            info["wrapper_counts"][p.wrapper] += 1

    valid_lines = {
        line_key
        for (line_key, _w, _v, _b), retailers in variation_retailers.items()
        if len(retailers) >= MIN_RETAILERS_FOR_COMPARISON
    }

    siblings = []
    for line_key in valid_lines:
        info = line_info[line_key]
        if not info["prices"]:
            continue
        most_common_wrapper = (
            max(info["wrapper_counts"].items(), key=lambda kv: kv[1])[0]
            if info["wrapper_counts"]
            else ""
        )
        siblings.append(
            {
                "line_display": info["line_display"],
                "line_slug": normalize_line_slug(info["line_display"]),
                "retailer_count": len(info["retailers"]),
                "vitola_count": len(info["vitolas"]),
                "min_price": min(info["prices"]),
                "wrapper": most_common_wrapper,
            }
        )

    siblings.sort(key=lambda s: (-s["retailer_count"], -s["vitola_count"], s["line_display"]))
    top_siblings = siblings[:3]

    if len(top_siblings) < 2:
        return "", ""

    button_html = (
        '<button\n'
        '            id="family-btn"\n'
        '            onclick="toggleFamily()"\n'
        '            class="w-full md:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 border border-brand-500 rounded-xl bg-white text-brand-500 font-semibold hover:bg-brand-50 transition-all text-sm"\n'
        '          >\n'
        '            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>'
        '<polyline points="2 17 12 22 22 17"></polyline>'
        '<polyline points="2 12 12 17 22 12"></polyline></svg>\n'
        '            <span id="family-btn-text">Related Releases</span>\n'
        '            <span id="family-arrow" class="text-xs">&#9660;</span>\n'
        '          </button>'
    )

    brand_display_for_heading = canonical_brand.strip()

    cards_html_parts = []
    for s in top_siblings:
        price_str = f"${s['min_price']:,.2f}"
        vitola_word = "vitola" if s["vitola_count"] == 1 else "vitolas"
        retailer_word = "retailer" if s["retailer_count"] == 1 else "retailers"
        wrapper_badge = (
            f'<span class="inline-block text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-semibold">{_escape_html(s["wrapper"])}</span>'
            if s["wrapper"]
            else ""
        )
        cards_html_parts.append(
            f'''<a href="/cigars/{brand_slug}/{s["line_slug"]}"
             class="block bg-brand-50 hover:bg-white border border-gray-200 hover:border-brand-500 rounded-xl p-5 transition-all hover:shadow-md group">
            <div class="flex items-start justify-between mb-2">
              <h4 class="font-display font-semibold text-lg text-ink group-hover:text-brand-500 transition-colors">{_escape_html(s["line_display"])}</h4>
            </div>
            <div class="flex flex-wrap gap-1.5 mb-3">
              {wrapper_badge}
            </div>
            <div class="text-sm text-muted mb-1">{s["vitola_count"]} {vitola_word} &middot; {s["retailer_count"]} {retailer_word}</div>
            <div class="flex items-end justify-between">
              <div>
                <div class="text-xs text-muted uppercase tracking-wider">From</div>
                <div class="text-xl font-bold text-emerald-600">{price_str}</div>
              </div>
              <span class="text-brand-500 font-semibold text-sm group-hover:translate-x-1 transition-transform">Compare &rarr;</span>
            </div>
          </a>'''
        )

    cards_html = "\n\n          ".join(cards_html_parts)

    section_html = f'''<!-- Related Releases Section (collapsed by default) -->
          <div id="familySection" style="display: none;" class="w-full md:basis-full md:order-last">
            <div class="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
              <h3 class="font-display font-semibold text-xl text-brand-500 text-center mb-1">Other {_escape_html(brand_display_for_heading)} Releases</h3>
              <p class="text-center text-sm text-muted italic mb-5">Prices are the current lowest advertised box price across tracked retailers.</p>

              <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            {cards_html}
              </div>

              <div class="text-center mt-6">
                <a href="/" class="inline-flex items-center gap-1 text-brand-500 hover:text-brand-600 font-semibold text-sm underline-offset-4 hover:underline">
                  View all cigars on cigarpricescout.com &rarr;
                </a>
              </div>
            </div>
          </div>'''

    return button_html, section_html


def _escape_html(s: str) -> str:
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# --- Outbound-link attribution (UTM + per-retailer affiliate) ----------------
# UTM tags prove to retailers that we sent them traffic. When we get approved
# for an affiliate program, add an entry to AFFILIATE_PARAMS below and the same
# wrapper will inject the affiliate tracking params in addition to UTM. Until
# then, UTM alone is enough evidence to negotiate direct CPA deals — retailers
# can see the inbound traffic in their own GA/Shopify analytics.
AFFILIATE_PARAMS: dict[str, dict[str, str]] = {
    # Populate as retailer programs get approved. Example shape:
    # "famous": {"refid": "cigarpricescout"},
    # "jrcigar": {"AID": "1234567", "PID": "8765432"},
}


def add_tracking_params(
    url: str,
    brand: str = "",
    line: str = "",
    retailer_key: str = "",
) -> str:
    """Wrap an outbound retailer URL with UTM + (if available) affiliate params.

    - Preserves any existing query string and fragment on the original URL.
    - Never overwrites a param the retailer URL already carries (defensive).
    - Falls back to the original URL on any parse error so broken wrapping
      never blocks a user from reaching a retailer.

    UTM schema:
      utm_source   = cigarpricescout.com          (who sent them)
      utm_medium   = price_comparison             (channel type)
      utm_campaign = <brand-slug>                 (aggregate by brand)
      utm_content  = <line-slug>                  (granular per cigar line)
    """
    if not url or not isinstance(url, str):
        return url
    if not url.startswith(("http://", "https://")):
        return url
    try:
        parsed = urlparse(url)
        existing = parse_qsl(parsed.query, keep_blank_values=True)
        existing_keys = {k.lower() for k, _ in existing}

        to_add: list[tuple[str, str]] = [
            ("utm_source", "cigarpricescout.com"),
            ("utm_medium", "price_comparison"),
        ]
        if brand:
            to_add.append(("utm_campaign", create_slug(brand)))
        if line:
            to_add.append(("utm_content", create_slug(line)))

        # Per-retailer affiliate params (future). Added BEFORE UTM so the
        # retailer's own cookie/attribution logic sees them first.
        aff = AFFILIATE_PARAMS.get(retailer_key or "", {})
        prefix: list[tuple[str, str]] = [(k, v) for k, v in aff.items()]

        for k, v in prefix + to_add:
            if k.lower() not in existing_keys:
                existing.append((k, v))
                existing_keys.add(k.lower())

        new_query = urlencode(existing, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return url


@app.get("/cigars/{brand}/{line}", response_class=HTMLResponse)
async def cigar_landing_page(brand: str, line: str):
    """
    SEO-friendly landing page for specific cigar brands/lines
    URL format: /cigars/padron/1964-anniversary-series
    """
    # Check if URL needs normalization (e.g., /opusx -> /opus-x)
    normalized_line = normalize_line_slug(line.replace('-', ' '))
    if normalized_line != line.lower():
        # Redirect to canonical URL
        return RedirectResponse(
            url=f"/cigars/{brand}/{normalized_line}",
            status_code=301  # Permanent redirect for SEO
        )
    
    # Convert URL-friendly format back to display format
    brand_display = brand.replace('-', ' ').title()
    line_display = line.replace('-', ' ').title()
    
    try:
        all_products = load_all_products()
        matching_products = [
            p for p in all_products 
            if p.brand.lower().replace(' ', '-').replace('&', 'and') == brand.lower()
            and normalize_line_slug(p.line) == line.lower()
        ]
        
        # Check if ANY variation has enough retailers for a meaningful comparison
        from collections import defaultdict as _defaultdict
        _var_retailers = _defaultdict(set)
        for p in matching_products:
            _var_retailers[(p.wrapper, p.vitola, p.box_qty)].add(p.retailer_key)
        has_valid_variation = any(
            len(r) >= MIN_RETAILERS_FOR_COMPARISON for r in _var_retailers.values()
        )
        
        if not matching_products or not has_valid_variation:
            return HTMLResponse(
                content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Cigar Not Found - Cigar Price Scout</title>
    <meta name="robots" content="noindex">
    <link rel="icon" type="image/png" href="/static/logo.png">
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 font-sans">
    <div class="max-w-2xl mx-auto px-5 py-20 text-center">
        <img src="/static/logo.png" alt="Cigar Price Scout" class="w-24 h-20 mx-auto mb-6">
        <h1 class="text-3xl font-bold text-gray-800 mb-4">Cigar Not Found</h1>
        <p class="text-gray-600 mb-6">We don't have enough pricing data for <strong>{brand_display} {line_display}</strong> yet.</p>
        <p class="text-gray-500 mb-8">We need at least {MIN_RETAILERS_FOR_COMPARISON} retailers to show a meaningful comparison. Want us to add more? Let us know!</p>
        <div class="space-x-4">
            <a href="/" class="inline-block bg-amber-700 hover:bg-amber-800 text-white font-semibold py-3 px-6 rounded-lg">Browse All Cigars</a>
            <a href="/request-box-pricing.html" class="inline-block border border-amber-700 text-amber-700 hover:bg-amber-50 font-semibold py-3 px-6 rounded-lg">Request This Cigar</a>
        </div>
    </div>
</body>
</html>""",
                status_code=404
            )

        # Use the master-CSV canonical brand/line casing for everything the user and
        # Google see going forward. URL-slug-derived `.title()` mangles numeric
        # suffixes (e.g., "10th" -> "10Th", "xxx" -> "Xxx"), which makes SERP snippets
        # look unprofessional and hurts CTR.
        brand_display = matching_products[0].brand
        line_display = matching_products[0].line

        # Read the template
        template_path = Path(f"{STATIC_PATH}/cigar-template.html")
        
        if not template_path.exists():
            return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)
        
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Load SEO content
        seo_data = load_seo_content()
        
        # Check if this cigar has quality SEO data
        has_seo = has_quality_seo_data(brand_display, line_display, seo_data)
        
        # Replace basic placeholders
        html = template.replace('{{BRAND}}', brand_display)
        html = html.replace('{{LINE}}', line_display)
        html = html.replace('{{BRAND_SLUG}}', brand)
        html = html.replace('{{LINE_SLUG}}', line)

        # Related Releases: other lines from the same brand with >= MIN_RETAILERS_FOR_COMPARISON
        # on at least one variation. Sorted by total distinct retailer count desc, capped at 3.
        # The toggle button is only rendered when there are >= 2 qualifying siblings.
        canonical_brand = matching_products[0].brand
        sibling_html_button, sibling_html_section = _build_related_releases_html(
            all_products=all_products,
            canonical_brand=canonical_brand,
            current_line_slug=line.lower(),
            brand_slug=brand,
        )
        html = html.replace('{{RELATED_RELEASES_BUTTON}}', sibling_html_button)
        html = html.replace('{{RELATED_RELEASES_SECTION}}', sibling_html_section)
        
        # Generate server-side rendered product rows for SEO (Google sees real content, not "Loading...")
        # Both desktop table rows AND mobile cards are SSR'd — critical for Googlebot
        # Smartphone / mobile-first indexing, where the desktop table is hidden by CSS
        # media queries. Without SSR mobile cards, mobile-first crawl sees an empty
        # content area and flags the page as Soft 404.
        ssr_rows = []
        ssr_mobile_cards = []
        prices = []
        # Deduplicate by (retailer, wrapper, vitola, box_qty) so the cards list doesn't
        # show near-duplicate cards for the same variation across data reloads.
        _seen_card_keys = set()
        for p in matching_products[:25]:
            price_dollars = p.price_cents / 100 if p.price_cents else 0
            price_str = f"${price_dollars:.2f}" if p.price_cents else "N/A"
            if p.price_cents:
                prices.append(price_dollars)

            # Desktop table row (cap at 10)
            if len(ssr_rows) < 10:
                ssr_rows.append(f'''<tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="p-3 text-sm">{_escape_html(p.retailer_name)}</td>
          <td class="p-3 text-sm">{_escape_html(p.wrapper or "N/A")}</td>
          <td class="p-3 text-sm">{_escape_html(p.vitola or "N/A")}</td>
          <td class="p-3 text-sm font-semibold">{price_str}</td>
        </tr>''')

            # Mobile card (cap at 10, dedupe on same-variation rows so Google
            # doesn't see 10 identical cards for the same box).
            card_key = (p.retailer_key, p.wrapper, p.vitola, p.box_qty)
            if len(ssr_mobile_cards) < 10 and card_key not in _seen_card_keys and p.price_cents:
                _seen_card_keys.add(card_key)
                stock_html = (
                    '<span class="text-emerald-600">In Stock</span>'
                    if p.in_stock else
                    '<span class="text-red-600">Out of Stock</span>'
                )
                wrapper_row = (
                    f'<div class="flex justify-between"><span class="text-muted">Wrapper:</span>'
                    f'<span class="font-semibold">{_escape_html(p.wrapper)}</span></div>'
                    if p.wrapper else ""
                )
                vitola_row = (
                    f'<div class="flex justify-between"><span class="text-muted">Vitola:</span>'
                    f'<span class="font-semibold">{_escape_html(p.vitola)}</span></div>'
                    if p.vitola else ""
                )
                product_url = _escape_html(
                    add_tracking_params(p.url, brand=brand, line=line, retailer_key=p.retailer_key)
                ) if p.url else "/"
                ssr_mobile_cards.append(f'''<div class="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div class="flex justify-between items-center pb-4 mb-4 border-b border-gray-200">
            <span class="font-display font-semibold text-lg">{_escape_html(p.retailer_name)}</span>
            <span class="text-2xl font-bold text-brand-500">{price_str}</span>
          </div>
          <div class="space-y-2 mb-4">
            {wrapper_row}
            {vitola_row}
            <div class="flex justify-between"><span class="text-muted">Box Size:</span><span class="font-semibold">{int(p.box_qty)}</span></div>
            <div class="flex justify-between"><span class="text-muted">Stock:</span><span class="font-semibold">{stock_html}</span></div>
          </div>
          <a href="{product_url}" class="flex items-center justify-center py-4 bg-brand-500 hover:bg-brand-600 text-white rounded-xl font-semibold transition-all" target="_blank" rel="noopener">
            View at {_escape_html(p.retailer_name)}
          </a>
        </div>''')

        if ssr_rows:
            html = html.replace('{{SSR_PRODUCT_ROWS}}', '\n'.join(ssr_rows))
        else:
            html = html.replace('{{SSR_PRODUCT_ROWS}}', '<tr><td colspan="4" class="p-4 text-center text-muted">Loading prices...</td></tr>')

        if ssr_mobile_cards:
            html = html.replace('{{SSR_MOBILE_CARDS}}', '\n'.join(ssr_mobile_cards))
        else:
            html = html.replace('{{SSR_MOBILE_CARDS}}', '')
        
        # Fill in JSON-LD structured data and meta tag values
        retailer_count = len({p.retailer_key for p in matching_products if p.price_cents})
        html = html.replace('{{OFFER_COUNT}}', str(len(matching_products)))
        html = html.replace('{{LOW_PRICE}}', f"{min(prices):.2f}" if prices else "0")
        html = html.replace('{{HIGH_PRICE}}', f"{max(prices):.2f}" if prices else "0")
        html = html.replace('{{RETAILER_COUNT}}', str(retailer_count))
        
        if has_seo:
            faq_1, faq_2, faq_3 = generate_faq_answers(brand_display, line_display, seo_data)
            
            key = f"{brand_display.lower()}|{line_display.lower()}"
            cigar_data = seo_data.get(key, {})
            
            seo_description = cigar_data.get('description', '')
            tasting_notes = cigar_data.get('tasting_notes', '')
            if tasting_notes:
                seo_description += f" Features rich flavors of {tasting_notes}."
            
            last_updated = datetime.now().strftime('%B %d, %Y')
            
            html = html.replace('{{SEO_DESCRIPTION}}', seo_description)
            html = html.replace('{{FAQ_ANSWER_1}}', faq_1)
            html = html.replace('{{FAQ_ANSWER_2}}', faq_2)
            html = html.replace('{{FAQ_ANSWER_3}}', faq_3)
            html = html.replace('{{LAST_UPDATED}}', last_updated)
            
            rating_value = cigar_data.get('rating_average', '')
            review_count = cigar_data.get('review_count', '').replace('+', '')
            
            if rating_value and review_count:
                aggregate_rating = (
                    '"aggregateRating": {\n'
                    '      "@type": "AggregateRating",\n'
                    f'      "ratingValue": "{rating_value}",\n'
                    '      "bestRating": "100",\n'
                    f'      "reviewCount": "{review_count}"\n'
                    '    },'
                )
                review_body = seo_description[:200].replace('"', '\\"')
                review_block = (
                    '"review": {\n'
                    '      "@type": "Review",\n'
                    '      "author": { "@type": "Organization", "name": "Cigar Price Scout" },\n'
                    '      "reviewRating": {\n'
                    '        "@type": "Rating",\n'
                    f'        "ratingValue": "{rating_value}",\n'
                    '        "bestRating": "100"\n'
                    '      },\n'
                    f'      "reviewBody": "{review_body}"\n'
                    '    },'
                )
                html = html.replace('{{AGGREGATE_RATING_BLOCK}}', aggregate_rating)
                html = html.replace('{{REVIEW_BLOCK}}', review_block)
            else:
                html = html.replace('{{AGGREGATE_RATING_BLOCK}}', '')
                html = html.replace('{{REVIEW_BLOCK}}', '')
        else:
            import re
            html = re.sub(r'<div class="text-center my-8">.*?Learn More About This Cigar.*?</button>\s*</div>', '', html, flags=re.DOTALL)
            html = re.sub(r'<section id="seo-content".*?</section>', '', html, flags=re.DOTALL)
            html = html.replace('{{AGGREGATE_RATING_BLOCK}}', '')
            html = html.replace('{{REVIEW_BLOCK}}', '')
        
        return HTMLResponse(content=html)
    
    except Exception as e:
        print(f"Error rendering cigar page /{brand}/{line}: {e}")
        return HTMLResponse(
            content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{brand_display} {line_display} - Cigar Price Scout</title>
    <meta name="robots" content="noindex">
    <link rel="icon" type="image/png" href="/static/logo.png">
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 font-sans">
    <div class="max-w-2xl mx-auto px-5 py-20 text-center">
        <img src="/static/logo.png" alt="Cigar Price Scout" class="w-24 h-20 mx-auto mb-6">
        <h1 class="text-3xl font-bold text-gray-800 mb-4">Temporarily Unavailable</h1>
        <p class="text-gray-600 mb-6">The page for <strong>{brand_display} {line_display}</strong> is temporarily unavailable. Please try again shortly.</p>
        <a href="/" class="inline-block bg-amber-700 hover:bg-amber-800 text-white font-semibold py-3 px-6 rounded-lg">Browse All Cigars</a>
    </div>
</body>
</html>""",
            status_code=404
        )


# Helper function to generate URL-friendly slugs
def create_slug(text: str) -> str:
    """Convert 'Padron 1964' to 'padron-1964'"""
    return text.lower().replace(' ', '-').replace('/', '-')


def normalize_line_slug(line: str) -> str:
    """Normalize line names for SEO-friendly URLs with special case handling.
    
    Handles cases like 'Opus X' stored as 'OPUSX' in CSV data.
    """
    line_lower = line.lower().strip()
    
    # Special case mappings for known lines that need hyphenation
    special_cases = {
        'opusx': 'opus-x',
        'opus x': 'opus-x',
        # Add more special cases as needed
    }
    
    if line_lower in special_cases:
        return special_cases[line_lower]
    
    # Default: convert spaces to hyphens, & to 'and', remove other special chars
    return line_lower.replace(' ', '-').replace('&', 'and').replace('/', '-')


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
            line_slug = normalize_line_slug(line['line'])  # Use normalize for proper SEO slugs
            url = f"/cigars/{brand_slug}/{line_slug}"
            pages.append({
                'url': url,
                'brand': brand['brand'],
                'line': line['line'],
                'full_url': f"https://cigarpricescout.com{url}"
            })
    
    return {"pages": pages, "count": len(pages)}

# Note: Duplicate sitemap route removed - using the one at /sitemap.xml above (line ~1284)

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

@app.get("/api/admin/analytics-health")
async def analytics_health(request: Request):
    """Snapshot of every analytics capture surface so we can verify data is
    flowing without opening Railway/GSC/GA4 separately. Returns row counts and
    first/last timestamps per table over the last 24h, 7d, and 30d. Also lists
    the top 5 brands/lines by recent search volume so we can eyeball
    realistic-looking data vs bot noise."""
    admin_key = request.headers.get("X-Admin-Key", "")
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        conn = get_analytics_conn()
        cur = conn.cursor()

        def _table_stats(table: str) -> dict:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            total = cur.fetchone()[0] or 0
            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE ts > NOW() - INTERVAL '24 hours'"
            )
            d1 = cur.fetchone()[0] or 0
            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE ts > NOW() - INTERVAL '7 days'"
            )
            d7 = cur.fetchone()[0] or 0
            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE ts > NOW() - INTERVAL '30 days'"
            )
            d30 = cur.fetchone()[0] or 0
            cur.execute(f"SELECT MIN(ts), MAX(ts) FROM {table}")
            mn, mx = cur.fetchone()
            return {
                "total_rows": total,
                "rows_last_24h": d1,
                "rows_last_7d": d7,
                "rows_last_30d": d30,
                "first_event_at": mn.isoformat() if mn else None,
                "last_event_at": mx.isoformat() if mx else None,
            }

        report: dict = {}
        for tbl in ("search_events", "click_events"):
            try:
                report[tbl] = _table_stats(tbl)
            except Exception as e:
                report[tbl] = {"error": str(e)}

        # Top 5 brand+line searches in the last 7 days — sanity check that rows
        # look like real users, not a flat stream of bots hitting one URL.
        try:
            cur.execute("""
                SELECT brand, line, COUNT(*) AS n
                FROM search_events
                WHERE ts > NOW() - INTERVAL '7 days'
                  AND brand IS NOT NULL AND line IS NOT NULL
                GROUP BY brand, line
                ORDER BY n DESC
                LIMIT 5
            """)
            report["top_brand_line_last_7d"] = [
                {"brand": r[0], "line": r[1], "searches": r[2]}
                for r in cur.fetchall()
            ]
        except Exception as e:
            report["top_brand_line_last_7d"] = {"error": str(e)}

        # Top 5 retailers clicked in the last 7 days — verifies click_events
        # is catching real traffic on the /go redirect (cheapest-retailer link).
        try:
            cur.execute("""
                SELECT retailer, COUNT(*) AS n
                FROM click_events
                WHERE ts > NOW() - INTERVAL '7 days'
                  AND retailer IS NOT NULL
                GROUP BY retailer
                ORDER BY n DESC
                LIMIT 5
            """)
            report["top_retailers_last_7d"] = [
                {"retailer": r[0], "clicks": r[1]} for r in cur.fetchall()
            ]
        except Exception as e:
            report["top_retailers_last_7d"] = {"error": str(e)}

        conn.close()

        report["generated_at"] = datetime.utcnow().isoformat() + "Z"
        report["ga4_measurement_id"] = "G-QV9XYRECFK"
        report["notes"] = [
            "search_events is populated by every /compare API call (one per page load).",
            "click_events is only populated by the /go redirect on the 'cheapest retailer' button at the top of each cigar page; main table + mobile card clicks go direct and are tracked in GA4 only.",
            "GA4 and Google Search Console data must be viewed in their respective UIs.",
        ]
        return report
    except Exception as e:
        return JSONResponse(
            {"error": f"analytics DB unreachable: {e}"},
            status_code=500,
        )

# ============== URL MATCH REVIEW API ==============

@app.post("/api/admin/upload-matches")
async def upload_staged_matches(request: Request):
    """Upload discovered URL matches from the weekly discovery agent."""
    admin_key = request.headers.get("X-Admin-Key", "")
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    data = await request.json()
    matches = data.get("matches", [])

    conn = get_analytics_conn()
    cur = conn.cursor()
    uploaded = 0
    tokens = []

    for m in matches:
        token = uuid.uuid4().hex[:16]
        try:
            cur.execute("""
                INSERT INTO url_staged_matches
                (match_token, cid, retailer_key, url, confidence, reason,
                 brand, line, vitola, wrapper, size, box_qty, price, in_stock)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (cid, retailer_key, url) DO NOTHING
            """, (
                token, m["cid"], m["retailer_key"], m["url"],
                m.get("confidence"), m.get("reason"),
                m.get("brand"), m.get("line"), m.get("vitola"),
                m.get("wrapper"), m.get("size"), m.get("box_qty"),
                m.get("price"), m.get("in_stock"),
            ))
            if cur.rowcount > 0:
                uploaded += 1
                tokens.append({"cid": m["cid"], "retailer_key": m["retailer_key"], "token": token})
        except Exception as e:
            logger.warning(f"Upload match error: {e}")
            conn.rollback()

    conn.commit()
    conn.close()
    return {"uploaded": uploaded, "tokens": tokens}


@app.get("/admin/match/{token}/{action}", response_class=HTMLResponse)
async def review_match_action(token: str, action: str):
    """One-click approve/reject from email link."""
    if action not in ("approve", "reject"):
        return HTMLResponse("<p>Invalid action</p>", status_code=400)

    try:
        conn = get_analytics_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT cid, retailer_key, url, brand, line, vitola, size, box_qty, status "
            "FROM url_staged_matches WHERE match_token=%s", (token,)
        )
        row = cur.fetchone()

        if not row:
            conn.close()
            return HTMLResponse(
                '<div style="font-family:sans-serif;text-align:center;padding:60px">'
                '<h2>Match not found</h2><p>This link may have expired.</p></div>',
                status_code=404,
            )

        cid, retailer, url, brand, line, vitola, size, box_qty, current_status = row

        if current_status != "staged":
            conn.close()
            return HTMLResponse(
                '<div style="font-family:sans-serif;text-align:center;padding:60px">'
                f'<h2>Already {current_status}</h2>'
                f'<p>{brand} {line} at {retailer} was already {current_status}.</p></div>'
            )

        new_status = "approved" if action == "approve" else "rejected"
        cur.execute(
            "UPDATE url_staged_matches SET status=%s, reviewed_at=NOW() WHERE match_token=%s",
            (new_status, token),
        )
        conn.commit()
        conn.close()

        color = "#2e7d32" if action == "approve" else "#c62828"
        icon = "&#10003;" if action == "approve" else "&#10007;"
        label = "Approved" if action == "approve" else "Rejected"
        next_step = (
            "This will be published to your website in the next daily price update."
            if action == "approve"
            else "This match has been rejected and won't be published."
        )

        return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Match {label} - Cigar Price Scout</title>
<link rel="icon" type="image/png" href="/static/logo.png">
<style>
body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f5f5f5; display:flex; justify-content:center; align-items:center; min-height:100vh; margin:0; }}
.card {{ background:#fff; border-radius:16px; padding:40px; max-width:480px; text-align:center; box-shadow:0 2px 8px rgba(0,0,0,.1); }}
.icon {{ width:64px; height:64px; border-radius:50%; background:{color}; color:#fff; font-size:32px; display:flex; align-items:center; justify-content:center; margin:0 auto 16px; }}
h1 {{ color:{color}; margin:0 0 4px; font-size:24px; }}
.cigar {{ font-size:18px; font-weight:600; margin:12px 0 4px; }}
.detail {{ color:#666; font-size:14px; margin:4px 0; }}
.cid {{ font-family:monospace; background:#f5f5f5; padding:8px 12px; border-radius:6px; font-size:11px; margin-top:16px; display:inline-block; word-break:break-all; }}
.next {{ color:#888; font-size:13px; margin-top:20px; }}
</style></head>
<body><div class="card">
<div class="icon">{icon}</div>
<h1>Match {label}</h1>
<p class="cigar">{brand} {line}</p>
<p class="detail">{vitola} &middot; {size} &middot; Box of {box_qty}</p>
<p class="detail">Retailer: {retailer}</p>
<div class="cid">{cid}</div>
<p class="next">{next_step}</p>
</div></body></html>""")

    except Exception as e:
        logger.error(f"Review match error: {e}")
        return HTMLResponse(f"<p>Error processing request</p>", status_code=500)


@app.get("/api/admin/pending-matches")
async def get_pending_matches(
    request: Request,
    confidence: Optional[str] = Query(None),
    retailer: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Fetch staged (unreviewed) matches with optional filtering and pagination."""
    admin_key = request.headers.get("X-Admin-Key", "") or request.query_params.get("key", "")
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    conn = get_analytics_conn()
    cur = conn.cursor()

    where = ["status='staged'"]
    params = []
    if confidence:
        where.append("confidence=%s")
        params.append(confidence)
    if retailer:
        where.append("retailer_key=%s")
        params.append(retailer)
    if brand:
        where.append("LOWER(brand)=LOWER(%s)")
        params.append(brand)
    if search:
        where.append("LOWER(cid) LIKE %s")
        params.append(f"%{search.lower()}%")

    where_sql = " AND ".join(where)

    cur.execute(f"SELECT COUNT(1) FROM url_staged_matches WHERE {where_sql}", params)
    total = cur.fetchone()[0]

    cur.execute(
        f"SELECT COUNT(1), confidence FROM url_staged_matches WHERE status='staged' GROUP BY confidence"
    )
    confidence_counts = {r[1]: r[0] for r in cur.fetchall()}

    cur.execute(
        f"SELECT DISTINCT retailer_key FROM url_staged_matches WHERE status='staged' ORDER BY retailer_key"
    )
    available_retailers = [r[0] for r in cur.fetchall()]

    cur.execute(
        f"SELECT DISTINCT brand FROM url_staged_matches WHERE status='staged' AND brand IS NOT NULL ORDER BY brand"
    )
    available_brands = [r[0] for r in cur.fetchall()]

    cur.execute(f"""
        SELECT match_token, cid, retailer_key, url, confidence, reason,
               brand, line, vitola, wrapper, size, box_qty, price, in_stock,
               created_at
        FROM url_staged_matches WHERE {where_sql}
        ORDER BY
            CASE confidence WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,
            brand, line, vitola, retailer_key
        LIMIT %s OFFSET %s
    """, params + [limit, offset])
    rows = cur.fetchall()
    conn.close()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "confidence_counts": confidence_counts,
        "available_retailers": available_retailers,
        "available_brands": available_brands,
        "matches": [
            {"token": r[0], "cid": r[1], "retailer_key": r[2], "url": r[3],
             "confidence": r[4], "reason": r[5], "brand": r[6], "line": r[7],
             "vitola": r[8], "wrapper": r[9], "size": r[10], "box_qty": r[11],
             "price": float(r[12]) if r[12] else None,
             "in_stock": r[13], "created_at": str(r[14]) if r[14] else None}
            for r in rows
        ],
    }


@app.post("/api/admin/bulk-review")
async def bulk_review_matches(request: Request):
    """Bulk approve or reject matches by token list."""
    admin_key = request.headers.get("X-Admin-Key", "")
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    data = await request.json()
    action = data.get("action")
    tokens = data.get("tokens", [])

    if action not in ("approve", "reject") or not tokens:
        return JSONResponse({"error": "action must be approve/reject and tokens required"}, status_code=400)

    new_status = "approved" if action == "approve" else "rejected"
    conn = get_analytics_conn()
    cur = conn.cursor()
    updated = 0
    for token in tokens:
        cur.execute(
            "UPDATE url_staged_matches SET status=%s, reviewed_at=NOW() WHERE match_token=%s AND status='staged'",
            (new_status, token),
        )
        updated += cur.rowcount
    conn.commit()
    conn.close()

    return {"action": new_status, "updated": updated}


@app.get("/admin/review", response_class=HTMLResponse)
async def admin_review_page(request: Request, key: str = Query("")):
    """Mobile-friendly match review dashboard."""
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or key != expected:
        return HTMLResponse(
            '<div style="font-family:sans-serif;text-align:center;padding:60px">'
            '<h2>Unauthorized</h2><p>Append ?key=YOUR_SECRET to the URL.</p></div>',
            status_code=401,
        )
    return FileResponse(f"{STATIC_PATH}/admin-review.html", media_type="text/html")


@app.get("/admin/smoke-tests", response_class=HTMLResponse)
async def admin_smoke_tests_page(request: Request, key: str = Query("")):
    """Click-driven dashboard for the AGENTS.md §11 manual smoke-test playbook.

    Auth is handled in-page by the user pasting their admin key into a
    sessionStorage-backed input — every JSON call sent from the dashboard
    appends ?key=... using the saved value. We still check ?key= here as a
    soft gate so the dashboard isn't directly indexable, but the real
    security boundary is the underlying /api/admin/* endpoints.
    """
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or key != expected:
        return HTMLResponse(
            '<div style="font-family:sans-serif;text-align:center;padding:60px">'
            '<h2>Smoke Test Dashboard</h2>'
            '<p>Append <code>?key=YOUR_ADMIN_SECRET_KEY</code> to the URL to load.</p>'
            '</div>',
            status_code=401,
        )
    return FileResponse(f"{STATIC_PATH}/admin/smoke-tests.html", media_type="text/html")


@app.get("/api/admin/approved-matches")
async def get_approved_matches(request: Request):
    """Fetch approved matches for publishing by local automation."""
    admin_key = request.headers.get("X-Admin-Key", "")
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    conn = get_analytics_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, cid, retailer_key, url, brand, line, vitola, wrapper, size, box_qty
        FROM url_staged_matches WHERE status='approved'
    """)
    rows = cur.fetchall()
    conn.close()

    return {"matches": [
        {"id": r[0], "cid": r[1], "retailer_key": r[2], "url": r[3],
         "brand": r[4], "line": r[5], "vitola": r[6], "wrapper": r[7],
         "size": r[8], "box_qty": r[9]}
        for r in rows
    ]}


@app.post("/api/admin/purge-staged")
async def purge_staged_matches(request: Request):
    """Delete all staged (unreviewed) matches to allow a clean re-upload."""
    admin_key = request.headers.get("X-Admin-Key", "")
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    conn = get_analytics_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM url_staged_matches WHERE status='staged'")
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"deleted": deleted}


@app.post("/api/admin/mark-published")
async def mark_matches_published(request: Request):
    """Mark matches as published after local automation processes them."""
    admin_key = request.headers.get("X-Admin-Key", "")
    expected = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected or admin_key != expected:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    data = await request.json()
    ids = data.get("ids", [])

    conn = get_analytics_conn()
    cur = conn.cursor()
    for match_id in ids:
        cur.execute(
            "UPDATE url_staged_matches SET status='published' WHERE id=%s",
            (match_id,),
        )
    conn.commit()
    conn.close()

    return {"published": len(ids)}

# ============== BEST CIGAR BOX PRICES API ==============

@app.get("/api/best-deals")
def get_best_deals(limit: int = Query(50, description="Max number of deals to return")):
    """
    Return products with the best value (those priced >10% below median).
    Groups by product and returns the cheapest offer for each.
    """
    all_products = load_all_products()
    
    # Group products by canonical identifier (brand + line + wrapper + size)
    product_groups = {}
    
    for p in all_products:
        if not p.in_stock:
            continue
            
        key = f"{p.brand}|{p.line}|{p.wrapper}|{p.size}"
        if key not in product_groups:
            product_groups[key] = []
        product_groups[key].append(p)
    
    deals = []
    
    for key, products in product_groups.items():
        distinct = {p.retailer_key for p in products}
        if len(distinct) < MIN_RETAILERS_FOR_COMPARISON:
            continue
        
        # Calculate prices for all offerings
        prices = []
        for p in products:
            base_cents = p.price_cents  # Advertised price
            
            # Check if promo applies
            promo_price_cents, promo_code, promo_discount = apply_promotion(base_cents, p.retailer_key)
            has_promo = promo_price_cents and promo_price_cents != base_cents
            
            # Use promo price if available, otherwise base price for comparison
            comparison_price = promo_price_cents if has_promo else base_cents
            
            prices.append((comparison_price, p, base_cents, promo_price_cents if has_promo else None, promo_code if has_promo else None))
        
        # Sort by comparison price
        prices.sort(key=lambda x: x[0])
        
        # Calculate median using comparison prices
        price_values = [p[0] for p in prices]
        n = len(price_values)
        median = price_values[n // 2] if n % 2 == 1 else (price_values[n // 2 - 1] + price_values[n // 2]) / 2
        
        # Check if cheapest is >10% below median (Value)
        cheapest_price, cheapest_product, base_cents, promo_price_cents, promo_code = prices[0]
        diff_percent = ((cheapest_price - median) / median) * 100
        
        if diff_percent <= -10:  # 10% or more below median = Value
            savings_vs_median = median - cheapest_price
            savings_percent = abs(diff_percent)
            
            deal_data = {
                "brand": cheapest_product.brand,
                "line": cheapest_product.line,
                "wrapper": cheapest_product.wrapper,
                "vitola": cheapest_product.vitola,
                "size": cheapest_product.size,
                "box_qty": cheapest_product.box_qty,
                "retailer": cheapest_product.retailer_name,
                "retailer_key": cheapest_product.retailer_key,
                "advertised_price": f"${base_cents / 100:.2f}",
                "advertised_price_cents": base_cents,
                "price": f"${cheapest_price / 100:.2f}",
                "price_cents": cheapest_price,
                "median_price": f"${median / 100:.2f}",
                "savings": f"${savings_vs_median / 100:.2f}",
                "savings_percent": round(savings_percent, 1),
                "url": cheapest_product.url,
                "num_retailers": len(products),
                "community": cheapest_product.community_id is not None,
            }
            
            # Add promo info if applicable
            if promo_price_cents:
                deal_data["promo_price"] = f"${promo_price_cents / 100:.2f}"
                deal_data["promo_code"] = promo_code
                deal_data["promo_savings"] = f"${(base_cents - promo_price_cents) / 100:.2f}"
            
            deals.append(deal_data)
    
    # Sort by price (lowest first)
    deals.sort(key=lambda x: x["price_cents"])
    
    return {
        "count": len(deals[:limit]),
        "deals": deals[:limit],
        "generated_at": datetime.now().isoformat()
    }

@app.get("/deals", response_class=HTMLResponse)
@app.get("/best-cigar-box-prices", response_class=HTMLResponse)
async def best_deals_page():
    """Serve the Best Cigar Box Prices page"""
    template_path = Path(f"{STATIC_PATH}/deals.html")
    if not template_path.exists():
        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)
    
    with open(template_path, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

# ============== DEAL SUBMISSION API ==============

class DealSubmission(BaseModel):
    retailer: str
    deal_type: str  # "promo_code", "sale_price", "bundle"
    scope: str  # "site", "brand", "line", "sku"
    brand: Optional[str] = None
    line: Optional[str] = None
    wrapper: Optional[str] = None
    size: Optional[str] = None
    promo_code: Optional[str] = None
    discount_percent: Optional[float] = None
    discount_dollars: Optional[float] = None
    expiration: Optional[str] = None
    deal_url: Optional[str] = None
    submitter_name: str
    submitter_email: str
    notes: Optional[str] = None

@app.post("/api/submit-deal")
async def submit_deal(deal: DealSubmission):
    """Handle community deal submissions"""
    try:
        # Format the deal for email
        scope_details = ""
        if deal.scope == "site":
            scope_details = "Site-wide"
        elif deal.scope == "brand":
            scope_details = f"Brand: {deal.brand}"
        elif deal.scope == "line":
            scope_details = f"Brand: {deal.brand}, Line: {deal.line}"
        elif deal.scope == "sku":
            scope_details = f"{deal.brand} {deal.line} {deal.wrapper or ''} {deal.size or ''}".strip()
        
        discount_info = ""
        if deal.discount_percent:
            discount_info = f"{deal.discount_percent}% off"
        elif deal.discount_dollars:
            discount_info = f"${deal.discount_dollars} off"
        
        subject = f"Deal Submission: {deal.retailer} - {scope_details}"
        
        body = f"""
========== NEW DEAL SUBMISSION ==========

RETAILER: {deal.retailer}
DEAL TYPE: {deal.deal_type}
SCOPE: {deal.scope}

DETAILS:
{scope_details}

DISCOUNT: {discount_info}
PROMO CODE: {deal.promo_code or 'N/A'}
EXPIRATION: {deal.expiration or 'Not specified'}
DEAL URL: {deal.deal_url or 'Not provided'}

NOTES:
{deal.notes or 'None'}

SUBMITTED BY:
- Name: {deal.submitter_name}
- Email: {deal.submitter_email}

Submitted: {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}
==========================================
"""
        
        logger.info(body)
        send_notification_email(subject, body, "info@cigarpricescout.com", reply_to=deal.submitter_email)
        
        return {"status": "success", "message": "Thank you! Your deal has been submitted for review."}
        
    except Exception as e:
        logger.error(f"Error processing deal submission: {e}")
        return {"status": "error", "message": "There was an error submitting your deal. Please try again."}

@app.get("/submit-deal", response_class=HTMLResponse)
async def submit_deal_page():
    """Serve the Submit a Deal page"""
    template_path = Path(f"{STATIC_PATH}/submit-deal.html")
    if not template_path.exists():
        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)
    
    with open(template_path, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())


# ── Community Contributions ──────────────────────────────────────────

class CommunityPriceSubmission(BaseModel):
    cid: str
    url: str
    price: float
    retailer_name: str
    brand: str
    line: str
    wrapper: str = ""
    vitola: str = ""
    size: str = ""
    box_qty: int = 20

@app.post("/api/community-price")
async def submit_community_price(request: Request):
    """Accept a community-submitted retailer price for a known CID."""
    try:
        data = await request.json()
        cid = data.get("cid", "").strip()
        url = data.get("url", "").strip()
        price = data.get("price")
        retailer_name = data.get("retailer_name", "").strip()
        brand = data.get("brand", "").strip()
        line = data.get("line", "").strip()
        wrapper = data.get("wrapper", "").strip()
        vitola = data.get("vitola", "").strip()
        size = data.get("size", "").strip()
        box_qty = int(data.get("box_qty", 20))

        if not url or not price or not retailer_name:
            return {"status": "error", "message": "URL, price, and retailer name are required."}

        if not url.startswith("http"):
            return {"status": "error", "message": "Please enter a valid URL starting with http."}

        price_cents = int(float(price) * 100)
        if price_cents <= 0:
            return {"status": "error", "message": "Price must be greater than zero."}

        free_shipping = 1 if data.get("free_shipping") else 0

        # Match to existing products to fill in size and CID if missing
        if brand and line and (not size or not cid):
            all_prods = load_all_products()
            for p in all_prods:
                if p.brand.lower() != brand.lower() or p.line.lower() != line.lower():
                    continue
                if wrapper and p.wrapper.lower() != wrapper.lower():
                    continue
                if vitola and p.vitola.lower() != vitola.lower():
                    continue
                if box_qty and p.box_qty != box_qty:
                    continue
                if not size and p.size:
                    size = p.size
                if not cid and p.cigar_id:
                    cid = p.cigar_id
                if size and cid:
                    break

        ip = request.client.host if request.client else ""
        voter_hash = hashlib.sha256(ip.encode()).hexdigest() if ip else ""

        conn = get_analytics_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM community_prices WHERE cid = %s AND url = %s AND active = 1",
            (cid, url),
        )
        if cur.fetchone():
            conn.close()
            return {"status": "error", "message": "This URL is already listed for this cigar."}

        cur.execute(
            """INSERT INTO community_prices
               (cid, url, price_cents, retailer_name, voter_hash, brand, line, wrapper, vitola, size, box_qty, free_shipping)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (cid, url, price_cents, retailer_name, voter_hash, brand, line, wrapper, vitola, size, box_qty, free_shipping),
        )

        conn.commit()
        conn.close()

        # Also log to local historical DB if available
        try:
            hist_db = Path("data/historical_prices.db")
            if hist_db.exists():
                hist_conn = sqlite3.connect(str(hist_db))
                today = datetime.now().strftime("%Y-%m-%d")
                hist_conn.execute(
                    "INSERT INTO price_history (cigar_id, retailer, url, price, in_stock, date) VALUES (?, ?, ?, ?, ?, ?)",
                    (cid, retailer_name.lower().replace(" ", ""), url, price_cents / 100, 1, today),
                )
                hist_conn.commit()
                hist_conn.close()
        except Exception as hist_err:
            logger.warning(f"Could not write community price to local history: {hist_err}")

        _product_cache["data"] = None
        _product_cache["timestamp"] = 0

        logger.info(f"Community price submitted: {retailer_name} ${price_cents/100:.2f} for {cid}")
        return {"status": "success", "message": "Retailer added successfully! It will appear in the comparison table shortly."}

    except Exception as e:
        logger.error(f"Error processing community price: {e}")
        return {"status": "error", "message": "There was an error submitting your price. Please try again."}


@app.post("/api/report-row")
async def report_row(request: Request):
    """Downvote a community-submitted row. After threshold, it gets deactivated."""
    try:
        data = await request.json()
        community_id = data.get("community_id")
        reason = data.get("reason", "").strip()

        if not community_id or not reason:
            return {"status": "error", "message": "Missing community_id or reason."}

        if reason not in ("price_changed", "out_of_stock", "link_broken"):
            return {"status": "error", "message": "Invalid reason."}

        ip = request.client.host if request.client else ""
        voter_hash = hashlib.sha256(ip.encode()).hexdigest() if ip else ""

        conn = get_analytics_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM community_votes WHERE community_price_id = %s AND voter_hash = %s",
            (community_id, voter_hash),
        )
        if cur.fetchone():
            conn.close()
            return {"status": "error", "message": "You have already reported this listing."}

        cur.execute(
            "INSERT INTO community_votes (community_price_id, reason, voter_hash) VALUES (%s, %s, %s)",
            (community_id, reason, voter_hash),
        )

        cur.execute(
            "UPDATE community_prices SET downvotes = downvotes + 1 WHERE id = %s",
            (community_id,),
        )

        cur.execute("SELECT downvotes FROM community_prices WHERE id = %s", (community_id,))
        row = cur.fetchone()
        deactivated = False
        if row and row[0] >= COMMUNITY_DOWNVOTE_THRESHOLD:
            cur.execute("UPDATE community_prices SET active = 0 WHERE id = %s", (community_id,))
            deactivated = True
            _product_cache["data"] = None
            _product_cache["timestamp"] = 0

        conn.commit()
        conn.close()

        if deactivated:
            return {"status": "success", "message": "This listing has been removed due to multiple reports. Thank you for helping keep data accurate."}
        return {"status": "success", "message": "Thank you for your report!"}

    except Exception as e:
        logger.error(f"Error processing row report: {e}")
        return {"status": "error", "message": "There was an error processing your report. Please try again."}


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)