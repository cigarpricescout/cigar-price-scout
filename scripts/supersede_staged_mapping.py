"""Find and supersede stuck pending extension_staged_approvals in production.

This is the operator's "kill switch" for a bad URL<->CID mapping that is
showing live on the site via the pending-approval overlay but is wrong (e.g.
a CID accidentally approved while sitting on a retailer's homepage, so the
comparison table links to the homepage with a junk price).

It talks to the SAME admin API the publisher uses:
  GET  /api/admin/pending-extension-approvals   (list pending rows)
  POST /api/admin/supersede-extension-staged    (retire rows by id)
  POST /api/admin/revoke-staged-url-mapping     (retire by retailer+url+cid;
                                                 can include a published row)

Auth + base URL come from the environment, identical to
tools/extension/publish_extension_approvals.py:
  ADMIN_SECRET_KEY      (required)
  EXTENSION_API_BASE    (optional; defaults to APP_BASE_URL, then prod)
  APP_BASE_URL          (optional fallback)

Usage (PowerShell):
  # 1) DRY RUN — see what matches (nothing is changed):
  $env:ADMIN_SECRET_KEY="<your key>"
  python scripts/supersede_staged_mapping.py --retailer bighumidor --search "mi amor"

  # 2) COMMIT — actually supersede the matched rows:
  python scripts/supersede_staged_mapping.py --retailer bighumidor --search "mi amor" --commit

  # Or target exact row ids printed by the dry run:
  python scripts/supersede_staged_mapping.py --id 1234 --id 1235 --commit

  # DIRECT RETIRE by url+cid (works even when the row is already PUBLISHED, so
  # it won't show up in the pending list above). Use --include-published only
  # after the matching CSV row has been removed from git:
  python scripts/supersede_staged_mapping.py \
      --retailer bighumidor \
      --url "https://www.bighumidor.com/index.cfm?ref2=3264" \
      --cid "LAAROMADECUBA|LAAROMADECUBA|MIAMOR|BELICOSO|BELICOSO|6.125x52|MEX|BOX25" \
      --include-published --commit

Exit codes:
  0 = success (including "nothing matched")
  1 = network / API / auth error
  2 = usage error
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List

try:
    import requests
except ImportError:  # pragma: no cover
    print("[ERROR] 'requests' is required. pip install requests")
    sys.exit(1)

DEFAULT_API_BASE = "https://cigarpricescout.com"


def _api_base() -> str:
    return (
        os.getenv("EXTENSION_API_BASE")
        or os.getenv("APP_BASE_URL")
        or DEFAULT_API_BASE
    ).rstrip("/")


def _admin_key() -> str:
    key = os.getenv("ADMIN_SECRET_KEY", "").strip()
    if not key:
        print("[ERROR] ADMIN_SECRET_KEY is not set in the environment.")
        sys.exit(1)
    return key


def fetch_pending(base: str, key: str) -> List[Dict]:
    r = requests.get(
        f"{base}/api/admin/pending-extension-approvals",
        headers={"X-Admin-Key": key},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("pending", [])


def supersede(base: str, key: str, ids: List[int]) -> int:
    r = requests.post(
        f"{base}/api/admin/supersede-extension-staged",
        headers={"X-Admin-Key": key},
        json={"ids": ids},
        timeout=30,
    )
    r.raise_for_status()
    return int(r.json().get("superseded", 0))


def revoke_url_mapping(
    base: str,
    key: str,
    retailer_key: str,
    url: str,
    cid: str,
    include_published: bool,
) -> int:
    r = requests.post(
        f"{base}/api/admin/revoke-staged-url-mapping",
        headers={"X-Admin-Key": key},
        json={
            "retailer_key": retailer_key,
            "url": url,
            "cid": cid,
            "include_published": include_published,
        },
        timeout=30,
    )
    if r.status_code == 404:
        # No matching row — surface the server's explanation, treat as "nothing to do".
        try:
            print(f"  {r.json().get('error', '404 — no matching row')}")
        except Exception:
            print("  404 — no matching row")
        return 0
    r.raise_for_status()
    return int(r.json().get("superseded", 0))


def _row_haystack(row: Dict) -> str:
    return " ".join(
        str(row.get(k) or "")
        for k in ("cid", "url", "brand", "line", "vitola", "title")
    ).lower()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--retailer", help="Only rows for this retailer_key (e.g. bighumidor).")
    ap.add_argument(
        "--search",
        help="Case-insensitive substring matched against cid/url/brand/line/vitola/title.",
    )
    ap.add_argument(
        "--id", type=int, action="append", default=[],
        help="Explicit staged-approval id(s) to supersede. Repeatable.",
    )
    ap.add_argument(
        "--url",
        help="Direct-retire mode: the exact URL to disassociate (requires --cid and --retailer).",
    )
    ap.add_argument(
        "--cid",
        help="Direct-retire mode: the exact CID to disassociate from --url.",
    )
    ap.add_argument(
        "--include-published",
        action="store_true",
        help=(
            "In direct-retire mode, also retire a leftover PUBLISHED record "
            "(use only after the matching CSV row has been removed from git)."
        ),
    )
    ap.add_argument("--commit", action="store_true", help="Actually supersede (default is dry run).")
    ap.add_argument("--base", help="Override API base URL.")
    args = ap.parse_args()

    direct_retire = bool(args.url or args.cid)
    if direct_retire and not (args.url and args.cid and args.retailer):
        print("[USAGE] Direct-retire mode needs --url, --cid, and --retailer together.")
        return 2
    if not (args.retailer or args.search or args.id):
        print("[USAGE] Provide at least one of --retailer, --search, or --id.")
        return 2

    base = (args.base or _api_base()).rstrip("/")
    key = _admin_key()
    print(f"API base: {base}")

    if direct_retire:
        scope = "pending + published" if args.include_published else "pending only"
        print("\nDirect retire (revoke-staged-url-mapping):")
        print(f"  retailer: {args.retailer}")
        print(f"  cid:      {args.cid}")
        print(f"  url:      {args.url}")
        print(f"  scope:    {scope}")
        if not args.commit:
            print("\nDRY RUN — nothing changed. Re-run with --commit to retire it.")
            return 0
        try:
            n = revoke_url_mapping(
                base, key, args.retailer.strip(), args.url.strip(),
                args.cid.strip(), args.include_published,
            )
        except Exception as e:
            print(f"[ERROR] revoke failed: {e}")
            return 1
        print(f"\nRetired {n} row(s). The live overlay refreshes on the next request.")
        if args.include_published:
            print(
                "Reminder: a published record only matters once its CSV row is "
                "already removed from git — double-check that the CSV no longer "
                "lists this URL."
            )
        return 0

    try:
        pending = fetch_pending(base, key)
    except requests.HTTPError as e:
        print(f"[ERROR] fetch failed: {e} — check ADMIN_SECRET_KEY / base URL.")
        return 1
    except Exception as e:
        print(f"[ERROR] fetch failed: {e}")
        return 1

    print(f"Fetched {len(pending)} pending approval(s).")

    if args.id:
        wanted = set(args.id)
        matches = [r for r in pending if int(r.get("id", -1)) in wanted]
    else:
        matches = pending
        if args.retailer:
            rk = args.retailer.strip().lower()
            matches = [r for r in matches if str(r.get("retailer_key") or "").lower() == rk]
        if args.search:
            needle = args.search.strip().lower()
            matches = [r for r in matches if needle in _row_haystack(r)]

    if not matches:
        print("No pending rows matched your filters. Nothing to do.")
        return 0

    print(f"\n{len(matches)} matching pending row(s):")
    print("-" * 78)
    for r in matches:
        print(f"  id={r.get('id')}  retailer={r.get('retailer_key')}")
        print(f"     cid:   {r.get('cid')}")
        print(f"     url:   {r.get('url')}")
        title = r.get("title")
        price = r.get("price")
        if title or price is not None:
            print(f"     title: {title!r}   price: {price}")
        print("-" * 78)

    ids = [int(r["id"]) for r in matches if r.get("id") is not None]

    if not args.commit:
        print(
            "\nDRY RUN — nothing changed. Re-run with --commit to supersede "
            f"the {len(ids)} row(s) above."
        )
        return 0

    try:
        n = supersede(base, key, ids)
    except Exception as e:
        print(f"[ERROR] supersede failed: {e}")
        return 1

    print(f"\nSuperseded {n} row(s). The live overlay refreshes on the next request.")
    print(
        "If any of these were already drained into a retailer CSV (status would "
        "have been 'published', not listed here), remove that CSV line in git too."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
