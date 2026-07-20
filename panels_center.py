"""Center overlay panel — rich analytics hub with all key metrics.

Design notes (2026-07-20 audit fix):
- ONE period filter drives every section (KPIs, chart, top pages, sources,
  devices) so numbers never disagree with each other — before this, Top
  Pages/Sources/Devices silently used "month to date" while the label said
  "last 30d", and the KPI row mixed a rolling 30-day window with a
  month-to-date bounce rate. Now `range` picks a single Matomo
  (period, date) pair reused everywhere, and every section title states the
  real window in plain words.
- "Views" was ambiguous (Matomo's nb_hits/pageviews, not unique people).
  Every visit-count label now says exactly what it counts: Visits,
  Unique visitors, or Pageviews.
- Real auto-refresh isn't available: the SDK's declared panel refresh only
  supports "manual" and "on_event:..." — an `interval:Ns` poll was tried on
  another extension (mail-client) and the platform silently dropped it.
  Instead we give an honest manual "Refresh now" button that bypasses the
  cache for one real re-fetch, plus refresh-on-event for actions taken
  elsewhere in the extension.
"""
from __future__ import annotations

import asyncio

from imperal_sdk import ui

from app import ext, load_settings, matomo_ready, active_site_label
from api_client import call_mos_cached, ensure_known_domains, REALTIME_CACHE_TTL
from panels_settings_render import settings_form
# NOTE: this import is load-bearing. The platform can load this center-panel
# module on its own (to render the center overlay); importing panels_side here
# is what pulls in and registers the LEFT sidebar panel in that path. Removing
# it (v5.2.3) made the left panel silently disappear. Keep the cross-import —
# do NOT inline a local copy of _domain_selector again.
from panels_side import _domain_selector


REFRESH = "on_event:analytics.action.result"

# One filter drives every section — (Matomo period, Matomo date, human label).
# "today" intentionally uses period=day/date=today so the KPI row can show a
# same-day figure; every other option is a clean, complete-day range (no
# partial "today" contaminating averages/bounce-rate/top-pages sections).
RANGE_OPTIONS: dict[str, tuple[str, str, str]] = {
    "today":     ("day",   "today",     "Today"),
    "7d":        ("day",   "last7",     "Last 7 days"),
    "30d":       ("day",   "last30",    "Last 30 days"),
    "month":     ("month", "today",     "This month"),
}
DEFAULT_RANGE = "30d"


def _range_selector(current: str) -> ui.UINode:
    """Select fires on_change immediately (no submit button needed) — same
    proven pattern as other extensions' live account/folder switchers."""
    return ui.Select(
        options=[{"value": k, "label": v[2]} for k, v in RANGE_OPTIONS.items()],
        value=current,
        on_change=ui.Call("__panel__analytics_hub", view="", range="$value"),
        param_name="range",
    )


@ext.panel("analytics_hub", slot="center", title="Analytics Dashboard",
           icon="icon.svg", refresh=REFRESH, center_overlay=True)
