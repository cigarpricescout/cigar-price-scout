#!/usr/bin/env python3
"""
Evaluate retailer extractors: import health, built-in tests, and live CSV spot-checks.

Usage:
  python scripts/evaluate_all_extractors.py              # full (imports + tests + live)
  python scripts/evaluate_all_extractors.py --no-live  # skip network spot-checks
  python scripts/evaluate_all_extractors.py --retailer cigarhustler
"""

from __future__ import annotations

import argparse
import csv
import importlib
import inspect
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
RETAILERS_DIR = PROJECT_ROOT / "tools" / "price_monitoring" / "retailers"
STATIC_DATA = PROJECT_ROOT / "static" / "data"

sys.path.insert(0, str(RETAILERS_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "price_monitoring"))

# Mirrors automation/automated_cigar_price_system.py
SCRIPT_TO_RETAILER = {
    "absolute_cigars": "absolutecigars",
    "atlantic": "atlantic",
    "bighumidor": "bighumidor",
    "bnbtobacco": "bnbtobacco",
    "cccrafter": "cccrafter",
    "cigarboxpa": "cigarboxpa",
    "cigarcellarofmiami": "cigarcellarofmiami",
    "cigardepot": "cigardepot",
    "cigarhustler": "cigarhustler",
    "cigarking": "cigarking",
    "cigarprimestore": "cigarprimestore",
    "cigarsdirect": "cigarsdirect",
    "coronacigar": "coronacigar",
    "foxcigar": "foxcigar",
    "gotham": "gothamcigars",
    "hilandscigars": "hilands",
    "holts": "holts",
    "iheartcigars": "iheartcigars",
    "neptune": "neptune",
    "nicks": "nickscigarworld",
    "planet_cigars": "planetcigars",
    "pyramidcigars": "pyramidcigars",
    "smallbatch_cigar": "smallbatchcigar",
    "smokeinn": "smokeinn",
    "stogies": "stogies",
    "tampasweethearts": "tampasweethearts",
    "thecigarshop": "thecigarshop",
    "tobaccolocker": "tobaccolocker",
    "tobaccostock": "tobaccostock",
    "two_guys": "twoguys",
    "watchcity": "watchcity",
    "cigaroasis": "cigaroasis",
    "escobarcigars": "escobarcigars",
    "santamonicacigars": "santamonicacigars",
    "momscigars": "momscigars",
    "baysidecigars": "baysidecigars",
}

# Manual wiring where update script import does not follow a simple pattern.
EXTRACTOR_WIRING: Dict[str, Dict[str, str]] = {
    "absolute_cigars": {"module": "absolute_cigars_extractor", "func": "extract_absolute_cigars_data"},
    "atlantic": {"module": "atlantic_cigar_extractor", "func": "extract_atlantic_cigar_data"},
    "bighumidor": {"module": "big_humidor_extractor", "class": "BigHumidorExtractor", "method": "extract_product_data"},
    "bnbtobacco": {"module": "bnb_tobacco_extractor", "func": "extract_bnb_tobacco_data"},
    "cccrafter": {"module": "cccrafter_extractor", "class": "CCCrafterExtractor", "method": "extract_product_data"},
    "cigarboxpa": {"module": "cigarboxpa_extractor", "func": "extract_cigarboxpa_data"},
    "cigarcellarofmiami": {"module": "cigarcellarofmiami_extractor", "func": "extract_cigarcellarofmiami_data"},
    "cigardepot": {"module": "cigardepot_extractor", "func": "extract_cigardepot_data"},
    "cigarhustler": {"module": "cigarhustler_extractor", "func": "extract_cigarhustler_data"},
    "cigarking": {"module": "cigar_king_extractor", "class": "CigarKingExtractor", "method": "extract_product_data"},
    "cigarprimestore": {"module": "cigarprimestore_extractor", "func": "extract_cigarprimestore_data"},
    "cigarsdirect": {"module": "cigarsdirect_extractor", "func": "extract_cigarsdirect_data"},
    "coronacigar": {"module": "coronacigar_extractor", "func": "extract_coronacigar_data"},
    "foxcigar": {"module": "fox_cigar", "func": "extract_fox_cigar_data"},
    "gotham": {"module": "gotham_cigars_extractor", "func": "extract_gotham_cigars_data"},
    "hilandscigars": {"module": "hilands_cigars", "func": "extract_hilands_cigars_data"},
    "holts": {"module": "holts_cigars_extractor", "func": "extract_holts_cigar_data"},
    "iheartcigars": {"module": "app.update_iheartcigars_prices", "func": "extract_iheartcigars_data_production"},
    "neptune": {"module": "neptune_cigar_extractor", "func": "extract_neptune_cigar_data"},
    "nicks": {"module": "nicks_cigars", "func": "extract_nicks_cigars_data"},
    "planet_cigars": {"module": "planet_cigars_extractor", "func": "extract_planet_cigars_data"},
    "pyramidcigars": {"module": "pyramid_cigars_extractor", "func": "extract_pyramid_cigars_data"},
    "smallbatch_cigar": {"module": "smallbatch_cigar_extractor", "func": "extract_smallbatch_cigar_data"},
    "smokeinn": {"module": "smokeinn_extractor", "func": "extract_smokeinn_cigar_data"},
    "stogies": {"module": "stogies_extractor", "func": "extract_stogies_data"},
    "tampasweethearts": {"module": "tampa_sweethearts_extractor", "func": "extract_tampa_sweethearts_data"},
    "thecigarshop": {"module": "thecigarshop_extractor", "func": "extract_thecigarshop_data"},
    "tobaccolocker": {"module": "tobacco_locker_extractor", "func": "extract_tobacco_locker_data"},
    "tobaccostock": {"module": "tobaccostock_extractor", "func": "extract_tobaccostock_data"},
    "two_guys": {"module": "two_guys_extractor", "func": "extract_two_guys_cigars_data"},
    "watchcity": {"module": "watch_city_extractor", "func": "extract_watch_city_data"},
    "cigaroasis": {"module": "shopify_generic_extractor", "func": "extract_shopify_store_data"},
    "escobarcigars": {"module": "shopify_generic_extractor", "func": "extract_shopify_store_data"},
    "santamonicacigars": {"module": "shopify_generic_extractor", "func": "extract_shopify_store_data"},
    "momscigars": {"module": "moms_cigars_extractor", "func": "extract_moms_cigars_data"},
    "baysidecigars": {"module": "baysidecigars_extractor", "func": "extract_bayside_cigars_data"},
}

