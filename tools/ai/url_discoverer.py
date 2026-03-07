#!/usr/bin/env python3
"""
URL Discovery Agent - Finds product URLs for unmonitored CIDs across retailers.

Uses a two-pass approach:
  1. Programmatic matching: decompose CID and URL slugs, score keyword overlap
  2. Claude verification: confirm ambiguous matches and resolve edge cases

Outputs staged results for human review before publishing to production CSVs.

Usage:
    # Discover URLs for top 50 unmonitored CIDs across all retailers
    python tools/ai/url_discoverer.py --top-cids 50

    # Discover for a specific retailer
    python tools/ai/url_discoverer.py --retailer foxcigar --top-cids 20

    # Review and approve staged matches
    python tools/ai/url_discoverer.py --approve-batch
    python tools/ai/url_discoverer.py --publish-approved

    # Reject flagged entries (after adding feedback in pending_review.csv)
    python tools/ai/url_discoverer.py --reject-flagged

Environment:
    ANTHROPIC_API_KEY - Required. Your Anthropic API key from console.anthropic.com
"""

import os
import sys
import csv
import json
import re
import time
import logging
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from urllib.parse import urlparse

import requests
import pandas as pd

try:
    import anthropic
except ImportError:
    print("[ERROR] anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DATA = PROJECT_ROOT / "static" / "data"
MASTER_CSV = PROJECT_ROOT / "data" / "master_cigars.csv"
MASTER_DB = PROJECT_ROOT / "data" / "master_cigars.db"
AI_DIR = Path(__file__).resolve().parent

STAGED_FILE = AI_DIR / "staged_matches.csv"
PENDING_FILE = AI_DIR / "pending_review.csv"
FEEDBACK_FILE = AI_DIR / "feedback_history.json"
REPORT_FILE = AI_DIR / "discovery_report.txt"

# ── Wrapper code mapping (mirrors cigar_db.py) ────────────────────────

WRAPPER_CODES = {
    "MAD": ["maduro", "mad"],
    "NAT": ["natural", "nat", "connecticut shade", "connecticut"],
    "CAM": ["cameroon", "cam"],
    "ECU": ["ecuadorian", "ecuador", "ecu", "ecuadorian habano", "ecuadorian connecticut"],
    "HAB": ["habano", "hab", "cuban", "corojo"],
    "SUM": ["sumatra", "sumatran", "sum"],
    "BRD": ["broadleaf", "brd", "connecticut broadleaf", "san andres"],
    "OSC": ["oscuro", "osc"],
    "NIC": ["nicaraguan", "nic", "nicaragua"],
    "MEX": ["mexican", "mex", "mexico", "san andres mexican"],
    "CLA": ["claro", "cla"],
}

WRAPPER_CODE_TO_NAMES = {}
for code, names in WRAPPER_CODES.items():
    WRAPPER_CODE_TO_NAMES[code] = names


def parse_cid(cid: str) -> Dict:
    """Decompose a CID into its components."""
    parts = cid.split("|")
    if len(parts) < 8:
        return {}
    return {
        "brand": parts[0],
        "parent_brand": parts[1],
        "line": parts[2],
        "vitola": parts[3],
        "vitola2": parts[4],
        "size": parts[5],
        "wrapper_code": parts[6],
        "box_qty_str": parts[7],
        "raw": cid,
    }


def cid_to_search_terms(cid_parts: Dict) -> List[str]:
    """Generate search-friendly terms from CID components."""
    terms = []

    brand = cid_parts.get("brand", "").replace("_", " ")
    line = cid_parts.get("line", "").replace("_", " ")
    vitola = cid_parts.get("vitola", "").replace("_", " ")

    # Add spaced-out versions of concatenated words (e.g., "1964ANNIVERSARY" -> "1964 anniversary")
    line_spaced = re.sub(r"(\d+)([A-Z])", r"\1 \2", line)
    line_spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", line_spaced)

    terms.extend([brand.lower(), line_spaced.lower(), vitola.lower()])

    wrapper_code = cid_parts.get("wrapper_code", "")
    if wrapper_code in WRAPPER_CODE_TO_NAMES:
        terms.extend(WRAPPER_CODE_TO_NAMES[wrapper_code])

    return [t for t in terms if t]


def slug_from_url(url: str) -> str:
    """Extract the product slug from a URL."""
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] if "/" in path else path
    return slug.lower().replace("-", " ").replace("_", " ")


