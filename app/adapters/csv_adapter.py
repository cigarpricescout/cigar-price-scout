import csv, os
from dataclasses import dataclass

PACK_OK = {10, 12, 20, 24, 25, 50}

@dataclass
class ListingCandidate:
    retailer_key: str
    retailer_name: str
    title: str
    url: str
    brand: str
    line: str
    size: str
    box_qty: int
    base_cents: int
    in_stock: bool

def is_box(row: dict) -> bool:
    qty = int(row.get("box_qty") or 0)
    title = (row.get("title") or "").lower()
    return (qty in PACK_OK) or (" box " in f" {title} ")

def load_csv(path: str, retailer_key: str, retailer_name: str) -> list[ListingCandidate]:
    out = []
    if not os.path.exists(path): return out
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not is_box(r): continue
            out.append(ListingCandidate(
                retailer_key=retailer_key,
                retailer_name=retailer_name,
                title=r["title"],
                url=r["url"],
                brand=r["brand"],
                line=r["line"],
                size=r["size"],
                box_qty=int(r["box_qty"]),
                base_cents=int(float(r["price"]) * 100),
                in_stock=(r.get("in_stock","true").strip().lower() != "false")
            ))
    return out
