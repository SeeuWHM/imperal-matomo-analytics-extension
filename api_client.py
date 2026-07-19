"""HTTP client - calls the shared backend bridge (matomo-analytics-api).

Backend URL is a baked-in constant (app.py) - not a secret, it's the public
gateway host every extension on this platform calls. The user's Matomo URL +
Auth Token live in ctx.secrets (EXT-SECRETS-V1); the backend itself doesn't
check any auth header, so none is sent.
"""
from __future__ import annotations

import hashlib
import json

from app import SERVER_URL, load_settings, matomo_ready, resolve_site, active_site_label
from response_models import CachedAnalyticsPayload

TIMEOUT = 30
HEAVY_TIMEOUT = 90  # full-report, daily-report: backend runs ~24 parallel Matomo calls

# ctx.cache TTL is platform-capped to [5, 300]s (I-CACHE-TTL-CAP-300S). Real-time
# visitor counts get a short TTL so "live" still feels live; everything else
# (traffic/trends/top-pages/sources/devices/geo/entry-exit) barely moves
# minute-to-minute, so a longer TTL turns repeat panel opens from ~6-8 live
# HTTP round-trips into a single cache read.
REALTIME_CACHE_TTL = 30
DASHBOARD_CACHE_TTL = 180


def _normalize_backend_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


def _cache_key(ctx_site_label: str, site_id: int, segment: str | None,
               endpoint: str, extra: dict | None) -> str:
    """Deterministic, key-safe ctx.cache key for one call_mos() shape.

    Includes site_id + segment (not just the label) so a stale/renamed label
    can never collide with a different project, and every distinct
    period/date/limit combination gets its own slot. Hashed to stay within
    ctx.cache's 128-char key-safety cap regardless of how long the label or
    extra params get.
    """
    parts = {
        "ep": endpoint,
        "site_id": site_id,
        "segment": segment or "",
        "extra": extra or {},
    }
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]
    return f"mos:{digest}"


async def call_mos_cached(ctx, endpoint: str, extra: dict | None = None, timeout: int = TIMEOUT,
                           site: str = "", ttl_seconds: int = DASHBOARD_CACHE_TTL) -> dict:
    """Cached wrapper over call_mos() for dashboard/panel reads.

    Only for single-target, read-only calls (the panels' KPI/chart/table
    fan-outs) — never for site_info_for/add_site's live lookups or any
    write path. On any error response, the error is NOT cached (so a
    transient Matomo hiccup doesn't stick around for the full TTL) — only
    a genuinely good payload gets written back.
    """
    s = await load_settings(ctx)
    if not matomo_ready(s):
        return {"error": "Matomo not configured - open Settings and add your URL + Auth Token.",
                "_config": True}

    cfg = resolve_site(s, site)
    key = _cache_key(site, int(cfg.get("site_id", 1)), cfg.get("segment"), endpoint, extra)

    async def _fetch() -> CachedAnalyticsPayload:
        data = await call_mos(ctx, endpoint, extra, timeout=timeout, site=site)
        return CachedAnalyticsPayload(data=data if isinstance(data, dict) else {"error": "bad_response"})

    if not hasattr(ctx, "cache") or ctx.cache is None:
        # MockContext/tests without a cache client — behave like call_mos().
        return await call_mos(ctx, endpoint, extra, timeout=timeout, site=site)

    cached = await ctx.cache.get(key, CachedAnalyticsPayload)
    if cached is not None and "error" not in cached.data:
        return cached.data

    payload = await _fetch()
    if "error" not in payload.data:
        try:
            await ctx.cache.set(key, payload, ttl_seconds=ttl_seconds)
        except Exception:
            pass  # cache write is an optimization, never the correctness path
    return payload.data


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


async def ensure_known_domains(ctx, s: dict) -> dict:
    """Best-effort, READ-ONLY enrichment for panel rendering: if the active
    site's known_domains cache is missing (e.g. it was added before this
    cache existed (pre-v5.1.0), or add_site's lookup failed at the time),
    fetch it live so the domain-level dropdown can still appear. Deliberately
    does NOT persist (panels must stay side-effect-free) - add_site remains
    the only place known_domains gets written to ctx.store. Returns `s`
    unchanged (a plain dict, never a coroutine/exception) on any failure or
    when there's nothing to enrich - never raises."""
    try:
        sites = s.get("sites") or []
        active_label = active_site_label(s)
        idx = next((i for i, site in enumerate(sites) if site.get("label") == active_label), None)
        if idx is None or sites[idx].get("known_domains"):
            return s
        site_id = sites[idx].get("site_id")
        if not site_id:
            return s
        info = await site_info_for(ctx, site_id, sites[idx].get("segment"))
        if "error" in info or not info.get("urls"):
            return s
        updated = list(sites)
        updated[idx] = {**updated[idx], "known_domains": info["urls"]}
        return {**s, "sites": updated}
    except Exception:
        return s