# ── Programmatic matching ──────────────────────────────────────────────

def programmatic_score(cid_parts: Dict, url: str) -> Tuple[float, Dict]:
    """
    Score how well a URL matches a CID using keyword overlap.
    Returns (score 0-1, details dict).
    """
    slug = slug_from_url(url)
    search_terms = cid_to_search_terms(cid_parts)

    brand = cid_parts["brand"].lower().replace("_", " ")
    line_raw = cid_parts["line"].lower().replace("_", " ")
    line_spaced = re.sub(r"(\d+)([a-z])", r"\1 \2", line_raw, flags=re.I)
    line_spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", line_spaced).lower()
    vitola = cid_parts["vitola"].lower().replace("_", " ")
    wrapper_code = cid_parts["wrapper_code"]
    box_qty_str = cid_parts["box_qty_str"]

    details = {
        "brand_match": False,
        "line_match": False,
        "vitola_match": False,
        "wrapper_match": False,
        "box_qty_match": False,
    }

    score = 0.0
    weights = {
        "brand": 0.30,
        "line": 0.30,
        "vitola": 0.20,
        "wrapper": 0.10,
        "box_qty": 0.10,
    }

    # Brand match
    brand_words = brand.split()
    if all(w in slug for w in brand_words):
        score += weights["brand"]
        details["brand_match"] = True
    elif any(w in slug for w in brand_words if len(w) > 3):
        score += weights["brand"] * 0.5
        details["brand_match"] = True

    # Line match
    line_words = [w for w in line_spaced.split() if len(w) > 2]
    if line_words:
        matched = sum(1 for w in line_words if w in slug)
        ratio = matched / len(line_words)
        if ratio >= 0.7:
            score += weights["line"]
            details["line_match"] = True
        elif ratio >= 0.4:
            score += weights["line"] * 0.5
            details["line_match"] = True

    # Vitola match
    vitola_words = [w for w in vitola.split() if len(w) > 2]
    if vitola_words:
        if all(w in slug for w in vitola_words):
            score += weights["vitola"]
            details["vitola_match"] = True
        elif any(w in slug for w in vitola_words):
            score += weights["vitola"] * 0.5
            details["vitola_match"] = True

    # Wrapper match
    wrapper_names = WRAPPER_CODE_TO_NAMES.get(wrapper_code, [])
    if any(name in slug for name in wrapper_names):
        score += weights["wrapper"]
        details["wrapper_match"] = True

    # Box quantity match
    box_qty_num = re.search(r"\d+", box_qty_str)
    if box_qty_num:
        qty = box_qty_num.group()
        if f"box {qty}" in slug or f"box of {qty}" in slug or f"{qty} count" in slug:
            score += weights["box_qty"]
            details["box_qty_match"] = True

    return score, details


# ── Sitemap fetching ───────────────────────────────────────────────────

SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

