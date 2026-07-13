"""Center overlay panel — rich analytics hub with all key metrics."""
from __future__ import annotations

import asyncio

from imperal_sdk import ui

from app import ext, load_settings, matomo_ready, active_site_label
from api_client import call_mos, ensure_known_domains
from panels_render import kpi_stats, chart, pages_table, breakdown_table
from panels_settings_render import settings_form


REFRESH = "on_event:analytics.action.result"


def _domain_selector(s: dict) -> ui.UINode | None:
    """Same domain-level switcher as panels_side.py's sidebar - kept as an
    independent copy rather than a cross-file import, matching this
    codebase's existing pattern (sidebar/settings each have their own copy
    of similar selectors) rather than coupling panel modules together."""
    sites = s.get("sites") or []
    active_label = active_site_label(s)
    active = next((site for site in sites if site.get("label") == active_label), None)
    domains = (active or {}).get("known_domains") or []
    if len(domains) < 2:
        return None
    segment = (active or {}).get("segment") or ""
    current = segment[len("pageUrl=^"):] if segment.startswith("pageUrl=^") else "All domains"
    return ui.Form(
        action="view_domain",
        submit_label="View",
        defaults={"site_id": active["site_id"]},
        children=[
            ui.Select(
                options=[{"value": "All domains", "label": "All domains"}]
                        + [{"value": d, "label": d} for d in domains],
                value=current,
                param_name="domain",
            ),
        ],
    )


@ext.panel("analytics_hub", slot="center", title="Analytics Dashboard",
           icon="icon.svg", refresh=REFRESH, center_overlay=True)
