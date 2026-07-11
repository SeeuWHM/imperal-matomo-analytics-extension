"""Unit tests — no network. Use MockContext + monkey-patched call_mos."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext

import api_client
import handlers_traffic
import handlers_settings
import app as app_module
from params import TrafficParams, TopPagesParams, TrendsParams, SaveSettingsParams


def _ctx(cfg: dict | None = None) -> MockContext:
    """Build a MockContext with analytics settings primed in the mock store."""
    ctx = MockContext(role="user")
    data = cfg if cfg is not None else {
        "matomo_url": "https://m.test",
        "matomo_token": "t",
        "matomo_site_id": 2,
    }
    # Collection scheme: one doc per user, any id works — load_settings
    # uses query(limit=1), not get(key).
    if data:
        ctx.store._data.setdefault("analytics_settings", {})["seed"] = data
    return ctx


@pytest.mark.asyncio
async def test_traffic_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None):
        assert endpoint == "/api/analytics/traffic"
        return {"visits": 100, "pageviews": 300, "series": []}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_traffic(_ctx(), TrafficParams())
    assert result.status == "success"
    assert result.data["visits"] == 100


@pytest.mark.asyncio
async def test_traffic_config_missing(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None):
        return {"error": "Matomo URL or token not set", "_config": True}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_traffic(_ctx({}), TrafficParams())
    assert result.status == "error"
    assert "Matomo" in result.error


@pytest.mark.asyncio
async def test_top_pages_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None):
        assert endpoint == "/api/analytics/top-pages"
        assert extra["limit"] == 5
        return {"pages": [{"url": "/a", "views": 10}], "count": 1}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_top_pages(_ctx(), TopPagesParams(limit=5))
    assert result.status == "success"
    assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_trends_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None):
        return {"current_week": 100, "previous_week": 80, "change_percent": 25.0,
                "direction": "up"}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_trends(_ctx(), TrendsParams())
    assert result.status == "success"
    assert "+25" in result.summary


@pytest.mark.asyncio
async def test_save_settings_merges_and_persists():
    ctx = _ctx({})  # empty — first save path
    params = SaveSettingsParams(
        matomo_url="https://m.test",
        matomo_token="tok",
        matomo_site_id=7,
    )
    result = await handlers_settings.fn_save_settings(ctx, params)
    assert result.status == "success"
    saved = await app_module.load_settings(ctx)
    assert saved["matomo_url"] == "https://m.test"
    assert saved["matomo_token"] == "tok"
    assert saved["matomo_site_id"] == 7


@pytest.mark.asyncio
async def test_save_settings_partial_update():
    ctx = _ctx()  # preseeded
    params = SaveSettingsParams(matomo_site_id=42)
    result = await handlers_settings.fn_save_settings(ctx, params)
    assert result.status == "success"
    saved = await app_module.load_settings(ctx)
    # Existing fields preserved
    assert saved["matomo_url"] == "https://m.test"
    # New value applied
    assert saved["matomo_site_id"] == 42


@pytest.mark.asyncio
async def test_api_client_reports_missing_matomo():
    ctx = _ctx({})  # no Matomo creds
    data = await api_client.call_mos(ctx, "/api/analytics/traffic", {})
    assert data["_config"] is True
    assert "Matomo" in data["error"]
