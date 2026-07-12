"""The full_report aggregate (all sections in one call) + its IPC export.
Split out of handlers_audience.py to stay under the 300-line file limit."""
# No `from __future__ import annotations` - V6 validator needs real annotations.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat, ext, save_result
from api_client import call_mos, HEAVY_TIMEOUT
from params import AudienceParams
from response_models import AnalyticsScalarResponse
from audience_helpers import err


# ─── full_report ──────────────────────────────────────────────────────────────

@chat.function("full_report",
               description="Fetch ALL analytics data in one call — traffic, geo, devices, referrers, engagement, AI referrers, audience. Runs in background, result delivered to chat.",
               action_type="read", event="analytics.action.result",
               background=True, long_running=False, data_model=AnalyticsScalarResponse)
async def fn_full_report(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_full_report."""
    await ctx.progress(10, "Fetching all analytics data from Matomo...")
    data = await call_mos(ctx, "/api/matomo-analytics/full-report", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, timeout=HEAVY_TIMEOUT, site=params.site)
    if "error" in data:
        return err(data)
    await ctx.progress(75, "Processing results...")

    # Persist each section individually so other functions can read them
    for key, label in [
        ("traffic", "Traffic"), ("top_pages", "Top pages"),
        ("sources", "Sources"), ("devices", "Devices"), ("geo", "Countries"),
        ("entry_exit", "Entry/Exit"), ("regions", "Regions"),
        ("brands", "Device brands"), ("browsers", "Browsers"),
        ("search_engines", "Search engines"), ("keywords", "Keywords"),
        ("campaigns", "Campaigns"), ("socials", "Social networks"),
        ("referring_sites", "Referring sites"), ("site_search", "Site search"),
        ("new_returning", "New vs returning"), ("visit_duration", "Visit duration"),
        ("languages", "Languages"), ("providers", "Providers"),
        ("resolutions", "Screen resolutions"), ("page_details", "Page details"),
        ("outlinks", "Outlinks"),
    ]:
        section = data.get(key)
        if section and "error" not in section:
            await save_result(ctx, key, label, section)

    # Build a compact summary from key metrics
    traffic     = data.get("traffic") or {}
    new_ret     = data.get("new_returning") or {}
    sources     = data.get("sources") or {}
    top_src     = (sources.get("sources") or [{}])[0]
    geo         = data.get("geo") or {}
    top_country = (geo.get("countries") or [{}])[0]

    visits   = traffic.get("visits", 0)
    brate    = traffic.get("bounce_rate", "n/a")
    new_pct  = new_ret.get("new_percent", 0)
    src_lbl  = top_src.get("label", "n/a")
    src_pct  = top_src.get("percent", 0)
    cntry    = top_country.get("label", "n/a")

    errors   = [k for k, v in data.items() if isinstance(v, dict) and "error" in v]
    err_note = f" ({len(errors)} sections unavailable)" if errors else ""

    summary = (
        f"Full report{err_note}: {visits:,} visits, bounce {brate}, "
        f"{new_pct}% new visitors. "
        f"Top source: {src_lbl} ({src_pct}%). Top country: {cntry}."
    )

    await ctx.progress(95, "Building report...")
    return ActionResult.success(
        data=data,
        summary=summary,
        ui=ui.Stats(children=[
            ui.Stat(label="Visits",    value=f"{visits:,}",     icon="BarChart2"),
            ui.Stat(label="Bounce",    value=str(brate),        icon="TrendingDown"),
            ui.Stat(label="New",       value=f"{new_pct}%",     icon="UserPlus", color="green"),
            ui.Stat(label="Top src",   value=src_lbl,           icon="Globe"),
        ]),
    )


# ─── IPC — expose for cross-extension use ────────────────────────────────────

@ext.expose("full_report")
async def ipc_full_report(ctx, period: str = "week", date: str = "today",
                          limit: int = 20, site: str = "") -> ActionResult:
    """Handler: ipc_full_report."""
    data = await call_mos(ctx, "/api/matomo-analytics/full-report", {
        "period": period, "date": date, "limit": limit,
    }, site=site)
    if "error" in data:
        return ActionResult.error(error=data.get("error", "unknown error"))
    return ActionResult.success(data=data, summary="Full analytics report fetched.")