# Extractor modules with dedicated offline/unit test entrypoints.
OFFLINE_TEST_COMMANDS = {
    "cigarhustler_extractor": [sys.executable, "-m", "tools.price_monitoring.retailers.cigarhustler_extractor", "offline"],
}


@dataclass
class EvalResult:
    script_key: str
    retailer_key: str
    import_ok: bool = False
    import_error: str = ""
    builtin_test_ok: Optional[bool] = None
    builtin_test_detail: str = ""
    live_ok: Optional[bool] = None
    live_detail: str = ""
    sample_url: str = ""
    csv_price: Optional[float] = None
    live_price: Optional[float] = None


def discover_update_scripts() -> List[Path]:
    scripts = sorted(APP_DIR.glob("update_*_prices*.py"))
    return scripts


def script_base_name(path: Path) -> str:
    name = path.name
    name = name.replace("update_", "").replace("_prices_final.py", "").replace("_prices.py", "")
    return name


def load_retailer_status() -> Dict[str, str]:
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "app"))
        from main import RETAILERS, get_extractor_status  # type: ignore

        return {r["key"]: get_extractor_status(r["key"]) for r in RETAILERS}
    except Exception:
        return {}


def resolve_callable(wiring: Dict[str, str]) -> Tuple[Callable[..., Any], str]:
    module_name = wiring["module"]
    if module_name.startswith("app."):
        sys.path.insert(0, str(PROJECT_ROOT))
        mod = importlib.import_module("update_iheartcigars_prices")
    else:
        mod = importlib.import_module(module_name)

    if "class" in wiring:
        cls = getattr(mod, wiring["class"])
        inst = cls()
        fn = getattr(inst, wiring["method"])
        label = f"{wiring['class']}.{wiring['method']}"
    else:
        fn = getattr(mod, wiring["func"])
        label = wiring["func"]
    return fn, label


def normalize_price(result: Any) -> Tuple[Optional[float], bool, str]:
    """Return (price, success, error_message)."""
    if result is None:
        return None, False, "extractor returned None"
    if isinstance(result, dict):
        if result.get("error"):
            return None, False, str(result["error"])
        if result.get("success") is False:
            return None, False, str(result.get("error") or "success=False")
        for key in ("price", "box_price", "current_price"):
            if key in result and result[key] is not None:
                try:
                    return float(result[key]), True, ""
                except (TypeError, ValueError):
                    pass
        return None, False, f"no price key in {list(result.keys())[:8]}"
    if isinstance(result, (int, float)):
        return float(result), True, ""
    return None, False, f"unexpected result type {type(result).__name__}"


