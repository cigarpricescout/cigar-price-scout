#!/usr/bin/env python3
"""
Daily URL Discovery Runner

Runs the URL Discovery Agent, uploads new matches to the live site API,
then fetches ALL pending (unreviewed) matches and sends an HTML email
with one-click Approve/Reject links. Matches carry over day-to-day
until reviewed.

Usage:
    python automation/run_weekly_discovery.py
    python automation/run_weekly_discovery.py --top-cids 100
    python automation/run_weekly_discovery.py --dry-run
"""

import csv
import os
import sys
import json
import smtplib
import argparse
import logging
import re
import time
import requests as http_requests
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

AUTOMATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AUTOMATION_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.ai.url_discoverer import run_discovery, STAGED_FILE, PENDING_FILE, REPORT_FILE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

APP_BASE_URL = os.getenv("APP_BASE_URL", "https://cigarpricescout.com")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "")

PRICE_RE = re.compile(r'\$(\d{1,4}(?:,\d{3})*(?:\.\d{2}))')
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

RETAILERS_PKG = "tools.price_monitoring.retailers"

RETAILER_EXTRACTOR_MAP = {
    # Active retailers  (csv_key -> module_name, function_name)
    "foxcigar":          ("fox_cigar",                       "extract_fox_cigar_data"),
    "hilands":           ("hilands_cigars",                  "extract_hilands_cigars_data"),
    "atlantic":          ("atlantic_cigar_extractor",        "extract_atlantic_cigar_data"),
    "holts":             ("holts_cigars_extractor",          "extract_holts_cigar_data"),
    "smallbatchcigar":   ("smallbatch_cigar_extractor",      "extract_smallbatch_cigar_data"),
    "bighumidor":        ("big_humidor_extractor",           "extract_big_humidor_data"),
    "cigarsdirect":      ("cigarsdirect_extractor",          "extract_cigarsdirect_data"),
    "absolutecigars":    ("absolute_cigars_extractor",       "extract_absolute_cigars_data"),
    "stogies":           ("stogies_extractor",               "extract_stogies_data"),
    "tobaccostock":      ("tobaccostock_extractor",          "extract_tobaccostock_data"),
    "thecigarshop":      ("thecigarshop_extractor",          "extract_thecigarshop_data"),
    "nickscigarworld":   ("nicks_cigars",                    "extract_nicks_cigars_data"),
    "twoguys":           ("two_guys_extractor",              "extract_two_guys_cigars_data"),
    "watchcity":         ("watch_city_extractor",            "extract_watch_city_data"),
    "tobaccolocker":     ("tobacco_locker_extractor",        "extract_tobacco_locker_data"),
    "tampasweethearts":  ("tampa_sweethearts_extractor",     "extract_tampa_sweethearts_data"),
    "smokeinn":          ("smokeinn_extractor",              "extract_smokeinn_cigar_data"),
    "planetcigars":      ("planet_cigars_extractor",         "extract_planet_cigars_data"),
    "bnbtobacco":        ("bnb_tobacco_extractor",           "extract_bnb_tobacco_data"),
    "cigarboxpa":        ("cigarboxpa_extractor",            "extract_cigarboxpa_data"),
    "pyramidcigars":     ("pyramid_cigars_extractor",        "extract_pyramid_cigars_data"),
    "coronacigar":       ("coronacigar_extractor",           "extract_coronacigar_data"),
    "cigarhustler":      ("cigarhustler_extractor",          "extract_cigarhustler_data"),
    "cigardepot":        ("cigardepot_extractor",            "extract_cigardepot_data"),
    "cigarking":         ("cigar_king_extractor",            "extract_cigar_king_data"),
    "iheartcigars":      ("iheartcigars_production_final",   "extract_iheartcigars_data_production"),
    # Dormant retailers
    "gothamcigars":      ("gotham_cigars_extractor",         "extract_gotham_cigars_data"),
    "neptune":           ("neptune_cigar_extractor",         "extract_neptune_cigar_data"),
    "cigarprimestore":   ("cigarprimestore_extractor",       "extract_cigarprimestore_data"),
    # Extra extractors (no active CSV yet, but discoverable)
    "cigarpage":         ("cigar_page_extractor",            "extract_cigar_page_data"),
    "abcfws":            ("abcfws_extractor",                "extract_abcfws_data"),
    "baysidecigars":     ("baysidecigars_extractor",         "extract_bayside_cigars_data"),
    "bestcigarprices":   ("best_cigar_prices_extractor",     "extract_best_cigar_prices_data"),
    "boutiquecigar":     ("boutiquecigar_extractor",         "extract_boutiquecigar_data"),
    "buitragocigars":    ("buitrago_cigars_extractor",       "extract_buitrago_cigars_data"),
    "cigarboxinc":       ("cigarboxinc_extractor",           "extract_cigarboxinc_data"),
    "cigarcellarofmiami":("cigarcellarofmiami_extractor",    "extract_cigarcellarofmiami_data"),
    "cigarcountry":      ("cigar_country_extractor",         "extract_cigar_country_data"),
    "famoussmoke":       ("famous_smoke_extractor",          "extract_famous_smoke_data"),
    "mikescigars":       ("mikescigars_extractor",           "extract_mikescigars_data"),
    "momscigars":        ("moms_cigars_extractor",           "extract_moms_cigars_data"),
    "smokezone":         ("smokezone_extractor",             "extract_smokezone_data"),
    "thompsoncigar":     ("thompson_cigars_extractor",       "extract_thompson_cigars_data"),
    "cigaroasis":        ("shopify_generic_extractor",       "extract_shopify_store_data"),
    "escobarcigars":     ("shopify_generic_extractor",       "extract_shopify_store_data"),
    "santamonicacigars": ("shopify_generic_extractor",       "extract_shopify_store_data"),
}

