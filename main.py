"""Analytics extension · entry point with module hot-reload."""
from __future__ import annotations

import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)

for _m in list(sys.modules):
    if _m in ("app", "api_client", "params", "response_models", "compare_render",
              "skeleton", "audience_helpers",
              "handlers_traffic", "handlers_settings",
              "handlers_detail", "handlers_insights",
              "handlers_audience", "handlers_channels",
              "handlers_demographics", "handlers_reports",
              "panels_render", "panels_settings_render",
              "panels_side", "panels_center"):
        del sys.modules[_m]

from app import ext, chat  # noqa: E402, F401

import skeleton              # noqa: E402, F401
import handlers_traffic      # noqa: E402, F401
import handlers_settings     # noqa: E402, F401
import handlers_detail       # noqa: E402, F401
import handlers_insights     # noqa: E402, F401
import handlers_audience     # noqa: E402, F401
import handlers_channels     # noqa: E402, F401
import handlers_demographics # noqa: E402, F401
import handlers_reports      # noqa: E402, F401
import panels_side           # noqa: E402, F401
import panels_center         # noqa: E402, F401


# Daily summary schedule - fires in-app notification if there are any
# critical insights, across every configured site. Runs at 09:00 UTC. No AI used.
@ext.schedule("daily_summary", cron="0 9 * * *")
async def daily_summary(ctx):
    from imperal_sdk.types import ActionResult
    from api_client import call_mos
    from app import load_settings

    s = await load_settings(ctx)
    sites = s.get("sites") or [{"label": "", "site_id": None}]

    total_critical = 0
    total_warnings = 0
    per_site_lines = []
    for site in sites:
        label = site.get("label", "")
        data = await call_mos(ctx, "/api/matomo-analytics/insights", {}, site=label)
        if "error" in data:
            continue
        critical = int(data.get("critical_count", 0) or 0)
        warnings = int(data.get("warning_count", 0) or 0)
        total_critical += critical
        total_warnings += warnings
        if critical or warnings:
            per_site_lines.append(f"{label or 'default site'}: {critical} critical, {warnings} warnings")

    if total_critical or total_warnings >= 3:
        try:
            await ctx.notify.push(
                title="Analytics - attention needed",
                body=("\n".join(per_site_lines) if per_site_lines else
                      f"{total_critical} critical, {total_warnings} warnings this morning.")
                     + "\nOpen Analytics to see what to do.",
            )
        except Exception:
            pass
    return ActionResult.success(
        data={"critical": total_critical, "warnings": total_warnings, "sites_checked": len(sites)},
        summary=f"Daily scan: {total_critical} critical, {total_warnings} warnings across {len(sites)} site(s)",
    )


@ext.on_install
async def on_install(ctx):
    """Fire on first install."""
    from imperal_sdk.types import ActionResult
    return ActionResult.success(
        summary="Matomo Analytics Connector installed. Open Settings to add your Matomo URL + Auth Token.",
    )


@ext.health_check
async def health(ctx):
    from imperal_sdk.types import ActionResult
    from app import ext, load_settings, matomo_ready
    s = await load_settings(ctx)
    configured = matomo_ready(s)
    return ActionResult.success(
        data={
            "version": ext.version,
            "matomo_configured": configured,
            "sites_configured": len(s.get("sites") or []),
        },
        summary="Matomo connected." if configured else "Matomo not configured.",
    )
