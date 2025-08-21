import os, base64
from datetime import datetime, timedelta, date
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from .db import get_session, init_db, Event, PricePoint
from .normalize import normalize_query
from .affiliate import cj_deeplink
from .shipping_tax import delivered_cents, zip_to_state
from .adapters.csv_adapter import load_csv
import re
from datetime import date

def _canon(s: str) -> str:
    return (s or "").strip().lower()

def _tok(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))

def _size_from_text(s: str) -> str | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[xX]\s*(\d+)", s or "")
    return f"{m.group(1)}x{m.group(2)}" if m else None

def _line_matches(requested: str | None, actual: str | None) -> bool:
    if not requested or not actual:
        return False
    r, a = _canon(requested), _canon(actual)
    return (r in a) or (a in r)

def _best_titles(q: str, products, brand: str | None = None):
    qtok = _tok(q)
    rows = []
    for p in products:
        if brand and _canon(p.brand) != _canon(brand):
            continue
        ttok = _tok(p.title)
        overlap = len(qtok & ttok)
        if overlap == 0:
            continue
        size_bonus = 1 if (p.size and p.size.replace("x","") in "".join(qtok)) else 0
        line_bonus = 1 if any(t in _canon(p.line) for t in qtok) else 0
        rows.append( (overlap + size_bonus + line_bonus, p) )
    rows.sort(key=lambda t: t[0], reverse=True)
    return [p for _,p in rows]

def _sid(brand, line, size) -> str:
    return "-".join([x for x in [brand, line, size] if x]).replace(" ", "_")[:100]

SITE_NAME = os.environ.get("SITE_NAME", "CigarPriceScout")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

app = FastAPI(title=SITE_NAME)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

RETAILERS = [
    ("famous", "Famous Smoke Shop", "static/data/famous.csv"),
    ("ci", "Cigars International", "static/data/ci.csv"),
    ("jr", "JR Cigar", "static/data/jr.csv"),
]

KNOWN_BRANDS = ["Arturo Fuente"]  # expand later

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}

class SearchOut(BaseModel):
    intent: str
    brand: str | None = None
    line: str | None = None
    size: str | None = None
    results: list[dict] = []

def make_sid(brand, line, size):
    return "-".join([x for x in [brand, line, size] if x]).replace(" ", "_")[:100]

def load_all_listings():
    listings = []
    for key, name, path in RETAILERS:
        listings.extend(load_csv(path, key, name))
    return listings

def cheapest_by_line(listings, brand, state):
    out = {}
    for L in listings:
        if L.brand != brand: continue
        d = delivered_cents(L.base_cents, L.retailer_key, state)
        cur = out.get(L.line)
        if (cur is None) or (d < cur["delivered_cents"]):
            out[L.line] = {"line": L.line, "retailer": L.retailer_name, "delivered_cents": d, "url": L.url, "retailer_key": L.retailer_key, "base_cents": L.base_cents}
    return [{"line": v["line"], "cheapest_delivered": f"${v['delivered_cents']/100:.2f}", "url": v["url"]} for v in out.values()]

def sizes_cheapest(listings, brand, line, state):
    out = {}
    for L in listings:
        if L.brand != brand or L.line != line: continue
        d = delivered_cents(L.base_cents, L.retailer_key, state)
        cur = out.get(L.size)
        if (cur is None) or (d < cur["delivered_cents"]):
            out[L.size] = {"size": L.size, "delivered_cents": d}
    return [{"size": s, "cheapest_delivered": f"${v['delivered_cents']/100:.2f}"} for s,v in sorted(out.items())]

def offers_for_sku(listings, brand, line, size, state):
    out = []
    for L in listings:
        if L.brand == brand and L.line == line and L.size == size and L.in_stock:
            d = delivered_cents(L.base_cents, L.retailer_key, state)
            out.append({"retailer": L.retailer_name, "retailer_key": L.retailer_key, "base_cents": L.base_cents, "delivered_cents": d, "url": L.url})
    out.sort(key=lambda x: x["delivered_cents"])
    return out

