"""Analytics extension - core init + shared helpers.

Settings live in ``ctx.store`` as a single doc per user, inside the
``analytics_settings`` collection. We look it up via ``query(limit=1)``
rather than a fixed doc_id because Imperal's ``ctx.store.create`` always
assigns a server-side id - there is no cross-version way to create with
a known id, and the v1.5.8 ``set()`` upsert shortcut calls the same
create and therefore also ends up with an auto id. Query-by-collection
works on every SDK version and on MockStore.
"""
from __future__ import annotations

import os

from imperal_sdk import Extension, ChatExtension

# Shared backend bridge for all installs. Users configure only their own Matomo.
#
# This is the public API gateway host every extension on this platform calls
# (web-tools, seo-tools, ...) - not a per-user secret, so it's a plain
# constant rather than a declared ctx.secrets entry. MATOMO_BACKEND_URL stays
# as an override hook for local/dev testing against a different bridge.
# The backend (matomo-analytics-api on api-server:8105) checks no auth header
# at all, so there's no API key to configure here.
SERVER_URL = os.environ.get("MATOMO_BACKEND_URL", "") or "https://api.webhostmost.com"

ext = Extension(
    "imperal-matomo-analytics-extension",
    version="5.2.3",
    display_name="Matomo Analytics Connector",
    description="Traffic analytics dashboard: visits, trends, top pages, sources, devices, geo, audience insights and AI anomaly detection from your Matomo instance. Track multiple sites/projects under one Matomo account.",
    icon="icon.svg",
    actions_explicit=True,
    capabilities=[
        "Traffic Overview",
        "Top Pages & Content",
        "Traffic Sources",
        "Audience Insights",
        "Real-time Visitors",
        "Campaign Analytics",
        "AI Daily Report",
        "Anomaly Detection",
        "Multi-Site Tracking",
    ],
)

chat = ChatExtension(
    ext,
    tool_name="analytics",
    description=(
        "Website traffic analytics powered by Matomo. Use for ANY question about: "
        "visits, pageviews, bounce rate, sessions, traffic sources, referrers, "
        "top pages, countries, devices, browsers, screen resolutions, ISPs, "
        "new vs returning visitors, session duration, organic keywords, UTM campaigns, "
        "social networks, outbound links, site search, AI referrers (ChatGPT/Perplexity/Claude), "
        "real-time visitors, traffic trends, anomalies, daily reports, audience insights, "
        "which domains/URLs are configured for a site (site_domains). "
        "Sites are per-project - pass `site` (a label from list_sites) when the user names "
        "a specific site/project; omit it for their default site. "
        "Keywords: трафик, посетители, визиты, страницы, аналитика сайта, "
        "откуда трафик, откуда идёт трафик, откуда приходит трафик, источники трафика, "
        "топ источников, прямые переходы, органический трафик Matomo, "
        "браузеры, страны, устройства, разрешения, аномалии, инсайты, "
        "домены сайта, привязанные домены, site domains."
    ),
    max_rounds=5,
)

# EXT-SECRETS-V1 - Matomo URL + Auth Token are real per-user credentials, so
# they're declared here and stored via the platform's own secrets vault
# (ctx.secrets), not as plain ctx.store fields. write_mode="user" means the
# platform auto-registers a "Secrets" panel where the user pastes these in
# directly - the extension only ever reads them (ctx.secrets.get), it never
# writes them itself.
ext.secret(
    name="matomo_url",
    description="Your Matomo instance URL, e.g. https://analytics.example.com",
    required=True,
    write_mode="user",
    max_bytes=500,
)(lambda: None)

ext.secret(
    name="matomo_token",
    description="Matomo Auth Token — Matomo → Personal → Security → Auth tokens",
    required=True,
    write_mode="user",
    max_bytes=200,
)(lambda: None)

SETTINGS_COLLECTION = "analytics_settings"
RESULT_COLLECTION = "analytics_result"


DEFAULT_SETTINGS = {
    "matomo_segment": "",
    "utm_source_dim_id": 0, # Custom Dimension ID for utm_source (0 = disabled)
    "sites": [],            # [{"label": str, "site_id": int}, ...] - per-project analytics
    "active_site": "",      # label of the site shown by default (sidebar/dashboard/chat)
}


