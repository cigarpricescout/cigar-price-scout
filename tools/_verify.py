import csv

with open("tools/catalog_harvester_output/matches_20260414_115441.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# Cross-brand check
cross = []
for r in rows:
    brand = r.get("brand", "").lower()
    vendor = r.get("product_vendor", "").lower()
    title = r.get("product_title", "").lower()
    if brand and brand not in title and brand.replace(" ", "") not in vendor.replace(" ", ""):
        cross.append(r)

print(f"Total matches: {len(rows)}")
print(f"Cross-brand matches remaining: {len(cross)}")
for r in cross[:5]:
    print(f"  CID brand={r['brand']}  vendor={r['product_vendor']}  product={r['product_title']}")

# Serie cross-match check
print("\nOliva Serie cross-matches remaining:")
count = 0
for r in rows:
    if "OLIVA" in r["cid"] and "SERIE" in r["cid"]:
        cid_line = r["cid"].split("|")[2]
        title = r["product_title"]
        bad = False
        if "Serie V" in title and "SERIEV" not in cid_line: bad = True
        if "Serie G" in title and "SERIEG" not in cid_line: bad = True
        if "Serie O" in title and "SERIEO" not in cid_line: bad = True
        if bad:
            count += 1
            print(f"  CID: {cid_line} -> {title}")
print(f"  Total: {count}")