async def hub_panel(ctx, view: str = "", range: str = DEFAULT_RANGE,
                     refresh_now: bool = False, **_kw):
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

    if range not in RANGE_OPTIONS:
        range = DEFAULT_RANGE
    period, date, range_label = RANGE_OPTIONS[range]

    # 7 parallel calls, all sharing the SAME period/date — insights excluded
    # to keep render under Temporal's 30s timeout (insights runs 5 sequential
    # Matomo calls inside MOS; ask Webbee "what should I fix?" for that on
    # demand instead). A separate always-30-day call feeds the trend chart so
    # switching the KPI range never blanks the visual history.
    (traffic, chart_traffic, trends, top, sources, devices, rt) = await asyncio.gather(
        call_mos_cached(ctx, "/api/matomo-analytics/traffic", {"period": period, "date": date},
                         bypass_cache=refresh_now),
        call_mos_cached(ctx, "/api/matomo-analytics/traffic", {"period": "day", "date": "last30"},
                         bypass_cache=refresh_now),
        call_mos_cached(ctx, "/api/matomo-analytics/trends", {}, bypass_cache=refresh_now),
        call_mos_cached(ctx, "/api/matomo-analytics/top-pages", {"period": period, "date": date, "limit": 10},
                         bypass_cache=refresh_now),
        call_mos_cached(ctx, "/api/matomo-analytics/sources", {"period": period, "date": date},
                         bypass_cache=refresh_now),
        call_mos_cached(ctx, "/api/matomo-analytics/devices", {"period": period, "date": date},
                         bypass_cache=refresh_now),
        call_mos_cached(ctx, "/api/matomo-analytics/real-time", {}, ttl_seconds=REALTIME_CACHE_TTL,
                         bypass_cache=refresh_now),
        return_exceptions=True,
    )

    def safe(r):
        return r if not isinstance(r, Exception) else {}

    traffic       = safe(traffic)
    chart_traffic = safe(chart_traffic)
    trends        = safe(trends)
    top           = safe(top)
    sources       = safe(sources)
    devices       = safe(devices)
    rt            = safe(rt)

    # ── Header: live counter + host + range filter + refresh ──────────────────
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
        ui.Stack(direction="h", gap=2, align="center", children=[
            ui.Badge(label=host_url, color="gray"),
            _range_selector(range),
            ui.Button(label="↻ Refresh", size="sm", variant="ghost",
                      on_click=ui.Call("__panel__analytics_hub", view="", range=range, refresh_now=True)),
            ui.Button(label="⚙️", size="sm", variant="ghost",
                      on_click=ui.Call("__panel__analytics_hub", view="settings")),
            ui.Button(label="✕", size="sm", variant="ghost",
                      on_click=ui.Call("__panel__analytics_hub", view="close")),
        ]),
    ])
    domain_selector = _domain_selector(s)

    # ── KPI stats row — everything here is for the SAME selected range ────────
    visits    = traffic.get("visits", 0)
    pageviews = traffic.get("pageviews", 0)
    uniques   = traffic.get("unique_visitors")
    bounce_raw = traffic.get("bounce_rate", "")
    bounce_str = str(bounce_raw).rstrip("%").strip()
    try:
        bounce = float(bounce_str) if bounce_str and bounce_str != "0" else 0
    except (ValueError, TypeError):
        bounce = 0
    avg_time = traffic.get("avg_time_on_site", 0) or 0

    # "Yesterday" always reads from the rolling 30-day daily series regardless
    # of the selected range filter, so it stays a stable point of comparison.
    daily_series = chart_traffic.get("series") or []
    yesterday_bucket = daily_series[-2] if len(daily_series) >= 2 else {}
    yesterday_visits = yesterday_bucket.get("visits", 0)

    kpis = ui.Stats(children=[
        ui.Stat(label="Live (30m)", value=str(live), color="violet", icon="Users"),
        ui.Stat(label=f"Visits ({range_label})", value=f"{visits:,}", color="blue", icon="TrendingUp"),
        *([ui.Stat(label="Unique visitors", value=f"{uniques:,}", color="teal", icon="User",
                   trend=f"of {visits:,} visits")] if uniques is not None else []),
        ui.Stat(label="Pageviews", value=f"{pageviews:,}", color="gray", icon="FileText"),
        ui.Stat(label="Yesterday", value=f"{yesterday_visits:,}", color="gray"),
        ui.Stat(label="WoW Δ", value=f"{change:+.1f}%",
                color="green" if direction == "up" else "red" if direction == "down" else "gray",
                icon="TrendingUp"),
        ui.Stat(label="Bounce", value=f"{bounce:.0f}%" if bounce else "—", color="yellow"),
        ui.Stat(label="Avg time", value=f"{int(avg_time//60)}m {int(avg_time%60)}s" if avg_time else "—"),
    ])

    # ── Traffic chart — always a stable rolling 30-day view (through
    # yesterday, excluding the partial "today" bucket which spikes down) ──────
    complete_series = daily_series[-31:-1] if len(daily_series) > 1 else daily_series
    chart_data = [
        {"date": s.get("date", "")[-5:], "visits": s.get("visits", 0), "pv": s.get("pageviews", 0)}
        for s in complete_series
    ]
    traffic_chart = ui.Section(title="Traffic — Last 30 days (through yesterday)", collapsible=False, children=[
        ui.Chart(
            type="line",
            data=chart_data,
            x_key="date",
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
    top_section = ui.Section(title=f"🏆 Top Pages ({range_label})", collapsible=True, children=[
        ui.DataTable(
            columns=[
                ui.DataColumn(key="page",   label="Page",       width="46%"),
                ui.DataColumn(key="views",  label="Pageviews",  width="18%"),
                ui.DataColumn(key="bounce", label="Bounce",     width="18%"),
                ui.DataColumn(key="time",   label="Avg time",   width="18%"),
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
    sources_section = ui.Section(title=f"📡 Traffic Sources ({range_label})", collapsible=True, children=[
        ui.Chart(
            type="bar",
            data=src_chart,
            x_key="label",
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
    devices_section = ui.Section(title=f"📱 Devices ({range_label})", collapsible=True, children=[
        ui.Chart(
            type="bar",
            data=dev_chart,
            x_key="label",
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