URL_DOMAIN_TO_KEY = {
    "foxcigar.com":              "foxcigar",
    "hilandscigars.com":         "hilands",
    "atlanticcigar.com":         "atlantic",
    "holts.com":                 "holts",
    "smallbatchcigar.com":       "smallbatchcigar",
    "bighumidor.com":            "bighumidor",
    "cigarsdirect.com":          "cigarsdirect",
    "absolutecigars.com":        "absolutecigars",
    "stogiesworldclasscigars.com": "stogies",
    "tobaccostock.com":          "tobaccostock",
    "thecigarshop.com":          "thecigarshop",
    "nickscigarworld.com":       "nickscigarworld",
    "2guyscigars.com":           "twoguys",
    "watchcitycigars.com":       "watchcity",
    "tobaccolocker.com":         "tobaccolocker",
    "tampasweethearts.com":      "tampasweethearts",
    "smokeinn.com":              "smokeinn",
    "planetcigars.com":          "planetcigars",
    "bnbtobacco.com":            "bnbtobacco",
    "cigarboxpa.com":            "cigarboxpa",
    "pyramidcigars.com":         "pyramidcigars",
    "coronacigar.com":           "coronacigar",
    "cigarhustler.com":          "cigarhustler",
    "cigardepot.com":            "cigardepot",
    "cigarking.com":             "cigarking",
    "iheartcigars.com":          "iheartcigars",
    "gothamcigars.com":          "gothamcigars",
    "neptunecigar.com":          "neptune",
    "cigarprimestore.com":       "cigarprimestore",
    "cigarpage.com":             "cigarpage",
    "abcfws.com":                "abcfws",
    "baysidecigars.com":         "baysidecigars",
    "bestcigarprices.com":       "bestcigarprices",
    "boutiquecigars.com":        "boutiquecigar",
    "buitragocigars.com":        "buitragocigars",
    "cigarboxinc.com":           "cigarboxinc",
    "cigarcellarofmiami.com":    "cigarcellarofmiami",
    "cigarcountry.com":          "cigarcountry",
    "famous-smoke.com":          "famoussmoke",
    "mikescigars.com":           "mikescigars",
    "momscigars.com":            "momscigars",
    "smokezonecigars.com":       "smokezone",
    "thompsoncigar.com":         "thompsoncigar",
    "cigarwarehouseusa.com":     "cigarwarehouse",
    "cigaroasis.com":            "cigaroasis",
    "escobarcigars.com":         "escobarcigars",
    "santamonicacigars.com":     "santamonicacigars",
}


def load_config():
    """Load automation config for email settings."""
    config_path = AUTOMATION_DIR / "automation_config.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)
    return {}


def _retailer_key_from_url(url: str) -> str | None:
    """Derive retailer key from a URL's domain via URL_DOMAIN_TO_KEY."""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().replace("www.", "")
        for suffix, key in URL_DOMAIN_TO_KEY.items():
            if domain.endswith(suffix):
                return key
    except Exception:
        pass
    return None


