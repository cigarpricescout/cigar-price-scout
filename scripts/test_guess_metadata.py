"""
Offline validation for /api/public/guess-metadata.

Replays the failure modes the user reported:
  Brand prefill "Arturo Fuente Cigars" (extra "Cigars" suffix)
  Line prefill "Hemingway Best" (truncated mid-vitola)

Plus a few catalog-edge cases (longest-match wins; no match returns
empty; vitola only attached when brand+line both match).

Pure Python — no FastAPI client or network needed.
"""
import os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DATABASE_URL', 'postgresql://stub')

from app.community_endpoints import _match_scraped_to_catalog, _get_catalog_match_index


def run(name, *, expected, **scrape):
    got = _match_scraped_to_catalog(**scrape)
    fail = []
    for k, v in expected.items():
        if got.get(k) != v:
            fail.append(f'{k}: expected {v!r}, got {got.get(k)!r}')
    flag = 'PASS' if not fail else 'FAIL'
    print(f'  [{flag}] {name}')
    if fail:
        print(f'         got={got}')
        for line in fail:
            print(f'         - {line}')
    return not fail


results = []
print('=' * 78)
print('GUESS-METADATA MATCHER VALIDATION')
print('=' * 78)

print('\n[A] User-reported failures (brand suffix + line truncation)')
results.append(run(
    'Shopify-style title with brand suffix "Cigars" + vitola in title',
    title='Arturo Fuente Hemingway Best Seller Maduro Cigar Box of 25',
    jsonld_brand='Arturo Fuente Cigars',
    expected={'brand': 'Arturo Fuente', 'line': 'Hemingway', 'vitola': 'Best Seller'},
))
results.append(run(
    'JSON-LD brand has trailing "Cigars" — must not leak into brand',
    title='Hemingway Short Story Natural',
    jsonld_brand='Arturo Fuente Cigars',
    expected={'brand': 'Arturo Fuente', 'line': 'Hemingway', 'vitola': 'Short Story'},
))

print('\n[B] Longest-match wins (specificity)')
results.append(run(
    'Multi-word brand "Hoyo de Monterrey" not collapsed to "Monterrey"',
    title='Hoyo de Monterrey Excalibur No.1 Maduro',
    expected={'brand': 'Hoyo de Monterrey'},
))
results.append(run(
    'Multi-word brand "La Flor Dominicana" wins over partial',
    title='La Flor Dominicana Andalusian Bull box',
    expected={'brand': 'La Flor Dominicana'},
))

print('\n[C] Line match: "Hemingway Best" must resolve to "Hemingway"')
results.append(run(
    'Line "Hemingway" wins even though title contains "Best Seller" too',
    title='Arturo Fuente Hemingway Best Seller Cigar',
    expected={'brand': 'Arturo Fuente', 'line': 'Hemingway', 'vitola': 'Best Seller'},
))
results.append(run(
    'Padron 1964 Anniversary Diplomatico — multi-word line "1964 Anniversary"',
    title='Padron 1964 Anniversary Diplomatico Maduro Cigar Box',
    expected={'brand': 'Padron', 'line': '1964 Anniversary'},
))

print('\n[D] Empty fields when catalog has no match (no junk leakage)')
results.append(run(
    'Brand not in catalog -> all empty (no fallback split)',
    title='Davidoff Aniversario No.3 Cigar Box of 10',
    expected={'brand': '', 'line': '', 'vitola': ''},
))
results.append(run(
    'Total junk -> all empty',
    title='Some Page Title With Nothing Relevant',
    expected={'brand': '', 'line': '', 'vitola': ''},
))
results.append(run(
    'Empty inputs -> empty output',
    title='', jsonld_brand='', jsonld_name='',
    expected={'brand': '', 'line': '', 'vitola': ''},
))

print('\n[E] Tokens with punctuation / casing')
results.append(run(
    'Lowercased + apostrophe-stripped title still matches catalog',
    title='ARTURO FUENTE\'s HEMINGWAY short-story (Natural)',
    expected={'brand': 'Arturo Fuente', 'line': 'Hemingway', 'vitola': 'Short Story'},
))
results.append(run(
    'JSON-LD name only (no title)',
    title='', jsonld_name='Padron 1926 No. 6 Maduro Belicoso',
    expected={'brand': 'Padron'},
))

