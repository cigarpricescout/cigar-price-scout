#!/usr/bin/env python3
"""
Weekly URL Discovery Runner

Runs the URL Discovery Agent, uploads matches to the live site API,
and sends an HTML email with one-click Approve/Reject links.

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


def load_config():
    """Load automation config for email settings."""
    config_path = AUTOMATION_DIR / "automation_config.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)
    return {}


def fetch_price(url: str, timeout: int = 12) -> dict:
    """Fetch price/stock from a product page for email display."""
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


def build_match_email_html(matches_with_tokens: list) -> str:
    """Build an HTML email body with approve/reject links for each match."""
    count = len(matches_with_tokens)
    date_str = datetime.now().strftime("%B %d, %Y")

    cards_html = ""
    for i, m in enumerate(matches_with_tokens, 1):
        conf = (m.get("confidence") or "MEDIUM").upper()
        conf_color = "#2e7d32" if conf == "HIGH" else "#e65100" if conf == "MEDIUM" else "#c62828"
        conf_bg = "#e8f5e9" if conf == "HIGH" else "#fff3e0" if conf == "MEDIUM" else "#ffebee"

        price_str = f"${m['price']:.2f}" if m.get("price") else "N/A"
        stock_str = "In Stock" if m.get("in_stock") else "Out of Stock" if m.get("in_stock") is False else "Unknown"
        stock_color = "#2e7d32" if m.get("in_stock") else "#c62828" if m.get("in_stock") is False else "#888"

        approve_url = f"{APP_BASE_URL}/admin/match/{m['token']}/approve"
        reject_url = f"{APP_BASE_URL}/admin/match/{m['token']}/reject"
        product_url = m.get("url", "")

        reason = m.get("reason", "")
        if len(reason) > 120:
            reason = reason[:117] + "..."

        cards_html += f"""
        <tr><td style="padding:8px 0">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden">
            <tr><td style="padding:16px 20px">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="font-size:16px;font-weight:bold;color:#333">
                    #{i}. {m.get('brand','')} {m.get('line','')} {m.get('vitola','')}
                  </td>
                  <td align="right">
                    <span style="background:{conf_bg};color:{conf_color};padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700">{conf}</span>
                  </td>
                </tr>
              </table>
              <p style="margin:8px 0 4px;color:#666;font-size:13px">
                {m.get('retailer_key','')} &middot; {m.get('size','')} &middot; Box of {m.get('box_qty','?')} &middot; {m.get('wrapper','')}
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0">
                <tr>
                  <td style="font-size:18px;font-weight:bold;color:#333">{price_str}</td>
                  <td style="font-size:13px;font-weight:600;color:{stock_color}">{stock_str}</td>
                </tr>
              </table>
              <p style="margin:4px 0 12px;color:#888;font-size:12px;font-style:italic">{reason}</p>
              <table cellpadding="0" cellspacing="0"><tr>
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

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f5f5f5">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:20px 0">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

  <tr><td style="background:#2d2d2d;padding:24px 24px 20px;border-radius:12px 12px 0 0">
    <h1 style="margin:0;color:#fff;font-size:22px">Weekly Discovery Digest</h1>
    <p style="margin:8px 0 0;color:#aaa;font-size:14px">
      <span style="color:#4CAF50;font-weight:600">{count}</span> new matches found &middot; {date_str}
    </p>
  </td></tr>

  <tr><td style="background:#fff;padding:20px 24px;border-radius:0 0 12px 12px">
    <p style="color:#666;font-size:14px;margin:0 0 16px">
      Click <strong style="color:#4CAF50">Approve</strong> or <strong style="color:#f44336">Reject</strong> for each match.
      Approved matches will be published in the next daily price update.
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


def send_digest_email(config: dict, matches_with_tokens: list, report_text: str = "", queue_report: str = ""):
    """Send the weekly discovery HTML email with approve/reject links."""
    email_config = config.get("email_notifications", {})
    if not email_config.get("enabled") or not email_config.get("sender_email"):
        logger.info("Email notifications disabled, skipping digest email")
        return

    count = len(matches_with_tokens)
    subject = f"Cigar Price Scout - {count} New URL Matches to Review - {datetime.now().strftime('%Y-%m-%d')}"

    if count > 0:
        html_body = build_match_email_html(matches_with_tokens)
    else:
        html_body = f"""<html><body style="font-family:sans-serif;background:#f5f5f5;padding:40px">
        <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;text-align:center">
        <h2>Weekly Discovery Digest</h2>
        <p style="color:#666">No new matches found this week.</p>
        <pre style="text-align:left;font-size:12px;color:#888;background:#f5f5f5;padding:16px;border-radius:8px">{report_text}</pre>
        </div></body></html>"""

    plain_body = f"Weekly Discovery: {count} new matches. Open this email in an HTML-capable client to review."

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
        logger.info(f"Weekly digest email sent ({count} matches)")

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
    """Fetch live prices for each match URL."""
    logger.info(f"Fetching prices for {len(matches)} URLs...")
    for i, m in enumerate(matches):
        logger.info(f"  [{i+1}/{len(matches)}] {m['url'][:70]}...")
        data = fetch_price(m["url"])
        m["price"] = data.get("price")
        m["in_stock"] = data.get("in_stock")
        time.sleep(1.2)
    found = sum(1 for m in matches if m.get("price"))
    logger.info(f"Prices found: {found}/{len(matches)}")
    return matches


def main():
    parser = argparse.ArgumentParser(description="Weekly URL Discovery Runner")
    parser.add_argument("--top-cids", type=int, default=50, help="Number of CIDs to search for")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending email")
    parser.add_argument("--skip-queue", action="store_true", help="Skip extractor generator queue")
    parser.add_argument("--skip-prices", action="store_true", help="Skip live price fetching")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"WEEKLY URL DISCOVERY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    config = load_config()

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

    # 1. Run URL discovery
    logger.info(f"Running URL discovery for top {args.top_cids} CIDs...")
    try:
        run_discovery(top_n_cids=args.top_cids)
    except Exception as e:
        logger.error(f"URL discovery failed: {e}")

    report_text = ""
    if REPORT_FILE.exists():
        with open(REPORT_FILE, "r") as f:
            report_text = f.read()

    # 2. Process extractor generator queue
    queue_report = ""
    if not args.skip_queue:
        logger.info("Checking extractor generator queue...")
        queue_report = run_queue_processor()

    # 3. Read staged matches and enrich with prices
    staged = read_staged_matches()
    logger.info(f"Found {len(staged)} staged matches")

    if staged and not args.skip_prices:
        staged = enrich_with_prices(staged)

    # 4. Upload matches to the live API
    matches_with_tokens = []
    if staged:
        tokens = upload_matches_to_api(staged)
        token_map = {(t["cid"], t["retailer_key"]): t["token"] for t in tokens}

        for m in staged:
            key = (m["cid"], m["retailer_key"])
            token = token_map.get(key)
            if token:
                m["token"] = token
                matches_with_tokens.append(m)

        logger.info(f"{len(matches_with_tokens)} matches uploaded with tokens")

    # 5. Send HTML email with approve/reject links
    if not args.dry_run:
        send_digest_email(config, matches_with_tokens, report_text, queue_report)

    print(f"\n{'='*70}")
    print("WEEKLY DISCOVERY COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
