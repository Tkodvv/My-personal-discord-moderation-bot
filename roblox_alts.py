# roblox_alts.py
import os, httpx, logging
log = logging.getLogger(__name__)

API_KEY  = os.getenv("TRIGEN_API_KEY")
API_BASE = (os.getenv("TRIGEN_BASE", "https://trigen.io") or "").rstrip("/")
ENDPOINT = os.getenv("TRIGEN_ALT_ENDPOINT", "/api/alt/generate")

_SENSITIVE = {"password","pass","pwd","token","roblosecurity",".roblosecurity",
              "cookie","session","otp","2fa","auth","secret","email"}

def _sanitize(x):
    if isinstance(x, dict):
        return {k: ("[redacted]" if k.lower() in _SENSITIVE else _sanitize(v)) for k, v in x.items()}
    if isinstance(x, list):
        return [_sanitize(v) for v in x]
    return x

async def get_alt_public():
    if not API_KEY:
        raise RuntimeError("TRIGEN_API_KEY missing")
    url = f"{API_BASE}{ENDPOINT}"
    headers = {"x-api-key": API_KEY, "Accept": "application/json", "User-Agent": "ModBot/1.0"}

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers)  # Use GET instead of POST (fixes 405 error)
        r.raise_for_status()
        data = r.json()  # Return raw data from TRIGEN API

    # Return the complete data from TRIGEN API
    return data