print('\n[F] Vitola only attached when brand+line both match')
results.append(run(
    'Brand match but no line -> vitola must be empty',
    title='Arturo Fuente Best Seller Cigar',
    expected={'brand': 'Arturo Fuente', 'line': '', 'vitola': ''},
))

print('\n[G] Catalog completeness (smoke check the cache)')
idx = _get_catalog_match_index()
brands = idx['brands_sorted']
ok = 'Arturo Fuente' in brands and 'Padron' in brands and len(brands) >= 20
print(f'  [{"PASS" if ok else "FAIL"}] catalog brands_sorted has Arturo Fuente, Padron, >=20 brands ({len(brands)} total)')
results.append(ok)

af_lines = idx['lines_by_brand'].get('Arturo Fuente', [])
ok = 'Hemingway' in af_lines and 'Opus X' in af_lines
print(f'  [{"PASS" if ok else "FAIL"}] Arturo Fuente lines include Hemingway + Opus X')
results.append(ok)

af_hem_vitolas = idx['vitolas_by_brand_line'].get('Arturo Fuente|Hemingway', [])
ok = 'Best Seller' in af_hem_vitolas and 'Short Story' in af_hem_vitolas
print(f'  [{"PASS" if ok else "FAIL"}] Hemingway vitolas include Best Seller + Short Story ({len(af_hem_vitolas)} total)')
results.append(ok)

print('\n[H] Consumer cascade facets (box counts + wrapper buckets from master)')
key = "Alec Bradley|Black Market Esteli|Gordo"
boxes = idx.get("boxes_by_brand_line_vitola", {}).get(key) or []
ok = isinstance(boxes, list) and len(boxes) >= 2 and 20 in boxes
print(f'  [{"PASS" if ok else "FAIL"}] {key} has multiple catalog box sizes (got {boxes})')
results.append(ok)
buckets = idx.get("buckets_by_brand_line_vitola", {}).get(key) or []
ok = isinstance(buckets, list) and "Sun Grown" in buckets
print(f'  [{"PASS" if ok else "FAIL"}] {key} wrapper buckets include Sun Grown (NIC) (got {buckets})')
results.append(ok)
abn = idx.get("all_bucket_names") or []
ok = len(abn) == 4
print(f'  [{"PASS" if ok else "FAIL"}] all_bucket_names has four consumer buckets')
results.append(ok)

print('\n[I] Brand+line wrapper facets then vitolas by bucket')
bl = "Alec Bradley|Black Market Esteli"
bb = idx.get("buckets_by_brand_line", {}).get(bl) or []
ok = "Sun Grown" in bb
print(f'  [{"PASS" if ok else "FAIL"}] buckets_by_brand_line includes Sun Grown (got {bb})')
results.append(ok)
vb = idx.get("vitolas_by_brand_line_bucket", {}).get(bl + "|Sun Grown") or []
ok = "Gordo" in vb
print(f'  [{"PASS" if ok else "FAIL"}] vitolas_by_brand_line_bucket Sun Grown includes Gordo (got {vb})')
results.append(ok)

print('\n[J] Per-vitola catalog wrapper labels (consumer extension)')
opus_key = "Arturo Fuente|Opus X|PerfecXion No. 4"
rows = idx.get("wrapper_catalog_rows_by_blv", {}).get(opus_key) or []
lab0 = (rows[0].get("label") or "") if rows else ""
ok = (
    isinstance(rows, list) and len(rows) >= 1
    and rows[0].get("bucket") == "Maduro"
    and "Dominican Rosado" in lab0
    and "code" in rows[0]
)
print(f'  [{"PASS" if ok else "FAIL"}] {opus_key} has wrapper_catalog row(s) with bucket+code (got {rows})')
results.append(ok)

print()
print('=' * 78)
total = len(results)
passed = sum(results)
print(f'{passed}/{total} cases passed')
print('=' * 78)
if passed < total:
    raise SystemExit(1)