def _normalize_extractor_result(raw: dict | None) -> dict:
    """Normalize varying extractor return formats into {price, in_stock, error}."""
    if raw is None:
        return {"price": None, "in_stock": None, "error": "extractor returned None"}

    price = raw.get("price") or raw.get("box_price") or raw.get("sale_price")
    if price is not None:
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = None

    in_stock = raw.get("in_stock")

    error = raw.get("error")
    if error is None and raw.get("success") is False:
        error = "extraction unsuccessful"

    return {"price": price, "in_stock": in_stock, "error": error}


def extract_via_retailer(url: str, retailer_key: str | None = None) -> dict:
    """
    Extract price/stock using the retailer-specific extractor.
    Falls back to generic scraper only if no extractor is found.
    """
    import importlib

    key = retailer_key or _retailer_key_from_url(url)
    if key:
        key = key.replace("-DORMANT", "")

    if key and key in RETAILER_EXTRACTOR_MAP:
        module_name, func_name = RETAILER_EXTRACTOR_MAP[key]
        fqn = f"{RETAILERS_PKG}.{module_name}"
        try:
            mod = importlib.import_module(fqn)
            func = getattr(mod, func_name)
            raw = func(url)
            result = _normalize_extractor_result(raw)
            logger.info(f"  Extractor [{key}] -> price={result['price']}, in_stock={result['in_stock']}")
            return result
        except Exception as e:
            logger.warning(f"  Extractor [{key}] failed: {e}, falling back to generic")

    return _fetch_price_generic(url)


def _fetch_price_generic(url: str, timeout: int = 12) -> dict:
    """Last-resort generic scraper when no retailer extractor matches."""
    try:
        from bs4 import BeautifulSoup
        resp = http_requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        return {"price": None, "in_stock": None, "error": str(e)[:60]}

    soup = BeautifulSoup(resp.content, "html.parser")
    price = None
    in_stock = None

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Product", ["Product"]):
                    offers = item.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    p = offers.get("price") or offers.get("lowPrice")
                    if p:
                        price = float(str(p).replace(",", ""))
                    avail = offers.get("availability", "")
                    if "InStock" in avail:
                        in_stock = True
                    elif "OutOfStock" in avail:
                        in_stock = False
                    if price:
                        break
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            continue

    if not price:
        og = soup.find("meta", property="product:price:amount")
        if og:
            try:
                price = float(og["content"].replace(",", ""))
            except (ValueError, KeyError):
                pass

    if not price:
        matches = PRICE_RE.findall(soup.get_text())
        for m in matches:
            try:
                val = float(m.replace(",", ""))
                if 25.0 <= val <= 3000.0:
                    price = val
                    break
            except ValueError:
                pass

    if in_stock is None:
        text = soup.get_text().lower()
        if "out of stock" in text or "sold out" in text:
            in_stock = False
        elif "add to cart" in text:
            in_stock = True

    return {"price": price, "in_stock": in_stock, "error": None}


