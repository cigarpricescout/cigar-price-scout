import re
SHIPPING_CENTS = {"famous": 995, "ci": 1495, "jr": 1295}
TAX_RATE = {"OR": 0.00}  # expand later

def zip_to_state(zip_str: str) -> str | None:
    z = (zip_str or "").strip()
    if not re.fullmatch(r"\d{5}", z): return None
    if 97000 <= int(z) <= 97999: return "OR"  # demo mapping
    return None

def delivered_cents(base_cents: int, retailer_key: str, state: str | None) -> int:
    ship = SHIPPING_CENTS.get(retailer_key, 1495)
    rate = TAX_RATE.get(state or "", 0.0)
    tax = int(round(base_cents * rate))
    return base_cents + ship + tax
