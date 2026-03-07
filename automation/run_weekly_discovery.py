#!/usr/bin/env python3
"""
Weekly URL Discovery Runner

Runs the URL Discovery Agent and Extractor Generator queue as a scheduled job.
Generates a weekly digest email summarizing what was found and what needs review.

Usage:
    python automation/run_weekly_discovery.py
    python automation/run_weekly_discovery.py --top-cids 100
    python automation/run_weekly_discovery.py --dry-run
"""

import os
import sys
import json
import smtplib
import argparse
import logging
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Add project root to path
AUTOMATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AUTOMATION_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.ai.url_discoverer import run_discovery, STAGED_FILE, PENDING_FILE, REPORT_FILE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config():
    """Load automation config for email settings."""
    config_path = AUTOMATION_DIR / "automation_config.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            return json.load(f)
    return {}


def send_digest_email(config: dict, report_text: str, queue_report: str = ""):
    """Send the weekly discovery digest email."""
    email_config = config.get("email_notifications", {})
    if not email_config.get("enabled") or not email_config.get("sender_email"):
        logger.info("Email notifications disabled, skipping digest email")
        return

    subject = f"Cigar Price Scout - Weekly Discovery Digest - {datetime.now().strftime('%Y-%m-%d')}"

    body = f"""Weekly URL Discovery Digest
{'='*40}

{report_text}
"""

    if queue_report:
        body += f"""
{'='*40}
Extractor Generator Queue
{'='*40}

{queue_report}
"""

    body += f"""
{'='*40}
Next Steps
{'='*40}

1. Review staged matches:
   Open tools/ai/staged_matches.csv and spot-check ~5% of entries

2. Approve if spot-checks pass:
   python tools/ai/url_discoverer.py --approve-batch

3. Review medium-confidence matches:
   Open tools/ai/pending_review.csv, add feedback to reject column

4. Process reviews:
   python tools/ai/url_discoverer.py --reject-flagged

5. Publish approved matches to retailer CSVs:
   python tools/ai/url_discoverer.py --publish-approved

Next daily price update will pick up the new entries automatically.
"""

    try:
        msg = MIMEMultipart()
        msg["From"] = email_config["sender_email"]
        msg["To"] = email_config.get("recipient_email") or email_config["sender_email"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"])
        server.starttls()
        server.login(email_config["sender_email"], email_config["sender_password"])
        server.sendmail(
            email_config["sender_email"],
            email_config.get("recipient_email") or email_config["sender_email"],
            msg.as_string(),
        )
        server.quit()
        logger.info("Weekly digest email sent")

    except Exception as e:
        logger.error(f"Failed to send digest email: {e}")


def run_queue_processor() -> str:
    """Process the extractor generator queue if there are entries."""
    queue_file = PROJECT_ROOT / "tools" / "ai" / "new_retailer_queue.txt"
    if not queue_file.exists():
        return "No queue file found."

    # Check if there are actual entries (not just comments)
    has_entries = False
    with open(queue_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "|" in line:
                has_entries = True
                break

    if not has_entries:
        return "Queue file is empty (no retailer entries)."

    try:
        from tools.ai.extractor_generator import parse_queue_file, generate_for_retailer

        entries = parse_queue_file()
        if not entries:
            return "No valid entries in queue file."

        results = []
        for entry in entries:
            try:
                generate_for_retailer(entry["name"], entry["key"], entry["urls"])
                results.append(f"  [OK] {entry['name']} ({entry['key']}): Extractor generated")
            except Exception as e:
                results.append(f"  [FAIL] {entry['name']} ({entry['key']}): {e}")

        return "\n".join(results)

    except Exception as e:
        return f"Queue processing failed: {e}"


def main():
    parser = argparse.ArgumentParser(description="Weekly URL Discovery Runner")
    parser.add_argument("--top-cids", type=int, default=50, help="Number of CIDs to search for")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending email")
    parser.add_argument("--skip-queue", action="store_true", help="Skip extractor generator queue")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"WEEKLY URL DISCOVERY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    config = load_config()

    # Run URL discovery
    logger.info(f"Running URL discovery for top {args.top_cids} CIDs...")
    try:
        run_discovery(top_n_cids=args.top_cids)
    except Exception as e:
        logger.error(f"URL discovery failed: {e}")

    # Read the generated report
    report_text = ""
    if REPORT_FILE.exists():
        with open(REPORT_FILE, "r") as f:
            report_text = f.read()

    # Process extractor generator queue
    queue_report = ""
    if not args.skip_queue:
        logger.info("Checking extractor generator queue...")
        queue_report = run_queue_processor()

    # Send digest email
    if not args.dry_run:
        send_digest_email(config, report_text, queue_report)

    print(f"\n{'='*70}")
    print("WEEKLY DISCOVERY COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
