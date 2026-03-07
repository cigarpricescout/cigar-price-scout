#!/usr/bin/env python3
"""
Extractor Generator - AI-powered retailer extractor creation.

Reads new retailer entries from a queue file, uses Playwright to analyze
product pages, and Claude to generate extractor code with self-testing.

Usage:
    # Process the queue file
    python tools/ai/extractor_generator.py --process-queue

    # Generate for a specific retailer directly
    python tools/ai/extractor_generator.py --generate \\
        --retailer-name "New Cigar Shop" --retailer-key newcigarshop \\
        --urls "https://example.com/product1" "https://example.com/product2"

    # Approve a generated extractor for production
    python tools/ai/extractor_generator.py --approve newcigarshop

Queue file format (tools/ai/new_retailer_queue.txt):
    # Lines starting with # are comments
    # Format: Retailer Name | retailer_key
    # Followed by one URL per line
    # Blank line separates entries
    New Cigar Shop | newcigarshop
    https://example.com/products/padron-1964
    https://example.com/products/arturo-fuente-hemingway

Environment:
    ANTHROPIC_API_KEY - Required
"""

import os
import sys
import re
import json
import time
import shutil
import logging
import argparse
import subprocess
import textwrap
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import anthropic
except ImportError:
    print("[ERROR] anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[ERROR] playwright package not installed. Run: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AI_DIR = Path(__file__).resolve().parent
RETAILERS_DIR = PROJECT_ROOT / "tools" / "price_monitoring" / "retailers"
APP_DIR = PROJECT_ROOT / "app"
STATIC_DATA = PROJECT_ROOT / "static" / "data"
QUEUE_FILE = AI_DIR / "new_retailer_queue.txt"
REPORTS_DIR = AI_DIR / "generator_reports"


# ── Page analysis ──────────────────────────────────────────────────────

def analyze_pages(urls: List[str]) -> List[Dict]:
    """
    Use Playwright to render product pages and capture HTML + screenshots.
    Returns list of {url, html, screenshot_path, title, page_text}.
    """
    results = []
    screenshots_dir = REPORTS_DIR / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        for i, url in enumerate(urls):
            logger.info(f"  Analyzing page {i+1}/{len(urls)}: {url}")
            page = context.new_page()

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(2)  # Extra wait for late-loading elements

                html = page.content()
                title = page.title()
                page_text = page.inner_text("body")

                # Take screenshot
                slug = re.sub(r"[^a-z0-9]", "_", url.split("/")[-1].lower())[:50]
                screenshot_path = screenshots_dir / f"page_{i+1}_{slug}.png"
                page.screenshot(path=str(screenshot_path), full_page=False)

                results.append({
                    "url": url,
                    "html": html,
                    "screenshot_path": str(screenshot_path),
                    "title": title,
                    "page_text": page_text[:5000],
                })

            except Exception as e:
                logger.error(f"  Failed to analyze {url}: {e}")
                results.append({
                    "url": url,
                    "html": "",
                    "screenshot_path": "",
                    "title": "",
                    "page_text": "",
                    "error": str(e),
                })
            finally:
                page.close()

        browser.close()

    return results


# ── Ground truth extraction via Claude ─────────────────────────────────

def extract_ground_truth(
    client: anthropic.Anthropic,
    page_data: List[Dict],
) -> List[Dict]:
    """
    Have Claude read page text/HTML to determine the 'correct' product data.
    This serves as the ground truth to validate the generated extractor.
    """
    results = []

    for pd_item in page_data:
        if pd_item.get("error"):
            results.append({"url": pd_item["url"], "error": pd_item["error"]})
            continue

        prompt = f"""Analyze this cigar product page and extract the following data.
Return ONLY a JSON object with these fields:

{{
  "price": <box price as float, e.g. 189.99>,
  "box_quantity": <number of cigars in the box, e.g. 25>,
  "in_stock": <true or false>,
  "product_title": "<full product title>"
}}

RULES:
- "price" should be the CURRENT/SALE price for a BOX (not per stick, not MSRP)
- If there are multiple pricing options (single, 5-pack, box), use the BOX price
- "box_quantity" is the number of cigars in the box (usually 10, 20, 25, or 50)
- "in_stock" is true if there's an "Add to Cart" button, false if "Sold Out" / "Notify Me"
- If the page is unavailable or has an error, set price to null

Page title: {pd_item['title']}
Page URL: {pd_item['url']}

Page text (first 4000 chars):
{pd_item['page_text'][:4000]}

Relevant HTML snippets (price/stock areas):
{_extract_relevant_html(pd_item['html'])}

Return ONLY the JSON object, no explanation."""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                data = json.loads(json_match.group())
                data["url"] = pd_item["url"]
                results.append(data)
            else:
                results.append({"url": pd_item["url"], "error": "No JSON in response"})
        except Exception as e:
            results.append({"url": pd_item["url"], "error": str(e)})

    return results


def _extract_relevant_html(html: str) -> str:
    """Extract HTML sections likely containing price/stock info."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    snippets = []

    # Price-related elements
    for selector in [
        '[class*="price"]', '[class*="Price"]',
        '[class*="product-price"]', '[class*="sale"]',
        '[id*="price"]', '[data-price]',
    ]:
        for elem in soup.select(selector)[:5]:
            snippets.append(str(elem)[:500])

    # Stock/cart buttons
    for elem in soup.find_all(["button", "input"], string=re.compile(
        r"add.to.cart|sold.out|notify|out.of.stock|buy.now", re.I
    )):
        snippets.append(str(elem)[:300])

    # Product title
    h1 = soup.find("h1")
    if h1:
        snippets.append(str(h1)[:300])

    # JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "Product":
                snippets.append(json.dumps(data, indent=2)[:1000])
        except (json.JSONDecodeError, TypeError):
            pass

    # JavaScript pricing data (BCData, Shopify, etc.)
    for script in soup.find_all("script"):
        text = script.string or ""
        if any(kw in text for kw in ["BCData", "ShopifyAnalytics", "product_price", "variants"]):
            snippets.append(text[:1000])

    return "\n---\n".join(snippets[:10]) if snippets else "(no relevant HTML found)"


# ── Extractor code generation via Claude ───────────────────────────────

GENERATOR_PROMPT = """You are generating a Python extractor for a cigar retailer website.

The extractor must inherit from BaseExtractor and follow this exact pattern:

```python
from base_extractor import BaseExtractor, create_extract_function

class {ClassName}Extractor(BaseExtractor):
    RETAILER_NAME = "{retailer_name}"
    RETAILER_KEY = "{retailer_key}"
    BASE_URL = "{base_url}"
    RATE_LIMIT_SECONDS = 1.5

    def extract_product_data(self, url):
        soup = self.fetch_page(url)
        
        price = self._extract_price(soup)
        box_quantity = self._extract_box_quantity(soup)
        in_stock = self._extract_stock_status(soup)
        
        return {{
            'price': price,
            'box_quantity': box_quantity,
            'in_stock': in_stock,
            'error': None,
        }}

    def _extract_price(self, soup):
        # Retailer-specific price extraction
        ...

    def _extract_box_quantity(self, soup):
        # Retailer-specific box quantity extraction
        ...

    def _extract_stock_status(self, soup):
        # Retailer-specific stock detection
        ...

extract_{retailer_key}_data = create_extract_function({ClassName}Extractor)
```

IMPORTANT RULES:
1. Import BaseExtractor from base_extractor (relative import, same directory)
2. Use self.fetch_page(url) to get BeautifulSoup - DO NOT create your own session
3. Use self.parse_price(), self.parse_all_prices(), self.extract_box_quantity() helpers when appropriate
4. Use self.detect_stock_from_soup() and self.detect_stock_from_text() helpers
5. The extract_product_data method must return a dict with: price, box_quantity, in_stock, error
6. Create the module-level function using create_extract_function() at the bottom
7. Handle edge cases gracefully - return None for missing data, don't crash
8. Price should be the BOX price (not per stick)
9. Use requests/BeautifulSoup, NOT Playwright (the extractor runs in automation)
"""


def generate_extractor_code(
    client: anthropic.Anthropic,
    retailer_name: str,
    retailer_key: str,
    page_data: List[Dict],
    ground_truth: List[Dict],
    attempt: int = 1,
    previous_errors: str = "",
) -> str:
    """Generate extractor code using Claude."""
    # Build class name from retailer key
    class_name = "".join(word.capitalize() for word in retailer_key.split("_"))
    if not class_name[0].isupper():
        class_name = class_name.capitalize()

    # Get base URL from first URL
    from urllib.parse import urlparse
    first_url = page_data[0]["url"]
    parsed = urlparse(first_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Build context about the pages
    page_analysis = []
    for pd_item, gt in zip(page_data, ground_truth):
        if pd_item.get("error"):
            continue
        page_analysis.append(f"""
URL: {pd_item['url']}
Title: {pd_item['title']}
Expected price: ${gt.get('price', 'unknown')}
Expected box qty: {gt.get('box_quantity', 'unknown')}
Expected in stock: {gt.get('in_stock', 'unknown')}

Relevant HTML:
{_extract_relevant_html(pd_item['html'])}
""")

    user_msg = f"""Generate a complete Python extractor for {retailer_name}.

Retailer: {retailer_name}
Key: {retailer_key}
Class name: {class_name}Extractor
Base URL: {base_url}

Here are the sample product pages I analyzed:
{"".join(page_analysis)}

{"PREVIOUS ATTEMPT FAILED. Here are the errors:" + chr(10) + previous_errors if previous_errors else ""}

Generate the COMPLETE Python file. Include all imports. The file should be ready to save and run.
Return ONLY the Python code, no markdown fences or explanations."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=GENERATOR_PROMPT.format(
            ClassName=class_name,
            retailer_name=retailer_name,
            retailer_key=retailer_key,
            base_url=base_url,
        ),
        messages=[{"role": "user", "content": user_msg}],
    )

    code = response.content[0].text.strip()

    # Strip markdown fences if present
    code = re.sub(r"^```python\s*", "", code)
    code = re.sub(r"\s*```$", "", code)

    return code


