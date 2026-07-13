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
import handlers_channels
import handlers_demographics
import app as app_module
from params import (
    TrafficParams, TopPagesParams, TrendsParams, SaveSettingsParams,
    AddSiteParams, RemoveSiteParams, ListSitesParams, ConversionsParams,
    SetActiveSiteParams, SiteDomainsParams, ViewDomainParams,
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


def test_resolve_site_returns_per_site_segment():
    s = {"sites": [{"label": "Main", "site_id": 2},
                    {"label": "Blog", "site_id": 2, "segment": "pageUrl=^https://blog.example.com"}]}
    assert app_module.resolve_site(s, "Blog") == {
        "label": "Blog", "site_id": 2, "segment": "pageUrl=^https://blog.example.com",
    }
    assert app_module.resolve_site(s, "Main").get("segment") is None


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
async def test_add_site_with_segment_scopes_a_subdomain():
    """Two 'projects' can share one Matomo site_id - the segment carves out
    just one subdomain (e.g. a blog) from the rest of that site's traffic."""
    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 2}]})
    result = await handlers_settings.fn_add_site(
        ctx, AddSiteParams(label="Blog", site_id=2, segment="pageUrl=^https://blog.example.com"),
    )
    assert result.status == "success"
    s = await app_module.load_settings(ctx)
    assert s["sites"][-1] == {"label": "Blog", "site_id": 2,
                              "segment": "pageUrl=^https://blog.example.com"}


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


# ─── site_domains — real Matomo SitesManager data, not inferred from traffic ──

@pytest.mark.asyncio
async def test_site_domains_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        assert endpoint == "/api/matomo-analytics/site-info"
        return {"name": "Front Websites", "main_url": "https://www.example.com",
                "urls": ["https://www.example.com", "https://blog.example.com"]}

    monkeypatch.setattr(handlers_settings, "call_mos", fake_call)
    result = await handlers_settings.fn_site_domains(_ctx(), SiteDomainsParams())
    assert result.status == "success"
    assert result.data["urls"] == ["https://www.example.com", "https://blog.example.com"]
    assert "2" in result.summary or "www.example.com" in result.summary


