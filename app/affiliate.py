import os
from urllib.parse import quote_plus

CJ_PID = os.getenv("CJ_PID")  # set these in Replit Secrets later
CJ_AID = os.getenv("CJ_AID")

def cj_deeplink(merchant_url: str, sid: str | None = None) -> str:
    if not (CJ_PID and CJ_AID):
        return merchant_url  # pass-through until you set secrets
    base = f"https://www.anrdoezrs.net/click-{CJ_PID}-{CJ_AID}?url={quote_plus(merchant_url)}"
    return base + (f"&sid={quote_plus(sid)}" if sid else "")