# ── Update script generation ──────────────────────────────────────────

def generate_update_script(retailer_name: str, retailer_key: str) -> str:
    """Generate the update_*_prices_final.py script from template."""
    class_name = "".join(word.capitalize() for word in retailer_key.split("_"))

    # Read an existing update script as reference for the exact pattern
    template = textwrap.dedent(f'''\
        """
        {retailer_name} Enhanced CSV Updater with Master-Driven Metadata Sync
        Auto-generated by Extractor Generator
        """

        import csv
        import os
        import sys
        import pandas as pd
        import sqlite3
        from datetime import datetime
        from typing import List, Dict

        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        tools_path = os.path.join(project_root, 'tools', 'price_monitoring', 'retailers')
        sys.path.insert(0, tools_path)

        from {retailer_key}_extractor import extract_{retailer_key}_data


        class {class_name}CSVUpdater:
            def __init__(self, csv_path=None, master_path=None, dry_run=False):
                if csv_path is None:
                    self.csv_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'data', '{retailer_key}.csv')
                else:
                    self.csv_path = csv_path

                if master_path is None:
                    self.master_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'master_cigars.db')
                else:
                    self.master_path = master_path

                self.master_df = None
                self.dry_run = dry_run

            def load_master_file(self):
                try:
                    conn = sqlite3.connect(self.master_path)
                    self.master_df = pd.read_sql_query("SELECT * FROM cigars", conn)
                    conn.close()
                    self.master_df['box_quantity'] = pd.to_numeric(self.master_df['box_quantity'], errors='coerce').fillna(0)
                    print(f"[INFO] Loaded master file with {{len(self.master_df)}} cigars")
                    return True
                except Exception as e:
                    print(f"[ERROR] Failed to load master file: {{e}}")
                    return False

            def get_cigar_metadata(self, cigar_id):
                if self.master_df is None:
                    return {{}}
                matching = self.master_df[self.master_df['cigar_id'] == cigar_id]
                if len(matching) == 0:
                    return {{}}
                row = matching.iloc[0]
                size = ''
                if pd.notna(row.get('length')) and pd.notna(row.get('ring_gauge')):
                    size = f"{{row.get('length')}}x{{row.get('ring_gauge')}}"
                box_qty = 0
                if pd.notna(row.get('box_quantity')):
                    try:
                        box_qty = int(row.get('box_quantity', 0))
                    except (ValueError, TypeError):
                        pass
                return {{
                    'title': row.get('product_name', ''),
                    'brand': row.get('brand', ''),
                    'line': row.get('line', ''),
                    'wrapper': row.get('wrapper', ''),
                    'vitola': row.get('vitola', ''),
                    'size': size,
                    'box_qty': box_qty,
                }}

            def auto_populate_metadata(self, row):
                cigar_id = row.get('cigar_id', '')
                if not cigar_id:
                    return row
                metadata = self.get_cigar_metadata(cigar_id)
                for field in ['title', 'brand', 'line', 'wrapper', 'vitola', 'size', 'box_qty']:
                    if field in metadata and metadata[field]:
                        row[field] = metadata[field]
                return row

            def run_update(self):
                print("=" * 70)
                print(f"{retailer_name.upper()} PRICE UPDATE - {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}")
                print("=" * 70)

                if not self.load_master_file():
                    return False

                try:
                    with open(self.csv_path, 'r', newline='', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        data = list(reader)
                    print(f"[INFO] Loaded {{len(data)}} products")
                except FileNotFoundError:
                    print(f"[ERROR] CSV not found: {{self.csv_path}}")
                    return False

                successful = 0
                failed = 0

                for i, row in enumerate(data):
                    cigar_id = row.get('cigar_id', 'Unknown')
                    url = row.get('url', '')
                    print(f"\\n[{{i+1}}/{{len(data)}}] {{cigar_id}}")

                    row = self.auto_populate_metadata(row)

                    if not url:
                        print("  [SKIP] No URL")
                        failed += 1
                        continue

                    if self.dry_run:
                        print("  [DRY RUN] Skipping extraction")
                        successful += 1
                        continue

                    try:
                        result = extract_{retailer_key}_data(url)
                        if result['success'] and result.get('price') and result['price'] > 0:
                            row['price'] = result['price']
                            row['in_stock'] = result['in_stock']
                            print(f"  [OK] ${{result['price']}} | {{'In Stock' if result['in_stock'] else 'Out of Stock'}}")
                            successful += 1
                        else:
                            current_price = row.get('price', 'N/A')
                            print(f"  [PRICE] Preserved ${{current_price}} ({{result.get('error', 'no valid price')}})")
                            row['in_stock'] = result.get('in_stock', row.get('in_stock', ''))
                            failed += 1
                    except Exception as e:
                        print(f"  [FAIL] {{e}}")
                        failed += 1

                if not self.dry_run:
                    fieldnames = list(data[0].keys()) if data else []
                    with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(data)

                print(f"\\nSuccessful updates: {{successful}}")
                print(f"Failed updates: {{failed}}")
                return True


        def main():
            import argparse
            parser = argparse.ArgumentParser(description='{retailer_name} price updater')
            parser.add_argument('--csv', help='Path to CSV file')
            parser.add_argument('--master', help='Path to master DB')
            parser.add_argument('--dry-run', action='store_true')
            args = parser.parse_args()

            updater = {class_name}CSVUpdater(csv_path=args.csv, master_path=args.master, dry_run=args.dry_run)
            success = updater.run_update()
            sys.exit(0 if success else 1)


        if __name__ == "__main__":
            main()
    ''')

    return template