def call_extractor(fn: Callable[..., Any], url: str, row: Dict[str, str]) -> Tuple[Optional[float], bool, str]:
    sig = inspect.signature(fn)
    params = list(sig.parameters.keys())
    kwargs: Dict[str, Any] = {}
    args: List[Any] = [url]

    if "cigar_id" in params:
        kwargs["cigar_id"] = row.get("cigar_id")
        if params[0] == "url" and len(params) >= 2 and params[1] == "cigar_id":
            args = [url, row.get("cigar_id")]
    if "target_box_qty" in params and row.get("box_qty"):
        try:
            kwargs["target_box_qty"] = int(float(row["box_qty"]))
        except ValueError:
            pass
    if "target_packaging" in params and row.get("box_qty"):
        kwargs["target_packaging"] = f"Box of {int(float(row['box_qty']))}"
    if "target_vitola" in params and row.get("vitola"):
        kwargs["target_vitola"] = row.get("vitola")
    if "rate_limit_seconds" in params:
        kwargs["rate_limit_seconds"] = 0.5

    try:
        if kwargs:
            result = fn(url, **kwargs) if "url" in params else fn(**kwargs)
        else:
            # Only pass url if function accepts it positionally or by name
            if len(params) == 0:
                result = fn()
            elif params[0] == "url":
                result = fn(url)
            else:
                result = fn(url)
    except TypeError:
        result = fn(url)

    return normalize_price(result)


def pick_sample_row(csv_path: Path) -> Optional[Dict[str, str]]:
    if not csv_path.exists():
        return None
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or "").strip()
            if not url.startswith("http"):
                continue
            price_raw = (row.get("price") or "").strip()
            if not price_raw:
                continue
            try:
                price = float(price_raw)
            except ValueError:
                continue
            if price <= 0:
                continue
            return row
        return None


