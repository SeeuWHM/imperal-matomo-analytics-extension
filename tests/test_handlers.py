"""Unit tests — no network. Use MockContext + monkey-patched call_mos.

Note: `imperal_sdk.testing.MockContext()` does NOT wire up `ctx.secrets` by
default (only `ctx.store`/`ctx.ai`/`ctx.http`/etc.) — in production the
kernel attaches `ctx.secrets` at dispatch time, outside the SDK's own
Context dataclass. Tests attach `imperal_sdk.testing.mock_secrets.
MockSecretStore` onto the mock context themselves via `_ctx()` below.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from imperal_sdk.testing import MockContext
from imperal_sdk.testing.mock_secrets import MockSecretStore

import api_client
import handlers_traffic
import handlers_settings
import handlers_detail
import handlers_audience
import app as app_module
from params import (
    TrafficParams, TopPagesParams, TrendsParams, SaveSettingsParams,
    AddSiteParams, RemoveSiteParams, ListSitesParams, ConversionsParams,
    SetActiveSiteParams,
)


def _ctx(secrets: dict | None = None, store: dict | None = None) -> MockContext:
    """Build a MockContext with Matomo credentials in ctx.secrets and
    non-secret settings (sites, segment, ...) in ctx.store — mirroring how
    the extension actually reads them (app.load_settings merges both).

    secrets=None -> configured with a default test Matomo URL/token.
    secrets={} -> unconfigured (matomo_ready() is False).
    """
    ctx = MockContext(role="user")
    secret_values = secrets if secrets is not None else {
        "matomo_url": "https://m.test",
        "matomo_token": "t",
    }
    ctx.secrets = MockSecretStore(secret_values)

    store_data = store if store is not None else {"sites": [{"label": "Main", "site_id": 2}]}
    if store_data:
        ctx.store._data.setdefault("analytics_settings", {})["seed"] = store_data
    return ctx


# ─── app.py — settings + secrets + site resolution ───────────────────────────

@pytest.mark.asyncio
async def test_load_settings_merges_secrets_and_store():
    ctx = _ctx()
    s = await app_module.load_settings(ctx)
    assert s["matomo_url"] == "https://m.test"
    assert s["matomo_token"] == "t"
    assert s["sites"] == [{"label": "Main", "site_id": 2}]


@pytest.mark.asyncio
async def test_load_settings_unconfigured():
    ctx = _ctx(secrets={}, store={})
    s = await app_module.load_settings(ctx)
    assert s["matomo_url"] == ""
    assert s["matomo_token"] == ""
    assert app_module.matomo_ready(s) is False


@pytest.mark.asyncio
async def test_load_settings_migrates_legacy_single_site_id():
    """Pre-multisite installs stored matomo_site_id directly - load_settings
    should fold it into `sites` as the default entry when `sites` is empty."""
    ctx = _ctx(store={"matomo_site_id": 5})
    s = await app_module.load_settings(ctx)
    assert s["sites"] == [{"label": "Основной сайт", "site_id": 5}]


def test_resolve_site_id_by_label():
    s = {"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}]}
    assert app_module.resolve_site_id(s, "Blog") == 2
    assert app_module.resolve_site_id(s, "blog") == 2  # case-insensitive
    assert app_module.resolve_site_id(s, "") == 1       # default = first site


def test_resolve_site_id_unknown_label_falls_back_to_default():
    s = {"sites": [{"label": "Main", "site_id": 7}]}
    assert app_module.resolve_site_id(s, "Nonexistent") == 7


def test_resolve_site_id_no_sites_configured():
    assert app_module.resolve_site_id({"sites": []}, "") == 1


def test_resolve_site_id_falls_back_to_active_site():
    s = {"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}],
         "active_site": "Blog"}
    assert app_module.resolve_site_id(s, "") == 2          # no explicit site -> active_site
    assert app_module.resolve_site_id(s, "Main") == 1       # explicit site still overrides


def test_resolve_site_id_ignores_stale_active_site():
    s = {"sites": [{"label": "Main", "site_id": 1}], "active_site": "Deleted"}
    assert app_module.resolve_site_id(s, "") == 1


def test_active_site_label():
    s = {"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}],
         "active_site": "Blog"}
    assert app_module.active_site_label(s) == "Blog"
    assert app_module.active_site_label({"sites": [{"label": "Main", "site_id": 1}]}) == "Main"
    assert app_module.active_site_label({"sites": []}) == ""


def test_sites_with_active_marks_correct_entry():
    s = {"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}],
         "active_site": "Blog"}
    marked = app_module.sites_with_active(s)
    assert marked == [
        {"label": "Main", "site_id": 1, "active": False},
        {"label": "Blog", "site_id": 2, "active": True},
    ]


@pytest.mark.asyncio
async def test_save_settings_never_persists_matomo_credentials():
    """matomo_url/matomo_token must never land in ctx.store - only ctx.secrets."""
    ctx = _ctx()
    await handlers_settings.save_settings(ctx, {"matomo_segment": "pageUrl=^/blog"})
    page = await ctx.store.query("analytics_settings", limit=1)
    stored = page.data[0].data
    assert "matomo_url" not in stored
    assert "matomo_token" not in stored
    assert stored["matomo_segment"] == "pageUrl=^/blog"


# ─── Multi-site management ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_site():
    ctx = _ctx(store={"sites": []})
    result = await handlers_settings.fn_add_site(ctx, AddSiteParams(label="Blog", site_id=3))
    assert result.status == "success"
    s = await app_module.load_settings(ctx)
    assert s["sites"] == [{"label": "Blog", "site_id": 3}]


@pytest.mark.asyncio
async def test_add_site_first_site_becomes_active():
    ctx = _ctx(store={"sites": []})
    await handlers_settings.fn_add_site(ctx, AddSiteParams(label="Blog", site_id=3))
    s = await app_module.load_settings(ctx)
    assert s["active_site"] == "Blog"


@pytest.mark.asyncio
async def test_add_site_second_site_does_not_change_active():
    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}], "active_site": "Main"})
    await handlers_settings.fn_add_site(ctx, AddSiteParams(label="Blog", site_id=2))
    s = await app_module.load_settings(ctx)
    assert s["active_site"] == "Main"


@pytest.mark.asyncio
async def test_add_site_replaces_existing_label():
    ctx = _ctx(store={"sites": [{"label": "Blog", "site_id": 3}]})
    await handlers_settings.fn_add_site(ctx, AddSiteParams(label="Blog", site_id=99))
    s = await app_module.load_settings(ctx)
    assert s["sites"] == [{"label": "Blog", "site_id": 99}]


@pytest.mark.asyncio
async def test_remove_site():
    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}]})
    result = await handlers_settings.fn_remove_site(ctx, RemoveSiteParams(label="Blog"))
    assert result.status == "success"
    s = await app_module.load_settings(ctx)
    assert s["sites"] == [{"label": "Main", "site_id": 1}]


@pytest.mark.asyncio
async def test_remove_site_not_found():
    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}]})
    result = await handlers_settings.fn_remove_site(ctx, RemoveSiteParams(label="Ghost"))
    assert result.status == "error"


@pytest.mark.asyncio
async def test_remove_active_site_reassigns_to_remaining_site():
    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}],
                       "active_site": "Blog"})
    await handlers_settings.fn_remove_site(ctx, RemoveSiteParams(label="Blog"))
    s = await app_module.load_settings(ctx)
    assert s["active_site"] == "Main"


@pytest.mark.asyncio
async def test_set_active_site():
    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}],
                       "active_site": "Main"})
    result = await handlers_settings.fn_set_active_site(ctx, SetActiveSiteParams(label="Blog"))
    assert result.status == "success"
    assert result.data["sites"] == [
        {"label": "Main", "site_id": 1, "active": False},
        {"label": "Blog", "site_id": 2, "active": True},
    ]
    s = await app_module.load_settings(ctx)
    assert s["active_site"] == "Blog"


@pytest.mark.asyncio
async def test_set_active_site_unknown_label():
    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}]})
    result = await handlers_settings.fn_set_active_site(ctx, SetActiveSiteParams(label="Ghost"))
    assert result.status == "error"


@pytest.mark.asyncio
async def test_list_sites_empty():
    ctx = _ctx(store={"sites": []})
    result = await handlers_settings.fn_list_sites(ctx, ListSitesParams())
    assert result.status == "success"
    assert result.data["sites"] == []


# ─── api_client.call_mos — site resolution + config guard ────────────────────

@pytest.mark.asyncio
async def test_call_mos_resolves_site_label_to_site_id(monkeypatch):
    captured = {}

    class _FakeResp:
        ok = True
        def json(self):
            return {"ok": True}

    async def fake_post(url, json, timeout):
        captured.update(json)
        return _FakeResp()

    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}]})
    ctx.http.post = fake_post
    await api_client.call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day"}, site="Blog")
    assert captured["site_id"] == 2


@pytest.mark.asyncio
async def test_call_mos_reports_missing_matomo():
    ctx = _ctx(secrets={})
    data = await api_client.call_mos(ctx, "/api/matomo-analytics/traffic", {})
    assert data["_config"] is True
    assert "Matomo" in data["error"]


# ─── Traffic / top pages / trends (existing coverage, kept + adapted) ────────

@pytest.mark.asyncio
async def test_traffic_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site=""):
        assert endpoint == "/api/matomo-analytics/traffic"
        return {"visits": 100, "pageviews": 300, "series": []}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_traffic(_ctx(), TrafficParams())
    assert result.status == "success"
    assert result.data["visits"] == 100


@pytest.mark.asyncio
async def test_traffic_config_missing(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site=""):
        return {"error": "Matomo not configured - open Settings and add your URL + Auth Token.", "_config": True}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_traffic(_ctx(secrets={}), TrafficParams())
    assert result.status == "error"
    assert "Matomo" in result.error


@pytest.mark.asyncio
async def test_top_pages_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site=""):
        assert endpoint == "/api/matomo-analytics/top-pages"
        assert extra["limit"] == 5
        return {"pages": [{"url": "/a", "views": 10}], "count": 1}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_top_pages(_ctx(), TopPagesParams(limit=5))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_trends_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site=""):
        return {"current_week": 100, "previous_week": 80, "change_percent": 25.0, "direction": "up"}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_trends(_ctx(), TrendsParams())
    assert result.status == "success"
    assert "+25" in result.summary


# ─── geo — regression test for the missing "countries" alias bug ─────────────

@pytest.mark.asyncio
async def test_geo_reads_countries_key(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site=""):
        assert endpoint == "/api/matomo-analytics/geo"
        return {"items": [{"label": "US", "visits": 10, "percent": 100.0}],
                "countries": [{"label": "US", "visits": 10, "percent": 100.0}]}

    monkeypatch.setattr(handlers_detail, "call_mos", fake_call)
    result = await handlers_detail.fn_geo(_ctx(), handlers_detail._PeriodParams())
    assert result.status == "success"
    assert "US" in result.summary


# ─── ipc_matomo_config — must never leak the raw token ───────────────────────

@pytest.mark.asyncio
async def test_ipc_matomo_config_does_not_leak_token():
    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}]})
    result = await handlers_traffic.ipc_matomo_config(ctx)
    assert result.status == "success"
    assert "matomo_token" not in result.data
    assert "matomo_url" not in result.data
    assert result.data["configured"] is True
    assert result.data["sites"] == [{"label": "Main", "site_id": 1}]


# ─── conversions — synthetic "All Goals" fallback ────────────────────────────

@pytest.mark.asyncio
async def test_conversions_no_named_goals_shows_message(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site=""):
        return {"has_goals": False, "goals": [], "total_conversions": 0,
                "message": "Configure goals in Matomo to track conversions."}

    monkeypatch.setattr(handlers_audience, "call_mos", fake_call)
    result = await handlers_audience.fn_conversions(
        ctx=_ctx(), params=ConversionsParams(),
    )
    assert result.status == "success"
    assert "No goals" in result.summary
