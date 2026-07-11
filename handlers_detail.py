"""Chat functions + IPC for detail analytics (real-time, sources, devices, geo, entry/exit)."""
# No `from __future__ import annotations` - V6 validator needs real annotations.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult
from pydantic import BaseModel, Field

from app import chat, ext, save_result
from api_client import call_mos
from params import _DATE_HELP, _PERIOD_HELP
from response_models import LiveVisitorsResponse, BreakdownResponse, AnalyticsScalarResponse


class _EmptyParams(BaseModel):
    pass


class _PeriodParams(BaseModel):
    period: str = Field(default="week", description=_PERIOD_HELP)
    date: str   = Field(default="today", description=_DATE_HELP)
    limit: int  = Field(default=10, ge=1, le=100)


def _err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


@chat.function("real_time",
               description="Live active visitors right now: 30 min / 60 min / 3 hour windows. "
                           "Use for: сколько людей сейчас на сайте, онлайн посетители, "
                           "live visitors, real-time, кто сейчас.",
               action_type="read", event="analytics.action.result", data_model=LiveVisitorsResponse)
async def fn_real_time(ctx, params: _EmptyParams) -> ActionResult:
    """Handler: fn_real_time."""
    data = await call_mos(ctx, "/api/matomo-analytics/real-time", {})
    if "error" in data:
        return _err(data)
    await save_result(ctx, "real_time", "Live visitors", data)
    c30 = data.get("live_30m") or {}
    c60 = data.get("live_60m") or {}
    c180 = data.get("live_180m") or {}
    return ActionResult.success(
        data=data,
        summary=f"Live: {c30.get('visitors', 0)} visitors in last 30 min",
        ui=ui.Stats(children=[
            ui.Stat(label="Last 30 min", value=str(c30.get("visitors", 0)), color="green", icon="Users"),
            ui.Stat(label="Last 60 min", value=str(c60.get("visitors", 0)), color="blue"),
            ui.Stat(label="Last 3 hours", value=str(c180.get("visitors", 0)), color="gray"),
        ]),
    )


@chat.function("sources",
               description="Traffic sources breakdown: Direct Entry, Search Engines, Websites, "
                           "Social Networks, Campaigns. "
                           "ALWAYS use for: откуда идёт трафик, откуда трафик на сайт, "
                           "источники трафика, откуда приходят люди, топ источников, "
                           "прямые переходы, реферальные ссылки, поисковый трафик, "
                           "direct vs organic, where does traffic come from, traffic sources.",
               action_type="read", event="analytics.action.result", data_model=LiveVisitorsResponse)
async def fn_sources(ctx, params: _PeriodParams) -> ActionResult:
    """Handler: fn_sources."""
    data = await call_mos(ctx, "/api/matomo-analytics/sources", {
        "period": params.period, "date": params.date,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "sources", "Traffic sources", data)
    sources = data.get("sources") or []
    top = (sources or [{}])[0]
    rows = [{"label": s.get("label", "-"), "visits": f"{s.get('visits',0):,}",
             "pct": f"{s.get('percent',0)}%"} for s in sources[:10]]
    ui_node = ui.DataTable(
        columns=[ui.DataColumn(key="label", label="Source", width="50%"),
                 ui.DataColumn(key="visits", label="Visits", width="25%"),
                 ui.DataColumn(key="pct", label="Share", width="25%")],
        rows=rows,
    ) if rows else ui.Empty(message="No data")
    return ActionResult.success(
        data=data,
        summary=f"Top source: {top.get('label', 'n/a')} ({top.get('percent', 0)}%)",
        ui=ui_node,
    )


@chat.function("devices",
               description="Device type split: Desktop vs Smartphone vs Tablet percentages. "
                           "Use for: с каких устройств, мобильные vs десктоп, "
                           "mobile traffic share, сколько с телефона, desktop percentage.",
               action_type="read", data_model=BreakdownResponse)
async def fn_devices(ctx, params: _PeriodParams) -> ActionResult:
    """Return device type breakdown."""
    data = await call_mos(ctx, "/api/matomo-analytics/devices", {
        "period": params.period, "date": params.date,
    })
    if "error" in data:
        return _err(data)
    top = (data.get("devices") or [{}])[0]
    return ActionResult.success(
        data=data,
        summary=f"Top device: {top.get('label', 'n/a')} ({top.get('percent', 0)}%)",
    )


@chat.function("geo",
               description="Top countries by visitor count with percentages. "
                           "Use for: из каких стран, топ страны, география трафика, "
                           "откуда люди, США Индия Китай, country breakdown, where visitors come from.",
               action_type="read", event="analytics.action.result", data_model=LiveVisitorsResponse)
async def fn_geo(ctx, params: _PeriodParams) -> ActionResult:
    """Handler: fn_geo."""
    data = await call_mos(ctx, "/api/matomo-analytics/geo", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "geo", "Top countries", data)
    countries = data.get("countries") or []
    top = (countries or [{}])[0]
    rows = [{"label": c.get("label", "-"), "visits": f"{c.get('visits',0):,}",
             "pct": f"{c.get('percent',0)}%"} for c in countries[:10]]
    ui_node = ui.DataTable(
        columns=[ui.DataColumn(key="label", label="Country", width="50%"),
                 ui.DataColumn(key="visits", label="Visits", width="25%"),
                 ui.DataColumn(key="pct", label="Share", width="25%")],
        rows=rows,
    ) if rows else ui.Empty(message="No data")
    return ActionResult.success(
        data=data,
        summary=f"Top country: {top.get('label', 'n/a')} ({top.get('percent', 0)}%)",
        ui=ui_node,
    )


@chat.function("entry_exit",
               description="Top landing pages (where sessions start) + top exit pages (where visitors leave). "
                           "Use for: где люди выходят, на каких страницах уходят, exit pages, "
                           "точки входа, landing pages, корзина теряет людей, где теряем посетителей.",
               action_type="read", data_model=AnalyticsScalarResponse)
async def fn_entry_exit(ctx, params: _PeriodParams) -> ActionResult:
    """Return entry and exit page rankings."""
    data = await call_mos(ctx, "/api/matomo-analytics/entry-exit", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    return ActionResult.success(
        data=data,
        summary=f"{len(data.get('entry_pages', []))} entry / {len(data.get('exit_pages', []))} exit pages",
    )


# ─── IPC - other extensions call these to compose cross-ext reports ───

@ext.expose("real_time")
async def ipc_real_time(ctx) -> ActionResult:
    """Handler: ipc_real_time."""
    data = await call_mos(ctx, "/api/matomo-analytics/real-time", {})
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data)


@ext.expose("sources")
async def ipc_sources(ctx, period: str = "week", date: str = "today") -> ActionResult:
    """Handler: ipc_sources."""
    data = await call_mos(ctx, "/api/matomo-analytics/sources", {"period": period, "date": date})
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data)


@ext.expose("devices")
async def ipc_devices(ctx, period: str = "week", date: str = "today") -> ActionResult:
    """Handler: ipc_devices."""
    data = await call_mos(ctx, "/api/matomo-analytics/devices", {"period": period, "date": date})
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data)


@ext.expose("geo")
async def ipc_geo(ctx, period: str = "week", date: str = "today", limit: int = 10) -> ActionResult:
    """Handler: ipc_geo."""
    data = await call_mos(ctx, "/api/matomo-analytics/geo", {
        "period": period, "date": date, "limit": limit,
    })
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data)
