"""Chat functions for referrer/content breakdowns: social networks,
referring sites, site search, languages, providers, screen resolutions,
page details, outlinks. Split out of handlers_audience.py (via
handlers_channels.py) to stay under the 300-line file limit."""
# No `from __future__ import annotations` - V6 validator needs real annotations.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat, ext, save_result
from api_client import call_mos
from params import AudienceParams
from response_models import BreakdownResponse, SiteSearchResponse
from audience_helpers import err, table, top


# ─── social_networks ──────────────────────────────────────────────────────────

@chat.function("social_networks",
               description="Social network traffic breakdown.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_social_networks(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_social_networks."""
    data = await call_mos(ctx, "/api/matomo-analytics/socials", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "social_networks", "Social networks", data)
    items = data.get("socials") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top social: {lbl} ({pct}%)",
        ui=table(items, "Network"),
    )


# ─── referring_sites ──────────────────────────────────────────────────────────

@chat.function("referring_sites",
               description="Referral websites sending visitors.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_referring_sites(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_referring_sites."""
    data = await call_mos(ctx, "/api/matomo-analytics/referring-sites", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "referring_sites", "Referring sites", data)
    items = data.get("referring_sites") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top referrer: {lbl} ({pct}%)",
        ui=table(items, "Referrer"),
    )


# ─── site_search ──────────────────────────────────────────────────────────────

@chat.function("site_search",
               description="Internal site search terms including zero-result queries.",
               action_type="read", event="analytics.action.result", data_model=SiteSearchResponse)
async def fn_site_search(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_site_search."""
    data = await call_mos(ctx, "/api/matomo-analytics/site-search", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "site_search", "Site search", data)
    keywords  = data.get("keywords") or []
    no_result = data.get("no_results") or []
    lbl, pct = top(keywords)
    return ActionResult.success(
        data=data,
        summary=f"Top search: '{lbl}' | {len(no_result)} zero-result terms",
        ui=ui.Section(title="Site Search", children=[
            table(keywords, "Search Term"),
            table(no_result, "No-Result Term"),
        ]),
    )


# ─── languages ────────────────────────────────────────────────────────────────

@chat.function("languages",
               description="Visitor browser language preferences.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_languages(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_languages."""
    data = await call_mos(ctx, "/api/matomo-analytics/languages", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "languages", "Languages", data)
    items = data.get("languages") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top language: {lbl} ({pct}%)",
        ui=table(items, "Language"),
    )


# ─── providers ────────────────────────────────────────────────────────────────

@chat.function("providers",
               description="ISP and network providers of visitors.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_providers(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_providers."""
    data = await call_mos(ctx, "/api/matomo-analytics/providers", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "providers", "Providers", data)
    items = data.get("providers") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top provider: {lbl} ({pct}%)",
        ui=table(items, "Provider"),
    )


# ─── screen_resolutions ───────────────────────────────────────────────────────

@chat.function("screen_resolutions",
               description="Screen resolution distribution: 1920x1080, 1366x768, mobile resolutions, etc. "
                           "Use for: разрешения экранов, с каких экранов заходят, "
                           "1080p vs 720p, мобильные разрешения, screen size breakdown.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_screen_resolutions(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_screen_resolutions."""
    data = await call_mos(ctx, "/api/matomo-analytics/resolutions", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "screen_resolutions", "Screen resolutions", data)
    items = data.get("resolutions") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top resolution: {lbl} ({pct}%)",
        ui=table(items, "Resolution"),
    )


# ─── page_details ─────────────────────────────────────────────────────────────

@chat.function("page_details",
               description="All pages with time-on-page, bounce rate, and avg actions.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_page_details(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_page_details."""
    data = await call_mos(ctx, "/api/matomo-analytics/page-details", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "page_details", "Page details", data)
    pages = data.get("pages") or []
    top_page = pages[0] if pages else {}
    rows = [
        {
            "url": p.get("url", "/"),
            "visits": f"{p.get('visits', 0):,}",
            "avg_time": str(p.get("avg_time_on_page", 0)),
            "bounce": p.get("bounce_rate", "0%"),
        }
        for p in pages[:15]
    ]
    data_table = ui.DataTable(
        columns=[
            ui.DataColumn(key="url",      label="Page",       width="45%"),
            ui.DataColumn(key="visits",   label="Visits",     width="18%"),
            ui.DataColumn(key="avg_time", label="Avg Time",   width="18%"),
            ui.DataColumn(key="bounce",   label="Bounce",     width="19%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No page data")
    return ActionResult.success(
        data=data,
        summary=f"Top page: {top_page.get('url', 'n/a')} ({top_page.get('visits', 0):,} visits)",
        ui=data_table,
    )


# ─── outlinks ─────────────────────────────────────────────────────────────────

@chat.function("outlinks",
               description="Outbound link clicks tracked by Matomo.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_outlinks(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_outlinks."""
    data = await call_mos(ctx, "/api/matomo-analytics/outlinks", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "outlinks", "Outlinks", data)
    items = data.get("outlinks") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top outlink: {lbl} ({pct}% of clicks)",
        ui=table(items, "URL"),
    )


# ─── IPC — other extensions call these to compose cross-ext reports ─────────

@ext.expose("site_search")
async def ipc_site_search(ctx, period: str = "month", date: str = "today",
                           limit: int = 20, site: str = "") -> ActionResult:
    """Internal site-search terms, including zero-result queries - the
    clearest signal for content that doesn't exist yet but visitors want."""
    data = await call_mos(ctx, "/api/matomo-analytics/site-search", {
        "period": period, "date": date, "limit": limit,
    }, site=site)
    if "error" in data:
        return err(data)
    return ActionResult.success(data=data, summary="Site search terms fetched.")


@ext.expose("page_details")
async def ipc_page_details(ctx, period: str = "month", date: str = "today",
                            limit: int = 20, site: str = "") -> ActionResult:
    """Per-page bounce rate and time-on-page - flags existing content that
    needs a rewrite/refresh."""
    data = await call_mos(ctx, "/api/matomo-analytics/page-details", {
        "period": period, "date": date, "limit": limit,
    }, site=site)
    if "error" in data:
        return err(data)
    return ActionResult.success(data=data, summary="Page details fetched.")