def upload_matches_to_api(staged_rows: list) -> list:
    """Upload staged matches to the live site API and return tokens."""
    if not ADMIN_SECRET_KEY:
        logger.warning("ADMIN_SECRET_KEY not set, skipping API upload")
        return []

    payload = {"matches": staged_rows}
    try:
        resp = http_requests.post(
            f"{APP_BASE_URL}/api/admin/upload-matches",
            json=payload,
            headers={"X-Admin-Key": ADMIN_SECRET_KEY},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Uploaded {data.get('uploaded', 0)} matches to API")
        return data.get("tokens", [])
    except Exception as e:
        logger.error(f"API upload failed: {e}")
        return []


def fetch_all_pending_from_api() -> list:
    """Fetch ALL pending (staged) matches from the live API, including old unreviewed ones."""
    if not ADMIN_SECRET_KEY:
        logger.warning("ADMIN_SECRET_KEY not set, cannot fetch pending matches")
        return []

    try:
        resp = http_requests.get(
            f"{APP_BASE_URL}/api/admin/pending-matches",
            headers={"X-Admin-Key": ADMIN_SECRET_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        matches = resp.json().get("matches", [])
        logger.info(f"Fetched {len(matches)} total pending matches from API")
        return matches
    except Exception as e:
        logger.error(f"Failed to fetch pending matches: {e}")
        return []


def fetch_approved_from_api() -> list:
    """Fetch approved matches ready to be published into retailer CSVs."""
    if not ADMIN_SECRET_KEY:
        logger.warning("ADMIN_SECRET_KEY not set, cannot fetch approved matches")
        return []

    try:
        resp = http_requests.get(
            f"{APP_BASE_URL}/api/admin/approved-matches",
            headers={"X-Admin-Key": ADMIN_SECRET_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        matches = resp.json().get("matches", [])
        logger.info(f"Fetched {len(matches)} approved matches from API")
        return matches
    except Exception as e:
        logger.error(f"Failed to fetch approved matches: {e}")
        return []


def publish_approved_to_csvs(approved: list) -> int:
    """Write approved matches into retailer CSVs and mark them as published."""
    import pandas as pd

    if not approved:
        return 0

    static_data = PROJECT_ROOT / "static" / "data"
    published_ids = []
    published_count = 0

    by_retailer = {}
    for m in approved:
        key = m["retailer_key"]
        by_retailer.setdefault(key, []).append(m)

    for retailer_key, matches in by_retailer.items():
        csv_path = static_data / f"{retailer_key}.csv"
        if not csv_path.exists():
            logger.warning(f"CSV not found for retailer: {retailer_key}, skipping {len(matches)} matches")
            continue

        retailer_df = pd.read_csv(csv_path)
        existing_cids = set(retailer_df["cigar_id"].dropna().unique())

        new_rows = []
        for m in matches:
            if m["cid"] in existing_cids:
                logger.info(f"  Skipping {m['cid']} — already in {retailer_key}.csv")
                published_ids.append(m["id"])
                continue

            new_row = {
                "cigar_id": m["cid"],
                "title": "",
                "url": m["url"],
                "brand": m.get("brand", ""),
                "line": m.get("line", ""),
                "wrapper": m.get("wrapper", ""),
                "vitola": m.get("vitola", ""),
                "size": m.get("size", ""),
                "box_qty": m.get("box_qty", ""),
                "price": "",
                "in_stock": "",
            }
            for col in retailer_df.columns:
                if col not in new_row:
                    new_row[col] = ""

            new_rows.append(new_row)
            published_ids.append(m["id"])

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            retailer_df = pd.concat([retailer_df, new_df], ignore_index=True)
            retailer_df.to_csv(csv_path, index=False)
            published_count += len(new_rows)
            logger.info(f"  Added {len(new_rows)} CIDs to {retailer_key}.csv")

    if published_ids:
        try:
            resp = http_requests.post(
                f"{APP_BASE_URL}/api/admin/mark-published",
                json={"ids": published_ids},
                headers={"X-Admin-Key": ADMIN_SECRET_KEY},
                timeout=15,
            )
            resp.raise_for_status()
            logger.info(f"Marked {len(published_ids)} matches as published in API")
        except Exception as e:
            logger.error(f"Failed to mark matches as published: {e}")

    return published_count


MIN_MATCH_PRICE = 50.0

def _render_match_card(i: int, m: dict) -> str:
    """Render a single match card for the email."""
    conf = (m.get("confidence") or "MEDIUM").upper()
    conf_color = "#2e7d32" if conf == "HIGH" else "#e65100" if conf == "MEDIUM" else "#c62828"
    conf_bg = "#e8f5e9" if conf == "HIGH" else "#fff3e0" if conf == "MEDIUM" else "#ffebee"

    price = m.get("price")
    price_str = f"${float(price):.2f}" if price else "N/A"
    in_stock = m.get("in_stock")
    stock_str = "In Stock" if in_stock else "Out of Stock" if in_stock is False else "Unknown"
    stock_color = "#2e7d32" if in_stock else "#c62828" if in_stock is False else "#888"

    approve_url = f"{APP_BASE_URL}/admin/match/{m['token']}/approve"
    reject_url = f"{APP_BASE_URL}/admin/match/{m['token']}/reject"
    product_url = m.get("url", "")

    cid = m.get("cid", "N/A")
    retailer = m.get("retailer_key", "")

    return f"""
    <tr><td style="padding:8px 0">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden">
        <tr><td style="padding:16px 20px">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="font-size:15px;font-weight:bold;color:#333">#{i}. {retailer}</td>
              <td align="right">
                <span style="background:{conf_bg};color:{conf_color};padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700">{conf}</span>
              </td>
            </tr>
          </table>
          <div style="background:#f5f5f5;padding:8px 12px;border-radius:6px;margin:10px 0;font-family:monospace;font-size:12px;word-break:break-all;color:#333">{cid}</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0">
            <tr>
              <td style="font-size:20px;font-weight:bold;color:#333">{price_str}</td>
              <td align="right" style="font-size:14px;font-weight:600;color:{stock_color}">{stock_str}</td>
            </tr>
          </table>
          <table cellpadding="0" cellspacing="0" style="margin-top:12px"><tr>
            <td style="padding-right:8px">
              <a href="{approve_url}" style="display:inline-block;background:#4CAF50;color:#fff;padding:8px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px">Approve</a>
            </td>
            <td style="padding-right:12px">
              <a href="{reject_url}" style="display:inline-block;background:#f44336;color:#fff;padding:8px 24px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px">Reject</a>
            </td>
            <td>
              <a href="{product_url}" style="color:#1565c0;font-size:13px;text-decoration:none" target="_blank">View Product &rarr;</a>
            </td>
          </tr></table>
        </td></tr>
      </table>
    </td></tr>"""


def build_match_email_html(all_pending: list, new_count: int = 0) -> str:
    """Build an HTML email body with approve/reject links for all pending matches."""
    viable = [
        m for m in all_pending
        if not m.get("price") or float(m["price"]) >= MIN_MATCH_PRICE
    ]
    skipped = len(all_pending) - len(viable)
    if skipped:
        logger.info(f"Filtered {skipped} matches with price below ${MIN_MATCH_PRICE:.0f}")

    total = len(viable)
    date_str = datetime.now().strftime("%B %d, %Y")

    cards_html = ""
    for i, m in enumerate(viable, 1):
        cards_html += _render_match_card(i, m)

    new_label = f"<span style='color:#4CAF50;font-weight:600'>{new_count}</span> new today &middot; " if new_count > 0 else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f5f5f5">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:20px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

  <tr><td style="background:#2d2d2d;padding:24px 24px 20px;border-radius:12px 12px 0 0">
    <h1 style="margin:0;color:#fff;font-size:22px">Daily Discovery Digest</h1>
    <p style="margin:8px 0 0;color:#aaa;font-size:14px">
      {new_label}<span style="color:#fff;font-weight:600">{total}</span> total pending &middot; {date_str}
    </p>
  </td></tr>

  <tr><td style="background:#fff;padding:20px 24px;border-radius:0 0 12px 12px">
    <p style="color:#666;font-size:14px;margin:0 0 16px">
      Click <strong style="color:#4CAF50">Approve</strong> or <strong style="color:#f44336">Reject</strong> for each match.
      Approved matches will be published in the next daily price update.
      Anything you skip will appear again tomorrow.
    </p>

    <table width="100%" cellpadding="0" cellspacing="0">
      {cards_html}
    </table>

    <p style="color:#888;font-size:12px;margin:20px 0 0;text-align:center">
      Cigar Price Scout &middot; Automated URL Discovery
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


def send_digest_email(config: dict, all_pending: list, new_count: int = 0):
    """Send the daily discovery HTML email with approve/reject links for all pending matches."""
    email_config = config.get("email_notifications", {})
    if not email_config.get("enabled") or not email_config.get("sender_email"):
        logger.info("Email notifications disabled, skipping digest email")
        return

    total = len(all_pending)
    date_str = datetime.now().strftime("%Y-%m-%d")

    if total > 0:
        subject = f"Cigar Price Scout - {total} URL Matches to Review - {date_str}"
        html_body = build_match_email_html(all_pending, new_count)
    else:
        subject = f"Cigar Price Scout - No Pending Matches - {date_str}"
        html_body = """<html><body style="font-family:sans-serif;background:#f5f5f5;padding:40px">
        <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;text-align:center">
        <h2>Daily Discovery Digest</h2>
        <p style="color:#666">No pending matches to review. New discoveries will appear here automatically.</p>
        </div></body></html>"""

    plain_body = f"Daily Discovery: {total} matches pending review ({new_count} new). Open in an HTML client to approve/reject."

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = email_config["sender_email"]
        msg["To"] = email_config.get("recipient_email") or email_config["sender_email"]
        msg["Subject"] = subject
        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"])
        server.starttls()
        server.login(email_config["sender_email"], email_config["sender_password"])
        server.sendmail(
            email_config["sender_email"],
            email_config.get("recipient_email") or email_config["sender_email"],
            msg.as_string(),
        )
        server.quit()
        logger.info(f"Daily digest email sent ({total} pending, {new_count} new)")

    except Exception as e:
        logger.error(f"Failed to send digest email: {e}")


def run_queue_processor() -> str:
    """Process the extractor generator queue if there are entries."""
    queue_file = PROJECT_ROOT / "tools" / "ai" / "new_retailer_queue.txt"
    if not queue_file.exists():
        return "No queue file found."

    # Check if there are actual entries (not just comments)
    has_entries = False
    with open(queue_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "|" in line:
                has_entries = True
                break

    if not has_entries:
        return "Queue file is empty (no retailer entries)."

    try:
        from tools.ai.extractor_generator import parse_queue_file, generate_for_retailer

        entries = parse_queue_file()
        if not entries:
            return "No valid entries in queue file."

        results = []
        for entry in entries:
            try:
                generate_for_retailer(entry["name"], entry["key"], entry["urls"])
                results.append(f"  [OK] {entry['name']} ({entry['key']}): Extractor generated")
            except Exception as e:
                results.append(f"  [FAIL] {entry['name']} ({entry['key']}): {e}")

        return "\n".join(results)

    except Exception as e:
        return f"Queue processing failed: {e}"


def read_staged_matches() -> list:
    """Read staged matches from CSV, return only those with status='staged'."""
    if not STAGED_FILE.exists():
        return []
    rows = []
    with open(STAGED_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status", "").strip() == "staged":
                rows.append(row)
    return rows


def enrich_with_prices(matches: list) -> list:
    """Fetch live prices using retailer-specific extractors."""
    logger.info(f"Fetching prices for {len(matches)} URLs via retailer extractors...")
    for i, m in enumerate(matches):
        retailer_key = m.get("retailer_key")
        logger.info(f"  [{i+1}/{len(matches)}] {retailer_key or '?'}: {m['url'][:70]}...")
        data = extract_via_retailer(m["url"], retailer_key)
        m["price"] = data.get("price")
        m["in_stock"] = data.get("in_stock")
        time.sleep(1.2)
    found = sum(1 for m in matches if m.get("price"))
    logger.info(f"Prices found: {found}/{len(matches)}")
    return matches


def main():
    parser = argparse.ArgumentParser(description="Daily URL Discovery Runner")
    parser.add_argument("--top-cids", type=int, default=50, help="Number of CIDs to search for")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending email")
    parser.add_argument("--skip-queue", action="store_true", help="Skip extractor generator queue")
    parser.add_argument("--skip-prices", action="store_true", help="Skip live price fetching for new matches")
    parser.add_argument("--email-only", action="store_true", help="Skip discovery, just send pending matches email")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"DAILY URL DISCOVERY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    config = load_config()

    if os.getenv("GITHUB_ACTIONS"):
        logger.info("Running in GitHub Actions -- skipping git pull (checkout is fresh)")
    else:
        import subprocess
        logger.info("Pulling latest from git...")
        pull_result = subprocess.run(
            ["git", "pull", "--rebase"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        if pull_result.returncode == 0:
            logger.info("Git pull successful")
        else:
            logger.warning(f"Git pull issue (continuing): {pull_result.stderr}")

    # 0. Publish any previously approved matches into retailer CSVs
    logger.info("Checking for approved matches to publish...")
    approved = fetch_approved_from_api()
    if approved:
        pub_count = publish_approved_to_csvs(approved)
        logger.info(f"Published {pub_count} approved matches to retailer CSVs")
    else:
        logger.info("No approved matches to publish")

    new_count = 0

    if not args.email_only:
        # 1. Run URL discovery (finds new matches)
        logger.info(f"Running URL discovery for top {args.top_cids} CIDs...")
        try:
            run_discovery(top_n_cids=args.top_cids)
        except Exception as e:
            logger.error(f"URL discovery failed: {e}")

        # 2. Process extractor generator queue
        if not args.skip_queue:
            logger.info("Checking extractor generator queue...")
            run_queue_processor()

        # 3. Read NEW staged matches from local CSV and upload to API
        staged = read_staged_matches()
        logger.info(f"Found {len(staged)} new staged matches in local CSV")

        if staged and not args.skip_prices:
            staged = enrich_with_prices(staged)

        if staged:
            tokens = upload_matches_to_api(staged)
            new_count = len(tokens)
            logger.info(f"{new_count} new matches uploaded to API")

    # 4. Fetch ALL pending matches from API (new + old unreviewed)
    all_pending = fetch_all_pending_from_api()
    logger.info(f"Total pending matches for review: {len(all_pending)}")

    # 5. Send daily email with the full pending queue
    if not args.dry_run:
        if all_pending or new_count > 0:
            send_digest_email(config, all_pending, new_count)
        else:
            logger.info("No pending matches and no new discoveries, skipping email")

    print(f"\n{'='*70}")
    print(f"DAILY DISCOVERY COMPLETE - {len(all_pending)} pending, {new_count} new")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