async def hub_panel(ctx, view: str = "", **_kw):
    """Center overlay analytics dashboard — traffic, trends, top pages, sources."""
    # Close/back: show empty state
    if view == "close":
        return ui.Empty(message="Analytics closed. Click '📊 Open Dashboard' in the left panel to reopen.")

    # Settings view
    if view == "settings":
        s = await ensure_known_domains(ctx, await load_settings(ctx))
        return ui.Stack(children=[
            ui.Stack(direction="h", justify="between", align="center", children=[
                ui.Header(text="⚙️ Analytics Settings", level=3),
                ui.Button(label="← Back", size="sm", variant="ghost",
                          on_click=ui.Call("__panel__analytics_hub", view="")),
            ]),
            settings_form(s),
        ])

    s = await load_settings(ctx)
    if not matomo_ready(s):
        return ui.Stack(children=[
            ui.Header(text="📊 Analytics", level=3),
            ui.Alert(
                message="Configure Matomo URL + Auth Token in Analytics settings to see your traffic data.",
                type="warning",
            ),
            ui.Button(label="⚙️ Open Settings", on_click=ui.Call("__panel__analytics_hub", view="settings")),
        ])
    s = await ensure_known_domains(ctx, s)

    # 6 parallel calls — insights removed to keep render under Temporal 30s timeout.
    # insights is expensive (5 sequential Matomo calls inside MOS) and not needed for
    # the visual dashboard. Ask Webbee "что нужно сделать?" to get insights on demand.
    # traffic_summary (period=month) gives bounce_rate + avg_time alongside the series.
    traffic_summary, traffic, trends, top, sources, devices, rt = await asyncio.gather(
        call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "month", "date": "today"}),
        call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day", "date": "last30"}),
        call_mos(ctx, "/api/matomo-analytics/trends", {}),
        call_mos(ctx, "/api/matomo-analytics/top-pages", {"period": "month", "date": "today", "limit": 10}),
        call_mos(ctx, "/api/matomo-analytics/sources", {"period": "month", "date": "today"}),
        call_mos(ctx, "/api/matomo-analytics/devices", {"period": "month", "date": "today"}),
        call_mos(ctx, "/api/matomo-analytics/real-time", {}),
        return_exceptions=True,
    )

    def safe(r):
        return r if not isinstance(r, Exception) else {}

    traffic_summary = safe(traffic_summary)
    traffic   = safe(traffic)
    trends    = safe(trends)
    top       = safe(top)
    sources   = safe(sources)
    devices   = safe(devices)
    rt        = safe(rt)

    # ── Header: live counter + host ───────────────────────────────────────────
    live     = (rt.get("live_30m") or {}).get("visitors", 0)
    host_url = (s.get("matomo_url", "") or "").replace("https://", "").replace("http://", "")[:40]
    change   = trends.get("change_percent", 0)
    direction = trends.get("direction", "flat")
    site     = active_site_label(s)
    multi_site = len(s.get("sites") or []) > 1

    header = ui.Stack(direction="h", justify="between", align="center", children=[
        ui.Stack(direction="h", gap=4, children=[
            ui.Header(text="📊 Analytics", level=3),
            *([ui.Badge(label=site, color="violet")] if multi_site else []),
            ui.Badge(label=f"● {live} live", color="green" if live > 0 else "gray"),
        ]),
        ui.Stack(direction="h", gap=2, children=[
            ui.Badge(label=host_url, color="gray"),
            ui.Button(label="⚙️", size="sm", variant="ghost",
                      on_click=ui.Call("__panel__analytics_hub", view="settings")),
            ui.Button(label="✕", size="sm", variant="ghost",
                      on_click=ui.Call("__panel__analytics_hub", view="close")),
        ]),
    ])
    domain_selector = _domain_selector(s)

    # ── KPI stats row ─────────────────────────────────────────────────────────
    series    = traffic.get("series") or []
    total_v   = sum(s.get("visits", 0) for s in series)
    total_pv  = sum(s.get("pageviews", 0) for s in series)
    today     = series[-1].get("visits", 0) if series else 0
    yesterday = series[-2].get("visits", 0) if len(series) >= 2 else 0
    # Bounce rate and avg time come from the monthly summary (not time series)
    bounce_raw = traffic_summary.get("bounce_rate", "")
    bounce_str = str(bounce_raw).rstrip("%").strip()
    try:
        bounce = float(bounce_str) if bounce_str and bounce_str != "0" else 0
    except (ValueError, TypeError):
        bounce = 0
    avg_time = traffic_summary.get("avg_time_on_site", 0) or 0

    kpis = ui.Stats(children=[
        ui.Stat(label="Live (30m)",   value=str(live),          color="violet", icon="Users"),
        ui.Stat(label="Today",        value=f"{today:,}",        color="blue",   icon="TrendingUp"),
        ui.Stat(label="Yesterday",    value=f"{yesterday:,}",    color="gray"),
        ui.Stat(label="Last 30d",     value=f"{total_v:,}",      color="blue",   icon="Eye"),
        ui.Stat(label="Pageviews",    value=f"{total_pv:,}",     color="gray",   icon="FileText"),
        ui.Stat(label="WoW Δ",        value=f"{change:+.1f}%",
                color="green" if direction == "up" else "red" if direction == "down" else "gray",
                icon="TrendingUp"),
        ui.Stat(label="Bounce",       value=f"{bounce:.0f}%" if bounce else "—", color="yellow"),
        ui.Stat(label="Avg time",     value=f"{int(avg_time//60)}m {int(avg_time%60)}s" if avg_time else "—"),
    ])

    # ── Traffic chart (30 days) ───────────────────────────────────────────────
    # Exclude today (last element) — partial day causes misleading spike down.
    # Use series[-31:-1] to get 30 complete days ending yesterday.
    complete_series = series[-31:-1] if len(series) > 1 else series
    chart_data = [
        {"date": s.get("date", "")[-5:], "visits": s.get("visits", 0), "pv": s.get("pageviews", 0)}
        for s in complete_series
    ]
    traffic_chart = ui.Section(title="Traffic — Last 30 days (through yesterday)", collapsible=False, children=[
        ui.Chart(
            type="line",
            data=chart_data,
            x_key="date",
            y2_keys=["visits", "pv"],
            colors={"visits": "#3b82f6", "pv": "#8b5cf6"},
            height=180,
        ) if chart_data else ui.Text(content="No traffic data", variant="caption"),
    ])

    # ── Top pages ─────────────────────────────────────────────────────────────
    top_pages_data = top.get("pages") or []
    top_rows = [
        {
            "page":   (p.get("title") or p.get("url", "—"))[:45],
            "views":  f"{p.get('views', 0):,}",
            "bounce": p.get("bounce_rate", "—"),
            "time":   f"{int(p.get('avg_time', 0)//60)}m{int(p.get('avg_time', 0)%60)}s" if p.get("avg_time") else "—",
        }
        for p in top_pages_data[:10]
    ]
    top_section = ui.Section(title=f"🏆 Top Pages (last 30d)", collapsible=True, children=[
        ui.DataTable(
            columns=[
                ui.DataColumn(key="page",   label="Page",     width="50%"),
                ui.DataColumn(key="views",  label="Views",    width="17%"),
                ui.DataColumn(key="bounce", label="Bounce",   width="16%"),
                ui.DataColumn(key="time",   label="Avg time", width="17%"),
            ],
            rows=top_rows,
        ) if top_rows else ui.Text(content="No page data", variant="caption"),
    ])

    # ── Traffic sources ───────────────────────────────────────────────────────
    src_data = sources.get("sources") or []
    src_rows = [
        {
            "source": s.get("label", "—")[:30],
            "visits": f"{s.get('visits', 0):,}",
            "pct":    f"{s.get('percent', 0):.1f}%",
        }
        for s in src_data[:8]
    ]
    src_chart = [{"label": s.get("label","")[:15], "value": s.get("visits", 0)} for s in src_data[:6]]
    sources_section = ui.Section(title="📡 Traffic Sources", collapsible=True, children=[
        ui.Chart(
            type="bar",
            data=src_chart,
            x_key="label",
            y2_keys=["value"],
            colors={"value": "#22c55e"},
            height=120,
        ) if src_chart else ui.Empty(message=""),
        ui.DataTable(
            columns=[
                ui.DataColumn(key="source", label="Source", width="55%"),
                ui.DataColumn(key="visits", label="Visits", width="25%"),
                ui.DataColumn(key="pct",    label="%",      width="20%"),
            ],
            rows=src_rows,
        ) if src_rows else ui.Text(content="No source data", variant="caption"),
    ])

    # ── Devices ───────────────────────────────────────────────────────────────
    dev_data = devices.get("devices") or []
    dev_chart = [{"label": d.get("label","")[:12], "value": d.get("visits", 0)} for d in dev_data[:5]]
    devices_section = ui.Section(title="📱 Devices", collapsible=True, children=[
        ui.Chart(
            type="bar",
            data=dev_chart,
            x_key="label",
            y2_keys=["value"],
            colors={"value": "#f97316"},
            height=100,
        ) if dev_chart else ui.Text(content="No device data", variant="caption"),
    ])

    return ui.Stack(children=[
        header,
        *([domain_selector] if domain_selector else []),
        kpis,
        ui.Divider(),
        traffic_chart,
        top_section,
        sources_section,
        devices_section,
    ])
