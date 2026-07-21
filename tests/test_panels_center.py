"""Regression tests for the center dashboard panel (panels_center.hub_panel).

These exist because of a real production incident (2026-07-21): a Matomo
outage/lockout made the backend return an error payload for /traffic (empty
of any real fields), and the panel's KPI-row code did `f"{uniques:,}"` on a
value that was actually None - an unguarded TypeError inside the render
function. The platform surfaced that as an infinitely-loading center panel
(the render never completed) while the sidebar, which degrades more
gracefully, showed honest zeros. This file locks in that the panel renders
SOMETHING (not necessarily good data, but not a crash) no matter what shape
of empty/error/partial data every one of the 7 parallel backend calls
returns.
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


@pytest.mark.asyncio
async def test_hub_panel_survives_all_calls_erroring(monkeypatch):
    """Every one of the 7 parallel backend calls returns an error dict (the
    real shape call_mos_cached returns on failure) - traffic.get("unique_visitors")
    is None, traffic.get("visits", 0) is the default 0. The panel must still
    render without raising."""
    async def fake_call_mos_cached(ctx, endpoint, extra=None, **kwargs):
        return {"error": "Matomo API error 500: locked out"}

    monkeypatch.setattr(panels_center, "call_mos_cached", fake_call_mos_cached)
    async def fake_ensure_known_domains(ctx, s):
        return s
    monkeypatch.setattr(panels_center, "ensure_known_domains", fake_ensure_known_domains)

    result = await panels_center.hub_panel(_ctx(), view="", range="30d")
    assert result is not None


@pytest.mark.asyncio
async def test_hub_panel_survives_completely_empty_traffic(monkeypatch):
    """traffic == {} (no error key, no data keys at all) - the most literal
    'empty response' shape. unique_visitors must fall back cleanly."""
    async def fake_call_mos_cached(ctx, endpoint, extra=None, **kwargs):
        return {}

    monkeypatch.setattr(panels_center, "call_mos_cached", fake_call_mos_cached)
    async def fake_ensure_known_domains(ctx, s):
        return s
    monkeypatch.setattr(panels_center, "ensure_known_domains", fake_ensure_known_domains)

    result = await panels_center.hub_panel(_ctx(), view="", range="30d")
    assert result is not None


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
