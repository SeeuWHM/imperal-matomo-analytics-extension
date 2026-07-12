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

from imperal_sdk import Extension, ChatExtension

ext = Extension(
    "imperal-matomo-analytics-extension",
    version="4.0.6",
    display_name="Matomo Analytics",
    description="Traffic analytics dashboard: visits, trends, top pages, sources, devices, geo, audience insights and AI anomaly detection from your Matomo instance.",
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
        "real-time visitors, traffic trends, anomalies, daily reports, audience insights. "
        "Keywords: трафик, посетители, визиты, страницы, аналитика сайта, "
        "откуда трафик, откуда идёт трафик, откуда приходит трафик, источники трафика, "
        "топ источников, прямые переходы, органический трафик Matomo, "
        "браузеры, страны, устройства, разрешения, аномалии, инсайты."
    ),
    max_rounds=5,
)

SETTINGS_COLLECTION = "analytics_settings"
RESULT_COLLECTION = "analytics_result"


DEFAULT_SETTINGS = {
    "backend_url": "",
    "backend_api_key": "",
    "matomo_url": "",
    "matomo_token": "",
    "matomo_site_id": 1,
    "matomo_segment": "",
    "blog_url": "",         # e.g. https://blog.webhostmost.com
    "blog_site_id": 2,      # Matomo site_id for blog subdomain (blog.webhostmost.com = site 2)
    "utm_source_dim_id": 0, # Custom Dimension ID for utm_source (0 = disabled)
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
    """Load the user's single settings doc; fall back to defaults if missing."""
    try:
        page = await ctx.store.query(SETTINGS_COLLECTION, limit=1)
    except Exception:
        return dict(DEFAULT_SETTINGS)
    docs = getattr(page, "data", None) or []
    if docs and isinstance(getattr(docs[0], "data", None), dict):
        return {**DEFAULT_SETTINGS, **docs[0].data}
    return dict(DEFAULT_SETTINGS)


async def save_settings(ctx, values: dict) -> dict:
    """Upsert the settings doc: update existing if present, else create."""
    current = await load_settings(ctx)
    merged = {**current, **{k: v for k, v in values.items() if v is not None and v != ""}}

    page = await ctx.store.query(SETTINGS_COLLECTION, limit=1)
    docs = getattr(page, "data", None) or []
    if docs:
        await ctx.store.update(SETTINGS_COLLECTION, docs[0].id, merged)
    else:
        await ctx.store.create(SETTINGS_COLLECTION, merged)
    return merged


def matomo_ready(s: dict) -> bool:
    return bool(
        s.get("backend_url")
        and s.get("backend_api_key")
        and s.get("matomo_url")
        and s.get("matomo_token")
    )
