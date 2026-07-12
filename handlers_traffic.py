"""Chat-function handlers for traffic, trends, top pages."""
# Note: no `from __future__ import annotations` - the V6 validator reads
# type annotations via inspect.signature and can only recognise BaseModel
# subclasses when annotations are real types, not PEP 563 strings.

import asyncio

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat, save_result, load_settings, matomo_ready, active_site_label
from api_client import call_mos
from params import TrafficParams, TopPagesParams, TrendsParams
from response_models import TrafficOverviewRecord, PageListResponse, TrendSummaryResponse


def _err(data: dict) -> ActionResult:
    """Translate a call_mos error dict into an ActionResult."""
    return ActionResult.error(error=data.get("error", "unknown error"))


@chat.function(
    "traffic",
    description="Website visits summary: total visits, pageviews, unique visitors, bounce rate, "
                "avg time on site, daily/weekly/monthly series. "
                "Use for: покажи трафик, сколько посетителей, визиты за период, "
                "pageviews, сводка по трафику, traffic overview, how many visitors.",
    action_type="read",
    data_model=TrafficOverviewRecord,
)
async def fn_traffic(ctx, params: TrafficParams) -> ActionResult:
    """Return visits/pageviews summary from Matomo for the requested period."""
    data = await call_mos(ctx, "/api/matomo-analytics/traffic", {
        "period": params.period, "date": params.date,
    }, site=params.site)
    if "error" in data:
        return _err(data)

    visits = data.get("visits", 0)
    pageviews = data.get("pageviews", 0)
    summary = f"{visits} visits, {pageviews} pageviews ({params.period} {params.date})"
    return ActionResult.success(data=data, summary=summary)


@chat.function(
    "top_pages",
    description="Most visited pages ranked by visits with bounce rate and avg time on page. "
                "Use for: топ страниц, популярные страницы, какие страницы смотрят, "
                "most popular content, best performing pages, top content.",
    action_type="read",
    event="analytics.action.result",
    data_model=PageListResponse,
)
async def fn_top_pages(ctx, params: TopPagesParams) -> ActionResult:
    """Return the N most visited pages for the chosen period and segment."""
    data = await call_mos(ctx, "/api/matomo-analytics/top-pages", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return _err(data)

    await save_result(ctx, "top_pages", "Top 10 pages", data)
    pages = data.get("pages") or []
    rows = [{"url": (p.get("url") or "/")[:70],
             "visits": f"{p.get('views', 0):,}",
             "bounce": p.get("bounce_rate", "-")}
            for p in pages[:15]]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="url", label="Page", width="60%"),
            ui.DataColumn(key="visits", label="Visits", width="20%"),
            ui.DataColumn(key="bounce", label="Bounce", width="20%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No data")
    return ActionResult.success(
        data=data,
        summary=f"Top {len(pages)} pages ({params.period} {params.date})",
        ui=ui_node,
    )


@chat.function(
    "trends",
    description="Week-over-week traffic comparison: this week vs last week, % change, direction. "
                "Use for: трафик растёт или падает, сравни недели, WoW, "
                "week over week, растёт ли сайт, динамика трафика, трафик вверх или вниз.",
    action_type="read",
    event="analytics.action.result",
    data_model=TrendSummaryResponse,
)
async def fn_trends(ctx, params: TrendsParams) -> ActionResult:
    """Return week-over-week visits and the % change, plus up/down direction."""
    data = await call_mos(ctx, "/api/matomo-analytics/trends", {}, site=params.site)
    if "error" in data:
        return _err(data)

    await save_result(ctx, "trends", "Week vs last week", data)
    change = data.get("change_percent", 0)
    direction = data.get("direction", "flat")
    cw = data.get("current_week", 0)
    pw = data.get("previous_week", 0)
    color = "green" if direction == "up" else "red" if direction == "down" else "gray"
    return ActionResult.success(
        data=data,
        summary=f"This week {cw:,} vs last week {pw:,} ({change:+.1f}%)",
        ui=ui.Stats(children=[
            ui.Stat(label="This week", value=f"{cw:,}", color=color),
            ui.Stat(label="Last week", value=f"{pw:,}", color="gray"),
            ui.Stat(label="WoW Δ", value=f"{change:+.1f}%", color=color),
        ]),
    )


