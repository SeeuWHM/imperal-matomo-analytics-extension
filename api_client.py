"""HTTP client - calls our Marketing OS server.

Server URL and API key are baked-in constants (app.py). Only the user's
Matomo credentials live in ctx.store.
"""
from __future__ import annotations

from app import SERVER_URL, SERVER_API_KEY, load_settings, matomo_ready

TIMEOUT = 30
HEAVY_TIMEOUT = 90  # full-report, daily-report: MOS runs 22 parallel Matomo calls


def _normalize_backend_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


async def call_mos(ctx, endpoint: str, extra: dict | None = None, timeout: int = TIMEOUT) -> dict:
    """POST to the MOS server. Auto-injects the user's Matomo creds."""
    s = await load_settings(ctx)

    if not matomo_ready(s):
        return {"error": "Matomo not configured - open Settings and add your URL + Auth Token.",
                "_config": True}

    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return {"error": "Analytics backend URL is not configured.", "_config": True}

    payload = {
        "matomo_url":        s["matomo_url"],
        "token":             s["matomo_token"],
        "site_id":           int(s.get("matomo_site_id", 1) or 1),
        "segment":           (s.get("matomo_segment") or None),
        "utm_source_dim_id": int(s.get("utm_source_dim_id") or 0),
        **(extra or {}),
    }

    resp = await ctx.http.post(
        f"{base_url}{endpoint}",
        json=payload,
        headers={"X-API-Key": SERVER_API_KEY},
        timeout=timeout,
    )
    if not resp.ok:
        try:
            body = resp.text()[:200]
        except Exception:
            body = ""
        return {"error": f"server returned {resp.status_code}: {body}"}
    return resp.json()