@pytest.mark.asyncio
async def test_site_domains_suggests_segment_per_url(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        return {"name": "Front Websites", "main_url": "https://www.example.com",
                "urls": ["https://www.example.com", "https://blog.example.com"]}

    monkeypatch.setattr(handlers_settings, "call_mos", fake_call)
    result = await handlers_settings.fn_site_domains(_ctx(), SiteDomainsParams())
    assert result.data["suggested_segments"] == [
        {"domain": "https://www.example.com", "segment": "pageUrl=^https://www.example.com"},
        {"domain": "https://blog.example.com", "segment": "pageUrl=^https://blog.example.com"},
    ]


@pytest.mark.asyncio
async def test_site_domains_error(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        return {"error": "Matomo not configured - open Settings and add your URL + Auth Token.", "_config": True}

    monkeypatch.setattr(handlers_settings, "call_mos", fake_call)
    result = await handlers_settings.fn_site_domains(_ctx(secrets={}), SiteDomainsParams())
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
    assert captured["targets"] == [{"label": "Blog", "site_id": 2, "segment": None}]


@pytest.mark.asyncio
async def test_call_mos_uses_per_site_segment_over_global(monkeypatch):
    """A site's own `segment` (e.g. carving a blog subdomain out of a shared
    site_id) must win over the account-wide matomo_segment setting."""
    captured = {}

    class _FakeResp:
        ok = True
        def json(self):
            return {"ok": True}

    async def fake_post(url, json, timeout):
        captured.update(json)
        return _FakeResp()

    ctx = _ctx(store={
        "sites": [{"label": "Main", "site_id": 2},
                  {"label": "Blog", "site_id": 2, "segment": "pageUrl=^https://blog.example.com"}],
        "matomo_segment": "visitorType==new",
    })
    ctx.http.post = fake_post
    await api_client.call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day"}, site="Blog")
    assert captured["targets"][0]["segment"] == "pageUrl=^https://blog.example.com"

    await api_client.call_mos(ctx, "/api/matomo-analytics/traffic", {"period": "day"}, site="Main")
    assert captured["targets"][0]["segment"] == "visitorType==new"


@pytest.mark.asyncio
async def test_call_mos_reports_missing_matomo():
    ctx = _ctx(secrets={})
    data = await api_client.call_mos(ctx, "/api/matomo-analytics/traffic", {})
    assert data["_config"] is True
    assert "Matomo" in data["error"]


# ─── Traffic / top pages / trends (existing coverage, kept + adapted) ────────

@pytest.mark.asyncio
async def test_traffic_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        assert endpoint == "/api/matomo-analytics/traffic"
        return {"visits": 100, "pageviews": 300, "series": []}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_traffic(_ctx(), TrafficParams())
    assert result.status == "success"
    assert result.data["visits"] == 100


@pytest.mark.asyncio
async def test_traffic_config_missing(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        return {"error": "Matomo not configured - open Settings and add your URL + Auth Token.", "_config": True}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_traffic(_ctx(secrets={}), TrafficParams())
    assert result.status == "error"
    assert "Matomo" in result.error


@pytest.mark.asyncio
async def test_top_pages_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        assert endpoint == "/api/matomo-analytics/top-pages"
        assert extra["limit"] == 5
        return {"pages": [{"url": "/a", "views": 10}], "count": 1}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_top_pages(_ctx(), TopPagesParams(limit=5))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_trends_success(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        return {"current_week": 100, "previous_week": 80, "change_percent": 25.0, "direction": "up"}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_trends(_ctx(), TrendsParams())
    assert result.status == "success"
    assert "+25" in result.summary


# ─── geo — regression test for the missing "countries" alias bug ─────────────

@pytest.mark.asyncio
async def test_geo_reads_countries_key(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
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
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        return {"has_goals": False, "goals": [], "total_conversions": 0,
                "message": "Configure goals in Matomo to track conversions."}

    monkeypatch.setattr(handlers_audience, "call_mos", fake_call)
    result = await handlers_audience.fn_conversions(
        ctx=_ctx(), params=ConversionsParams(),
    )
    assert result.status == "success"
    assert "No goals" in result.summary


# ─── call_mos — universal single-or-multi targets envelope ───────────────────

class _FakeResp:
    def __init__(self, body, ok=True):
        self._body = body
        self.ok = ok
    def json(self):
        return self._body


@pytest.mark.asyncio
async def test_call_mos_single_target_unwraps_multiresult_envelope(monkeypatch):
    """A single site_id/label still reaches every existing handler as the old
    flat shape - the backend's MultiResult envelope is unwrapped for them."""
    async def fake_post(url, json, timeout):
        assert len(json["targets"]) == 1
        return _FakeResp({"results": [{"label": "Main", "site_id": 1, "error": None,
                                       "data": {"visits": 42}}]})

    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}]})
    ctx.http.post = fake_post
    data = await api_client.call_mos(ctx, "/api/matomo-analytics/traffic", {})
    assert data == {"visits": 42}


@pytest.mark.asyncio
async def test_call_mos_single_target_error_becomes_error_dict(monkeypatch):
    async def fake_post(url, json, timeout):
        return _FakeResp({"results": [{"label": "Main", "site_id": 1,
                                       "error": "Matomo said no", "data": {}}]})

    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}]})
    ctx.http.post = fake_post
    data = await api_client.call_mos(ctx, "/api/matomo-analytics/traffic", {})
    assert data == {"error": "Matomo said no"}


