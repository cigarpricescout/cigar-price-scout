"""
Add 10 new Padron CIDs (5 cigars x 2 wrappers) to all retailer CSVs.
Only adds the cigar_id column; all other fields left blank for the user to fill URLs.
Skips any CID that already exists in a given CSV.
"""

import csv
import os
import glob

CSV_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'data')

NEW_CIDS = [
    'PADRON|PADRON|1926SERIE|NO.6|NO.6|4.75x50|MAD|BOX24',
    'PADRON|PADRON|1926SERIE|NO.6|NO.6|4.75x50|NAT|BOX24',
    'PADRON|PADRON|1926SERIE|NO.2BELICOSO|NO.2BELICOSO|5.25x52|MAD|BOX24',
    'PADRON|PADRON|1926SERIE|NO.2BELICOSO|NO.2BELICOSO|5.25x52|NAT|BOX24',
    'PADRON|PADRON|1964ANNIVERSARY|TORPEDO|TORPEDO|6x52|MAD|BOX20',
    'PADRON|PADRON|1964ANNIVERSARY|TORPEDO|TORPEDO|6x52|NAT|BOX20',
    'PADRON|PADRON|1964ANNIVERSARY|IMPERIAL|IMPERIAL|6x54|MAD|BOX25',
    'PADRON|PADRON|1964ANNIVERSARY|IMPERIAL|IMPERIAL|6x54|NAT|BOX25',
    'PADRON|PADRON|1964ANNIVERSARY|MONARCA|MONARCA|6.5x46|MAD|BOX25',
    'PADRON|PADRON|1964ANNIVERSARY|MONARCA|MONARCA|6.5x46|NAT|BOX25',
]


def add_cids_to_csv(filepath):
    """Add new CIDs to a single retailer CSV. Returns count of CIDs added."""
    fname = os.path.basename(filepath)

    # Read existing data
    with open(filepath, 'r', encoding='utf-8', errors='replace', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        existing_rows = list(reader)

    if not headers or 'cigar_id' not in headers:
        print(f"  SKIP {fname}: no cigar_id column found")
        return 0

    # Collect existing CIDs
    existing_cids = {row.get('cigar_id', '').strip() for row in existing_rows}

    # Add new CIDs that don't already exist
    added = 0
    for cid in NEW_CIDS:
        if cid in existing_cids:
            continue

        new_row = {h: '' for h in headers}
        new_row['cigar_id'] = cid
        existing_rows.append(new_row)
        added += 1

    if added == 0:
        print(f"  SKIP {fname}: all 10 CIDs already present")
        return 0

    # Write back
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(existing_rows)

    print(f"  OK   {fname}: added {added} CIDs")
    return added


def main():
    csv_files = sorted(glob.glob(os.path.join(CSV_DIR, '*.csv')))
    csv_files = [f for f in csv_files if '_backup_' not in os.path.basename(f)]

    print(f"Adding 10 Padron CIDs to {len(csv_files)} retailer CSVs\n")

    total_added = 0
    files_modified = 0
    for fpath in csv_files:
        added = add_cids_to_csv(fpath)
        total_added += added
        if added > 0:
            files_modified += 1

    print(f"\n=== Summary ===")
    print(f"  Files modified: {files_modified}")
    print(f"  Total CID rows added: {total_added}")
    print(f"  Average per file: {total_added / files_modified:.1f}" if files_modified else "")


if __name__ == '__main__':
    main()
