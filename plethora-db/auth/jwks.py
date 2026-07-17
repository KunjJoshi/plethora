import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL_REST", "")

_cache: dict = {"keys": [], "fetched_at": 0.0}
_TTL = 3600.0  # re-fetch public keys every hour


def _fetch_jwks() -> list[dict]:
    url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"JWKS endpoint returned {e.response.status_code}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach JWKS endpoint: {e}")
    return response.json().get("keys", [])


def get_jwks() -> list[dict]:
    now = time.monotonic()
    if _cache["keys"] and now - _cache["fetched_at"] < _TTL:
        return _cache["keys"]

    try:
        keys = _fetch_jwks()
    except RuntimeError:
        if _cache["keys"]:
            return _cache["keys"]   # serve stale keys on transient network error
        raise

    _cache["keys"] = keys
    _cache["fetched_at"] = now
    return keys


def get_key_for_kid(kid: str) -> dict | None:
    """Return the JWK whose 'kid' matches, triggering a cache refresh if not found."""
    for key in get_jwks():
        if key.get("kid") == kid:
            return key

    # Not found — Supabase may have rotated keys; force a refresh and retry once.
    _cache["fetched_at"] = 0.0
    for key in get_jwks():
        if key.get("kid") == kid:
            return key

    return None
