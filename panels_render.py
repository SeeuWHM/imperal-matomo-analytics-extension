"""Pure-render helpers for the workspace dashboard.

Kept separate from panels_side.py so neither file blows past the 300-line
platform limit. Every function here is stateless - pass it the gathered
data dict and it returns a UINode.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import matomo_ready


SEV_TYPE = {"critical": "error", "warning": "warn", "info": "info"}


def kpi_stats(d: dict) -> ui.UINode:
    traffic = d.get("traffic") or {}
    trends = d.get("trends") or {}
    rt = (d.get("real_time") or {}).get("live_30m") or {}
    series = traffic.get("series") or []
    today = series[-1]["visits"] if series else 0
    yesterday = series[-2]["visits"] if len(series) >= 2 else 0
    week = sum(s.get("visits", 0) for s in series)
    change = trends.get("change_percent", 0)
    direction = trends.get("direction", "flat")

    return ui.Stats(children=[
        ui.Stat(label="Live (30 min)", value=str(rt.get("visitors", 0)),
                color="violet", icon="Users"),
        ui.Stat(label="Today", value=f"{today:,}", color="blue"),
        ui.Stat(label="Yesterday", value=f"{yesterday:,}", color="gray"),
        ui.Stat(label="Last 7d", value=f"{week:,}", color="blue"),
        ui.Stat(label="WoW Δ", value=f"{change:+.1f}%",
                color="green" if direction == "up"
                else "red" if direction == "down" else "gray"),
    ])


def chart(traffic: dict) -> ui.UINode:
    series = traffic.get("series") or []
    if not series:
        return ui.Empty(message="No traffic data yet.")
    data = [
        {"date": s["date"][-5:], "visits": s.get("visits", 0),
         "pageviews": s.get("pageviews", 0)}
        for s in series
    ]
    return ui.Chart(type="line", data=data, x_key="date", height=220)


def insights_cards(insights: dict) -> ui.UINode:
    items = insights.get("insights") or []
    if not items:
        return ui.Alert(message="All green - no anomalies detected in the last 7 days.",
                        type="info")
    return ui.Stack(children=[
        ui.Alert(
            message=f"{i.get('title', '')} - {i.get('detail', '')}\n-> {i.get('action', '')}",
            title=(i.get("severity", "info")).upper(),
            type=SEV_TYPE.get(i.get("severity"), "info"),
        ) for i in items[:8]
    ])


def pages_table(pages: list) -> ui.UINode:
    if not pages:
        return ui.Empty(message="No data")
    return ui.DataTable(
        columns=[
            ui.DataColumn(key="url", label="Page", width="60%"),
            ui.DataColumn(key="views", label="Visits", width="20%"),
            ui.DataColumn(key="bounce_rate", label="Bounce", width="20%"),
        ],
        rows=[{"url": (p.get("url") or "/")[:70],
               "views": f"{p.get('views', 0):,}",
               "bounce_rate": p.get("bounce_rate", "-")}
              for p in pages[:15]],
    )


def breakdown_table(items: list, title_col: str) -> ui.UINode:
    if not items:
        return ui.Empty(message="No data")
    return ui.DataTable(
        columns=[
            ui.DataColumn(key="label", label=title_col, width="60%"),
            ui.DataColumn(key="visits", label="Visits", width="20%"),
            ui.DataColumn(key="percent", label="Share", width="20%"),
        ],
        rows=[{"label": it.get("label", "-"),
               "visits": f"{it.get('visits', 0):,}",
               "percent": f"{it.get('percent', 0)}%"}
              for it in items[:10]],
    )


def entry_exit_table(rows: list, count_key: str, label: str) -> ui.UINode:
    if not rows:
        return ui.Empty(message="No data")
    return ui.DataTable(
        columns=[
            ui.DataColumn(key="url", label="Page", width="60%"),
            ui.DataColumn(key=count_key, label=label, width="20%"),
            ui.DataColumn(key="bounce_rate", label="Bounce", width="20%"),
        ],
        rows=[{"url": (r.get("url") or "/")[:70],
               count_key: f"{r.get(count_key, 0):,}",
               "bounce_rate": r.get("bounce_rate", "-")}
              for r in rows[:10]],
    )


_RESULT_LABELS = {
    "insights": "What to do",
    "anomaly_check": "Anomalies",
    "real_time": "Live visitors",
    "top_pages": "Top 10 pages",
    "trends": "Week vs last week",
    "sources": "Traffic sources",
    "geo": "Top countries",
    "daily_report": "Daily brief",
}


def _render_result_body(action: str, data: dict) -> ui.UINode:
    if action == "insights":
        return insights_cards(data)
    if action == "anomaly_check":
        alerts = data.get("alerts") or []
        if not alerts:
            return ui.Alert(message="No anomalies — traffic looks normal.", type="info")
        return ui.Stack(children=[
            ui.Alert(
                title=a.get("severity", "warning").upper(),
                message=f"{a.get('title', '')}: {a.get('detail', '')}\n→ {a.get('action', '')}",
                type=SEV_TYPE.get(a.get("severity"), "warning"),
            ) for a in alerts
        ])
    if action == "real_time":
        c30 = data.get("live_30m") or {}
        c60 = data.get("live_60m") or {}
        c180 = data.get("live_180m") or {}
        return ui.Stats(children=[
            ui.Stat(label="Last 30 min", value=str(c30.get("visitors", 0)),
                    color="green", icon="Users"),
            ui.Stat(label="Last 60 min", value=str(c60.get("visitors", 0)), color="blue"),
            ui.Stat(label="Last 3 h", value=str(c180.get("visitors", 0)), color="gray"),
        ])
    if action == "top_pages":
        return pages_table(data.get("pages") or [])
    if action == "trends":
        cw = data.get("current_week", 0)
        pw = data.get("previous_week", 0)
        chg = data.get("change_percent", 0)
        color = "green" if data.get("direction") == "up" else \
                "red" if data.get("direction") == "down" else "gray"
        return ui.Stats(children=[
            ui.Stat(label="This week", value=f"{cw:,}", color=color),
            ui.Stat(label="Last week", value=f"{pw:,}", color="gray"),
            ui.Stat(label="WoW Δ", value=f"{chg:+.1f}%", color=color),
        ])
    if action == "sources":
        return breakdown_table(data.get("sources") or [], "Source")
    if action == "geo":
        return breakdown_table(data.get("countries") or [], "Country")
    if action == "devices":
        return breakdown_table(data.get("devices") or [], "Device type")
    if action in ("resolutions", "screen_resolutions"):
        return breakdown_table(data.get("resolutions") or [], "Resolution")
    if action == "browsers":
        items = data.get("browsers") or []
        os_items = data.get("os_families") or []
        parts: list = [breakdown_table(items, "Browser")]
        if os_items:
            parts += [ui.Divider(), breakdown_table(os_items, "OS")]
        return ui.Stack(children=parts)
    if action == "brands":
        items = data.get("brands") or []
        models = data.get("models") or []
        parts: list = [breakdown_table(items, "Device brand")]
        if models:
            parts += [ui.Divider(), breakdown_table(models, "Model")]
        return ui.Stack(children=parts)
    if action == "languages":
        return breakdown_table(data.get("languages") or [], "Language")
    if action == "providers":
        return breakdown_table(data.get("providers") or [], "Network provider")
    if action == "new_returning":
        new_pct = data.get("new_percent", 0)
        ret_pct = data.get("returning_percent", 0)
        new_v   = data.get("new_visits", 0)
        ret_v   = data.get("returning_visits", 0)
        return ui.Stats(children=[
            ui.Stat(label="New visitors",       value=f"{new_pct}%",   color="green",
                    icon="UserPlus", trend=f"{new_v:,} visits"),
            ui.Stat(label="Returning visitors", value=f"{ret_pct}%",   color="blue",
                    icon="Repeat",   trend=f"{ret_v:,} visits"),
        ])
    if action == "visit_duration":
        return breakdown_table(data.get("buckets") or [], "Session duration")
    if action == "regions":
        parts: list = []
        cities = data.get("cities") or []
        regions = data.get("regions") or []
        if cities:
            parts.append(breakdown_table(cities, "City"))
        if regions:
            if parts:
                parts.append(ui.Divider())
            parts.append(breakdown_table(regions, "Region"))
        return ui.Stack(children=parts) if parts else ui.Empty(message="No region data")
    if action == "entry_exit":
        entries = data.get("entries") or []
        exits   = data.get("exits") or []
        parts: list = []
        if entries:
            parts.append(breakdown_table(entries, "Entry page"))
        if exits:
            if parts:
                parts.append(ui.Divider())
            parts.append(breakdown_table(exits, "Exit page"))
        return ui.Stack(children=parts) if parts else ui.Empty(message="No entry/exit data")
    if action in ("search_engines", "search-engines"):
        return breakdown_table(data.get("search_engines") or [], "Search engine")
    if action in ("referring_sites", "referring-sites"):
        return breakdown_table(data.get("sites") or [], "Referring site")
    if action == "page_details":
        pages = data.get("pages") or []
        rows = [
            {"url": p.get("url", "/")[-50:], "time": str(p.get("avg_time_on_page", 0)) + "s",
             "bounce": p.get("bounce_rate", "0%")}
            for p in pages[:15]
        ]
        return ui.DataTable(
            columns=[
                ui.DataColumn(key="url",    label="Page",       width="55%"),
                ui.DataColumn(key="time",   label="Avg time",   width="22%"),
                ui.DataColumn(key="bounce", label="Bounce",     width="23%"),
            ],
            rows=rows,
        ) if rows else ui.Empty(message="No page data")
    if action == "daily_report":
        brief = data.get("brief") or data.get("facts") or ""
        ins = data.get("insights") or {}
        parts: list = []
        if brief:
            parts.append(ui.Markdown(content=brief))
            parts.append(ui.Divider())
        parts.append(insights_cards(ins))
        return ui.Stack(children=parts)
    return ui.Empty(message="Result ready.")


def result_zone(result_doc: dict | None) -> ui.UINode:
    """Dedicated panel area that shows the last chat result persistently."""
    if not result_doc:
        return ui.Empty(message="Ask Webbee — results appear here.")
    action = result_doc.get("action", "")
    title = result_doc.get("title") or _RESULT_LABELS.get(action, "Result")
    body = _render_result_body(action, result_doc.get("data") or {})
    return ui.Section(title=f"↳ {title}", children=[body])


def _masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return "••••" + value[-4:]


def settings_form(s: dict) -> ui.UINode:
    status = ui.Badge(
        label="Matomo connected" if matomo_ready(s) else "Matomo not configured",
        color="green" if matomo_ready(s) else "red",
    )
    form = ui.Form(
        action="save_settings",
        submit_label="Save settings",
        children=[
            ui.Input(placeholder="Backend URL - https://api.example.com",
                     value=s.get("backend_url", ""), param_name="backend_url"),
            ui.Input(
                placeholder=(f"Backend API Key - current {_masked(s.get('backend_api_key', ''))}"
                             if s.get("backend_api_key") else "Backend API Key / Bearer token"),
                value="", param_name="backend_api_key",
            ),
            ui.Input(placeholder="Matomo URL - https://analytics.example.com",
                     value=s.get("matomo_url", ""), param_name="matomo_url"),
            ui.Input(
                placeholder=(f"Auth Token - current {_masked(s.get('matomo_token', ''))}"
                             if s.get("matomo_token") else "Matomo Auth Token"),
                value="", param_name="matomo_token",
            ),
            ui.Input(placeholder="Site ID - e.g. 1",
                     value=str(s.get("matomo_site_id", 1)), param_name="matomo_site_id"),
            ui.Input(placeholder="Segment (optional) - pageUrl=^https://blog.example.com",
                     value=s.get("matomo_segment", ""), param_name="matomo_segment"),
            ui.Input(placeholder="Blog URL (optional) - https://blog.example.com",
                     value=s.get("blog_url", ""), param_name="blog_url"),
            ui.Input(placeholder="Blog Site ID (optional) - if blog is a separate Matomo site, e.g. 2",
                     value=str(s.get("blog_site_id") or ""), param_name="blog_site_id"),
            ui.Input(placeholder="UTM source Dimension ID (optional) - e.g. 8",
                     value=str(s.get("utm_source_dim_id") or ""), param_name="utm_source_dim_id"),
        ],
    )
    return ui.Stack(children=[
        status,
        ui.Text(content=("Your backend URL/API key and Matomo URL/Auth Token are stored encrypted per-user. "
                         "This extension uses your own backend + your own Matomo connection."),
                variant="caption"),
        ui.Divider(),
        form,
        ui.Text(content="Leave a field blank to keep the current value.",
                variant="caption"),
    ])
