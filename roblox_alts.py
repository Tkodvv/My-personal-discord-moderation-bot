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
        r = await client.post(url, headers=headers)  # provider’s example shows POST
        r.raise_for_status()
        data = _sanitize(r.json())

    username     = data.get("username") or data.get("name") or data.get("user")
    display_name = data.get("displayName") or data.get("display_name") or username
    avatar_url   = data.get("avatarUrl")  or data.get("avatar_url")
    bio          = data.get("bio") or ""

    core = {"username","name","user","displayName","display_name","avatarUrl","avatar_url","bio"}
    meta = {k: v for k, v in data.items() if k not in core}
    return {"username": username, "displayName": display_name, "avatarUrl": avatar_url, "bio": bio, "meta": meta}
