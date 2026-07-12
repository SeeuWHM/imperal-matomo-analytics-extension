"""Skeleton context providers for Matomo Analytics.

Per Imperal SDK: skeleton = LLM context cache holding ready API responses.
More data here = better Webbee routing and answers.
"""
from app import ext, load_settings, matomo_ready
from api_client import call_mos


@ext.skeleton("traffic_overview", ttl=300,
              description="Last 7 days traffic: visits, pageviews, bounce rate, avg session time, week-over-week change")
async def skeleton_refresh_traffic_overview(ctx) -> dict:
    data = await call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day", "date": "last7"})
    if "error" in data:
        s = await load_settings(ctx)
        return {"response": {
            "configured": matomo_ready(s),
            "instruction": (
                "Matomo not configured — open Settings to add URL and Auth Token."
                if not matomo_ready(s) else f"Traffic API error: {data['error']}"
            ),
        }}

    visits = data.get("visits", 0)
    pageviews = data.get("pageviews", 0)
    bounce = data.get("bounce_rate", 0)
    avg_time = data.get("avg_time_on_site", 0)

    # WoW change comes from the separate /trends endpoint, not /traffic.
    trends = await call_mos(ctx, "/api/matomo-analytics/trends", {})
    wow = trends.get("change_percent") if "error" not in trends else None

    return {"response": {
        "configured": True,
        "period": "last7days",
        "visits": visits,
        "pageviews": pageviews,
        "bounce_rate_pct": bounce,
        "avg_time_seconds": avg_time,
        "wow_pct": wow,
        "instruction": (
            f"Last 7 days: {visits} visits, {pageviews} pageviews, "
            f"{bounce}% bounce, {avg_time}s avg session"
            + (f", WoW {wow:+.1f}%" if isinstance(wow, (int, float)) else "") + "."
        ),
    }}


@ext.skeleton("top_pages", ttl=600,
              description="Top 10 pages by visits this week with bounce rate and avg time on page")
async def skeleton_refresh_top_pages(ctx) -> dict:
    data = await call_mos(ctx, "/api/matomo-analytics/top-pages",
                          {"period": "week", "date": "thisWeek", "limit": 10})
    if "error" in data:
        return {"response": {"pages": [], "total": 0,
                             "instruction": "Top pages unavailable."}}

    raw = (data.get("pages") or [])[:10]
    pages = []
    for p in raw:
        pages.append({
            "url": p.get("url", ""),
            "visits": p.get("views", 0),
            "bounce_pct": p.get("bounce_rate", 0),
            "avg_time_s": p.get("avg_time_on_page", 0),
        })

    instruction = "Top pages this week: " + "; ".join(
        f"{p['url']} ({p['visits']} visits)" for p in pages[:5]
    ) if pages else "No top pages data."

    return {"response": {"pages": pages, "total": len(pages), "instruction": instruction}}


@ext.skeleton("realtime", ttl=60,
              description="Real-time visitor counts: last 30, 60, 180 minutes")
async def skeleton_refresh_realtime(ctx) -> dict:
    data = await call_mos(ctx, "/api/matomo-analytics/real-time", {})
    if "error" in data:
        return {"response": {"visitors_30m": 0, "instruction": "Real-time data unavailable."}}

    v30  = (data.get("live_30m")  or {}).get("visitors", 0)
    v60  = (data.get("live_60m")  or {}).get("visitors", 0)
    v180 = (data.get("live_180m") or {}).get("visitors", 0)

    return {"response": {
        "visitors_30m": v30,
        "visitors_60m": v60,
        "visitors_180m": v180,
        "instruction": f"Live visitors: {v30} (30min) / {v60} (60min) / {v180} (3h).",
    }}


@ext.skeleton("matomo_config", ttl=600,
              description="Matomo connection status, configured sites/projects, UTM dimension ID")
async def skeleton_refresh_matomo_config(ctx) -> dict:
    s = await load_settings(ctx)
    configured = matomo_ready(s)
    sites = s.get("sites") or []
    site_labels = ", ".join(site.get("label", "") for site in sites) if sites else "none"
    return {"response": {
        "configured": configured,
        "sites": sites,
        "utm_source_dim_id": s.get("utm_source_dim_id", 0),
        "instruction": (
            f"Matomo: {'✓ connected, sites: ' + site_labels if configured else '✗ NOT configured — open Settings'}"
        ),
    }}
