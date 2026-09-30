"""Reject scraper prices that cannot be a real change from the stored box price.

Cents-as-dollars (8499 vs 84.99) and a 5-pack written over a box (125 vs 602)
both survived because a failed extract kept the old value, and a bad extract
overwrote a good one. This gate stops the overwrite. It does not invent a price.
"""

from __future__ import annotations


def price_change_is_implausible(old_price, new_price) -> bool:
    try:
        old = float(old_price)
        new = float(new_price)
    except (TypeError, ValueError):
        return False
    if old <= 0 or new <= 0:
        return False
    # Shopify data-price cents stored as dollars: 8499 against a real $84.99.
    if new >= 1000 and abs((new / 100.0) - old) / old <= 0.15:
        return True
    if old >= 50 and (new > old * 4 or new < old * 0.35):
        return True
    return False
