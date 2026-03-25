#!/usr/bin/env python3
"""
Review Batch - Generate an HTML review page for AI-discovered URL matches.

Reads staged_matches.csv, prioritizes by search demand, and creates a local
HTML page where you can click URLs to verify, then approve/reject each match.
Decisions are saved to review_decisions.csv and fed back into staged_matches.

Usage:
    # Generate HTML review page for top 15 CIDs
    python tools/ai/review_batch.py --batch-size 15

    # Process decisions after reviewing in browser
    python tools/ai/review_batch.py --process-decisions

    # Show status summary
    python tools/ai/review_batch.py --status
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
STAGED_CSV = SCRIPT_DIR / "staged_matches.csv"
DECISIONS_CSV = SCRIPT_DIR / "review_decisions.csv"
REVIEW_HTML = SCRIPT_DIR / "review_batch.html"

# Google Search Console impression data — update periodically from GSC exports.
# Combined impressions across all query variations for each brand/line.
SEARCH_DEMAND = {
    ("cohiba", "red dot"): 82,
    ("arturo fuente", "opus x"): 70,
    ("padron", "1964 anniversary"): 75,
    ("perdomo", "reserve 10th anniversary champagne"): 58,
    ("perdomo", "champagne noir"): 58,
    ("ashton", "vsg"): 33,
    ("arturo fuente", "hemingway"): 18,
    ("romeo y julieta", "1875"): 14,
    ("my father", "the judge"): 12,
    ("drew estate", "herrera esteli norteno"): 12,
    ("arturo fuente", "gran reserva"): 5,
    ("padron", "1926 serie"): 8,
    ("oliva", "serie v"): 5,
    ("drew estate", "liga privada no. 9"): 5,
    ("my father", "le bijou 1922"): 5,
    ("drew estate", "undercrown maduro"): 4,
    ("hoyo de monterrey", "excalibur"): 4,
    ("montecristo", "classic"): 3,
    ("drew estate", "acid"): 3,
    ("padron", "padron series"): 3,
    ("alec bradley", "prensado"): 2,
    ("alec bradley", "project 40 maduro"): 1,
    ("cao", "flathead"): 1,
    ("foundation", "olmec"): 1,
}

# Brands with demonstrated search presence get a baseline boost
BRAND_BOOST = {
    "cohiba": 10,
    "arturo fuente": 10,
    "padron": 8,
    "perdomo": 8,
    "ashton": 6,
    "my father": 5,
    "drew estate": 5,
    "romeo y julieta": 4,
    "oliva": 4,
    "hoyo de monterrey": 3,
    "montecristo": 3,
    "alec bradley": 2,
    "cao": 2,
    "foundation": 1,
}


PRICE_RE = re.compile(r'\$(\d{1,4}(?:,\d{3})*(?:\.\d{2}))')
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def fetch_price(url: str, timeout: int = 12) -> dict:
    """
    Generic price extraction from a product page URL.
    Tries JSON-LD, Open Graph meta, then regex fallback.
    Returns {price: float|None, title: str|None, in_stock: bool|None}.
    """
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        return {"price": None, "title": None, "in_stock": None, "error": str(e)[:80]}

    soup = BeautifulSoup(resp.content, "html.parser")
    price = None
    title = None
    in_stock = None

    # Try JSON-LD first (most reliable)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Product" or item.get("@type") == ["Product"]:
                    title = item.get("name")
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

    # Try Open Graph / meta tags
    if not price:
        og_price = soup.find("meta", property="product:price:amount")
        if og_price:
            try:
                price = float(og_price["content"].replace(",", ""))
            except (ValueError, KeyError):
                pass

    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "")
        elif soup.title:
            title = soup.title.string

    # Regex fallback — find prices in a reasonable box-price range
    if not price:
        matches = PRICE_RE.findall(soup.get_text())
        candidates = []
        for m in matches:
            try:
                val = float(m.replace(",", ""))
                if 25.0 <= val <= 3000.0:
                    candidates.append(val)
            except ValueError:
                pass
        if candidates:
            price = min(candidates)

    # Stock status fallback
    if in_stock is None:
        text = soup.get_text().lower()
        if "out of stock" in text or "sold out" in text:
            in_stock = False
        elif "add to cart" in text:
            in_stock = True

    return {"price": price, "title": title, "in_stock": in_stock, "error": None}


def get_search_score(brand: str, line: str) -> int:
    """Score a CID based on actual Google Search Console impression data."""
    b = brand.lower().strip()
    l = line.lower().strip()

    score = 0

    for (db, dl), impressions in SEARCH_DEMAND.items():
        if db in b and dl in l:
            score = max(score, impressions)
        elif db in b and any(word in l for word in dl.split()):
            score = max(score, impressions // 3)

    score += BRAND_BOOST.get(b, 0)

    return score


def load_staged_matches():
    """Load staged_matches.csv and return rows with status == 'staged'."""
    if not STAGED_CSV.exists():
        print(f"No staged matches found at {STAGED_CSV}")
        print("Run url_discoverer.py first to discover URLs.")
        sys.exit(1)

    rows = []
    with open(STAGED_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status", "").strip() == "staged":
                rows.append(row)

    if not rows:
        print("No staged matches awaiting review.")
        print("All matches have been processed. Run url_discoverer.py to discover more.")
        sys.exit(0)

    return rows


def group_by_cid(rows):
    """Group rows by CID and compute priority score for each group."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["cid"]].append(row)

    scored = []
    for cid, matches in groups.items():
        first = matches[0]
        brand = first.get("brand", "")
        line = first.get("line", "")
        score = get_search_score(brand, line)

        popular_vitolas = {"robusto", "toro", "churchill", "corona", "gordo"}
        vitola = first.get("vitola", "").lower()
        if vitola in popular_vitolas:
            score += 3

        high_count = sum(1 for m in matches if m.get("confidence", "").upper() == "HIGH")
        score += high_count * 2

        scored.append({
            "cid": cid,
            "brand": brand,
            "line": line,
            "wrapper": first.get("wrapper", ""),
            "vitola": first.get("vitola", ""),
            "size": first.get("size", ""),
            "box_qty": first.get("box_qty", ""),
            "score": score,
            "matches": matches,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def fetch_prices_for_batch(groups, batch_size):
    """Fetch prices for all URLs in the batch. Returns {url: price_data} dict."""
    batch = groups[:batch_size]
    all_urls = []
    for g in batch:
        for m in g["matches"]:
            all_urls.append(m["url"])

    print(f"Fetching prices for {len(all_urls)} URLs...")
    price_data = {}
    for i, url in enumerate(all_urls):
        print(f"  [{i+1}/{len(all_urls)}] {url[:70]}...", end="", flush=True)
        data = fetch_price(url)
        price_data[url] = data
        p = data.get("price")
        if p:
            print(f" ${p:.2f}")
        else:
            err = data.get("error", "no price found")
            print(f" ({err})")
        time.sleep(1.2)

    found = sum(1 for d in price_data.values() if d.get("price"))
    print(f"\nPrices found: {found}/{len(all_urls)}")
    return price_data


def generate_html(groups, batch_size, price_data=None):
    """Generate the HTML review page."""
    batch = groups[:batch_size]
    total_urls = sum(len(g["matches"]) for g in batch)
    if price_data is None:
        price_data = {}

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CID Review Batch - Cigar Price Scout</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; padding: 20px; }}
  .header {{ background: #2d2d2d; color: #fff; padding: 24px; border-radius: 12px; margin-bottom: 24px; }}
  .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
  .header .stats {{ color: #aaa; font-size: 14px; }}
  .header .stats span {{ color: #4CAF50; font-weight: 600; }}
  .card {{ background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }}
  .card-num {{ background: #2d2d2d; color: #fff; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 600; flex-shrink: 0; margin-right: 12px; }}
  .card-title {{ font-size: 20px; font-weight: 600; }}
  .card-score {{ background: #e8f5e9; color: #2e7d32; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; white-space: nowrap; }}
  .card-meta {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; font-size: 14px; color: #666; }}
  .card-meta strong {{ color: #333; }}
  .card-cid {{ font-family: monospace; font-size: 12px; color: #888; background: #f5f5f5; padding: 4px 8px; border-radius: 4px; margin-bottom: 16px; word-break: break-all; }}
  .url-row {{ display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 8px; margin-bottom: 6px; background: #fafafa; }}
  .url-row:hover {{ background: #f0f0f0; }}
  .confidence {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; flex-shrink: 0; width: 52px; text-align: center; }}
  .confidence.high {{ background: #c8e6c9; color: #2e7d32; }}
  .confidence.medium {{ background: #fff3e0; color: #e65100; }}
  .confidence.low {{ background: #ffcdd2; color: #c62828; }}
  .retailer {{ font-weight: 600; width: 140px; flex-shrink: 0; font-size: 14px; }}
  .price-found {{ font-weight: 700; color: #2e7d32; font-size: 15px; min-width: 80px; text-align: right; flex-shrink: 0; }}
  .price-missing {{ color: #bbb; font-size: 13px; min-width: 80px; text-align: right; flex-shrink: 0; }}
  .stock {{ font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; }}
  .stock.in {{ background: #e8f5e9; color: #2e7d32; }}
  .stock.oos {{ background: #ffebee; color: #c62828; }}
  .page-title {{ color: #999; font-size: 11px; margin-right: 8px; }}
  .url-link {{ color: #1565c0; text-decoration: none; font-size: 13px; word-break: break-all; flex: 1; }}
  .url-link:hover {{ text-decoration: underline; }}
  .reason {{ font-size: 12px; color: #888; font-style: italic; margin-top: 2px; }}
  .actions {{ display: flex; gap: 8px; margin-top: 14px; padding-top: 14px; border-top: 1px solid #eee; }}
  .btn {{ padding: 8px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; transition: all 0.15s; }}
  .btn-approve {{ background: #4CAF50; color: #fff; }}
  .btn-approve:hover {{ background: #388E3C; }}
  .btn-reject {{ background: #f44336; color: #fff; }}
  .btn-reject:hover {{ background: #c62828; }}
  .btn-skip {{ background: #e0e0e0; color: #666; }}
  .btn-skip:hover {{ background: #bdbdbd; }}
  .btn-approve.selected {{ box-shadow: 0 0 0 3px rgba(76,175,80,0.4); }}
  .btn-reject.selected {{ box-shadow: 0 0 0 3px rgba(244,67,54,0.4); }}
  .btn-skip.selected {{ box-shadow: 0 0 0 3px rgba(158,158,158,0.4); }}
  .url-action {{ display: flex; gap: 4px; flex-shrink: 0; }}
  .url-btn {{ padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; border: 1px solid #ddd; background: #fff; }}
  .url-btn.approve {{ color: #2e7d32; border-color: #a5d6a7; }}
  .url-btn.approve:hover, .url-btn.approve.selected {{ background: #c8e6c9; }}
  .url-btn.reject {{ color: #c62828; border-color: #ef9a9a; }}
  .url-btn.reject:hover, .url-btn.reject.selected {{ background: #ffcdd2; }}
  .submit-bar {{ position: sticky; bottom: 0; background: #fff; padding: 16px 24px; border-radius: 12px 12px 0 0; box-shadow: 0 -2px 8px rgba(0,0,0,0.1); display: flex; justify-content: space-between; align-items: center; margin-top: 24px; }}
  .submit-btn {{ background: #1565c0; color: #fff; padding: 12px 32px; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; border: none; }}
  .submit-btn:hover {{ background: #0d47a1; }}
  .submit-btn:disabled {{ background: #bbb; cursor: not-allowed; }}
  .progress {{ font-size: 14px; color: #666; }}
  .toast {{ position: fixed; top: 20px; right: 20px; background: #4CAF50; color: #fff; padding: 16px 24px; border-radius: 8px; font-weight: 600; display: none; z-index: 100; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
</style>
</head>
<body>

<div class="header">
  <h1>CID Review Batch</h1>
  <div class="stats">
    <span>{len(batch)}</span> CIDs &middot; <span>{total_urls}</span> URLs to verify &middot;
    Prioritized by Google Search Console traffic &middot;
    Generated {datetime.now().strftime('%B %d, %Y %I:%M %p')}
  </div>
</div>

<div id="toast" class="toast"></div>

<div id="cards">
"""

    for i, group in enumerate(batch):
        matches = group["matches"]
        matches.sort(key=lambda m: 0 if m.get("confidence", "").upper() == "HIGH" else 1 if m.get("confidence", "").upper() == "MEDIUM" else 2)

        html += f"""
<div class="card" id="card-{i}" data-cid="{group['cid']}">
  <div class="card-header">
    <div style="display:flex;align-items:center;gap:12px;flex:1">
      <div class="card-num">{i + 1}</div>
      <div>
        <div class="card-title">{group['brand']} - {group['line']}</div>
        <div class="card-meta">
          <span><strong>Wrapper:</strong> {group['wrapper'] or 'N/A'}</span>
          <span><strong>Vitola:</strong> {group['vitola'] or 'N/A'}</span>
          <span><strong>Size:</strong> {group['size'] or 'N/A'}</span>
          <span><strong>Box:</strong> {group['box_qty'] or 'N/A'}</span>
        </div>
      </div>
    </div>
    <div class="card-score">{group['score']} pts</div>
  </div>
  <div class="card-cid">{group['cid']}</div>
"""

        for j, match in enumerate(matches):
            conf = match.get("confidence", "MEDIUM").upper()
            conf_class = conf.lower()
            reason = match.get("reason", "").replace('"', "&quot;")

            url_price = price_data.get(match["url"], {})
            p = url_price.get("price")
            price_display = f"${p:,.2f}" if p else "—"
            price_class = "price-found" if p else "price-missing"
            stock = url_price.get("in_stock")
            stock_display = ""
            if stock is True:
                stock_display = '<span class="stock in">In Stock</span>'
            elif stock is False:
                stock_display = '<span class="stock oos">OOS</span>'
            page_title = url_price.get("title", "") or ""
            if len(page_title) > 80:
                page_title = page_title[:77] + "..."
            title_display = f'<span class="page-title">{page_title}</span>' if page_title else ""

            html += f"""
  <div class="url-row" id="url-{i}-{j}" data-retailer="{match['retailer_key']}" data-url="{match['url']}">
    <span class="confidence {conf_class}">{conf}</span>
    <span class="retailer">{match['retailer_key']}</span>
    <span class="{price_class}">{price_display}</span>
    {stock_display}
    <a href="{match['url']}" target="_blank" rel="noopener" class="url-link">{match['url']}</a>
    <div class="url-action">
      <button class="url-btn approve" onclick="setUrlAction({i},{j},'approve')" title="Approve">&#10003;</button>
      <button class="url-btn reject" onclick="setUrlAction({i},{j},'reject')" title="Reject">&#10007;</button>
    </div>
  </div>
  <div class="reason" style="margin-left:220px;margin-bottom:8px">{title_display} {reason}</div>
"""

        html += f"""
  <div class="actions">
    <button class="btn btn-approve" onclick="setCidAction({i},'approve')">Approve All</button>
    <button class="btn btn-reject" onclick="setCidAction({i},'reject')">Reject All</button>
    <button class="btn btn-skip" onclick="setCidAction({i},'skip')">Skip</button>
  </div>
</div>
"""

    decisions_path = DECISIONS_CSV.as_posix()

    html += f"""
</div>

<div class="submit-bar">
  <div class="progress" id="progress">0 of {len(batch)} CIDs reviewed</div>
  <button class="submit-btn" id="submitBtn" onclick="submitDecisions()">Submit Batch</button>
</div>

<script>
const decisions = {{}};
const urlDecisions = {{}};
const totalCids = {len(batch)};

function setUrlAction(cardIdx, urlIdx, action) {{
  const key = cardIdx + '-' + urlIdx;
  urlDecisions[key] = action;
  document.querySelectorAll('#url-' + cardIdx + '-' + urlIdx + ' .url-btn').forEach(b => b.classList.remove('selected'));
  const btn = document.querySelector('#url-' + cardIdx + '-' + urlIdx + ' .url-btn.' + action);
  if (btn) btn.classList.add('selected');
  updateProgress();
}}

function setCidAction(cardIdx, action) {{
  decisions[cardIdx] = action;
  const card = document.getElementById('card-' + cardIdx);
  card.querySelectorAll('.btn').forEach(b => b.classList.remove('selected'));
  card.querySelector('.btn-' + action).classList.add('selected');

  if (action === 'approve' || action === 'reject') {{
    const urlRows = card.querySelectorAll('.url-row');
    urlRows.forEach((row, j) => {{
      const key = cardIdx + '-' + j;
      if (!(key in urlDecisions)) {{
        urlDecisions[key] = action;
        row.querySelectorAll('.url-btn').forEach(b => b.classList.remove('selected'));
        const btn = row.querySelector('.url-btn.' + action);
        if (btn) btn.classList.add('selected');
      }}
    }});
  }}
  updateProgress();
}}

function updateProgress() {{
  const reviewed = Object.keys(decisions).length;
  document.getElementById('progress').textContent = reviewed + ' of ' + totalCids + ' CIDs reviewed';
}}

function submitDecisions() {{
  const rows = [];
"""

    for i, group in enumerate(batch):
        for j, match in enumerate(group["matches"]):
            html += f"""
  {{
    const key = '{i}-{j}';
    const action = urlDecisions[key] || decisions[{i}] || 'skip';
    rows.push({{
      cid: '{match["cid"]}',
      retailer_key: '{match["retailer_key"]}',
      url: '{match["url"]}',
      action: action
    }});
  }}
"""

    html += """
  let csvContent = 'cid,retailer_key,url,action\\n';
  rows.forEach(r => {
    csvContent += '"' + r.cid + '",' + r.retailer_key + ',"' + r.url + '",' + r.action + '\\n';
  });

  const blob = new Blob([csvContent], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'review_decisions.csv';
  a.click();

  const toast = document.getElementById('toast');
  toast.textContent = 'Decisions downloaded as review_decisions.csv — run: python tools/ai/review_batch.py --process-decisions';
  toast.style.display = 'block';
  setTimeout(() => { toast.style.display = 'none'; }, 8000);
}
</script>

</body>
</html>
"""

    with open(REVIEW_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Review page generated: {REVIEW_HTML}")
    print(f"  {len(batch)} CIDs, {total_urls} URLs")
    print(f"  Opening in browser...")

    webbrowser.open(REVIEW_HTML.as_uri())


def process_decisions():
    """Read review_decisions.csv and update staged_matches.csv."""
    search_paths = [
        DECISIONS_CSV,
        PROJECT_ROOT / "review_decisions.csv",
        Path.home() / "Downloads" / "review_decisions.csv",
    ]

    decisions_path = None
    for p in search_paths:
        if p.exists():
            decisions_path = p
            break

    if not decisions_path:
        print("No review_decisions.csv found.")
        print("Searched:")
        for p in search_paths:
            print(f"  {p}")
        print("\nMove the downloaded file to one of these locations and retry.")
        sys.exit(1)

    print(f"Reading decisions from: {decisions_path}")

    decision_map = {}
    with open(decisions_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["cid"].strip(), row["retailer_key"].strip(), row["url"].strip())
            decision_map[key] = row["action"].strip()

    if not STAGED_CSV.exists():
        print("staged_matches.csv not found.")
        sys.exit(1)

    rows = []
    with open(STAGED_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    approved = 0
    rejected = 0
    skipped = 0

    for row in rows:
        key = (row["cid"].strip(), row["retailer_key"].strip(), row["url"].strip())
        action = decision_map.get(key)
        if action == "approve":
            row["status"] = "approved"
            approved += 1
        elif action == "reject":
            row["status"] = "rejected"
            rejected += 1
        elif action == "skip":
            skipped += 1

    with open(STAGED_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nResults:")
    print(f"  Approved: {approved}")
    print(f"  Rejected: {rejected}")
    print(f"  Skipped:  {skipped}")

    if approved > 0:
        print(f"\nNext step: publish approved matches to retailer CSVs:")
        print(f"  python tools/ai/url_discoverer.py --publish-approved")

    if decisions_path != DECISIONS_CSV:
        print(f"\nNote: Processed file at {decisions_path}")


def show_status():
    """Show summary of staged_matches.csv status."""
    if not STAGED_CSV.exists():
        print("No staged_matches.csv found.")
        return

    counts = defaultdict(int)
    cids = defaultdict(set)

    with open(STAGED_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("status", "unknown").strip()
            counts[status] += 1
            cids[status].add(row["cid"])

    print("Staged Matches Status:")
    print(f"  {'Status':<12} {'URLs':>6}  {'CIDs':>6}")
    print(f"  {'-'*30}")
    for status in ["staged", "approved", "rejected", "published"]:
        if status in counts:
            print(f"  {status:<12} {counts[status]:>6}  {len(cids[status]):>6}")

    total = sum(counts.values())
    print(f"  {'-'*30}")
    print(f"  {'Total':<12} {total:>6}")


def main():
    parser = argparse.ArgumentParser(description="Generate HTML review page for URL matches")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of CIDs to review (default: 10)")
    parser.add_argument("--skip-prices", action="store_true", help="Skip fetching prices from URLs (faster)")
    parser.add_argument("--process-decisions", action="store_true", help="Process review_decisions.csv")
    parser.add_argument("--status", action="store_true", help="Show staged matches status")
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.process_decisions:
        process_decisions()
    else:
        rows = load_staged_matches()
        groups = group_by_cid(rows)
        print(f"Found {len(groups)} CIDs with staged matches ({len(rows)} URLs total)")

        prices = {}
        if not args.skip_prices:
            prices = fetch_prices_for_batch(groups, args.batch_size)

        generate_html(groups, args.batch_size, price_data=prices)


if __name__ == "__main__":
    main()
