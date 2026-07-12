"""Insights + AI-powered reports. Rule-based insights are FREE (server-side);
the AI reports burn user tokens and only run on explicit user invocation.
"""
# No `from __future__ import annotations` - V6 validator needs real annotations.

import asyncio

from imperal_sdk import ui
from imperal_sdk.types import ActionResult
from pydantic import BaseModel, Field

from app import chat, ext, save_result
from api_client import call_mos, HEAVY_TIMEOUT
from params import _SITE_HELP
from response_models import InsightsResponse, DailyReportResponse, AlertListResponse


class _EmptyParams(BaseModel):
    site: str = Field(default="", description=_SITE_HELP)


_SEV_TYPE = {"critical": "error", "warning": "warn", "info": "info"}


def _err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


def _insights_ui(data: dict):
    items = data.get("insights") or []
    if not items:
        return ui.Alert(message="All green - no anomalies detected.", type="info")
    return ui.Stack(children=[
        ui.Alert(
            title=i.get("severity", "info").upper(),
            message=f"{i.get('title','')} - {i.get('detail','')}\n-> {i.get('action','')}",
            type=_SEV_TYPE.get(i.get("severity"), "info"),
        ) for i in items[:8]
    ])


@chat.function("insights",
               description="Actionable insights: traffic drops, high bounce hotspots, growing/dying pages. "
                           "Free, no AI tokens. "
                           "Use for: что нужно исправить, аномалии, проблемы с сайтом, "
                           "что плохо работает, что делать, где теряем трафик, recommendations.",
               action_type="read",
               event="analytics.action.result",
               data_model=InsightsResponse)
async def fn_insights(ctx, params: _EmptyParams) -> ActionResult:
    """Handler: fn_insights."""
    data = await call_mos(ctx, "/api/matomo-analytics/insights", {}, site=params.site)
    if "error" in data:
        return _err(data)
    await save_result(ctx, "insights", "What to do", data)
    crit = data.get("critical_count", 0)
    warn = data.get("warning_count", 0)
    return ActionResult.success(
        data=data,
        summary=f"{data.get('count', 0)} insights — {crit} critical, {warn} warnings",
        ui=_insights_ui(data),
    )


@chat.function("daily_report",
               description="Daily traffic brief with AI narration. USES AI TOKENS. Runs in background — result auto-delivered to chat when done.",
               action_type="read",
               event="analytics.action.result",
               background=True, long_running=True,
               data_model=DailyReportResponse)
async def fn_daily_report(ctx, params: _EmptyParams) -> ActionResult:
    """Handler: fn_daily_report."""
    await ctx.progress(10, "Fetching traffic data...")
    traffic, trends, top, insights = await asyncio.gather(
        call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day", "date": "last7"}, site=params.site),
        call_mos(ctx, "/api/matomo-analytics/trends", {}, site=params.site),
        call_mos(ctx, "/api/matomo-analytics/top-pages", {"period": "day", "date": "yesterday", "limit": 5}, site=params.site),
        call_mos(ctx, "/api/matomo-analytics/insights", {}, site=params.site),
    )
    for d in (traffic, trends, top, insights):
        if "error" in d:
            return _err(d)
    await ctx.progress(50, "Generating AI brief...")

    cw = trends.get("current_week", 0)
    pw = trends.get("previous_week", 0)
    chg = trends.get("change_percent", 0)
    pages_lines = "\n".join(
        f"- {p['url']} ({p.get('views',0)} views)"
        for p in (top.get("pages") or [])[:5]
    )
    facts = (
        f"**Traffic last 7 days:** {traffic.get('visits',0):,} visits, "
        f"{traffic.get('pageviews',0):,} pageviews\n"
        f"**Week trend:** {cw:,} this vs {pw:,} last ({chg:+.1f}%)\n"
        f"**Yesterday top pages:**\n{pages_lines}\n"
        f"**Alerts:** {insights.get('critical_count',0)} critical, "
        f"{insights.get('warning_count',0)} warnings"
    )

    brief = facts
    try:
        result = await ctx.ai.complete(
            "Write a 3-sentence daily traffic brief. Be specific and actionable. "
            "Use only the numbers provided - do not invent any.\n\n" + facts,
        )
        brief = getattr(result, "text", None) or facts
    except Exception:
        pass

    await ctx.progress(90, "Saving...")
    await save_result(ctx, "daily_report", "Daily brief", {
        "brief": brief, "facts": facts, "insights": insights,
    })
    return ActionResult.success(
        data={"brief": brief, "facts": facts},
        summary="Daily brief",
        ui=ui.Stack(children=[
            ui.Markdown(content=brief),
            ui.Divider(),
            _insights_ui(insights),
        ]),
    )


@chat.function("anomaly_check",
               description="Spot anomalies against the last 7 days. Free (no AI tokens).",
               action_type="read",
               event="analytics.action.result",
               data_model=AlertListResponse)
async def fn_anomaly_check(ctx, params: _EmptyParams) -> ActionResult:
    """Handler: fn_anomaly_check."""
    data = await call_mos(ctx, "/api/matomo-analytics/insights", {}, site=params.site)
    if "error" in data:
        return _err(data)
    alerts = [i for i in (data.get("insights") or [])
              if i.get("severity") in ("critical", "warning")]
    await save_result(ctx, "anomaly_check", "Anomalies", {"alerts": alerts, "count": len(alerts)})
    ui_node = (
        ui.Alert(message="No anomalies — traffic looks normal.", type="info")
        if not alerts else
        ui.Stack(children=[
            ui.Alert(
                title=a.get("severity", "warning").upper(),
                message=f"{a.get('title', '')} — {a.get('detail', '')}\n→ {a.get('action', '')}",
                type=_SEV_TYPE.get(a.get("severity"), "warning"),
            ) for a in alerts
        ])
    )
    return ActionResult.success(
        data={"alerts": alerts, "count": len(alerts)},
        summary=f"{len(alerts)} alert(s)",
        ui=ui_node,
    )


# ─── IPC - other extensions pull insights into their own reports ───

@ext.expose("insights")
async def ipc_insights(ctx, site: str = "") -> ActionResult:
    """Handler: ipc_insights."""
    data = await call_mos(ctx, "/api/matomo-analytics/insights", {}, site=site)
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data, summary="Insights fetched.")


@ext.expose("daily_summary")
async def ipc_daily_summary(ctx, site: str = "") -> ActionResult:
    """IPC: raw facts only (no AI). For aggregators like imperal-reports."""
    traffic = await call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day", "date": "last7"}, site=site)
    trends = await call_mos(ctx, "/api/matomo-analytics/trends", {}, site=site)
    insights = await call_mos(ctx, "/api/matomo-analytics/insights", {}, site=site)
    for d in (traffic, trends, insights):
        if "error" in d:
            return _err(d)
    return ActionResult.success(
        data={"traffic": traffic, "trends": trends, "insights": insights},
        summary="Daily summary facts fetched.",
    )
