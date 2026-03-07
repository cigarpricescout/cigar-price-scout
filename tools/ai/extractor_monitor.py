#!/usr/bin/env python3
"""
Extractor Health Monitor - Tracks extraction success rates and detects breakages.

Runs after each automated price update cycle. Analyzes per-retailer results,
compares to historical baselines, and generates a health report section for
the morning email.

Usage:
    # Generate health report (called by automated_cigar_price_system.py)
    from tools.ai.extractor_monitor import ExtractorHealthMonitor
    monitor = ExtractorHealthMonitor(project_root)
    report = monitor.generate_health_report()

    # Standalone: check health and print report
    python tools/ai/extractor_monitor.py

    # Diagnose a specific retailer
    python tools/ai/extractor_monitor.py --diagnose foxcigar
"""

import os
import sys
import re
import csv
import json
import sqlite3
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DATA = PROJECT_ROOT / "static" / "data"
HISTORICAL_DB = PROJECT_ROOT / "data" / "historical_prices.db"
HEALTH_DB = PROJECT_ROOT / "data" / "extractor_health.db"


class ExtractorHealthMonitor:
    """Monitors extractor health across automated runs."""

    # Success rate below this triggers a warning
    WARNING_THRESHOLD = 0.80
    # Success rate below this triggers a critical alert
    CRITICAL_THRESHOLD = 0.50
    # Minimum drop from baseline to trigger an alert
    DROP_THRESHOLD = 0.15
    # How many recent runs to use for baseline
    BASELINE_WINDOW_DAYS = 14

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root) if project_root else PROJECT_ROOT
        self.static_data = self.project_root / "static" / "data"
        self.historical_db = self.project_root / "data" / "historical_prices.db"
        self.health_db = self.project_root / "data" / "extractor_health.db"
        self._init_health_db()

    def _init_health_db(self):
        """Initialize health tracking database."""
        try:
            conn = sqlite3.connect(self.health_db)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    snapshot_date DATE NOT NULL,
                    total_products INTEGER,
                    products_with_url INTEGER,
                    products_with_price INTEGER,
                    products_in_stock INTEGER,
                    success_rate REAL,
                    avg_price REAL,
                    zero_price_count INTEGER,
                    empty_url_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(retailer, snapshot_date)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    alert_date DATE NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize health DB: {e}")

    def _get_retailer_run_results(self) -> Dict[str, Dict]:
        """Get the most recent run results from historical_prices.db."""
        if not self.historical_db.exists():
            return {}

        try:
            conn = sqlite3.connect(self.historical_db)
            cursor = conn.cursor()

            # Get the latest automation run
            cursor.execute("""
                SELECT id, run_date, retailers_attempted, retailers_successful
                FROM automation_runs
                ORDER BY id DESC LIMIT 1
            """)
            latest_run = cursor.fetchone()
            if not latest_run:
                conn.close()
                return {}

            run_id = latest_run[0]

            # Get per-retailer results from that run
            cursor.execute("""
                SELECT retailer, success, duration_seconds,
                       products_updated, products_failed, error
                FROM retailer_runs
                WHERE automation_run_id = ?
            """, (run_id,))

            results = {}
            for row in cursor.fetchall():
                results[row[0]] = {
                    "success": bool(row[1]),
                    "duration": row[2],
                    "products_updated": row[3] or 0,
                    "products_failed": row[4] or 0,
                    "error": row[5],
                }

            conn.close()
            return results

        except Exception as e:
            logger.error(f"Failed to read retailer run results: {e}")
            return {}

    def _get_baseline(self, retailer: str) -> Optional[float]:
        """Get the baseline success rate for a retailer over the last N days."""
        try:
            conn = sqlite3.connect(self.health_db)
            cursor = conn.cursor()

            cutoff = (datetime.now() - timedelta(days=self.BASELINE_WINDOW_DAYS)).strftime("%Y-%m-%d")

            cursor.execute("""
                SELECT AVG(success_rate)
                FROM health_snapshots
                WHERE retailer = ? AND snapshot_date >= ?
            """, (retailer, cutoff))

            result = cursor.fetchone()
            conn.close()

            if result and result[0] is not None:
                return result[0]
            return None

        except Exception:
            return None

    def analyze_csv_health(self, retailer_key: str) -> Dict:
        """Analyze the current state of a retailer's CSV for health indicators."""
        csv_path = self.static_data / f"{retailer_key}.csv"
        if not csv_path.exists():
            return {"error": f"CSV not found: {csv_path}"}

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            return {"error": f"Failed to read CSV: {e}"}

        total = len(df)
        if total == 0:
            return {"error": "CSV is empty", "total": 0}

        has_url = df["url"].notna() & (df["url"] != "")
        has_price = pd.to_numeric(df.get("price", pd.Series(dtype=float)), errors="coerce") > 0
        in_stock = df.get("in_stock", pd.Series(dtype=str)).astype(str).str.lower() == "true"

        with_url = has_url.sum()
        with_price = (has_url & has_price).sum()
        zero_price = (has_url & ~has_price).sum()
        stock_in = (has_url & in_stock).sum()
        empty_url = (~has_url).sum()

        success_rate = with_price / with_url if with_url > 0 else 0.0

        prices = pd.to_numeric(df.loc[has_url & has_price, "price"], errors="coerce")
        avg_price = prices.mean() if len(prices) > 0 else 0.0

        return {
            "total": total,
            "with_url": int(with_url),
            "with_price": int(with_price),
            "in_stock": int(stock_in),
            "success_rate": round(success_rate, 3),
            "avg_price": round(avg_price, 2),
            "zero_price": int(zero_price),
            "empty_url": int(empty_url),
        }

    def take_snapshot(self):
        """Take a health snapshot of all active retailers."""
        today = datetime.now().strftime("%Y-%m-%d")

        for csv_file in sorted(self.static_data.glob("*.csv")):
            name = csv_file.stem
            if any(x in name for x in ["DORMANT", "BROKEN", "backup"]):
                continue

            health = self.analyze_csv_health(name)
            if "error" in health:
                continue

            try:
                conn = sqlite3.connect(self.health_db)
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO health_snapshots
                    (retailer, snapshot_date, total_products, products_with_url,
                     products_with_price, products_in_stock, success_rate,
                     avg_price, zero_price_count, empty_url_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name, today, health["total"], health["with_url"],
                    health["with_price"], health["in_stock"], health["success_rate"],
                    health["avg_price"], health["zero_price"], health["empty_url"],
                ))

                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to save snapshot for {name}: {e}")

    def detect_anomalies(self) -> List[Dict]:
        """Detect health anomalies across all retailers."""
        alerts = []
        run_results = self._get_retailer_run_results()

        for csv_file in sorted(self.static_data.glob("*.csv")):
            name = csv_file.stem
            if any(x in name for x in ["DORMANT", "BROKEN", "backup"]):
                continue

            health = self.analyze_csv_health(name)
            if "error" in health:
                continue

            rate = health["success_rate"]
            baseline = self._get_baseline(name)

            # Check absolute thresholds
            if rate < self.CRITICAL_THRESHOLD and health["with_url"] > 0:
                alerts.append({
                    "retailer": name,
                    "severity": "CRITICAL",
                    "type": "low_success_rate",
                    "message": (
                        f"Success rate {rate:.0%} is critically low. "
                        f"{health['zero_price']} of {health['with_url']} products have no price."
                    ),
                    "rate": rate,
                    "baseline": baseline,
                })
            elif rate < self.WARNING_THRESHOLD and health["with_url"] > 0:
                alerts.append({
                    "retailer": name,
                    "severity": "WARNING",
                    "type": "low_success_rate",
                    "message": (
                        f"Success rate {rate:.0%} is below threshold. "
                        f"{health['zero_price']} products missing prices."
                    ),
                    "rate": rate,
                    "baseline": baseline,
                })

            # Check for sudden drop from baseline
            if baseline is not None and (baseline - rate) > self.DROP_THRESHOLD:
                alerts.append({
                    "retailer": name,
                    "severity": "WARNING",
                    "type": "rate_drop",
                    "message": (
                        f"Success rate dropped from {baseline:.0%} to {rate:.0%} "
                        f"({(baseline - rate):.0%} decrease)."
                    ),
                    "rate": rate,
                    "baseline": baseline,
                })

            # Check for script failures from latest run
            if name in run_results:
                result = run_results[name]
                if not result["success"]:
                    error_msg = result.get("error", "Unknown error")
                    severity = "CRITICAL" if "Timeout" in str(error_msg) else "WARNING"
                    alerts.append({
                        "retailer": name,
                        "severity": severity,
                        "type": "script_failure",
                        "message": f"Update script failed: {str(error_msg)[:150]}",
                        "rate": rate,
                        "baseline": baseline,
                    })

            # Check for all products out of stock (suspicious)
            if health["with_url"] > 5 and health["in_stock"] == 0:
                alerts.append({
                    "retailer": name,
                    "severity": "WARNING",
                    "type": "all_out_of_stock",
                    "message": (
                        f"All {health['with_url']} products showing out of stock. "
                        f"Stock detection may be broken."
                    ),
                    "rate": rate,
                    "baseline": baseline,
                })

        # Save alerts to DB
        self._save_alerts(alerts)

        return alerts

    def _save_alerts(self, alerts: List[Dict]):
        """Save alerts to the health database."""
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            conn = sqlite3.connect(self.health_db)
            cursor = conn.cursor()

            for alert in alerts:
                cursor.execute("""
                    INSERT INTO health_alerts
                    (retailer, alert_date, alert_type, severity, message)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    alert["retailer"], today,
                    alert["type"], alert["severity"], alert["message"],
                ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save alerts: {e}")

    def generate_health_report(self) -> str:
        """
        Generate a health report section for the morning email.
        Called by automated_cigar_price_system.py after each run.
        """
        self.take_snapshot()
        alerts = self.detect_anomalies()

        lines = [
            "",
            "=" * 50,
            "EXTRACTOR HEALTH REPORT",
            "=" * 50,
        ]

        # Count healthy retailers
        healthy_count = 0
        total_count = 0
        for csv_file in sorted(self.static_data.glob("*.csv")):
            name = csv_file.stem
            if any(x in name for x in ["DORMANT", "BROKEN", "backup"]):
                continue
            total_count += 1

        retailer_alerts = defaultdict(list)
        for a in alerts:
            retailer_alerts[a["retailer"]].append(a)

        healthy_count = total_count - len(retailer_alerts)

        if not alerts:
            lines.append(f"\nAll Healthy ({total_count} retailers): OK")
            lines.append("")
            return "\n".join(lines)

        if healthy_count > 0:
            lines.append(f"\nHealthy ({healthy_count} retailers): OK")

        # Group alerts by severity
        critical = [a for a in alerts if a["severity"] == "CRITICAL"]
        warnings = [a for a in alerts if a["severity"] == "WARNING"]

        if critical:
            lines.append(f"\nCRITICAL ({len(critical)} issues):")
            for a in critical:
                lines.append(f"  {a['retailer']}: {a['message']}")

        if warnings:
            lines.append(f"\nWarnings ({len(warnings)} issues):")
            for a in warnings:
                lines.append(f"  {a['retailer']}: {a['message']}")

        lines.append("")
        return "\n".join(lines)

    def diagnose_retailer(self, retailer_key: str) -> str:
        """
        Deep diagnosis of a specific retailer.
        Checks CSV state, recent history, and common failure patterns.
        """
        lines = [
            f"\n{'='*50}",
            f"DIAGNOSIS: {retailer_key}",
            f"{'='*50}",
        ]

        # Current CSV health
        health = self.analyze_csv_health(retailer_key)
        if "error" in health:
            lines.append(f"\nError: {health['error']}")
            return "\n".join(lines)

        lines.extend([
            f"\nCurrent State:",
            f"  Total products: {health['total']}",
            f"  With URL: {health['with_url']}",
            f"  With valid price: {health['with_price']}",
            f"  In stock: {health['in_stock']}",
            f"  Success rate: {health['success_rate']:.0%}",
            f"  Average price: ${health['avg_price']:.2f}",
            f"  Zero/missing price: {health['zero_price']}",
            f"  Empty URL: {health['empty_url']}",
        ])

        # Baseline comparison
        baseline = self._get_baseline(retailer_key)
        if baseline is not None:
            lines.append(f"\n  14-day baseline: {baseline:.0%}")
            diff = health["success_rate"] - baseline
            if abs(diff) > 0.01:
                direction = "up" if diff > 0 else "down"
                lines.append(f"  Trend: {direction} {abs(diff):.0%}")

        # Recent run results
        run_results = self._get_retailer_run_results()
        if retailer_key in run_results:
            result = run_results[retailer_key]
            lines.extend([
                f"\nLast Run:",
                f"  Success: {result['success']}",
                f"  Duration: {result['duration']:.1f}s",
                f"  Updated: {result['products_updated']}",
                f"  Failed: {result['products_failed']}",
            ])
            if result.get("error"):
                lines.append(f"  Error: {result['error'][:200]}")

        # Analyze failure patterns from CSV
        csv_path = self.static_data / f"{retailer_key}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            has_url = df["url"].notna() & (df["url"] != "")
            has_price = pd.to_numeric(df.get("price", pd.Series(dtype=float)), errors="coerce") > 0
            failing = df[has_url & ~has_price]

            if len(failing) > 0:
                lines.append(f"\nFailing Products ({len(failing)}):")
                for _, row in failing.head(5).iterrows():
                    cid = row.get("cigar_id", "Unknown")
                    url = row.get("url", "N/A")
                    lines.append(f"  {cid[:60]}")
                    lines.append(f"    URL: {url}")
                if len(failing) > 5:
                    lines.append(f"  ... and {len(failing) - 5} more")

        # Historical alerts
        try:
            conn = sqlite3.connect(self.health_db)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT alert_date, severity, alert_type, message
                FROM health_alerts
                WHERE retailer = ?
                ORDER BY id DESC LIMIT 5
            """, (retailer_key,))

            recent_alerts = cursor.fetchall()
            conn.close()

            if recent_alerts:
                lines.append(f"\nRecent Alerts:")
                for date, sev, atype, msg in recent_alerts:
                    lines.append(f"  [{date}] {sev}: {msg[:100]}")
        except Exception:
            pass

        lines.append("")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extractor Health Monitor - Check extraction health",
    )
    parser.add_argument(
        "--diagnose", type=str, metavar="RETAILER",
        help="Deep diagnosis of a specific retailer (e.g., foxcigar)",
    )
    parser.add_argument(
        "--project-root", type=str,
        help="Path to project root directory",
    )

    args = parser.parse_args()

    root = Path(args.project_root) if args.project_root else PROJECT_ROOT
    monitor = ExtractorHealthMonitor(project_root=root)

    if args.diagnose:
        print(monitor.diagnose_retailer(args.diagnose))
    else:
        print(monitor.generate_health_report())


if __name__ == "__main__":
    main()
