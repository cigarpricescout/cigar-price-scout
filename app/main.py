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
    n = normalize_query(q, KNOWN_BRANDS)
    listings = load_all_listings()

    if n.brand and not n.line:
        results = cheapest_by_line(listings, n.brand, state)
        return SearchOut(intent="brand", brand=n.brand, results=results)
    if n.brand and n.line and not n.size:
        results = sizes_cheapest(listings, n.brand, n.line, state)
        return SearchOut(intent="line", brand=n.brand, line=n.line, results=results)
    if n.brand and n.line and n.size:
        offs = offers_for_sku(listings, n.brand, n.line, n.size, state)
        sid = make_sid(n.brand, n.line, n.size)
        for o in offs: o["url"] = cj_deeplink(o["url"], sid=sid)
        if offs:
            cheapest = offs[0]
            session.add(Event(event_type="CLICK_LIST", brand=n.brand, line=n.line, size=n.size, retailer=cheapest["retailer"], state=state, delivered_cents=cheapest["delivered_cents"]))
            today = date.today().isoformat()
            await session.execute(PricePoint.__table__.delete().where((PricePoint.day==today)&(PricePoint.brand==n.brand)&(PricePoint.line==n.line)&(PricePoint.size==n.size)&(PricePoint.source=="cheapest")))
            session.add(PricePoint(day=today, brand=n.brand, line=n.line, size=n.size, delivered_cents=cheapest["delivered_cents"], source="cheapest"))
            await session.commit()
        results = [{"retailer": o["retailer"], "base": f"${o['base_cents']/100:.2f}", "shipping": "est", "tax": "est", "delivered": f"${o['delivered_cents']/100:.2f}", "url": o["url"], "cheapest": (i==0)} for i,o in enumerate(offs)]
        return SearchOut(intent="sku", brand=n.brand, line=n.line, size=n.size, results=results)

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