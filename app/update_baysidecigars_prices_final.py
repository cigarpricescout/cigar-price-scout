#!/usr/bin/env python3
"""Bayside Cigars — daily price update (Shopify JSON + metadata sync)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "price_monitoring" / "retailers"))

from baysidecigars_extractor import extract_bayside_cigars_data  # noqa: E402
from shopify_retailer_update_core import run_shopify_retailer_update  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_shopify_retailer_update("baysidecigars", extract_bayside_cigars_data))
