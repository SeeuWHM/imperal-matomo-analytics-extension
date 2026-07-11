"""MOS analytics API — integration tests.

Run:  pytest tests/test_mos_api.py -v
Deps: pip install httpx pytest

Hits the live MOS server + real Matomo instance.
All tests are read-only; nothing is written.
Skipped automatically if MOS or Matomo is unreachable (CI-safe).
"""
import time
import os
import pytest
import httpx

MOS     = os.getenv("MOS_URL",      "")
KEY     = os.getenv("MOS_API_KEY",  "")
MATOMO  = {
    "matomo_url": os.getenv("MATOMO_URL",   "https://analytics.webhostmost.com"),
    "token":      os.getenv("MATOMO_TOKEN", "25019648c74b2340b577f6956928da2f"),
    "site_id":    int(os.getenv("MATOMO_SITE_ID", "2")),
}
HDR = {"X-API-Key": KEY, "Content-Type": "application/json"}


def _matomo_reachable() -> bool:
    """Return True if MOS can reach Matomo (health check via /traffic)."""
    try:
        r = httpx.post(
            f"{MOS}/api/matomo-analytics/traffic",
            json={**MATOMO, "period": "day", "date": "yesterday"},
            headers=HDR,
            timeout=15,
        )
        return r.status_code == 200
    except Exception:
        return False


# Skip entire module when Matomo is temporarily unreachable (e.g. IP ban, downtime).
pytestmark = pytest.mark.skipif(
    not _matomo_reachable(),
    reason="MOS→Matomo unreachable (IP ban, downtime, or no credentials)",
)


@pytest.fixture(scope="module")
def http():
    with httpx.Client(timeout=60) as c:
        yield c


def post(http, path: str, extra: dict = None) -> dict:
    payload = {**MATOMO, **(extra or {})}
    r = http.post(f"{MOS}/api/matomo-analytics/{path}", json=payload, headers=HDR)
    assert r.status_code == 200, f"{path}: HTTP {r.status_code} — {r.text[:300]}"
    return r.json()


# ─── /traffic ────────────────────────────────────────────────────────────────

class TestTraffic:
    def test_has_required_keys(self, http):
        d = post(http, "traffic", {"period": "day", "date": "last7"})
        assert {"visits", "pageviews", "series"} <= d.keys()

    def test_visits_positive(self, http):
        d = post(http, "traffic", {"period": "day", "date": "last7"})
        assert d["visits"] > 0

    def test_series_length(self, http):
        d = post(http, "traffic", {"period": "day", "date": "last7"})
        assert len(d["series"]) >= 6

    def test_series_has_date_field(self, http):
        d = post(http, "traffic", {"period": "day", "date": "last7"})
        assert "date" in d["series"][0]


# ─── /trends ─────────────────────────────────────────────────────────────────

class TestTrends:
    def test_direction_valid(self, http):
        d = post(http, "trends")
        assert d["direction"] in ("up", "down", "flat")

    def test_change_is_float(self, http):
        d = post(http, "trends")
        assert isinstance(d["change_percent"], (int, float))

    def test_weeks_present(self, http):
        d = post(http, "trends")
        assert "current_week" in d and "previous_week" in d


# ─── /top-pages ───────────────────────────────────────────────────────────────

class TestTopPages:
    def test_returns_pages(self, http):
        d = post(http, "top-pages", {"period": "week", "date": "today", "limit": 5})
        assert len(d["pages"]) > 0

    def test_limit_respected(self, http):
        d = post(http, "top-pages", {"period": "week", "date": "today", "limit": 3})
        assert len(d["pages"]) <= 3

    def test_page_schema(self, http):
        d = post(http, "top-pages", {"period": "week", "date": "today", "limit": 3})
        p = d["pages"][0]
        assert {"url", "views", "pageviews", "bounce_rate"} <= p.keys()


# ─── /geo ────────────────────────────────────────────────────────────────────

class TestGeo:
    def test_has_countries(self, http):
        d = post(http, "geo", {"period": "week", "date": "today", "limit": 5})
        assert len(d["countries"]) > 0

    def test_country_schema(self, http):
        d = post(http, "geo", {"period": "week", "date": "today", "limit": 5})
        c = d["countries"][0]
        assert {"label", "visits", "percent"} <= c.keys()

    def test_percent_range(self, http):
        d = post(http, "geo", {"period": "week", "date": "today", "limit": 10})
        for c in d["countries"]:
            assert 0 <= c["percent"] <= 100


# ─── /sources ────────────────────────────────────────────────────────────────

class TestSources:
    def test_known_source_types(self, http):
        d = post(http, "sources", {"period": "week", "date": "today"})
        labels = {s["label"] for s in d["sources"]}
        assert labels & {"Direct Entry", "Search Engines", "Websites"}

    def test_percent_sums_to_100(self, http):
        d = post(http, "sources", {"period": "week", "date": "today"})
        total = sum(s["percent"] for s in d["sources"])
        assert abs(total - 100.0) < 2


# ─── /devices ────────────────────────────────────────────────────────────────

class TestDevices:
    def test_has_desktop_or_mobile(self, http):
        d = post(http, "devices", {"period": "week", "date": "today"})
        labels = {dev["label"] for dev in d["devices"]}
        assert labels & {"Desktop", "Smartphone"}


# ─── /real-time ───────────────────────────────────────────────────────────────

