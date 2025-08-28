#!/usr/bin/env python3
from __future__ import annotations
import csv, argparse, re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from app.utils import parse_size_to_lr
from app.catalog import ROOT  # reuse same ROOT as app

MASTER = ROOT / "static" / "master_products.csv"
DATA_DIR = ROOT / "static" / "data"

HEADER = ["brand","line","wrapper","vitola_name","length_in","ring","box_qty","shape","size_display","origin","pack_type","strength","product_slug"]

def slugify(*parts: str) -> str:
    s = "-".join(p.strip().lower() for p in parts if p and str(p).strip() != "")
    s = re.sub(r"[^a-z0-9\-x\.]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s

def load_master() -> List[Dict[str,str]]:
    if not MASTER.exists():
        MASTER.parent.mkdir(parents=True, exist_ok=True)
        with MASTER.open("w", encoding="utf-8", newline="") as g:
            csv.DictWriter(g, fieldnames=HEADER).writeheader()
        return []
    with MASTER.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def save_master(rows: List[Dict[str,str]]):
    with MASTER.open("w", encoding="utf-8", newline="") as g:
        w = csv.DictWriter(g, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def discover_sizes(brand: str, line: str, vitola_hint: Optional[str]) -> List[Tuple[str, float, int, int]]:
    """Return list of (vitola_name, length_in, ring, box_qty). Pulls from static/data/*.csv."""
    found = {}
    for p in sorted(DATA_DIR.glob("*.csv")):
        try:
            with p.open("r", encoding="utf-8", newline="") as f:
                rdr = csv.DictReader(f)
                for r in rdr:
                    if (r.get("brand","").strip().lower() != brand.lower() or
                        r.get("line","").strip().lower() != line.lower()):
                        continue
                    title = (r.get("title") or "")
                    url = (r.get("url") or "")
                    size = (r.get("size") or "")
                    try:
                        box_qty = int(r.get("box_qty") or "0")
                    except Exception:
                        box_qty = 0
                    if vitola_hint:
                        if vitola_hint.lower() not in (title + " " + url).lower():
                            # keep scanning; we still allow size-only matches
                            pass
                    length_in, ring = parse_size_to_lr(size)
                    if not (length_in and ring):
                        continue
                    # try to infer vitola from title (last word token if matches hint), else use hint, else blank
                    vitola_name = ""
                    if vitola_hint:
                        if re.search(rf"\b{re.escape(vitola_hint)}\b", title, re.I):
                            vitola_name = vitola_hint
                        else:
                            vitola_name = vitola_hint  # fallback: use provided name
                    key = (vitola_name.lower(), float(length_in), int(ring), int(box_qty or 0))
                    found[key] = (vitola_name, float(length_in), int(ring), int(box_qty or 0))
        except Exception:
            continue
    return list(found.values())

def add_master_rows(brand: str, line: str, wrappers: List[str], vitola_hint: Optional[str]):
    master = load_master()
    existing = {(r["brand"].lower(), r["line"].lower(), r["wrapper"].lower(),
                 r.get("vitola_name","").lower(), r.get("length_in",""), r.get("ring",""), r.get("box_qty",""))
                for r in master}

    sizes = discover_sizes(brand, line, vitola_hint)
    if not sizes:
        print(f"[warn] No sizes discovered for {brand} / {line}. Add retailer rows first.")
        return

    new_rows = 0
    for (vitola_name, length_in, ring, box_qty) in sizes:
        size_display = f"{length_in}x{ring}"
        vname = vitola_name or (vitola_hint or "")
        for wrapper in wrappers:
            key = (brand.lower(), line.lower(), wrapper.lower(),
                   vname.lower(), f"{length_in}", f"{ring}", f"{box_qty}")
            if key in existing:
                continue
            slug = slugify(brand, line, wrapper, vname or "", f"{length_in}x{ring}", f"{box_qty}")
            master.append({
                "brand": brand,
                "line": line,
                "wrapper": wrapper,
                "vitola_name": vname,
                "length_in": f"{length_in}",
                "ring": f"{ring}",
                "box_qty": f"{box_qty or ''}",
                "shape": "",
                "size_display": size_display,
                "origin": "",
                "pack_type": "box",
                "strength": "",
                "product_slug": slug
            })
            new_rows += 1

    save_master(master)
    print(f"[ok] Added {new_rows} rows to master for {brand} / {line} with wrappers={wrappers}")

def main():
    ap = argparse.ArgumentParser(description="Seed master_products.csv from retailer data with wrapper variants.")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--line", required=True)
    ap.add_argument("--wrappers", required=True, help="Comma-separated list. e.g. 'Natural,Maduro' or 'Connecticut,Connecticut Broadleaf'")
    ap.add_argument("--vitola", default="", help="Optional: vitola name hint (e.g., 'Classic')")
    args = ap.parse_args()

    wrappers = [w.strip() for w in args.wrappers.split(",") if w.strip()]
    add_master_rows(args.brand, args.line, wrappers, args.vitola or None)

if __name__ == "__main__":
    main()