# ── Self-test loop ─────────────────────────────────────────────────────

def test_extractor(
    retailer_key: str,
    extractor_path: Path,
    urls: List[str],
    ground_truth: List[Dict],
) -> Tuple[List[Dict], bool]:
    """
    Test the generated extractor against sample URLs.
    Returns (results, all_passed).
    """
    results = []
    all_passed = True

    # Import the extractor dynamically
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"{retailer_key}_extractor", str(extractor_path),
    )
    mod = importlib.util.module_from_spec(spec)

    # Add retailers dir to path for base_extractor import
    retailers_dir = str(RETAILERS_DIR)
    if retailers_dir not in sys.path:
        sys.path.insert(0, retailers_dir)

    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        return [{"error": f"Import failed: {e}"}], False

    extract_fn_name = f"extract_{retailer_key}_data"
    extract_fn = getattr(mod, extract_fn_name, None)
    if not extract_fn:
        return [{"error": f"Function {extract_fn_name} not found in module"}], False

    for url_data, gt in zip(urls, ground_truth):
        url = url_data if isinstance(url_data, str) else url_data["url"]
        if gt.get("error"):
            continue

        try:
            result = extract_fn(url)

            test_result = {
                "url": url,
                "extracted_price": result.get("price"),
                "expected_price": gt.get("price"),
                "extracted_box_qty": result.get("box_quantity"),
                "expected_box_qty": gt.get("box_quantity"),
                "extracted_in_stock": result.get("in_stock"),
                "expected_in_stock": gt.get("in_stock"),
                "error": result.get("error"),
                "passed": True,
                "issues": [],
            }

            # Check price
            if gt.get("price") is not None and result.get("price") is not None:
                price_diff = abs(float(result["price"]) - float(gt["price"]))
                if price_diff > 1.0:
                    test_result["passed"] = False
                    test_result["issues"].append(
                        f"Price mismatch: got ${result['price']}, expected ${gt['price']}"
                    )
            elif gt.get("price") is not None and result.get("price") is None:
                test_result["passed"] = False
                test_result["issues"].append("Price extraction returned None")

            # Check box quantity
            if gt.get("box_quantity") and result.get("box_quantity"):
                if int(result["box_quantity"]) != int(gt["box_quantity"]):
                    test_result["passed"] = False
                    test_result["issues"].append(
                        f"Box qty mismatch: got {result['box_quantity']}, expected {gt['box_quantity']}"
                    )

            # Check stock
            if gt.get("in_stock") is not None and result.get("in_stock") is not None:
                if bool(result["in_stock"]) != bool(gt["in_stock"]):
                    test_result["issues"].append(
                        f"Stock mismatch: got {result['in_stock']}, expected {gt['in_stock']}"
                    )

            if not test_result["passed"]:
                all_passed = False

            results.append(test_result)

        except Exception as e:
            results.append({
                "url": url,
                "error": str(e),
                "passed": False,
                "issues": [f"Exception: {e}"],
            })
            all_passed = False

        time.sleep(1.5)

    return results, all_passed