async def save_result(ctx, action: str, title: str, data: dict) -> None:
    """Upsert the last quick-action result so the workspace panel can render it."""
    doc = {"action": action, "title": title, "data": data}
    page = await ctx.store.query(RESULT_COLLECTION, limit=1)
    docs = getattr(page, "data", None) or []
    if docs:
        await ctx.store.update(RESULT_COLLECTION, docs[0].id, doc)
    else:
        await ctx.store.create(RESULT_COLLECTION, doc)


async def load_result(ctx) -> dict | None:
    """Return the last saved result doc, or None if none exists yet."""
    try:
        page = await ctx.store.query(RESULT_COLLECTION, limit=1)
    except Exception:
        return None
    docs = getattr(page, "data", None) or []
    if docs and isinstance(getattr(docs[0], "data", None), dict):
        return docs[0].data
    return None


async def load_settings(ctx) -> dict:
    """Load the user's settings doc (ctx.store) merged with Matomo credentials
    (ctx.secrets) - credentials go through the platform's own secrets vault
    (EXT-SECRETS-V1), not plain ctx.store fields."""
    try:
        page = await ctx.store.query(SETTINGS_COLLECTION, limit=1)
    except Exception:
        page = None
    docs = (getattr(page, "data", None) or []) if page else []
    stored = docs[0].data if docs and isinstance(getattr(docs[0], "data", None), dict) else {}
    settings = {**DEFAULT_SETTINGS, **stored}

    # One-time migration: pre-multisite installs stored a single
    # matomo_site_id - fold it into `sites` as the default entry.
    if not settings["sites"] and stored.get("matomo_site_id"):
        settings["sites"] = [{"label": "Основной сайт", "site_id": int(stored["matomo_site_id"])}]

    settings["matomo_url"] = await ctx.secrets.get("matomo_url") or ""
    settings["matomo_token"] = await ctx.secrets.get("matomo_token") or ""
    return settings


async def save_settings(ctx, values: dict) -> dict:
    """Upsert the settings doc: update existing if present, else create.
    matomo_url/matomo_token are never persisted here - they live in
    ctx.secrets, written only via the platform's own Secrets panel."""
    current = await load_settings(ctx)
    merged = {**current, **{k: v for k, v in values.items() if v is not None and v != ""}}
    store_fields = {k: v for k, v in merged.items() if k not in ("matomo_url", "matomo_token")}

    page = await ctx.store.query(SETTINGS_COLLECTION, limit=1)
    docs = getattr(page, "data", None) or []
    if docs:
        await ctx.store.update(SETTINGS_COLLECTION, docs[0].id, store_fields)
    else:
        await ctx.store.create(SETTINGS_COLLECTION, store_fields)
    return merged


def matomo_ready(s: dict) -> bool:
    return bool(s.get("matomo_url") and s.get("matomo_token"))


def resolve_site(s: dict, site: str = "") -> dict:
    """Resolve a `site` label (from list_sites) to its full config entry
    (site_id + optional per-project `segment` override) - lets two "projects"
    share one Matomo site_id while each tracking only its own subdomain/path
    (e.g. label="Blog" -> site_id=2, segment="pageUrl=^https://blog.example.com").
    Falls back to the user's active site, then the first configured site,
    then Matomo's default site 1 with no segment override."""
    sites = s.get("sites") or []
    needle = (site or s.get("active_site") or "").strip().lower()
    if needle:
        for entry in sites:
            if str(entry.get("label", "")).strip().lower() == needle:
                return entry
    if sites:
        return sites[0]
    return {"site_id": 1}


def resolve_site_id(s: dict, site: str = "") -> int:
    """Resolve a `site` label (from list_sites) to its Matomo site_id."""
    return int(resolve_site(s, site).get("site_id", 1))


def active_site_label(s: dict) -> str:
    """Which site label is currently the default - the explicit active_site
    if set (and still valid), else the first configured site, else ''."""
    sites = s.get("sites") or []
    active = (s.get("active_site") or "").strip().lower()
    for entry in sites:
        if str(entry.get("label", "")).strip().lower() == active:
            return entry["label"]
    return sites[0]["label"] if sites else ""


def sites_with_active(s: dict) -> list[dict]:
    """Sites list annotated with `active: bool` for display/IPC."""
    active = active_site_label(s)
    return [{**site, "active": site.get("label") == active} for site in (s.get("sites") or [])]
