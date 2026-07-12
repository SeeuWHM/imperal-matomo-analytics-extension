"""HTTP client - calls the shared backend bridge (matomo-analytics-api).

Backend URL is a baked-in constant (app.py) - not a secret, it's the public
gateway host every extension on this platform calls. The user's Matomo URL +
Auth Token live in ctx.secrets (EXT-SECRETS-V1); the backend itself doesn't
check any auth header, so none is sent.
"""
from __future__ import annotations

from app import SERVER_URL, load_settings, matomo_ready, resolve_site

TIMEOUT = 30
HEAVY_TIMEOUT = 90  # full-report, daily-report: backend runs ~24 parallel Matomo calls


def _normalize_backend_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


async def call_mos(ctx, endpoint: str, extra: dict | None = None, timeout: int = TIMEOUT, site: str = "") -> dict:
    """POST to the backend bridge. Auto-injects the user's Matomo creds and
    resolves `site` (a label from list_sites) to the matching Matomo site_id -
    plus that site's own segment override if it has one (lets two "projects"
    share a Matomo site_id, e.g. a blog subdomain scoped out of the main site),
    falling back to the account-wide matomo_segment setting otherwise."""
    s = await load_settings(ctx)

    if not matomo_ready(s):
        return {"error": "Matomo not configured - open Settings and add your URL + Auth Token.",
                "_config": True}

    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return {"error": "Analytics backend URL is not configured.", "_config": True}

    site_cfg = resolve_site(s, site)
    payload = {
        "matomo_url":        s["matomo_url"],
        "token":             s["matomo_token"],
        "site_id":           int(site_cfg.get("site_id", 1)),
        "segment":           (site_cfg.get("segment") or s.get("matomo_segment") or None),
        "utm_source_dim_id": int(s.get("utm_source_dim_id") or 0),
        **(extra or {}),
    }

    resp = await ctx.http.post(
        f"{base_url}{endpoint}",
        json=payload,
        timeout=timeout,
    )
    if not resp.ok:
        try:
            body = resp.text()[:200]
        except Exception:
            body = ""
        return {"error": f"server returned {resp.status_code}: {body}"}
    return resp.json()