@pytest.mark.asyncio
async def test_call_mos_multiple_sites_builds_one_target_per_label_and_returns_raw_results(monkeypatch):
    """Asking to compare 2 sites sends ONE request with 2 targets (not 2
    separate calls), and the caller gets the raw per-site list back."""
    captured = {}

    async def fake_post(url, json, timeout):
        captured.update(json)
        return _FakeResp({"results": [
            {"label": "Main", "site_id": 1, "error": None, "data": {"visits": 10}},
            {"label": "Blog", "site_id": 2, "error": None, "data": {"visits": 20}},
        ]})

    ctx = _ctx(store={"sites": [{"label": "Main", "site_id": 1}, {"label": "Blog", "site_id": 2}]})
    ctx.http.post = fake_post
    data = await api_client.call_mos(ctx, "/api/matomo-analytics/traffic", {}, sites=["Main", "Blog"])
    assert [t["site_id"] for t in captured["targets"]] == [1, 2]
    assert data == {"results": [
        {"label": "Main", "site_id": 1, "error": None, "data": {"visits": 10}},
        {"label": "Blog", "site_id": 2, "error": None, "data": {"visits": 20}},
    ]}


@pytest.mark.asyncio
async def test_traffic_renders_comparison_table_for_multiple_sites(monkeypatch):
    """fn_traffic must branch to a comparison render, not crash on the
    envelope shape, when the caller passes sites=[...]."""
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        assert sites == ["Main", "Blog"]
        return {"results": [
            {"label": "Main", "site_id": 1, "error": None,
             "data": {"visits": 10, "pageviews": 30, "bounce_rate": 40.0}},
            {"label": "Blog", "site_id": 2, "error": None,
             "data": {"visits": 20, "pageviews": 60, "bounce_rate": 50.0}},
        ]}

    monkeypatch.setattr(handlers_traffic, "call_mos", fake_call)
    result = await handlers_traffic.fn_traffic(_ctx(), TrafficParams(sites=["Main", "Blog"]))
    assert result.status == "success"
    assert "2 sites" in result.summary


# ─── view_domain — domain-level switcher within one Matomo site_id ───────────

@pytest.mark.asyncio
async def test_view_domain_updates_existing_site_segment_in_place():
    """view_domain must scope the EXISTING project entry, never add a new
    top-level site - that's what polluted the site_id selector with
    per-domain fakes before this fix."""
    ctx = _ctx(store={"sites": [{"label": "WHM Front", "site_id": 2,
                                  "known_domains": ["https://a.example.com", "https://blog.example.com"]}],
                       "active_site": "WHM Front"})
    result = await handlers_settings.fn_view_domain(
        ctx, ViewDomainParams(site_id=2, domain="https://blog.example.com"),
    )
    assert result.status == "success"
    s = await app_module.load_settings(ctx)
    assert len(s["sites"]) == 1  # no new entry - same project, just re-scoped
    assert s["active_site"] == "WHM Front"
    assert s["sites"][0]["segment"] == "pageUrl=^https://blog.example.com"


@pytest.mark.asyncio
async def test_view_domain_prefers_active_entry_when_site_id_shared():
    """If the user deliberately used add_site to give a sub-project its own
    persistent label (same site_id, different segment), view_domain must not
    touch that one - it re-scopes whichever entry is currently active."""
    ctx = _ctx(store={"sites": [
        {"label": "WHM Front", "site_id": 2},
        {"label": "Blog", "site_id": 2, "segment": "pageUrl=^https://blog.example.com"},
    ], "active_site": "WHM Front"})
    result = await handlers_settings.fn_view_domain(
        ctx, ViewDomainParams(site_id=2, domain="https://a.example.com"),
    )
    assert result.status == "success"
    s = await app_module.load_settings(ctx)
    assert len(s["sites"]) == 2
    assert s["sites"][0]["label"] == "WHM Front"
    assert s["sites"][0]["segment"] == "pageUrl=^https://a.example.com"
    assert s["sites"][1] == {"label": "Blog", "site_id": 2, "segment": "pageUrl=^https://blog.example.com"}


@pytest.mark.asyncio
async def test_view_domain_all_domains_clears_segment_in_place():
    ctx = _ctx(store={"sites": [
        {"label": "WHM Front", "site_id": 2, "segment": "pageUrl=^https://blog.example.com"},
    ], "active_site": "WHM Front"})
    result = await handlers_settings.fn_view_domain(
        ctx, ViewDomainParams(site_id=2, domain="All domains"),
    )
    assert result.status == "success"
    s = await app_module.load_settings(ctx)
    assert len(s["sites"]) == 1
    assert "segment" not in s["sites"][0]
    assert s["active_site"] == "WHM Front"


