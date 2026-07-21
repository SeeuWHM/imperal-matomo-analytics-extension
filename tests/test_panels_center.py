"""Regression tests for the center dashboard panel (panels_center.hub_panel).

These exist because of TWO real production incidents on 2026-07-21, both
triggered by the same underlying cause (a Matomo outage/lockout making every
backend call return {"error": "..."}):

1. The panel's KPI-row code did f"{uniques:,}" on a value that was actually
   None - an unguarded TypeError inside the render function. The platform
   surfaced that as an infinitely-loading center panel (the render never
   completed).
2. AFTER fixing #1, the panel loaded fast but showed an all-zero dashboard
   with no indication anything had failed - every section silently read
   `.get(x, 0)` from an {"error": ...} payload, which is indistinguishable
   from a genuinely empty-but-successful response once you're only looking
   at individual fields. This is what the user reported as "loaded fast but
   everything is 0, like it didn't finish loading". Fixed by error_banner()
   in panels_render.py, which explicitly checks each section's payload for
   an "error" key and renders a visible Alert naming what failed.

This file locks in both: the panel never crashes AND a real failure is never
silently presented as legitimate zero data.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import panels_center


def _ctx() -> MockContext:
    ctx = MockContext(role="user")
    ctx.secrets = MockSecretStore({"matomo_url": "https://m.test", "matomo_token": "t"})
    ctx.store._data.setdefault("analytics_settings", {})["seed"] = {
        "sites": [{"label": "Main", "site_id": 2}]
    }
    return ctx


def _find_alert(node) -> bool:
    """Walk a UINode tree (dict or ui.UINode) looking for an Alert."""
    if node is None:
        return False
    d = node.to_dict() if hasattr(node, "to_dict") else node
    if not isinstance(d, dict):
        return False
    if d.get("type") == "Alert":
        return True
    props = d.get("props") or {}
    children = props.get("children")
    if isinstance(children, list):
        return any(_find_alert(c) for c in children)
    if isinstance(children, dict):
        return _find_alert(children)
    return False


@pytest.mark.asyncio
async def test_hub_panel_survives_all_calls_erroring(monkeypatch):
    """Every one of the 7 parallel backend calls returns an error dict (the
    real shape call_mos_cached returns on failure) - traffic.get("unique_visitors")
    is None, traffic.get("visits", 0) is the default 0. The panel must still
    render without raising, AND must show a visible error banner instead of
    presenting the resulting all-zero KPIs as real data."""
    async def fake_call_mos_cached(ctx, endpoint, extra=None, **kwargs):
        return {"error": "Matomo API error 500: locked out"}

    monkeypatch.setattr(panels_center, "call_mos_cached", fake_call_mos_cached)
    async def fake_ensure_known_domains(ctx, s):
        return s
    monkeypatch.setattr(panels_center, "ensure_known_domains", fake_ensure_known_domains)

    result = await panels_center.hub_panel(_ctx(), view="", range="30d")
    assert result is not None
    assert _find_alert(result), "expected an error Alert banner when every backend call failed"


@pytest.mark.asyncio
async def test_hub_panel_survives_completely_empty_traffic(monkeypatch):
    """traffic == {} (no error key, no data keys at all) - the most literal
    'empty response' shape, e.g. a genuinely brand-new site with zero visits.
    unique_visitors must fall back cleanly AND no error banner should appear
    (this is real zero data, not a failure)."""
    async def fake_call_mos_cached(ctx, endpoint, extra=None, **kwargs):
        return {}

    monkeypatch.setattr(panels_center, "call_mos_cached", fake_call_mos_cached)
    async def fake_ensure_known_domains(ctx, s):
        return s
    monkeypatch.setattr(panels_center, "ensure_known_domains", fake_ensure_known_domains)

    result = await panels_center.hub_panel(_ctx(), view="", range="30d")
    assert result is not None
    assert not _find_alert(result), "a genuinely empty (not errored) payload should NOT show an error banner"


@pytest.mark.asyncio
async def test_hub_panel_renders_with_real_data(monkeypatch):
    """Sanity check: a fully-populated happy-path payload also renders fine,
    including the unique_visitors_is_estimate Tooltip-wrapped path."""
    async def fake_call_mos_cached(ctx, endpoint, extra=None, **kwargs):
        if endpoint.endswith("/traffic"):
            return {
                "visits": 169, "pageviews": 300, "unique_visitors": 128,
                "unique_visitors_is_estimate": True, "bounce_rate": "42%",
                "avg_time_on_site": 120, "series": [
                    {"date": "2026-07-20", "visits": 90}, {"date": "2026-07-21", "visits": 79},
                ],
            }
        if endpoint.endswith("/trends"):
            return {"change_percent": 5.2, "direction": "up"}
        if endpoint.endswith("/top-pages"):
            return {"pages": [{"url": "/", "views": 100, "bounce_rate": 40.0}]}
        if endpoint.endswith("/real-time"):
            return {"live_30m": {"visitors": 3}}
        return {}

    monkeypatch.setattr(panels_center, "call_mos_cached", fake_call_mos_cached)
    async def fake_ensure_known_domains(ctx, s):
        return s
    monkeypatch.setattr(panels_center, "ensure_known_domains", fake_ensure_known_domains)

    result = await panels_center.hub_panel(_ctx(), view="", range="30d")
    assert result is not None