# IPC - callable from other extensions (e.g. imperal-reports aggregator)
from app import ext  # noqa: E402


@ext.expose("traffic")
async def ipc_traffic(ctx, period: str = "day", date: str = "last7", site: str = "") -> ActionResult:
    """Handler: ipc_traffic."""
    data = await call_mos(ctx, "/api/matomo-analytics/traffic", {"period": period, "date": date}, site=site)
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data, summary="Traffic summary fetched.")


@ext.expose("trends")
async def ipc_trends(ctx, site: str = "") -> ActionResult:
    """Handler: ipc_trends."""
    data = await call_mos(ctx, "/api/matomo-analytics/trends", {}, site=site)
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data, summary="Week-over-week trend fetched.")


@ext.expose("top_pages")
async def ipc_top_pages(ctx, period: str = "month", date: str = "today", limit: int = 10, site: str = "") -> ActionResult:
    """Handler: ipc_top_pages."""
    data = await call_mos(ctx, "/api/matomo-analytics/top-pages", {
        "period": period, "date": date, "limit": limit,
    }, site=site)
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data, summary="Top pages fetched.")


@ext.expose("growing_pages")
async def ipc_growing_pages(ctx, limit: int = 20, site: str = "") -> ActionResult:
    """Top pages this month with month-over-month growth %, for whichever
    site the caller asks for (or the user's default site)."""
    current, previous = await asyncio.gather(
        call_mos(ctx, "/api/matomo-analytics/top-pages", {
            "period": "month", "date": "today", "limit": limit,
        }, site=site),
        call_mos(ctx, "/api/matomo-analytics/top-pages", {
            "period": "month", "date": "previous1", "limit": limit,
        }, site=site),
    )
    if "error" in current:
        return _err(current)
    prev_by_url = {
        p.get("url"): p.get("views", 0)
        for p in (previous.get("pages") or [])
    } if "error" not in previous else {}

    pages = []
    for p in (current.get("pages") or []):
        views = p.get("views", 0)
        prev_views = prev_by_url.get(p.get("url"), 0)
        if prev_views:
            growth_pct = round((views - prev_views) * 100.0 / prev_views, 1)
        else:
            growth_pct = 100.0 if views else 0.0
        pages.append({"url": p.get("url", ""), "visits": views, "growth_pct": growth_pct})
    pages.sort(key=lambda p: p["growth_pct"], reverse=True)
    return ActionResult.success(
        data={"pages": pages, "count": len(pages)},
        summary=f"{len(pages)} growing pages fetched.",
    )


@ext.expose("ai_referrers")
async def ipc_ai_referrers(ctx, period: str = "month", site: str = "") -> ActionResult:
    """Return AI referrer traffic (ChatGPT, Perplexity, Gemini, etc.)."""
    data = await call_mos(ctx, "/api/matomo-analytics/ai-referrers", {
        "period": period, "date": "today",
    }, site=site)
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data, summary="AI referrer traffic fetched.")


@ext.expose("matomo_config")
async def ipc_matomo_config(ctx) -> ActionResult:
    """Share connection status + configured sites with other extensions -
    never the raw credentials (those stay in this extension's ctx.secrets)."""
    s = await load_settings(ctx)
    if not matomo_ready(s):
        return ActionResult.error(error="Matomo not configured in Analytics extension.")
    return ActionResult.success(
        data={
            "configured": True,
            "sites": s.get("sites", []),
            "active_site": active_site_label(s),
            "matomo_segment": s.get("matomo_segment", ""),
        },
        summary="Matomo connection status shared.",
    )