@pytest.mark.asyncio
async def test_view_domain_unknown_site_id_errors():
    ctx = _ctx(store={"sites": [{"label": "WHM Front", "site_id": 2}], "active_site": "WHM Front"})
    result = await handlers_settings.fn_view_domain(
        ctx, ViewDomainParams(site_id=999, domain="https://a.example.com"),
    )
    assert result.status == "error"
    s = await app_module.load_settings(ctx)
    assert s["sites"] == [{"label": "WHM Front", "site_id": 2}]  # untouched


@pytest.mark.asyncio
async def test_add_site_caches_known_domains(monkeypatch):
    async def fake_site_info_for(ctx, site_id, segment=None):
        return {"name": "Test", "main_url": "https://a.example.com",
                "urls": ["https://a.example.com", "https://blog.example.com"]}

    monkeypatch.setattr(handlers_settings, "site_info_for", fake_site_info_for)
    ctx = _ctx(store={"sites": []})
    await handlers_settings.fn_add_site(ctx, AddSiteParams(label="Main", site_id=2))
    s = await app_module.load_settings(ctx)
    assert s["sites"][0]["known_domains"] == ["https://a.example.com", "https://blog.example.com"]


@pytest.mark.asyncio
async def test_add_site_ignores_known_domains_lookup_failure(monkeypatch):
    """add_site must still succeed even if the best-effort domain lookup fails."""
    async def fake_site_info_for(ctx, site_id, segment=None):
        return {"error": "backend down"}

    monkeypatch.setattr(handlers_settings, "site_info_for", fake_site_info_for)
    ctx = _ctx(store={"sites": []})
    result = await handlers_settings.fn_add_site(ctx, AddSiteParams(label="Main", site_id=2))
    assert result.status == "success"
    s = await app_module.load_settings(ctx)
    assert "known_domains" not in s["sites"][0]


# ─── new IPC exposes — content-gap signals for cross-extension consumers ────

@pytest.mark.asyncio
async def test_ipc_organic_keywords(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        assert endpoint == "/api/matomo-analytics/keywords"
        return {"keywords": [{"label": "matomo hosting", "visits": 5, "percent": 100.0}]}

    monkeypatch.setattr(handlers_channels, "call_mos", fake_call)
    result = await handlers_channels.ipc_organic_keywords(_ctx())
    assert result.status == "success"
    assert result.data["keywords"][0]["label"] == "matomo hosting"


@pytest.mark.asyncio
async def test_ipc_site_search(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        assert endpoint == "/api/matomo-analytics/site-search"
        return {"keywords": [], "no_results": [{"label": "docker hosting", "visits": 3, "percent": 100.0}]}

    monkeypatch.setattr(handlers_demographics, "call_mos", fake_call)
    result = await handlers_demographics.ipc_site_search(_ctx())
    assert result.status == "success"
    assert result.data["no_results"][0]["label"] == "docker hosting"


@pytest.mark.asyncio
async def test_ipc_page_details(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        assert endpoint == "/api/matomo-analytics/page-details"
        return {"pages": [{"url": "/old-post", "visits": 10, "avg_time_on_page": 5, "bounce_rate": "90%"}]}

    monkeypatch.setattr(handlers_demographics, "call_mos", fake_call)
    result = await handlers_demographics.ipc_page_details(_ctx())
    assert result.status == "success"
    assert result.data["pages"][0]["bounce_rate"] == "90%"


@pytest.mark.asyncio
async def test_ipc_entry_exit(monkeypatch):
    async def fake_call(ctx, endpoint, extra=None, site="", sites=None):
        assert endpoint == "/api/matomo-analytics/entry-exit"
        return {"entry_pages": [{"url": "/"}], "exit_pages": [{"url": "/pricing"}]}

    monkeypatch.setattr(handlers_detail, "call_mos", fake_call)
    result = await handlers_detail.ipc_entry_exit(_ctx())
    assert result.status == "success"
    assert result.data["entry_pages"][0]["url"] == "/"
