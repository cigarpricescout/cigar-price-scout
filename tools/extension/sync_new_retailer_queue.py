"""
Drain `pending_new_retailers` from the live API into `tools/ai/new_retailer_queue.txt`.

When the Chrome extension lands on an unknown retailer (no extractor in the
repo), the user can click "Add to new-retailer queue". That POSTs to
`/api/admin/queue-new-retailer` and rows accumulate in Postgres. This script
drains those rows into the existing queue file your `extractor_generator.py`
already consumes, so the new-retailer onboarding pipeline is untouched.

Output format matches the existing queue file convention:

    Retailer Display Name | retailer_key
    https://url-1
    https://url-2

For URLs hitting the same hostname, all URLs are grouped under one entry. The
retailer_key is derived from the hostname (e.g. www.foo.com -> foo). The
display name is a Title-Cased best guess from the hostname; you can rename it
before running `extractor_generator.py --process-queue`.

Run after `git pull` and before `git push`.
"""
from __future__ import annotations

import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' is required. pip install requests")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
QUEUE_FILE = PROJECT_ROOT / "tools" / "ai" / "new_retailer_queue.txt"

DEFAULT_API_BASE = "https://cigarpricescout.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sync_new_retailer_queue")


def _api_base() -> str:
    return os.getenv("EXTENSION_API_BASE", DEFAULT_API_BASE).rstrip("/")


def _admin_key() -> str:
    key = os.getenv("ADMIN_SECRET_KEY", "")
    if not key:
        log.error("ADMIN_SECRET_KEY is not set in the environment")
        sys.exit(1)
    return key


def _derive_retailer_key(hostname: str) -> str:
    """Best-effort retailer_key from hostname (e.g. www.foo-cigars.com -> foocigars).

    The user can edit this in the queue file before running the generator.
    """
    h = (hostname or "").lower()
    if h.startswith("www."):
        h = h[4:]
    base = h.split(".")[0] if "." in h else h
    return base.replace("-", "").replace("_", "")


def _derive_display_name(hostname: str) -> str:
    """Best-effort display name (e.g. www.foo-cigars.com -> Foo Cigars)."""
    h = (hostname or "").lower()
    if h.startswith("www."):
        h = h[4:]
    base = h.split(".")[0] if "." in h else h
    return " ".join(part.capitalize() for part in base.replace("_", "-").split("-"))


def fetch_pending() -> List[Dict]:
    r = requests.get(
        f"{_api_base()}/api/admin/pending-new-retailers",
        headers={"X-Admin-Key": _admin_key()},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("pending", [])


def mark_processed(ids: List[int]) -> int:
    if not ids:
        return 0
    r = requests.post(
        f"{_api_base()}/api/admin/mark-retailer-queued",
        headers={"X-Admin-Key": _admin_key()},
        json={"ids": ids},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("processed", 0)


def _read_existing_queue_entries() -> Dict[str, List[str]]:
    """Parse the existing queue file into {retailer_key: [urls]}.

    Used to avoid duplicating an entry that already exists in the queue.
    Header / comment lines (#) are preserved separately by the writer.
    """
    entries: Dict[str, List[str]] = defaultdict(list)
    if not QUEUE_FILE.exists():
        return entries

    current_key: Optional[str] = None
    for raw in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            current_key = None
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|", 1)]
            if len(parts) == 2 and not parts[1].startswith("http"):
                current_key = parts[1]
                entries.setdefault(current_key, [])
                continue
        if current_key and line.startswith("http"):
            entries[current_key].append(line)
    return entries


def append_to_queue(new_groups: Dict[str, Dict]) -> int:
    """Append new entries to the queue file. Returns count of URLs added.

    new_groups: {retailer_key: {"display": display_name, "urls": [...]}}
    """
    if not new_groups:
        return 0

    existing = _read_existing_queue_entries()
    appended_urls = 0

    # Build the block to append.
    chunks: List[str] = []
    for key, info in sorted(new_groups.items()):
        urls_already = set(existing.get(key, []))
        urls_to_add = [u for u in info["urls"] if u not in urls_already]
        if not urls_to_add:
            continue
        if key in existing:
            # Append URLs under the existing entry header isn't trivial without
            # rewriting the file; instead, write a new block — extractor_generator
            # de-duplicates per-URL anyway.
            chunks.append(f"\n# Continued from extension queue\n{info['display']} | {key}")
        else:
            chunks.append(f"\n# Added by Chrome extension queue\n{info['display']} | {key}")
        for url in urls_to_add:
            chunks.append(url)
            appended_urls += 1
        chunks.append("")  # trailing blank line

    if not chunks:
        return 0

    with QUEUE_FILE.open("a", encoding="utf-8") as f:
        f.write("\n".join(chunks))
        f.write("\n")

    return appended_urls


def sync(dry_run: bool = False) -> Dict[str, int]:
    stats = {"fetched": 0, "groups": 0, "urls_appended": 0, "marked_processed": 0}

    pending = fetch_pending()
    stats["fetched"] = len(pending)
    if not pending:
        log.info("No pending new-retailer URLs.")
        return stats

    # Group by hostname.
    groups: Dict[str, Dict] = {}
    by_id: List[int] = []
    for row in pending:
        host = (row.get("hostname") or "").lower().strip()
        url = (row.get("url") or "").strip()
        if not host or not url:
            continue
        key = _derive_retailer_key(host)
        display = _derive_display_name(host)
        g = groups.setdefault(key, {"display": display, "urls": []})
        if url not in g["urls"]:
            g["urls"].append(url)
        by_id.append(int(row["id"]))

    stats["groups"] = len(groups)

    if dry_run:
        for key, info in groups.items():
            log.info("[dry-run] %s | %s (%d URLs)", info["display"], key, len(info["urls"]))
            for u in info["urls"]:
                log.info("    %s", u)
        return stats

    appended = append_to_queue(groups)
    stats["urls_appended"] = appended
    log.info("Appended %d URL(s) across %d retailer group(s) to %s",
             appended, len(groups), QUEUE_FILE.name)

    if by_id:
        stats["marked_processed"] = mark_processed(by_id)
        log.info("Marked %d row(s) as processed", stats["marked_processed"])

    return stats


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        stats = sync(dry_run=args.dry_run)
    except requests.RequestException as e:
        log.error("API error: %s", e)
        return 1
    except Exception as e:
        log.exception("Unexpected error: %s", e)
        return 2
    log.info("=" * 60)
    for k, v in stats.items():
        log.info("  %-20s %d", k, v)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
