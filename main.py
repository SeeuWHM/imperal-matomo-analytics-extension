"""Analytics extension · entry point with module hot-reload."""
from __future__ import annotations

import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)

for _m in list(sys.modules):
    if _m in ("app", "api_client", "params", "skeleton",
              "handlers_traffic", "handlers_settings",
              "handlers_detail", "handlers_insights",
              "handlers_audience",
              "panels_render", "panels_side", "panels_center"):
        del sys.modules[_m]

from app import ext, chat  # noqa: E402, F401

import skeleton            # noqa: E402, F401
import handlers_traffic    # noqa: E402, F401
import handlers_settings   # noqa: E402, F401
import handlers_detail     # noqa: E402, F401
import handlers_insights   # noqa: E402, F401
import handlers_audience   # noqa: E402, F401
import panels_side         # noqa: E402, F401
import panels_center       # noqa: E402, F401


# Daily summary schedule - fires in-app notification if there are any
# critical insights. Runs at 09:00 UTC. No AI used.
@ext.schedule("daily_summary", cron="0 9 * * *")
async def daily_summary(ctx):
    from imperal_sdk.types import ActionResult
    from api_client import call_mos
    data = await call_mos(ctx, "/api/matomo-analytics/insights", {})
    if "error" in data:
        return ActionResult.error(error=data["error"])
    critical = int(data.get("critical_count", 0) or 0)
    warnings = int(data.get("warning_count", 0) or 0)
    if critical or warnings >= 3:
        try:
            await ctx.notify.push(
                title="Analytics - attention needed",
                body=f"{critical} critical, {warnings} warnings this morning. Open Analytics to see what to do.",
            )
        except Exception:
            pass
    return ActionResult.success(
        data={"critical": critical, "warnings": warnings},
        summary=f"Daily scan: {critical} critical, {warnings} warnings",
    )


@ext.on_install
async def on_install(ctx):
    """Fire on first install."""
    from imperal_sdk.types import ActionResult
    return ActionResult.success(
        summary="Analytics installed. Open Settings to add your Matomo credentials.",
    )


@ext.health_check
async def health(ctx):
    from imperal_sdk.types import ActionResult
    from app import load_settings, matomo_ready
    s = await load_settings(ctx)
    return ActionResult.success(data={
        "version": "4.0.2",
        "matomo_configured": matomo_ready(s),
    })