@app.get("/search", response_model=SearchOut)
async def search(q: str, zip: str | None = None, session=Depends(get_session)):
    state = zip_to_state(zip or "") or "OR"
    nq = normalize_query(q, KNOWN_BRANDS)
    all_products = load_all_listings()

    # Use brand list from data if normalize_query missed it
    if not nq.brand:
        # choose a brand whose tokens intersect the query
        qtok = _tok(q)
        by = {}
        for p in all_products:
            bt = _tok(p.brand)
            sc = len(qtok & bt)
            if sc:
                by[p.brand] = max(by.get(p.brand, 0), sc)
        if by:
            nq.brand = max(by.items(), key=lambda x: x[1])[0]

    # Pull size from free text if not detected
    if not nq.size:
        nq.size = _size_from_text(q)

    # If user typed extra words (e.g., "Hemingway Short Story"), pick the canonical line by best title match
    if nq.brand and nq.line:
        tops = _best_titles(q, all_products, brand=nq.brand)
        if tops:
            # choose the line that appears most among best titles
            from collections import Counter
            c = Counter(p.line for p in tops[:10])
            nq.line = c.most_common(1)[0][0]

    if nq.brand and not nq.line:
        intent = "brand"
        filtered = [p for p in all_products if _canon(p.brand) == _canon(nq.brand)]
        by_line = {}
        qtok = _tok(q)
        for p in filtered:
            d = delivered_cents(p.base_cents, p.retailer_key, state)
            rec = by_line.get(p.line)
            # relevance score by overlap with line/title
            rel = len(qtok & (_tok(p.line) | _tok(p.title)))
            if (rec is None) or (d < rec["delivered"]):
                by_line[p.line] = {"line": p.line, "delivered": d, "rel": rel}
            else:
                by_line[p.line]["rel"] = max(by_line[p.line]["rel"], rel)
        rows = list(by_line.values())
        rows.sort(key=lambda r: (-r["rel"], r["delivered"]))  # relevant first, then cheapest
        results = [{"line": r["line"], "cheapest_delivered": f"${r['delivered']/100:.2f}"} for r in rows]
        return {"intent": intent, "brand": nq.brand, "results": results}

    if nq.brand and nq.line and not nq.size:
        intent = "line"
        filtered = [p for p in all_products
                    if _canon(p.brand) == _canon(nq.brand) and _line_matches(nq.line, p.line)]
        by_size = {}
        for p in filtered:
            d = delivered_cents(p.base_cents, p.retailer_key, state)
            cur = by_size.get(p.size)
            if cur is None or d < cur:
                by_size[p.size] = d
        results = [{"size": s, "cheapest_delivered": f"${c/100:.2f}"} for s, c in sorted(by_size.items())]
        return {"intent": intent, "brand": nq.brand, "line": nq.line, "results": results}

    if nq.brand and nq.line and nq.size:
        intent = "sku"
        filtered = [p for p in all_products
                    if _canon(p.brand) == _canon(nq.brand)
                    and _line_matches(nq.line, p.line)
                    and _canon(p.size) == _canon(nq.size)
                    and p.in_stock]
        rows = []
        min_del = None
        for p in filtered:
            d = delivered_cents(p.base_cents, p.retailer_key, state)
            rows.append((p, d))
            min_del = d if (min_del is None or d < min_del) else min_del
        rows.sort(key=lambda t: t[1])

        results = [{
            "retailer": p.retailer_name,
            "base": f"${p.base_cents/100:.2f}",
            "shipping": f"${(d - p.base_cents)/100:.2f}",
            "tax": "$0.00",
            "delivered": f"${d/100:.2f}",
            "url": cj_deeplink(p.url, sid=_sid(nq.brand, nq.line, nq.size)),
            "cheapest": (d == min_del),
        } for (p, d) in rows]

        if min_del is not None:
            await session.execute(
                PricePoint.__table__.delete().where(
                    (PricePoint.day == date.today().isoformat()) &
                    (PricePoint.brand == nq.brand) &
                    (PricePoint.line == nq.line) &
                    (PricePoint.size == nq.size) &
                    (PricePoint.source == "cheapest")
                )
            )
            session.add(PricePoint(
                day=date.today().isoformat(),
                brand=nq.brand, line=nq.line, size=nq.size,
                delivered_cents=min_del, source="cheapest"
            ))
            await session.commit()

        return {"intent": intent, "brand": nq.brand, "line": nq.line, "size": nq.size, "results": results}

    return SearchOut(intent="help", results=[{"message":"Try a brand (e.g., Arturo Fuente) or include a line (e.g., Arturo Fuente Hemingway)."}])

class EventIn(BaseModel):
    event_type: str
    brand: str | None = None
    line: str | None = None
    size: str | None = None
    retailer: str | None = None
    state: str | None = None
    delivered_cents: int | None = None

@app.post("/event")
async def log_event(payload: EventIn, session=Depends(get_session)):
    session.add(Event(event_type=payload.event_type, brand=payload.brand, line=payload.line, size=payload.size, retailer=payload.retailer, state=payload.state, delivered_cents=payload.delivered_cents))
    await session.commit()
    return {"ok": True}

def check_basic_auth(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate":"Basic"})
    try:
        userpass = base64.b64decode(auth.split(" ",1)[1]).decode("utf-8"); u,p = userpass.split(":",1)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate":"Basic"})
    if not (u == ADMIN_USER and p == ADMIN_PASS):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate":"Basic"})

@app.get("/api/summary")
async def get_summary(request: Request, session=Depends(get_session)):
    check_basic_auth(request)
    since = datetime.utcnow() - timedelta(days=30)
    q1 = await session.execute(select(Event.brand, func.count()).where(Event.event_type=="CLICK_LIST", Event.ts >= since, Event.brand.isnot(None)).group_by(Event.brand).order_by(desc(func.count())).limit(10))
    top_brands = [{"brand": b or "Unknown", "clicks": c} for b,c in q1.all()]
    q2 = await session.execute(select(Event.size, func.count()).where(Event.event_type=="CLICK_LIST", Event.ts >= since, Event.size.isnot(None)).group_by(Event.size).order_by(desc(func.count())).limit(10))
    top_sizes = [{"size": s or "Unknown", "clicks": c} for s,c in q2.all()]
    q3 = await session.execute(select(Event.line, func.avg(Event.delivered_cents)).where(Event.event_type=="CLICK_LIST", Event.ts >= since, Event.delivered_cents.isnot(None), Event.line.isnot(None)).group_by(Event.line).order_by(desc(func.avg(Event.delivered_cents))).limit(10))
    prices = [{"line": ln or "Unknown", "avg_delivered": int(avg or 0)} for ln,avg in q3.all()]
    return {"since": since.isoformat(), "top_brands": top_brands, "top_sizes": top_sizes, "avg_delivered_by_line": prices}

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request, "site": SITE_NAME})

@app.get("/price_history")
async def price_history(brand: str, line: str, size: str, session=Depends(get_session)):
    rows = await session.execute(select(PricePoint.day, PricePoint.delivered_cents).where(PricePoint.brand==brand, PricePoint.line==line, PricePoint.size==size, PricePoint.source=="cheapest").order_by(PricePoint.day.asc()))
    pts = [{"day": d, "delivered_cents": v} for d,v in rows.all()]
    return {"points": pts}