def run_builtin_test(module_file: Path) -> Tuple[Optional[bool], str]:
    mod_name = module_file.stem
    if mod_name in OFFLINE_TEST_COMMANDS:
        cmd = OFFLINE_TEST_COMMANDS[mod_name]
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out[-500:] if out else f"exit {proc.returncode}"

    if not module_file.exists():
        return None, "no module file"

    proc = subprocess.run(
        [sys.executable, str(module_file)],
        cwd=str(RETAILERS_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return True, out[-400:] if out else "ok"
    # Some modules exit 0 only on pass; non-zero = fail
    if "PASSED" in out or "SUCCESS" in out:
        return "FAILED" not in out and proc.returncode == 0, out[-500:]
    return False, out[-500:] if out else f"exit {proc.returncode}"


def price_close(a: float, b: float, pct: float = 0.15, abs_tol: float = 5.0) -> bool:
    if a <= 0 or b <= 0:
        return False
    return abs(a - b) <= max(abs_tol, a * pct)


def evaluate_one(script_key: str, *, run_live: bool, statuses: Dict[str, str]) -> EvalResult:
    retailer_key = SCRIPT_TO_RETAILER.get(script_key, script_key)
    res = EvalResult(script_key=script_key, retailer_key=retailer_key)
    wiring = EXTRACTOR_WIRING.get(script_key)
    if not wiring:
        res.import_error = "no wiring entry in evaluate script"
        return res

    try:
        fn, label = resolve_callable(wiring)
        res.import_ok = True
    except Exception as e:
        res.import_error = f"{type(e).__name__}: {e}"
        return res

    module_path = RETAILERS_DIR / f"{wiring['module'].replace('.', '/')}.py"
    if wiring["module"] == "fox_cigar":
        module_path = RETAILERS_DIR / "fox_cigar.py"
    if wiring["module"] == "hilands_cigars":
        module_path = RETAILERS_DIR / "hilands_cigars.py"
    if wiring["module"] == "nicks_cigars":
        module_path = RETAILERS_DIR / "nicks_cigars.py"
    if wiring["module"].startswith("app."):
        module_path = PROJECT_ROOT / "app" / "update_iheartcigars_prices.py"

    test_ok, test_detail = run_builtin_test(module_path)
    res.builtin_test_ok = test_ok
    res.builtin_test_detail = test_detail

    if not run_live:
        return res

    status = statuses.get(retailer_key, "active")
    if status == "blocked":
        res.live_ok = None
        res.live_detail = "skipped (blocked retailer)"
        return res

    csv_path = STATIC_DATA / f"{retailer_key}.csv"
    row = pick_sample_row(csv_path)
    if not row:
        res.live_ok = None
        res.live_detail = "no sample row with url+price in CSV"
        return res

    url = row["url"].strip()
    res.sample_url = url
    try:
        res.csv_price = float(row["price"])
    except ValueError:
        res.csv_price = None

    time.sleep(1.0)  # polite rate limit between retailers
    try:
        live_price, ok, err = call_extractor(fn, url, row)
        res.live_price = live_price
        if not ok:
            res.live_ok = False
            res.live_detail = err
            return res
        if live_price is None:
            res.live_ok = False
            res.live_detail = "no price extracted"
            return res
        if res.csv_price and price_close(res.csv_price, live_price):
            res.live_ok = True
            res.live_detail = f"csv ${res.csv_price:.2f} ~ live ${live_price:.2f}"
        elif res.csv_price:
            drift = abs(live_price - res.csv_price) / res.csv_price * 100
            res.live_ok = True  # extractor works; CSV may be stale
            res.live_detail = f"DRIFT {drift:.0f}%: csv ${res.csv_price:.2f} vs live ${live_price:.2f}"
        else:
            res.live_ok = True
            res.live_detail = f"live ${live_price:.2f} (no csv price)"
    except Exception as e:
        res.live_ok = False
        res.live_detail = f"{type(e).__name__}: {e}"

    return res


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retailer extractors")
    parser.add_argument("--no-live", action="store_true", help="Skip live URL spot-checks")
    parser.add_argument("--retailer", help="Only evaluate one script key (e.g. cigarhustler)")
    args = parser.parse_args()

    scripts = discover_update_scripts()
    statuses = load_retailer_status()
    results: List[EvalResult] = []

    for script_path in scripts:
        key = script_base_name(script_path)
        if args.retailer and key != args.retailer:
            continue
        if key not in EXTRACTOR_WIRING:
            results.append(
                EvalResult(
                    script_key=key,
                    retailer_key=SCRIPT_TO_RETAILER.get(key, key),
                    import_error="not in EXTRACTOR_WIRING — add mapping",
                )
            )
            continue
        results.append(evaluate_one(key, run_live=not args.no_live, statuses=statuses))

    # Report
    print("=" * 72)
    print("EXTRACTOR EVALUATION REPORT")
    print("=" * 72)

    import_fail = [r for r in results if not r.import_ok]
    test_fail = [r for r in results if r.builtin_test_ok is False]
    live_fail = [r for r in results if r.live_ok is False]
    live_drift = [r for r in results if r.live_ok and r.live_detail.startswith("DRIFT")]

    for r in results:
        flags = []
        if not r.import_ok:
            flags.append("IMPORT_FAIL")
        elif r.builtin_test_ok is False:
            flags.append("TEST_FAIL")
        elif r.live_ok is False:
            flags.append("LIVE_FAIL")
        elif r.live_detail.startswith("DRIFT"):
            flags.append("DRIFT")
        elif r.live_ok:
            flags.append("OK")
        elif r.builtin_test_ok:
            flags.append("TEST_OK")
        else:
            flags.append("—")

        status = statuses.get(r.retailer_key, "?")
        print(f"\n[{', '.join(flags)}] {r.retailer_key} (script={r.script_key}, status={status})")
        if not r.import_ok:
            print(f"  import: {r.import_error}")
            continue
        print(f"  import: ok")
        if r.builtin_test_ok is True:
            print(f"  builtin test: PASS")
        elif r.builtin_test_ok is False:
            print(f"  builtin test: FAIL — {r.builtin_test_detail[:200]}")
        else:
            print(f"  builtin test: (not run / no test)")
        if r.live_ok is True:
            print(f"  live spot-check: {r.live_detail}")
            if r.sample_url:
                print(f"    url: {r.sample_url[:90]}...")
        elif r.live_ok is False:
            print(f"  live spot-check: FAIL — {r.live_detail}")
        elif not args.no_live:
            print(f"  live spot-check: {r.live_detail or 'skipped'}")

    print("\n" + "=" * 72)
    print("SUMMARY")
    print(f"  retailers evaluated: {len(results)}")
    print(f"  import failures:     {len(import_fail)}")
    print(f"  builtin test fails:  {len(test_fail)}")
    print(f"  live failures:       {len(live_fail)}")
    print(f"  live drift warnings: {len(live_drift)}")
    print("=" * 72)

    return 1 if import_fail or test_fail or live_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