def fetch_sitemap_urls(base_url: str) -> List[str]:
    """
    Fetch product URLs from a retailer's sitemap.
    Tries common sitemap locations and follows sitemap index files.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    session = requests.Session()
    session.headers.update(headers)

    sitemap_candidates = [
        f"{base_url}/sitemap.xml",
        f"{base_url}/sitemap_index.xml",
        f"{base_url}/sitemap_products_1.xml",  # Shopify
    ]

    # Try robots.txt for sitemap location
    try:
        robots = session.get(f"{base_url}/robots.txt", timeout=10)
        if robots.ok:
            for line in robots.text.splitlines():
                if line.strip().lower().startswith("sitemap:"):
                    sm_url = line.split(":", 1)[1].strip()
                    if sm_url not in sitemap_candidates:
                        sitemap_candidates.insert(0, sm_url)
    except Exception:
        pass

    all_urls = []
    visited = set()

    def _parse_sitemap(url: str, depth: int = 0):
        if depth > 3 or url in visited:
            return
        visited.add(url)

        try:
            resp = session.get(url, timeout=15)
            if not resp.ok:
                return
        except Exception as e:
            logger.debug(f"Failed to fetch sitemap {url}: {e}")
            return

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            return

        tag = root.tag.lower()

        # Sitemap index → recurse into child sitemaps
        if "sitemapindex" in tag:
            for sm in root.findall("sm:sitemap/sm:loc", SITEMAP_NAMESPACE):
                child_url = sm.text.strip() if sm.text else ""
                if child_url and "product" in child_url.lower():
                    _parse_sitemap(child_url, depth + 1)
            # If no product-specific sitemaps, try all of them
            if not all_urls:
                for sm in root.findall("sm:sitemap/sm:loc", SITEMAP_NAMESPACE):
                    child_url = sm.text.strip() if sm.text else ""
                    if child_url:
                        _parse_sitemap(child_url, depth + 1)
        # URL set → collect URLs
        elif "urlset" in tag:
            for loc in root.findall("sm:url/sm:loc", SITEMAP_NAMESPACE):
                page_url = loc.text.strip() if loc.text else ""
                if page_url:
                    all_urls.append(page_url)

    for candidate in sitemap_candidates:
        _parse_sitemap(candidate)
        if all_urls:
            break

    return all_urls


def filter_product_urls(urls: List[str]) -> List[str]:
    """Keep only URLs that look like product pages."""
    product_patterns = [
        r"/products?/",
        r"/shop/",
        r"/collections/.+/products/",
        r"/cigars?/",
        r"-cigar",
        r"-box-",
        r"-maduro",
        r"-natural",
        r"-robusto",
        r"-toro",
    ]
    exclude_patterns = [
        r"/cart",
        r"/account",
        r"/login",
        r"/blog",
        r"/pages?/",
        r"/collections/?$",
        r"/categories/",
        r"\.(jpg|png|gif|css|js|pdf)",
        r"/search",
        r"/checkout",
        r"/wishlist",
    ]

    filtered = []
    for url in urls:
        path = urlparse(url).path.lower()
        if any(re.search(p, path) for p in exclude_patterns):
            continue
        if any(re.search(p, path) for p in product_patterns):
            filtered.append(url)

    return filtered


# ── Retailer discovery ─────────────────────────────────────────────────

def get_active_retailers() -> List[Dict]:
    """
    Discover active retailers from static/data/*.csv.
    Returns list of {key, csv_path, base_url, product_count}.
    """
    retailers = []
    for csv_file in sorted(STATIC_DATA.glob("*.csv")):
        name = csv_file.stem
        if any(x in name for x in ["DORMANT", "BROKEN", "backup"]):
            continue

        try:
            df = pd.read_csv(csv_file)
        except Exception:
            continue

        if "url" not in df.columns or "cigar_id" not in df.columns:
            continue

        urls = df["url"].dropna().tolist()
        if not urls:
            continue

        # Extract base URL from first valid URL
        sample_url = next((u for u in urls if u.startswith("http")), None)
        if not sample_url:
            continue

        parsed = urlparse(sample_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        retailers.append({
            "key": name,
            "csv_path": str(csv_file),
            "base_url": base_url,
            "product_count": len(df),
            "existing_cids": set(df["cigar_id"].dropna().unique()),
        })

    return retailers


def get_unmonitored_cids(top_n: int = 50) -> pd.DataFrame:
    """
    Get unmonitored CIDs prioritized by search demand.
    Mirrors find_unmonitored_cids.py logic.
    """
    if not MASTER_CSV.exists():
        logger.error(f"Master CSV not found: {MASTER_CSV}")
        return pd.DataFrame()

    master_df = pd.read_csv(MASTER_CSV)
    master_cids = set(master_df["cigar_id"].dropna().unique())

    monitored_cids = set()
    for csv_file in STATIC_DATA.glob("*.csv"):
        if any(x in csv_file.stem for x in ["DORMANT", "BROKEN", "backup"]):
            continue
        try:
            df = pd.read_csv(csv_file)
            if "cigar_id" in df.columns:
                monitored_cids.update(df["cigar_id"].dropna().unique())
        except Exception:
            continue

    unmonitored = master_cids - monitored_cids
    unmonitored_df = master_df[master_df["cigar_id"].isin(unmonitored)].copy()

    if unmonitored_df.empty:
        return unmonitored_df

    unmonitored_df = unmonitored_df.sort_values("Brand")
    return unmonitored_df.head(top_n)


# ── Claude API matching ───────────────────────────────────────────────

MATCH_PROMPT = """You are matching cigar products to URLs. Given a cigar CID (canonical ID) and a list of candidate product URLs, determine which URL (if any) sells the exact same cigar.

CID format: BRAND|PARENT_BRAND|LINE|VITOLA|VITOLA|SIZE|WRAPPER_CODE|BOX_QTY

Wrapper codes:
- MAD = Maduro
- NAT = Natural / Connecticut Shade
- CAM = Cameroon
- ECU = Ecuadorian (Habano or Connecticut)
- HAB = Habano / Corojo
- SUM = Sumatra
- BRD = Broadleaf / San Andres
- OSC = Oscuro
- NIC = Nicaraguan
- MEX = Mexican / San Andres
- CLA = Claro

CRITICAL RULES:
1. The brand AND line must match. "Padron 1964 Anniversary" is different from "Padron 1926 Anniversary".
2. The vitola (shape/name) must match. "Robusto" is different from "Toro".
3. The wrapper must match. Maduro is different from Natural.
4. The URL should be for a BOX purchase, not singles or 5-packs.
5. If no URL is a confident match, say NONE.

For each CID, respond with EXACTLY this JSON format:
{
  "matches": [
    {
      "cid": "THE_CID",
      "url": "matched_url_or_NONE",
      "confidence": "HIGH|MEDIUM|LOW|NONE",
      "reason": "brief explanation"
    }
  ]
}

Confidence levels:
- HIGH: All components clearly match (brand, line, vitola, wrapper, box)
- MEDIUM: Most components match but one is ambiguous (e.g., vitola name differs slightly)
- LOW: Brand and line match but other components are uncertain
- NONE: No good match found
"""


def claude_batch_match(
    client: anthropic.Anthropic,
    cid_batch: List[Dict],
    candidate_urls: List[str],
    retailer_name: str,
) -> List[Dict]:
    """
    Use Claude to match a batch of CIDs against candidate URLs.
    Returns list of {cid, url, confidence, reason}.
    """
    if not candidate_urls:
        return [
            {"cid": c["raw"], "url": None, "confidence": "NONE", "reason": "No product URLs found for retailer"}
            for c in cid_batch
        ]

    # Build the prompt with CIDs and URLs
    cid_list = "\n".join(f"  - {c['raw']}" for c in cid_batch)

    # Limit URL list to keep prompt manageable — send the top candidates
    # Pre-filter: only include URLs that share at least one keyword with any CID
    all_keywords = set()
    for c in cid_batch:
        all_keywords.update(cid_to_search_terms(c))

    relevant_urls = []
    for url in candidate_urls:
        slug = slug_from_url(url)
        if any(kw in slug for kw in all_keywords if len(kw) > 3):
            relevant_urls.append(url)

    # Cap at 200 URLs to keep costs reasonable
    relevant_urls = relevant_urls[:200]

    if not relevant_urls:
        return [
            {"cid": c["raw"], "url": None, "confidence": "NONE", "reason": "No relevant product URLs on this retailer"}
            for c in cid_batch
        ]

    url_list = "\n".join(f"  - {u}" for u in relevant_urls)

    user_msg = f"""Retailer: {retailer_name}

CIDs to match:
{cid_list}

Candidate product URLs:
{url_list}

Find the best matching URL for each CID. Return JSON only."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=MATCH_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            logger.warning(f"No JSON found in Claude response for {retailer_name}")
            return []

        result = json.loads(json_match.group())
        matches = result.get("matches", [])

        # Normalize
        for m in matches:
            if m.get("url") == "NONE" or not m.get("url"):
                m["url"] = None
                m["confidence"] = "NONE"

        return matches

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response for {retailer_name}: {e}")
        return []
    except anthropic.APIError as e:
        logger.error(f"Claude API error for {retailer_name}: {e}")
        return []


# ── Staged output management ──────────────────────────────────────────

STAGED_COLUMNS = [
    "cid", "retailer_key", "url", "confidence", "reason",
    "brand", "line", "vitola", "wrapper", "size", "box_qty",
    "status", "feedback", "discovered_at",
]


def load_feedback_history() -> Dict:
    """Load accumulated feedback for LLM learning."""
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r") as f:
            return json.load(f)
    return {"rejections": [], "corrections": []}


def save_feedback_history(history: Dict):
    with open(FEEDBACK_FILE, "w") as f:
        json.dump(history, f, indent=2)


def write_staged_output(matches: List[Dict], master_df: pd.DataFrame):
    """Write all matches to staged_matches.csv and pending_review.csv."""
    now = datetime.now().isoformat()

    staged_rows = []
    pending_rows = []

    for m in matches:
        if not m.get("url"):
            continue

        cid = m["cid"]
        cid_parts = parse_cid(cid)

        # Look up metadata from master
        master_row = master_df[master_df["cigar_id"] == cid]
        brand = master_row.iloc[0]["Brand"] if len(master_row) > 0 else cid_parts.get("brand", "")
        line = master_row.iloc[0]["Line"] if len(master_row) > 0 else cid_parts.get("line", "")
        vitola = master_row.iloc[0]["Vitola"] if len(master_row) > 0 else cid_parts.get("vitola", "")
        wrapper = master_row.iloc[0]["Wrapper"] if len(master_row) > 0 else ""
        size = ""
        if len(master_row) > 0:
            length = master_row.iloc[0].get("Length", "")
            rg = master_row.iloc[0].get("Ring Gauge", "")
            if pd.notna(length) and pd.notna(rg):
                size = f"{length}x{rg}"
        box_qty = ""
        if len(master_row) > 0:
            bq = master_row.iloc[0].get("Box Quantity", "")
            if pd.notna(bq):
                box_qty = str(int(bq))

        row = {
            "cid": cid,
            "retailer_key": m.get("retailer_key", ""),
            "url": m["url"],
            "confidence": m.get("confidence", "UNKNOWN"),
            "reason": m.get("reason", ""),
            "brand": brand,
            "line": line,
            "vitola": vitola,
            "wrapper": wrapper,
            "size": size,
            "box_qty": box_qty,
            "status": "staged",
            "feedback": "",
            "discovered_at": now,
        }

        staged_rows.append(row)
        if m.get("confidence") == "MEDIUM":
            pending_rows.append(row)

    # Append to existing staged file (don't overwrite previous runs)
    staged_exists = STAGED_FILE.exists()
    with open(STAGED_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=STAGED_COLUMNS)
        if not staged_exists:
            writer.writeheader()
        writer.writerows(staged_rows)

    # Overwrite pending review (only current batch)
    with open(PENDING_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=STAGED_COLUMNS)
        writer.writeheader()
        writer.writerows(pending_rows)

    return len(staged_rows), len(pending_rows)


def write_report(
    all_matches: List[Dict],
    retailers_scanned: int,
    cids_searched: int,
    elapsed: float,
):
    """Write a human-readable discovery report."""
    high = [m for m in all_matches if m.get("confidence") == "HIGH"]
    medium = [m for m in all_matches if m.get("confidence") == "MEDIUM"]
    low = [m for m in all_matches if m.get("confidence") == "LOW"]
    none = [m for m in all_matches if m.get("confidence") == "NONE"]

    lines = [
        f"=== URL Discovery Report - {datetime.now().strftime('%B %d, %Y %I:%M %p')} ===",
        "",
        f"Retailers scanned: {retailers_scanned}",
        f"CIDs searched: {cids_searched}",
        f"Time elapsed: {elapsed:.0f}s",
        "",
        f"STAGED FOR BATCH APPROVAL (high confidence): {len(high)} matches",
    ]

    for m in high[:5]:
        lines.append(f"  {m['cid'][:50]}... -> {m.get('url', 'N/A')}")
    if len(high) > 5:
        lines.append(f"  ... and {len(high) - 5} more")

    lines.extend([
        "",
        f"NEEDS INDIVIDUAL REVIEW (medium confidence): {len(medium)} matches",
        f"  -> Review file: {PENDING_FILE}",
    ])

    for m in medium[:5]:
        lines.append(f"  {m['cid'][:50]}...")
        lines.append(f"    Reason: {m.get('reason', 'N/A')}")
    if len(medium) > 5:
        lines.append(f"  ... and {len(medium) - 5} more")

    lines.extend([
        "",
        f"NO MATCH FOUND: {len(none)} CIDs had no matches",
        f"LOW CONFIDENCE (skipped): {len(low)} matches discarded",
        "",
        "Next steps:",
        f"  1. Spot-check ~5% of high-confidence matches in {STAGED_FILE}",
        "  2. If spot-checks pass: python tools/ai/url_discoverer.py --approve-batch",
        f"  3. Review medium matches in {PENDING_FILE}",
        "  4. Publish approved: python tools/ai/url_discoverer.py --publish-approved",
    ])

    report = "\n".join(lines)

    with open(REPORT_FILE, "w") as f:
        f.write(report)

    print("\n" + report)


# ── Approval workflow ──────────────────────────────────────────────────

def approve_batch():
    """Mark all high-confidence staged matches as approved."""
    if not STAGED_FILE.exists():
        print("[ERROR] No staged matches found. Run discovery first.")
        return

    df = pd.read_csv(STAGED_FILE)
    high_staged = (df["confidence"] == "HIGH") & (df["status"] == "staged")
    count = high_staged.sum()

    df.loc[high_staged, "status"] = "approved"
    df.to_csv(STAGED_FILE, index=False)
    print(f"[OK] Approved {count} high-confidence matches.")
    print(f"     Run --publish-approved to push them to retailer CSVs.")


def reject_flagged():
    """
    Process rejections from pending_review.csv.
    Rows with non-empty 'feedback' column and status='staged' are rejected.
    Feedback is saved to history for future LLM learning.
    """
    if not PENDING_FILE.exists():
        print("[ERROR] No pending review file found.")
        return

    pending_df = pd.read_csv(PENDING_FILE)
    has_feedback = pending_df["feedback"].notna() & (pending_df["feedback"] != "")
    rejected = pending_df[has_feedback]

    if rejected.empty:
        print("[INFO] No feedback found in pending_review.csv. Add feedback to reject entries.")
        return

    # Save to feedback history
    history = load_feedback_history()
    for _, row in rejected.iterrows():
        history["rejections"].append({
            "cid": row["cid"],
            "url": row["url"],
            "retailer_key": row["retailer_key"],
            "feedback": row["feedback"],
            "timestamp": datetime.now().isoformat(),
        })
    save_feedback_history(history)

    # Update staged file
    if STAGED_FILE.exists():
        staged_df = pd.read_csv(STAGED_FILE)
        for _, row in rejected.iterrows():
            mask = (staged_df["cid"] == row["cid"]) & (staged_df["url"] == row["url"])
            staged_df.loc[mask, "status"] = "rejected"
            staged_df.loc[mask, "feedback"] = row["feedback"]
        staged_df.to_csv(STAGED_FILE, index=False)

    # Mark reviewed in pending
    pending_df.loc[has_feedback, "status"] = "rejected"

    # Approve remaining (no feedback = approved)
    no_feedback = ~has_feedback & (pending_df["status"] == "staged")
    pending_df.loc[no_feedback, "status"] = "approved"

    # Update staged file for approved pending items too
    if STAGED_FILE.exists():
        staged_df = pd.read_csv(STAGED_FILE)
        for _, row in pending_df[no_feedback].iterrows():
            mask = (staged_df["cid"] == row["cid"]) & (staged_df["url"] == row["url"])
            staged_df.loc[mask, "status"] = "approved"
        staged_df.to_csv(STAGED_FILE, index=False)

    pending_df.to_csv(PENDING_FILE, index=False)

    print(f"[OK] Rejected {len(rejected)} entries with feedback.")
    print(f"     Approved {no_feedback.sum()} entries without feedback.")
    print(f"     Feedback saved to {FEEDBACK_FILE}")


def publish_approved():
    """Push approved matches from staged_matches.csv into production retailer CSVs."""
    if not STAGED_FILE.exists():
        print("[ERROR] No staged matches found.")
        return

    staged_df = pd.read_csv(STAGED_FILE)
    approved = staged_df[staged_df["status"] == "approved"]

    if approved.empty:
        print("[INFO] No approved matches to publish.")
        return

    published = 0
    skipped = 0

    for retailer_key, group in approved.groupby("retailer_key"):
        csv_path = STATIC_DATA / f"{retailer_key}.csv"
        if not csv_path.exists():
            logger.warning(f"CSV not found for retailer: {retailer_key}")
            skipped += len(group)
            continue

        retailer_df = pd.read_csv(csv_path)
        existing_cids = set(retailer_df["cigar_id"].dropna().unique())

        new_rows = []
        for _, match in group.iterrows():
            if match["cid"] in existing_cids:
                skipped += 1
                continue

            new_row = {
                "cigar_id": match["cid"],
                "title": "",
                "url": match["url"],
                "brand": match.get("brand", ""),
                "line": match.get("line", ""),
                "wrapper": match.get("wrapper", ""),
                "vitola": match.get("vitola", ""),
                "size": match.get("size", ""),
                "box_qty": match.get("box_qty", ""),
                "price": "",
                "in_stock": "",
            }

            # Fill any extra columns from the existing CSV
            for col in retailer_df.columns:
                if col not in new_row:
                    new_row[col] = ""

            new_rows.append(new_row)

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            retailer_df = pd.concat([retailer_df, new_df], ignore_index=True)
            retailer_df.to_csv(csv_path, index=False)
            published += len(new_rows)
            print(f"  [OK] Added {len(new_rows)} CIDs to {retailer_key}.csv")

    # Mark published in staged file
    staged_df.loc[staged_df["status"] == "approved", "status"] = "published"
    staged_df.to_csv(STAGED_FILE, index=False)

    print(f"\n[DONE] Published {published} new CID-URL pairs. Skipped {skipped} (already exist or CSV missing).")
    print("       Next price update run will fetch prices for these new entries.")


# ── Main discovery pipeline ───────────────────────────────────────────

def run_discovery(
    top_n_cids: int = 50,
    retailer_filter: Optional[str] = None,
    api_key: Optional[str] = None,
):
    """Main discovery pipeline."""
    start_time = time.time()

    # Load API key
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[ERROR] ANTHROPIC_API_KEY not set.")
        print("        Set it as an environment variable or pass --api-key")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=key)

    # Load feedback history for context
    feedback = load_feedback_history()

    # Get retailers and unmonitored CIDs
    retailers = get_active_retailers()
    if retailer_filter:
        retailers = [r for r in retailers if r["key"] == retailer_filter]
        if not retailers:
            print(f"[ERROR] Retailer '{retailer_filter}' not found.")
            return

    unmonitored_df = get_unmonitored_cids(top_n_cids)
    if unmonitored_df.empty:
        print("[INFO] No unmonitored CIDs found. All CIDs are covered!")
        return

    master_df = pd.read_csv(MASTER_CSV)

    cid_list = unmonitored_df["cigar_id"].tolist()
    cid_parts_list = [parse_cid(c) for c in cid_list]
    cid_parts_list = [c for c in cid_parts_list if c]  # Filter out parse failures

    print(f"\n{'='*70}")
    print(f"URL DISCOVERY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    print(f"Retailers to scan: {len(retailers)}")
    print(f"CIDs to match: {len(cid_parts_list)}")
    print(f"{'='*70}\n")

    all_matches = []

    for ri, retailer in enumerate(retailers, 1):
        rkey = retailer["key"]
        base = retailer["base_url"]
        existing = retailer["existing_cids"]

        # Skip CIDs already in this retailer
        cids_for_retailer = [c for c in cid_parts_list if c["raw"] not in existing]
        if not cids_for_retailer:
            continue

        print(f"[{ri}/{len(retailers)}] Scanning {rkey} ({base})...")

        # Fetch sitemap
        sitemap_urls = fetch_sitemap_urls(base)
        product_urls = filter_product_urls(sitemap_urls)

        if not product_urls:
            logger.info(f"  No product URLs found in sitemap for {rkey}")
            # Still record NONE matches for reporting
            for c in cids_for_retailer:
                all_matches.append({
                    "cid": c["raw"],
                    "retailer_key": rkey,
                    "url": None,
                    "confidence": "NONE",
                    "reason": f"No sitemap or product URLs found for {rkey}",
                })
            continue

        print(f"  Found {len(product_urls)} product URLs in sitemap")

        # Pass 1: Programmatic pre-filtering to find strong candidates
        candidates_by_cid = {}
        for c in cids_for_retailer:
            scored = []
            for url in product_urls:
                score, details = programmatic_score(c, url)
                if score >= 0.3:
                    scored.append((url, score, details))
            scored.sort(key=lambda x: x[1], reverse=True)
            candidates_by_cid[c["raw"]] = scored[:10]

        # Split into auto-match (very high programmatic score) and needs-Claude
        needs_claude = []
        for c in cids_for_retailer:
            candidates = candidates_by_cid.get(c["raw"], [])
            if candidates and candidates[0][1] >= 0.85:
                # Very high programmatic match — still send to Claude for verification
                # but batch these with better context
                needs_claude.append(c)
            elif candidates:
                needs_claude.append(c)
            else:
                all_matches.append({
                    "cid": c["raw"],
                    "retailer_key": rkey,
                    "url": None,
                    "confidence": "NONE",
                    "reason": "No keyword overlap with any product URL",
                })

        if not needs_claude:
            continue

        # Pass 2: Claude verification in batches of 10
        batch_size = 10
        for i in range(0, len(needs_claude), batch_size):
            batch = needs_claude[i:i + batch_size]

            # Collect candidate URLs for this batch
            batch_urls = set()
            for c in batch:
                for url, score, _ in candidates_by_cid.get(c["raw"], []):
                    batch_urls.add(url)

            if not batch_urls:
                continue

            print(f"  Sending {len(batch)} CIDs to Claude ({len(batch_urls)} candidate URLs)...")

            claude_results = claude_batch_match(
                client, batch, list(batch_urls), rkey,
            )

            for m in claude_results:
                m["retailer_key"] = rkey
                all_matches.append(m)

            # Rate limit between Claude calls
            time.sleep(1)

    elapsed = time.time() - start_time

    # Write outputs
    matched = [m for m in all_matches if m.get("url")]
    staged_count, pending_count = write_staged_output(matched, master_df)
    write_report(all_matches, len(retailers), len(cid_parts_list), elapsed)

    print(f"\nStaged {staged_count} matches ({pending_count} need individual review)")
    print(f"Report saved to: {REPORT_FILE}")


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="URL Discovery Agent - Find product URLs for unmonitored CIDs",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--top-cids", type=int, metavar="N",
        help="Discover URLs for the top N unmonitored CIDs",
    )
    group.add_argument(
        "--approve-batch", action="store_true",
        help="Approve all high-confidence staged matches after spot-checking",
    )
    group.add_argument(
        "--reject-flagged", action="store_true",
        help="Process rejections from pending_review.csv (rows with feedback)",
    )
    group.add_argument(
        "--publish-approved", action="store_true",
        help="Push approved matches into production retailer CSVs",
    )

    parser.add_argument(
        "--retailer", type=str, metavar="KEY",
        help="Only scan a specific retailer (e.g., foxcigar, atlantic)",
    )
    parser.add_argument(
        "--api-key", type=str,
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )

    args = parser.parse_args()

    if args.approve_batch:
        approve_batch()
    elif args.reject_flagged:
        reject_flagged()
    elif args.publish_approved:
        publish_approved()
    else:
        run_discovery(
            top_n_cids=args.top_cids,
            retailer_filter=args.retailer,
            api_key=args.api_key,
        )


if __name__ == "__main__":
    main()
