import csv, asyncio
from pathlib import Path
import httpx, re

ROOT = Path(__file__).resolve().parents[2]
URL_LIST = ROOT / "static" / "url_list.csv"
OUT_DIR = ROOT / "static" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CigarPriceScout/0.1)"}
PRICE_RE = re.compile(r"\$\s*([0-9]{1,4}(?:\.[0-9]{2})?)")

def dollars_to_cents(s: str) -> int:
    return int(round(float(s) * 100))

async def fetch_price_guess(url: str) -> int | None:
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=12) as c:
            r = await c.get(url)
            r.raise_for_status()
            m = PRICE_RE.search(r.text)
            if not m:
                return None
            return dollars_to_cents(m.group(1))
    except Exception:
        return None

async def main():
    if not URL_LIST.exists():
        print(f"Missing {URL_LIST}")
        return

    # Read your URL list (with optional price_override)
    rows = []
    with open(URL_LIST, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    # Fire off fetches in parallel (only used when no override is provided)
    tasks = []
    for r in rows:
        override = (r.get("price_override") or "").strip()
        if override:
            tasks.append((r, None))  # no fetch needed
        else:
            tasks.append((r, asyncio.create_task(fetch_price_guess(r["url"]))))

    # Build per-retailer CSV rows
    per_retailer = {}
    for r, task in tasks:
        rk = r["retailer_key"]
        per_retailer.setdefault(rk, [])
        title = f"{r['brand']} {r['line']} {r['size']} (Box of {r['box_qty']})"
        override = (r.get("price_override") or "").strip()
        if override:
            cents = dollars_to_cents(override)
        else:
            cents = await task if task else None
            if cents is None:
                # fallback visible price to prove links end-to-end
                cents = dollars_to_cents("999.99")

        per_retailer[rk].append({
            "title": title,
            "url": r["url"],
            "brand": r["brand"],
            "line": r["line"],
            "size": r["size"],
            "box_qty": r["box_qty"],
            "price": f"{cents/100:.2f}",
            "in_stock": "true"
        })

    # Write the exact files the app reads
    name_map = {"famous": "famous.csv", "ci": "ci.csv", "jr": "jr.csv"}
    for rk, items in per_retailer.items():
        out_path = OUT_DIR / name_map.get(rk, f"{rk}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["title","url","brand","line","size","box_qty","price","in_stock"])
            w.writeheader()
            for it in items:
                w.writerow(it)
        print(f"Wrote {out_path}")
