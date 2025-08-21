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
        
        # Check for token exhaustion or quota exceeded
        if r.status_code == 402:  # Payment Required - usually means quota exceeded
            raise RuntimeError("TOKENS_EXHAUSTED")
        elif r.status_code == 429:  # Too Many Requests - rate limit/quota
            raise RuntimeError("TOKENS_EXHAUSTED")
        elif r.status_code == 403:  # Forbidden - could be invalid API key or no tokens
            response_text = r.text.lower()
            if any(phrase in response_text for phrase in ["quota", "token", "limit", "exceeded", "insufficient"]):
                raise RuntimeError("TOKENS_EXHAUSTED")
        
        r.raise_for_status()
        data = r.json()  # Return raw data from TRIGEN API
        
        # Check if the response indicates no tokens/quota in the data
        if isinstance(data, dict):
            error_msg = data.get("error", "").lower()
            message = data.get("message", "").lower()
            if any(phrase in error_msg or phrase in message for phrase in ["quota", "token", "limit", "exceeded", "insufficient", "balance"]):
                raise RuntimeError("TOKENS_EXHAUSTED")

    # Return the complete data from TRIGEN API
    return data