class TestRealTime:
    def test_all_windows_present(self, http):
        d = post(http, "real-time")
        assert {"live_30m", "live_60m", "live_180m"} <= d.keys()

    def test_visitors_key_present(self, http):
        d = post(http, "real-time")
        assert "visitors" in d["live_30m"]

    def test_monotonic_visitor_counts(self, http):
        """30m ≤ 60m ≤ 180m — more time = at least as many visitors."""
        d = post(http, "real-time")
        v30  = d["live_30m"]["visitors"]
        v60  = d["live_60m"]["visitors"]
        v180 = d["live_180m"]["visitors"]
        assert v30 <= v60 <= v180, f"not monotonic: {v30} / {v60} / {v180}"


# ─── /browsers ───────────────────────────────────────────────────────────────

class TestBrowsers:
    def test_browsers_and_os(self, http):
        d = post(http, "browsers", {"period": "week", "date": "today"})
        assert len(d["browsers"]) > 0
        assert len(d["os_families"]) > 0

    def test_chrome_present(self, http):
        d = post(http, "browsers", {"period": "week", "date": "today"})
        labels = {b["label"] for b in d["browsers"]}
        assert any("Chrome" in l for l in labels)


# ─── /new-returning ───────────────────────────────────────────────────────────

class TestNewReturning:
    def test_percentages_sum_to_100(self, http):
        d = post(http, "new-returning", {"period": "week", "date": "today"})
        total = d["new_percent"] + d["returning_percent"]
        assert abs(total - 100.0) < 1

    def test_counts_match_total(self, http):
        d = post(http, "new-returning", {"period": "week", "date": "today"})
        assert d["new_visits"] + d["returning_visits"] == d["total_visits"]


# ─── /resolutions ────────────────────────────────────────────────────────────

class TestResolutions:
    def test_has_data(self, http):
        d = post(http, "resolutions", {"period": "week", "date": "today"})
        assert len(d["resolutions"]) > 0

    def test_label_looks_like_resolution(self, http):
        d = post(http, "resolutions", {"period": "week", "date": "today"})
        label = d["resolutions"][0]["label"]
        assert "x" in label.lower() or "×" in label or label == "unknown"


# ─── /ai-referrers ────────────────────────────────────────────────────────────

class TestAIReferrers:
    def test_schema(self, http):
        d = post(http, "ai-referrers", {"period": "month", "date": "today"})
        assert {"sources", "total_visits", "period"} <= d.keys()

    def test_no_date_format_regression(self, http):
        """Regression: previous1,{date} caused Matomo 502."""
        d = post(http, "ai-referrers", {"period": "month", "date": "today"})
        assert "error" not in d

    def test_source_schema(self, http):
        d = post(http, "ai-referrers", {"period": "month", "date": "today"})
        for s in d["sources"]:
            assert {"source", "visits", "prev_visits", "change_pct", "trend"} <= s.keys()
            assert s["trend"] in ("up", "down", "flat")

    def test_week_period(self, http):
        d = post(http, "ai-referrers", {"period": "week", "date": "today"})
        assert "error" not in d


# ─── /insights ───────────────────────────────────────────────────────────────

class TestInsights:
    def test_schema(self, http):
        d = post(http, "insights")
        assert {"insights", "count", "critical_count", "warning_count"} <= d.keys()

    def test_severity_values(self, http):
        d = post(http, "insights")
        for i in d["insights"]:
            assert i["severity"] in ("critical", "warning", "info")

    def test_counts_consistent(self, http):
        d = post(http, "insights")
        assert d["critical_count"] + d["warning_count"] <= d["count"]

    def test_insight_has_action(self, http):
        d = post(http, "insights")
        for i in d["insights"]:
            assert i.get("action"), "insight missing action field"


# ─── /full-report ─────────────────────────────────────────────────────────────

FULL_REPORT_SECTIONS = {
    "traffic", "top_pages", "sources", "devices", "geo", "entry_exit",
    "regions", "brands", "browsers", "search_engines", "keywords",
    "campaigns", "socials", "referring_sites", "site_search",
    "new_returning", "visit_duration", "languages", "providers",
    "resolutions", "page_details", "outlinks",
}


class TestFullReport:
    def test_all_22_sections_present(self, http):
        d = post(http, "full-report", {"period": "week", "date": "today", "limit": 5})
        missing = FULL_REPORT_SECTIONS - d.keys()
        assert not missing, f"missing sections: {missing}"

    def test_zero_error_sections(self, http):
        d = post(http, "full-report", {"period": "week", "date": "today", "limit": 5})
        errors = {k: v["error"] for k, v in d.items()
                  if isinstance(v, dict) and "error" in v}
        assert not errors, f"sections with errors: {errors}"

    def test_completes_under_10s(self, http):
        """22 parallel Matomo calls must finish in under 10 s."""
        payload = {**MATOMO, "period": "week", "date": "today", "limit": 5}
        t0 = time.time()
        r = http.post(f"{MOS}/api/matomo-analytics/full-report", json=payload, headers=HDR)
        elapsed = time.time() - t0
        assert r.status_code == 200
        assert elapsed < 10, f"full-report took {elapsed:.1f}s — too slow"


# ─── error handling ───────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_bad_matomo_token_returns_502(self, http):
        payload = {**MATOMO, "token": "invalid_bad_token_xxx"}
        r = http.post(f"{MOS}/api/matomo-analytics/traffic", json=payload, headers=HDR)
        assert r.status_code == 502

    def test_missing_api_key_returns_401_or_403(self, http):
        r = http.post(f"{MOS}/api/matomo-analytics/traffic",
                      json=MATOMO,
                      headers={"Content-Type": "application/json"})
        assert r.status_code in (401, 403)

    def test_health_check_no_auth(self, http):
        r = http.get(f"{MOS}/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
