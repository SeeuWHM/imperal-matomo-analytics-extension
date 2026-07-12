"""Left sidebar (passive status) + right workspace (dense dashboard).

Observed behaviour:
- `ui.Send(text)` does NOT fire from either slot in third-party extensions.
  Root cause: the platform's onAction handler checks j.current (a ref to
  the Webbee send function), but j.current is null in the right-panel slot.
  Fix: replace every ui.Send button with ui.Form(action="fn_name"), which
  calls the chat.function directly - no j.current needed.
- `ui.Tabs` renders but tab switching doesn't fire; we use collapsible
  `ui.Section`s instead.
- Render helpers live in panels_render.py so this file stays small.
"""
from __future__ import annotations

import asyncio

from imperal_sdk import ui

from app import ext, load_settings, load_result, matomo_ready
from api_client import call_mos
from panels_render import (
    kpi_stats, chart, insights_cards, pages_table,
    breakdown_table, entry_exit_table, settings_form, result_zone,
)


# ─────────────────────── Left sidebar ─────────────────────

@ext.panel("sidebar", slot="left", title="Analytics", icon="BarChart3",
           default_width=240,
           refresh="on_event:analytics.settings.saved")
async def sidebar_panel(ctx):
    s = await load_settings(ctx)
    configured = matomo_ready(s)
    host = (s.get("matomo_url", "") or "").replace("https://", "").replace("http://", "")[:40]

    if not configured:
        return ui.Stack(children=[
            ui.Header(text="Analytics", level=4),
            ui.Badge(label="* offline", color="red"),
            ui.Divider(),
            ui.Alert(message="Open the right panel -> Settings -> add Matomo URL + Auth Token.",
                     type="warn"),
        ])

    traffic, rt = await asyncio.gather(
        call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day", "date": "last7"}),
        call_mos(ctx, "/api/matomo-analytics/real-time", {}),
        return_exceptions=True,
    )
    series = (traffic.get("series") or []) if not isinstance(traffic, Exception) else []
    today = series[-1].get("visits", 0) if series else 0
    yesterday = series[-2].get("visits", 0) if len(series) >= 2 else 0
    live = (rt.get("live_30m") or {}).get("visitors", 0) if not isinstance(rt, Exception) else 0

    root = ui.Stack(children=[
        ui.Header(text="📊 Analytics", level=4),
        ui.Stack(children=[
            ui.Badge(label="● live", color="green"),
            ui.Text(content=host, variant="caption"),
        ], direction="h"),
        ui.Divider(),
        ui.Stats(children=[
            ui.Stat(label="Live", value=str(live), color="violet", icon="Users"),
            ui.Stat(label="Today", value=f"{today:,}", color="blue"),
            ui.Stat(label="Yesterday", value=f"{yesterday:,}", color="gray"),
        ]),
        ui.Divider(),
        ui.Button(
            label="📊 Open Dashboard",
            on_click=ui.Call("__panel__analytics_hub", view="", note_id="analytics"),
        ),
    ])
    # Auto-open center dashboard on first load — view="" forces main view
    root.props["auto_action"] = ui.Call("__panel__analytics_hub", view="", note_id="analytics").to_dict()
    return root


# ─────────────────────── Right workspace ─────────────────

async def _gather(ctx) -> dict:
    """Fan out dashboard queries in parallel. insights excluded — 5 sequential
    Matomo calls inside MOS push render time past Temporal's 30s timeout."""
    keys = ("traffic", "trends", "top", "sources", "devices", "geo",
            "real_time", "entry_exit")
    calls = [
        call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day", "date": "last7"}),
        call_mos(ctx, "/api/matomo-analytics/trends", {}),
        call_mos(ctx, "/api/matomo-analytics/top-pages", {"period": "week", "date": "today", "limit": 10}),
        call_mos(ctx, "/api/matomo-analytics/sources", {"period": "week", "date": "today"}),
        call_mos(ctx, "/api/matomo-analytics/devices", {"period": "week", "date": "today"}),
        call_mos(ctx, "/api/matomo-analytics/geo", {"period": "week", "date": "today", "limit": 10}),
        call_mos(ctx, "/api/matomo-analytics/real-time", {}),
        call_mos(ctx, "/api/matomo-analytics/entry-exit", {"period": "week", "date": "today", "limit": 8}),
    ]
    results = await asyncio.gather(*calls, return_exceptions=True)
    return {k: (r if not isinstance(r, Exception) else {"error": str(r)})
            for k, r in zip(keys, results)}


@ext.panel("workspace", slot="right", title="Analytics", icon="BarChart3",
           default_width=380,
           refresh="on_event:analytics.action.result")
async def workspace_panel(ctx):
    """Dense, scrollable dashboard. Actions -> Cockpit -> Detail sections."""
    s = await load_settings(ctx)

    if not matomo_ready(s):
        return ui.Stack(children=[
            ui.Header(text="Analytics", level=3),
            ui.Alert(message="Add your Matomo URL and Auth Token to activate the dashboard.",
                     type="warn"),
            settings_form(s),
        ])

    d, last = await asyncio.gather(_gather(ctx), load_result(ctx))

    sources = (d.get("sources") or {}).get("sources") or []
    devices = (d.get("devices") or {}).get("devices") or []
    countries = (d.get("geo") or {}).get("countries") or []
    top_pages = (d.get("top") or {}).get("pages") or []
    ee = d.get("entry_exit") or {}

    detail_sections = [
        ui.Section(title="Top pages", collapsible=True,
                   children=[pages_table(top_pages)]),
        ui.Section(title="Traffic sources", collapsible=False,
                   children=[breakdown_table(sources, "Source")]),
        ui.Section(title="Devices", collapsible=True,
                   children=[breakdown_table(devices, "Device")]),
        ui.Section(title="Top countries", collapsible=True,
                   children=[breakdown_table(countries, "Country")]),
        ui.Section(title="Entry pages (landing)", collapsible=True,
                   children=[entry_exit_table(ee.get("entry_pages") or [],
                                              "visits", "Entrances")]),
        ui.Section(title="Exit pages", collapsible=True,
                   children=[entry_exit_table(ee.get("exit_pages") or [],
                                              "visits", "Exits")]),
        ui.Section(title="Settings", collapsible=True,
                   children=[settings_form(s)]),
    ]

    return ui.Stack(children=[
        ui.Header(text="Analytics", level=3),
        result_zone(last),
        ui.Divider(),
        kpi_stats(d),
        ui.Divider(),
        ui.Stack(children=detail_sections),
    ])