# ── Report generation ──────────────────────────────────────────────────

def write_report(
    retailer_name: str,
    retailer_key: str,
    test_results: List[Dict],
    all_passed: bool,
    attempt: int,
) -> str:
    """Write a human-readable report for the generated extractor."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{retailer_key}_report.txt"

    passed = sum(1 for r in test_results if r.get("passed", False))
    total = len(test_results)

    lines = [
        f"=== Extractor Generation Report ===",
        f"",
        f"Retailer: {retailer_name}",
        f"Generated: tools/price_monitoring/retailers/{retailer_key}_extractor.py",
        f"Update script: app/update_{retailer_key}_prices_final.py",
        f"CSV: static/data/{retailer_key}.csv",
        f"Attempt: {attempt}",
        f"Time: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
        f"",
        f"Test Results ({passed}/{total} passed):",
    ]

    for i, r in enumerate(test_results, 1):
        if r.get("error") and not r.get("extracted_price"):
            lines.append(f"  URL {i}: ERROR - {r['error']}")
            continue

        status = "OK" if r.get("passed") else "FAIL"
        price_str = f"${r.get('extracted_price', 'N/A')}"
        qty_str = str(r.get("extracted_box_qty", "N/A"))
        stock_str = "In Stock" if r.get("extracted_in_stock") else "Out of Stock"
        lines.append(f"  URL {i}: Price={price_str}, Box={qty_str}, {stock_str}  {status}")

        if r.get("issues"):
            for issue in r["issues"]:
                lines.append(f"         {issue}")

    lines.append("")

    if all_passed:
        confidence = "HIGH" if total >= 3 else "MEDIUM"
        lines.extend([
            f"Confidence: {confidence} -- {passed}/{total} test URLs extracted correctly.",
            f"",
            f"Ready for production? Run:",
            f"  python tools/ai/extractor_generator.py --approve {retailer_key}",
        ])
    else:
        lines.extend([
            f"Confidence: LOW -- {total - passed}/{total} test URLs failed.",
            f"",
            f"Options:",
            f"  1. Add more sample URLs and retry",
            f"  2. Manually tweak the generated extractor",
            f"  3. Open Cursor for interactive debugging",
        ])

    report = "\n".join(lines)

    with open(report_path, "w") as f:
        f.write(report)

    return report


# ── Queue file parsing ─────────────────────────────────────────────────

def parse_queue_file() -> List[Dict]:
    """Parse the new_retailer_queue.txt file."""
    if not QUEUE_FILE.exists():
        return []

    entries = []
    current_entry = None

    with open(QUEUE_FILE, "r") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                if current_entry and current_entry.get("urls"):
                    entries.append(current_entry)
                    current_entry = None
                continue

            if "|" in line and not line.startswith("http"):
                # Header line: Retailer Name | retailer_key
                if current_entry and current_entry.get("urls"):
                    entries.append(current_entry)

                parts = line.split("|")
                name = parts[0].strip()
                key = parts[1].strip() if len(parts) > 1 else re.sub(
                    r"[^a-z0-9]", "", name.lower()
                )
                current_entry = {"name": name, "key": key, "urls": []}

            elif line.startswith("http") and current_entry:
                current_entry["urls"].append(line)

    if current_entry and current_entry.get("urls"):
        entries.append(current_entry)

    return entries


# ── Approval workflow ──────────────────────────────────────────────────

def approve_retailer(retailer_key: str):
    """Approve a generated extractor for production use."""
    extractor_path = RETAILERS_DIR / f"{retailer_key}_extractor.py"
    update_script = APP_DIR / f"update_{retailer_key}_prices_final.py"
    csv_path = STATIC_DATA / f"{retailer_key}.csv"

    if not extractor_path.exists():
        print(f"[ERROR] Extractor not found: {extractor_path}")
        return False

    if not update_script.exists():
        print(f"[ERROR] Update script not found: {update_script}")
        return False

    # Create empty CSV if it doesn't exist
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "cigar_id", "title", "url", "brand", "line", "wrapper",
                "vitola", "size", "box_qty", "price", "in_stock",
            ])
        print(f"[OK] Created CSV: {csv_path}")

    print(f"[OK] Extractor approved: {extractor_path}")
    print(f"[OK] Update script ready: {update_script}")
    print(f"[OK] CSV ready: {csv_path}")
    print(f"\n{retailer_key} is now ready for the automation system.")
    print(f"The URL Discovery Agent will find CIDs for this retailer on its next run.")
    return True


# ── Main generation pipeline ──────────────────────────────────────────

def generate_for_retailer(
    retailer_name: str,
    retailer_key: str,
    urls: List[str],
    api_key: Optional[str] = None,
):
    """Full generation pipeline for a single retailer."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[ERROR] ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=key)

    print(f"\n{'='*70}")
    print(f"EXTRACTOR GENERATOR - {retailer_name}")
    print(f"{'='*70}")

    # Step 1: Analyze pages with Playwright
    print(f"\nStep 1: Analyzing {len(urls)} product pages...")
    page_data = analyze_pages(urls)

    valid_pages = [p for p in page_data if not p.get("error")]
    if not valid_pages:
        print("[ERROR] All pages failed to load. Check URLs and try again.")
        return

    # Step 2: Extract ground truth via Claude
    print(f"\nStep 2: Extracting ground truth from pages...")
    ground_truth = extract_ground_truth(client, page_data)

    for gt in ground_truth:
        if gt.get("error"):
            print(f"  [WARN] Ground truth failed for {gt['url']}: {gt['error']}")
        else:
            print(f"  [OK] {gt['url']}: ${gt.get('price', 'N/A')}, "
                  f"Box={gt.get('box_quantity', 'N/A')}, "
                  f"Stock={gt.get('in_stock', 'N/A')}")

    # Step 3: Generate extractor with self-correction loop
    max_attempts = 3
    extractor_path = RETAILERS_DIR / f"{retailer_key}_extractor.py"
    previous_errors = ""

    for attempt in range(1, max_attempts + 1):
        print(f"\nStep 3: Generating extractor (attempt {attempt}/{max_attempts})...")

        code = generate_extractor_code(
            client, retailer_name, retailer_key,
            page_data, ground_truth,
            attempt=attempt,
            previous_errors=previous_errors,
        )

        # Save the extractor
        with open(extractor_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"  Saved: {extractor_path}")

        # Step 4: Test it
        print(f"\nStep 4: Testing extractor (attempt {attempt})...")
        test_results, all_passed = test_extractor(
            retailer_key, extractor_path, urls, ground_truth,
        )

        if all_passed:
            print(f"\n  All {len(test_results)} tests passed!")
            break

        # Collect errors for next attempt
        error_lines = []
        for r in test_results:
            if not r.get("passed"):
                error_lines.append(f"URL: {r.get('url', 'unknown')}")
                for issue in r.get("issues", []):
                    error_lines.append(f"  Issue: {issue}")
                if r.get("error"):
                    error_lines.append(f"  Error: {r['error']}")
        previous_errors = "\n".join(error_lines)

        if attempt < max_attempts:
            print(f"\n  {len(test_results) - sum(1 for r in test_results if r.get('passed'))} "
                  f"tests failed. Retrying...")

    # Step 5: Generate update script
    print(f"\nStep 5: Generating update script...")
    update_code = generate_update_script(retailer_name, retailer_key)
    update_path = APP_DIR / f"update_{retailer_key}_prices_final.py"
    with open(update_path, "w", encoding="utf-8") as f:
        f.write(update_code)
    print(f"  Saved: {update_path}")

    # Step 6: Create empty CSV
    csv_path = STATIC_DATA / f"{retailer_key}.csv"
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "cigar_id", "title", "url", "brand", "line", "wrapper",
                "vitola", "size", "box_qty", "price", "in_stock",
            ])
        print(f"  Created: {csv_path}")

    # Step 7: Write report
    report = write_report(retailer_name, retailer_key, test_results, all_passed, attempt)
    print(f"\n{report}")


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extractor Generator - AI-powered retailer extractor creation",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--process-queue", action="store_true",
        help="Process entries from new_retailer_queue.txt",
    )
    group.add_argument(
        "--generate", action="store_true",
        help="Generate extractor for a specific retailer (requires --retailer-name, --retailer-key, --urls)",
    )
    group.add_argument(
        "--approve", type=str, metavar="RETAILER_KEY",
        help="Approve a generated extractor for production",
    )

    parser.add_argument("--retailer-name", type=str, help="Display name for the retailer")
    parser.add_argument("--retailer-key", type=str, help="Key for filenames (e.g., newcigarshop)")
    parser.add_argument("--urls", nargs="+", help="Sample product page URLs")
    parser.add_argument("--api-key", type=str, help="Anthropic API key")

    args = parser.parse_args()

    if args.approve:
        approve_retailer(args.approve)

    elif args.generate:
        if not args.retailer_name or not args.retailer_key or not args.urls:
            parser.error("--generate requires --retailer-name, --retailer-key, and --urls")
        generate_for_retailer(
            args.retailer_name, args.retailer_key, args.urls,
            api_key=args.api_key,
        )

    elif args.process_queue:
        entries = parse_queue_file()
        if not entries:
            print(f"[INFO] No entries in queue file: {QUEUE_FILE}")
            print(f"       Create the file with retailer entries to process.")
            return

        print(f"Found {len(entries)} retailer(s) in queue:")
        for e in entries:
            print(f"  {e['name']} ({e['key']}): {len(e['urls'])} URLs")

        for entry in entries:
            generate_for_retailer(
                entry["name"], entry["key"], entry["urls"],
                api_key=args.api_key,
            )


if __name__ == "__main__":
    main()
