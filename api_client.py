"""HTTP client - calls the shared backend bridge (matomo-analytics-api).

Backend URL is a baked-in constant (app.py) - not a secret, it's the public
gateway host every extension on this platform calls. The user's Matomo URL +
Auth Token live in ctx.secrets (EXT-SECRETS-V1); the backend itself doesn't
check any auth header, so none is sent.
"""
from __future__ import annotations

from app import SERVER_URL, load_settings, matomo_ready, resolve_site, active_site_label

TIMEOUT = 30
HEAVY_TIMEOUT = 90  # full-report, daily-report: backend runs ~24 parallel Matomo calls


def _normalize_backend_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


def _target(s: dict, label: str) -> dict:
    """Resolve one `site` label to the {label, site_id, segment} shape the
    backend's Target model expects - same resolution resolve_site() already
    does (per-site segment override, else the account-wide matomo_segment)."""
    cfg = resolve_site(s, label)
    return {
        "label": cfg.get("label") or label or active_site_label(s) or "default",
        "site_id": int(cfg.get("site_id", 1)),
        "segment": (cfg.get("segment") or s.get("matomo_segment") or None),
    }


async def call_mos(ctx, endpoint: str, extra: dict | None = None, timeout: int = TIMEOUT,
                    site: str = "", sites: list[str] | None = None) -> dict:
    """POST to the backend bridge. Auto-injects the user's Matomo creds and
    resolves `site`/`sites` (labels from list_sites) into the backend's
    `targets: [...]` list - the SAME route handles one site or several, the
    backend fans them out concurrently on its side.

    Asking for exactly one target (the default - just `site`, or `sites` with
    a single label) returns the flat, unwrapped shape every existing handler
    already expects: `data.get("visits")`, `data.get("countries")`, etc. -
    zero changes needed anywhere that doesn't want a comparison.

    Asking for 2+ labels via `sites` returns the raw envelope instead:
    `{"results": [{"label", "site_id", "error", "data"}, ...]}` - the caller
    opted into a comparison, so it's the caller's job to render the list."""
    s = await load_settings(ctx)

    if not matomo_ready(s):
        return {"error": "Matomo not configured - open Settings and add your URL + Auth Token.",
                "_config": True}

    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return {"error": "Analytics backend URL is not configured.", "_config": True}

    labels = [lbl for lbl in (sites or []) if lbl] or [site]
    targets = [_target(s, lbl) for lbl in labels]

    payload = {
        "matomo_url":        s["matomo_url"],
        "token":             s["matomo_token"],
        "targets":           targets,
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

    body = resp.json()
    results = body.get("results") if isinstance(body, dict) else None
    if results is None:
        return body  # /health or any route that doesn't use the MultiResult envelope

    if len(targets) <= 1:
        if not results:
            return {}
        r = results[0]
        return {"error": r["error"]} if r.get("error") else (r.get("data") or {})

    return {"results": results}


async def site_info_for(ctx, site_id: int, segment: str | None = None) -> dict:
    """Fetch Matomo's own domain list for a site_id directly, by site_id
    rather than by label - used right after add_site/view_domain, before the
    new entry exists in `sites` and can be resolved by label."""
    s = await load_settings(ctx)
    if not matomo_ready(s):
        return {"error": "Matomo not configured.", "_config": True}
    base_url = _normalize_backend_url(SERVER_URL)
    if not base_url:
        return {"error": "Analytics backend URL is not configured.", "_config": True}

    payload = {
        "matomo_url": s["matomo_url"],
        "token": s["matomo_token"],
        "targets": [{"label": "probe", "site_id": int(site_id), "segment": segment}],
        "utm_source_dim_id": int(s.get("utm_source_dim_id") or 0),
    }
    resp = await ctx.http.post(f"{base_url}/api/matomo-analytics/site-info", json=payload, timeout=TIMEOUT)
    if not resp.ok:
        return {"error": f"server returned {resp.status_code}"}
    results = (resp.json() or {}).get("results") or []
    if not results or results[0].get("error"):
        return {"error": results[0].get("error") if results else "no data"}
    return results[0].get("data") or {}
