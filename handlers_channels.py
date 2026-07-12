"""Chat functions for geo/device/search-engine breakdowns: regions, device
brands, browsers, search engines, organic keywords, campaigns. Demographic +
content breakdowns (socials, referring sites, site search, languages,
providers, resolutions, page details, outlinks) live in
handlers_demographics.py — split out of handlers_audience.py to stay under
the 300-line file limit."""
# No `from __future__ import annotations` - V6 validator needs real annotations.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat, save_result
from api_client import call_mos
from params import AudienceParams
from response_models import BreakdownResponse, BrowsersResponse
from audience_helpers import err, table, top


# ─── regions ──────────────────────────────────────────────────────────────────

@chat.function("regions",
               description="Visitor breakdown by city and region.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_regions(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_regions."""
    data = await call_mos(ctx, "/api/matomo-analytics/regions", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "regions", "Regions", data)
    regions = data.get("regions") or []
    lbl, pct = top(regions)
    return ActionResult.success(
        data=data,
        summary=f"Top region: {lbl} ({pct}%)",
        ui=ui.Section(title="Top Regions", children=[table(regions, "Region")]),
    )


# ─── device_brands ────────────────────────────────────────────────────────────

@chat.function("device_brands",
               description="Phone and tablet brands (Apple, Samsung, etc.).",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_device_brands(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_device_brands."""
    data = await call_mos(ctx, "/api/matomo-analytics/brands", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "device_brands", "Device brands", data)
    brands = data.get("brands") or []
    lbl, pct = top(brands)
    return ActionResult.success(
        data=data,
        summary=f"Top brand: {lbl} ({pct}%)",
        ui=ui.Section(title="Device Brands", children=[table(brands, "Brand")]),
    )


# ─── browsers ─────────────────────────────────────────────────────────────────

@chat.function("browsers",
               description="Browser breakdown (Chrome, Firefox, Safari, Edge, Opera) AND OS breakdown "
                           "(Windows, macOS, Linux, Android, iOS). "
                           "Use for: сравни браузеры, какие браузеры используют, Chrome vs Safari, "
                           "browser compatibility, ОС пользователей, работает ли на всех браузерах.",
               action_type="read", event="analytics.action.result", data_model=BrowsersResponse)
async def fn_browsers(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_browsers."""
    data = await call_mos(ctx, "/api/matomo-analytics/browsers", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "browsers", "Browsers & OS", data)
    browsers = data.get("browsers") or []
    os_fams  = data.get("os_families") or []
    lbl, pct = top(browsers)
    return ActionResult.success(
        data=data,
        summary=f"Top browser: {lbl} ({pct}%)",
        ui=ui.Section(title="Browsers & OS", children=[
            table(browsers, "Browser"),
            table(os_fams, "OS"),
        ]),
    )


# ─── search_engines ───────────────────────────────────────────────────────────

@chat.function("search_engines",
               description="Which search engines send organic traffic.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_search_engines(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_search_engines."""
    data = await call_mos(ctx, "/api/matomo-analytics/search-engines", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "search_engines", "Search engines", data)
    items = data.get("search_engines") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top search engine: {lbl} ({pct}%)",
        ui=table(items, "Search Engine"),
    )


# ─── organic_keywords ─────────────────────────────────────────────────────────

@chat.function("organic_keywords",
               description="Organic search keywords (may show 'not provided' if encrypted).",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_organic_keywords(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_organic_keywords."""
    data = await call_mos(ctx, "/api/matomo-analytics/keywords", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "organic_keywords", "Organic keywords", data)
    items = data.get("keywords") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top keyword: {lbl} ({pct}%)",
        ui=table(items, "Keyword"),
    )


# ─── campaigns ────────────────────────────────────────────────────────────────

@chat.function("campaigns",
               description="UTM campaign performance.",
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_campaigns(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_campaigns."""
    data = await call_mos(ctx, "/api/matomo-analytics/campaigns", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "campaigns", "Campaigns", data)
    items = data.get("campaigns") or []
    lbl, pct = top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top campaign: {lbl} ({pct}%)",
        ui=table(items, "Campaign"),
    )


