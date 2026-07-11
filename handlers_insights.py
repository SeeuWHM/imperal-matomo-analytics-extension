"""Insights + AI-powered reports. Rule-based insights are FREE (server-side);
the AI reports burn user tokens and only run on explicit user invocation.
"""
# No `from __future__ import annotations` - V6 validator needs real annotations.

import asyncio

from imperal_sdk import ui
from imperal_sdk.types import ActionResult
from pydantic import BaseModel, Field

from app import chat, ext, save_result, load_settings
from api_client import call_mos, HEAVY_TIMEOUT
from params import _DATE_HELP, _PERIOD_HELP
from response_models import InsightsResponse, DailyReportResponse, AlertListResponse, AnalyticsScalarResponse


class _EmptyParams(BaseModel):
    pass


class _BlogParams(BaseModel):
    period: str = Field(default="month", description=_PERIOD_HELP)
    date: str   = Field(default="today", description=_DATE_HELP)


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
    data = await call_mos(ctx, "/api/analytics/insights", {})
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
        call_mos(ctx, "/api/analytics/traffic", {"period": "day", "date": "last7"}),
        call_mos(ctx, "/api/analytics/trends", {}),
        call_mos(ctx, "/api/analytics/top-pages", {"period": "day", "date": "yesterday", "limit": 5}),
        call_mos(ctx, "/api/analytics/insights", {}),
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
    data = await call_mos(ctx, "/api/analytics/insights", {})
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
async def ipc_insights(ctx) -> ActionResult:
    """Handler: ipc_insights."""
    data = await call_mos(ctx, "/api/analytics/insights", {})
    if "error" in data:
        return _err(data)
    return ActionResult.success(data=data)


@ext.expose("daily_summary")
async def ipc_daily_summary(ctx) -> ActionResult:
    """IPC: raw facts only (no AI). For aggregators like imperal-reports."""
    traffic = await call_mos(ctx, "/api/analytics/traffic", {"period": "day", "date": "last7"})
    trends = await call_mos(ctx, "/api/analytics/trends", {})
    insights = await call_mos(ctx, "/api/analytics/insights", {})
    for d in (traffic, trends, insights):
        if "error" in d:
            return _err(d)
    return ActionResult.success(data={
        "traffic": traffic, "trends": trends, "insights": insights,
    })


# ─── blog_analytics ───────────────────────────────────────────────────────────

@chat.function("blog_analytics",
               description=(
                   "Traffic and top content for the blog subdomain only (e.g. blog.example.com). "
                   "Filters Matomo to blog pages, shows top articles, traffic, trends. "
                   "Use for: аналитика блога, топ статьи, трафик блога, "
                   "blog traffic, which articles perform best, блог статистика, "
                   "blog.webhostmost.com, контент который читают."
               ),
               action_type="read", event="analytics.action.result", data_model=AnalyticsScalarResponse)
async def fn_blog_analytics(ctx, params: _BlogParams) -> ActionResult:
    """Handler: fn_blog_analytics."""
    s = await load_settings(ctx)
    blog_url = (s.get("blog_url") or "").strip().rstrip("/")

    if not blog_url:
        return ActionResult.success(
            data={},
            summary="Blog URL not configured — add blog URL in Analytics Settings",
            ui=ui.Alert(
                message="Set your blog URL in Analytics Settings (e.g. https://blog.webhostmost.com) "
                        "to enable blog-specific analytics.",
                type="warning",
            ),
        )

    # Build Matomo segment for blog pages
    blog_segment = f"pageUrl=^{blog_url}"
    # Use blog_site_id if explicitly configured (blog may be on a different Matomo site)
    raw_blog_site = s.get("blog_site_id") or 0
    blog_site_override = {"site_id": int(raw_blog_site)} if raw_blog_site else {}

    traffic, top_pages, insights = await asyncio.gather(
        call_mos(ctx, "/api/analytics/traffic", {
            "period": params.period, "date": params.date, "segment": blog_segment,
            **blog_site_override,
        }),
        call_mos(ctx, "/api/analytics/top-pages", {
            "period": params.period, "date": params.date, "limit": 10, "segment": blog_segment,
            **blog_site_override,
        }),
        call_mos(ctx, "/api/analytics/insights", {"segment": blog_segment, **blog_site_override}),
    )

    for d in (traffic, top_pages, insights):
        if "error" in d:
            return ActionResult.error(error=d.get("error", "unknown error"))

    await save_result(ctx, "blog_analytics", "Blog analytics", {
        "traffic": traffic, "top_pages": top_pages, "insights": insights,
    })

    visits   = traffic.get("visits", 0)
    pv       = traffic.get("pageviews", 0)
    pages    = top_pages.get("pages") or []
    top_art  = pages[0].get("url", "—") if pages else "—"
    top_v    = pages[0].get("views", 0) if pages else 0
    crit     = insights.get("critical_count", 0)
    warn     = insights.get("warning_count", 0)

    rows = [
        {
            "article": (p.get("url") or "/")[-60:],
            "views":   f"{p.get('views', 0):,}",
            "bounce":  p.get("bounce_rate", "—"),
            "time":    f"{int(p.get('avg_time', 0)//60)}m{int(p.get('avg_time', 0)%60)}s" if p.get("avg_time") else "—",
        }
        for p in pages[:10]
    ]

    table = ui.DataTable(
        columns=[
            ui.DataColumn(key="article", label="Article",  width="50%"),
            ui.DataColumn(key="views",   label="Views",    width="17%"),
            ui.DataColumn(key="bounce",  label="Bounce",   width="16%"),
            ui.DataColumn(key="time",    label="Avg time", width="17%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No blog posts found for this period")

    return ActionResult.success(
        data={"traffic": traffic, "top_pages": top_pages, "insights": insights},
        summary=(
            f"Blog {blog_url}: {visits:,} visits, {pv:,} pageviews | "
            f"Top: {top_art} ({top_v:,}) | Alerts: {crit} critical, {warn} warnings"
        ),
        ui=ui.Stack(children=[
            ui.Stats(children=[
                ui.Stat(label="Visits",    value=f"{visits:,}", color="blue", icon="FileText"),
                ui.Stat(label="Pageviews", value=f"{pv:,}",    color="gray"),
                ui.Stat(label="Articles",  value=str(len(pages)), color="violet"),
                ui.Stat(label="Alerts",    value=f"{crit}/{warn}",
                        color="red" if crit else "yellow" if warn else "green"),
            ]),
            table,
        ]),
    )
