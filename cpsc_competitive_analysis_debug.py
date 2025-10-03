import os, csv, argparse, traceback
from collections import defaultdict
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

print("=== CPSC Competitive Analysis (DEBUG MODE) ===")

try:
    from serpapi import GoogleSearch
    print("[OK] serpapi client imported")
except Exception as e:
    print("[ERROR] serpapi import failed:", e)
    print("Try: pip install google-search-results")
    raise

def normalize_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""

NON_RETAILER_DOMAIN_DENY = {
    "cigaraficionado.com","halfwheel.com","reddit.com","youtube.com","facebook.com","instagram.com",
    "pinterest.com","x.com","twitter.com","tiktok.com","wikipedia.org","quora.com","ask.com",
}
RETAILER_ALLOW_HINTS = ["/product","/products","/collections","/shop","/cigars","/item","/p/","/buy","/category","/box","/boxes"]
KNOWN_RETAILERS = {"gothamcigars.com","famous-smoke.com","jrcigars.com","cigarsinternational.com","cigar.com","atlanticcigar.com","neptunecigar.com","holts.com"}

def is_non_retailer(url: str) -> bool:
    d = normalize_domain(url)
    return any(d.endswith(bad) or bad in d for bad in NON_RETAILER_DOMAIN_DENY)

def looks_like_retail(url: str) -> bool:
    d = normalize_domain(url)
    if d in KNOWN_RETAILERS: return True
    if is_non_retailer(url): return False
    path = urlparse(url).path.lower()
    if any(h in path for h in RETAILER_ALLOW_HINTS): return True
    if "cigar" in d and not any(x in d for x in ["journal","aficionado","dojo","blog"]): return True
    return False

def clean_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        drop = {"utm_source","utm_medium","utm_campaign","utm_content","utm_term","gclid","fbclid","cjevent","cjdata","srsltid"}
        q = {k:v for k,v in q.items() if k not in drop}
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(q, doseq=True), ""))
    except Exception:
        return url

def parse_serp_results(d):
    urls = []
    for key in ["organic_results","shopping_results","top_stories"]:
        items = d.get(key, [])
        for it in items:
            url = it.get("link") or it.get("source")
            if url: urls.append(url)
    return urls

def main():
    print("[STEP] parse args")
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--results-per-query", type=int, default=50)
    ap.add_argument("--max-results", type=int, default=100)
    ap.add_argument("--output-prefix", default="cpsc_out")
    args = ap.parse_args()

    key = os.environ.get("SERPAPI_KEY")
    print("[INFO] SERPAPI_KEY present?", bool(key))
    if not key:
        print("[FATAL] SERPAPI_KEY not set"); return

    print(f"[STEP] load input CSV: {args.input}")
    rows = []
    with open(args.input, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            if not r.get("product_name"): continue
            if not r.get("query"):
                base = " ".join([r.get("product_name",""), r.get("brand",""), r.get("line",""), r.get("vitola","")]).strip()
                r["query"] = f"{base} box 20 25 price buy"
            rows.append(r)
    print(f"[OK] loaded {len(rows)} rows")

    matrix_header = ["retailer_domain"] + [r["product_name"] for r in rows]
    rank_matrix = defaultdict(lambda: {r["product_name"]: "" for r in rows})
    per_cigar = []

    for idx, r in enumerate(rows, start=1):
        q = r["query"]
        print(f"[QUERY {idx}/{len(rows)}] {q}")
        try:
            params = {"engine":"google","q":q,"num":min(args.results_per_query,100),"api_key":key,"hl":"en","gl":"us"}
            res = GoogleSearch(params).get_dict()
            print("[INFO] got SERP keys:", list(res.keys())[:5])
            urls = parse_serp_results(res)
            print(f"[INFO] raw urls: {len(urls)}")
            seen, ranked = set(), []
            for u in urls:
                cu = clean_url(u)
                if cu in seen: continue
                seen.add(cu); ranked.append(cu)
                if len(ranked) >= args.max_results: break

            first_rank = {}
            example = {}
            for rank, u in enumerate(ranked, start=1):
                if is_non_retailer(u): continue
                if not looks_like_retail(u): continue
                dom = normalize_domain(u)
                if dom and dom not in first_rank:
                    first_rank[dom] = rank
                    example[dom] = u

            print(f"[INFO] retailers found: {len(first_rank)}")
            for dom, rr in first_rank.items():
                rank_matrix[dom][r['product_name']] = rr
                per_cigar.append({"product_name": r["product_name"], "query": q, "rank": rr, "retailer_domain": dom, "example_url": example[dom]})
        except Exception as e:
            print("[ERROR] query failed:", e)
            traceback.print_exc()

    out_matrix = f"{args.output_prefix}_retailer_rank_matrix.csv"
    print(f"[WRITE] {out_matrix}")
    with open(out_matrix, "w", newline="", encoding="utf-8") as f:
        import csv as _csv
        w = _csv.writer(f); w.writerow(matrix_header)
        for dom, row in sorted(rank_matrix.items(), key=lambda kv: kv[0]):
            w.writerow([dom] + [row.get(p,"") for p in matrix_header[1:]])

    out_per = f"{args.output_prefix}_per_cigar_top.csv"
    print(f"[WRITE] {out_per}")
    with open(out_per, "w", newline="", encoding="utf-8") as f:
        import csv as _csv
        w = _csv.DictWriter(f, fieldnames=["product_name","query","rank","retailer_domain","example_url"])
        w.writeheader(); w.writerows(sorted(per_cigar, key=lambda x: (x["product_name"], x["rank"])))

    print("[DONE]")

if __name__ == "__main__":
    main()
