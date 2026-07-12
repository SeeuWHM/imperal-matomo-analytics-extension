"""HTTP client - calls the user's configured analytics backend.

Both backend connection details and Matomo credentials live in per-user
settings, so every install can point at its own bridge/API server.
"""
from __future__ import annotations

from app import load_settings, matomo_ready

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
        return {
            "error": "Analytics backend and Matomo connection are not fully configured - open Settings and add backend URL/API key plus Matomo URL/Auth Token.",
            "_config": True,
        }

    base_url = _normalize_backend_url(s.get("backend_url", ""))
    if not base_url:
        return {"error": "Analytics backend URL is not configured.", "_config": True}

    backend_api_key = (s.get("backend_api_key", "") or "").strip()
    if not backend_api_key:
        return {"error": "Analytics backend API key is not configured.", "_config": True}

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
        headers={"X-API-Key": backend_api_key},
        timeout=timeout,
    )
    if not resp.ok:
        try:
            body = resp.text()[:200]
        except Exception:
            body = ""
        return {"error": f"server returned {resp.status_code}: {body}"}
    return resp.json()
