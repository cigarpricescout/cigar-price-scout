import os, csv, argparse
from collections import defaultdict, Counter
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
try:
    from serpapi import GoogleSearch
except ImportError:
    raise SystemExit("pip install google-search-results")

RETAILER_ALLOW_HINTS = ["/product","/products","/collections","/shop","/cigars","/item","/p/","/buy","/cart","/category","/brand","/store","/sku","/box","/boxes"]
NON_RETAILER_DOMAIN_DENY = {"cigaraficionado.com","halfwheel.com","reddit.com","youtube.com","facebook.com","instagram.com","pinterest.com","x.com","twitter.com","tiktok.com","wikipedia.org","quora.com","ask.com","famous-smoke.com/blog"}
KNOWN_RETAILERS = {"gothamcigars.com","famous-smoke.com","jrcigars.com","cigarsinternational.com","cigar.com","atlanticcigar.com","neptunecigar.com","holts.com","mikescigars.com","absolutecigars.com","bestcigarprices.com","cigarplace.biz","cigarscity.com","cigarking.com","lmcigars.com","gttobacco.com","cigarwarehouseusa.com","nickscigarworld.com","niceashcigars.com","dramfellows.com","cigarsncigars.com","finckcigarcompany.com","cigarcountry.com","cigars.com","smokeinn.com","bnbtobacco.com","cigarpage.com","cigora.com","thompsoncigar.com","cigarsdirect.com","cigarsdaily.com"}

def normalize_domain(url):
    try:
        d = urlparse(url).netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except:
        return ""

def is_non_retailer(url):
    d = normalize_domain(url)
    return any(d.endswith(b) or b in d for b in NON_RETAILER_DOMAIN_DENY)

def looks_like_retail(url):
    d = normalize_domain(url)
    if d in KNOWN_RETAILERS: return True
    if is_non_retailer(url): return False
    path = urlparse(url).path.lower()
    if any(h in path for h in RETAILER_ALLOW_HINTS): return True
    if "cigar" in d and not any(x in d for x in ["journal","aficionado","dojo","blog"]): return True
    return False

def clean_url(url):
    try:
        p = urlparse(url); q = parse_qs(p.query)
        drop = {"utm_source","utm_medium","utm_campaign","utm_content","utm_term","gclid","fbclid","cjevent","cjdata","srsltid"}
        q = {k:v for k,v in q.items() if k not in drop}
        return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q,doseq=True),""))
    except: return url

def parse_serp_results(d):
    urls=[]
    for k in ["organic_results","shopping_results","top_stories"]:
        for it in d.get(k, []):
            url = it.get("link") or it.get("source")
            if url: urls.append(url)
    return urls

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--results-per-query", type=int, default=50)
    ap.add_argument("--max-results", type=int, default=100)
    ap.add_argument("--output-prefix", default="cpsc_out")
    args = ap.parse_args()

    key = os.environ.get("SERPAPI_KEY")
    if not key: raise SystemExit("ERROR: Please set SERPAPI_KEY")

    cigars=[]
    with open(args.input, newline="", encoding="utf-8") as f:
        rd=csv.DictReader(f)
        for r in rd:
            if not r.get("product_name"): continue
            if not r.get("query"):
                base=" ".join([r.get("product_name",""), r.get("brand",""), r.get("line",""), r.get("vitola","")]).strip()
                r["query"]=f"{base} box 20 25 price buy"
            cigars.append(r)

    matrix_header=["retailer_domain"]+[c["product_name"] for c in cigars]
    rank_matrix=defaultdict(lambda:{c["product_name"]:"" for c in cigars})
    per_cigar_top=[]
    from collections import defaultdict as _dd

    for c in cigars:
        q=c["query"]
        res=GoogleSearch({"engine":"google","q":q,"num":min(args.results_per_query,100),"api_key":key,"hl":"en","gl":"us"}).get_dict()
        urls=parse_serp_results(res)
        seen=set(); ranked=[]
        for u in urls:
            cu=clean_url(u)
            if cu in seen: continue
            seen.add(cu); ranked.append(cu)
            if len(ranked)>=args.max_results: break
        first_rank={}; example={}
        for i,u in enumerate(ranked, start=1):
            if is_non_retailer(u): continue
            if not looks_like_retail(u): continue
            d=normalize_domain(u)
            if d and d not in first_rank:
                first_rank[d]=i; example[d]=u
        for d,r in first_rank.items():
            rank_matrix[d][c["product_name"]]=r
            per_cigar_top.append({"product_name":c["product_name"],"query":q,"rank":r,"retailer_domain":d,"example_url":example[d]})

    # write matrix
    out_matrix=f"{args.output_prefix}_retailer_rank_matrix.csv"
    with open(out_matrix, "w", newline="", encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(matrix_header)
        for d,row in sorted(rank_matrix.items(), key=lambda kv: kv[0]):
            w.writerow([d]+[row.get(p,"") for p in matrix_header[1:]])

    # write per-cigar
    out_per=f"{args.output_prefix}_per_cigar_top.csv"
    with open(out_per, "w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["product_name","query","rank","retailer_domain","example_url"])
        w.writeheader(); w.writerows(sorted(per_cigar_top, key=lambda x:(x["product_name"], x["rank"])))

    # write summary
    vis=[]
    for d,row in rank_matrix.items():
        score=0.0; cov=0
        for v in row.values():
            if isinstance(v,int) or (isinstance(v,str) and v.isdigit()):
                r=int(v)
                if r>0: score+=1.0/r; cov+=1
        vis.append((d,cov,round(score,4)))
    vis.sort(key=lambda x:(-x[2], -x[1], x[0]))
    out_sum=f"{args.output_prefix}_retailer_summary.csv"
    with open(out_sum,"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["retailer_domain","coverage_count","visibility_score"]); w.writerows(vis)

if __name__=="__main__": main()
