import re
from dataclasses import dataclass

@dataclass
class NQ:
    brand: str | None
    line: str | None
    size: str | None

def normalize_query(q: str, known_brands: list[str]) -> NQ:
    s = (q or "").strip()
    brand = None
    for b in known_brands:
        if re.search(rf"\b{re.escape(b)}\b", s, flags=re.IGNORECASE):
            brand = b
            break
    line = None
    if brand:
        rest = re.sub(rf"\b{re.escape(brand)}\b", "", s, flags=re.IGNORECASE).strip()
        m = re.search(r"(\d+(?:\.\d+)?)\s*[xX]\s*(\d+)", rest)
        candidate = rest[:m.start()].strip() if m else rest
        line = candidate if candidate else None
    m = re.search(r"(\d+(?:\.\d+)?)\s*[xX]\s*(\d+)", s)
    size = f"{m.group(1)}x{m.group(2)}" if m else None
    return NQ(brand=brand, line=line if line else None, size=size if size else None)
