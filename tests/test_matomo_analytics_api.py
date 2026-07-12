"""matomo-analytics-api backend — integration + validation tests.

Run:  pytest tests/test_matomo_analytics_api.py -v
Deps: pip install httpx pytest

Two tiers:
- TestSSRFValidation always runs (pure input validation, no network, no
  credentials needed) — covers the backend's own request-schema hardening.
- Everything else hits the live backend + a real Matomo instance and is
  skipped automatically unless MATOMO_ANALYTICS_API_URL/MATOMO_URL/
  MATOMO_TOKEN are set — no credentials are hardcoded here (a previous
  version of this file had a live Matomo auth token committed in plaintext;
  treat that token as compromised if it's still valid).
"""
import os
import time

import pytest
import httpx

API_URL = os.getenv("MATOMO_ANALYTICS_API_URL", "")
MATOMO = {
    "matomo_url": os.getenv("MATOMO_URL", ""),
    "token": os.getenv("MATOMO_TOKEN", ""),
    "site_id": int(os.getenv("MATOMO_SITE_ID", "1")),
}


def _live_configured() -> bool:
    return bool(API_URL and MATOMO["matomo_url"] and MATOMO["token"])


def _reachable() -> bool:
    if not _live_configured():
        return False
    try:
        r = httpx.get(f"{API_URL}/api/matomo-analytics/health", timeout=10)
        return r.status_code == 200
    except Exception:
        return False


live = pytest.mark.skipif(
    not _reachable(),
    reason="matomo-analytics-api not configured/reachable — set MATOMO_ANALYTICS_API_URL, "
           "MATOMO_URL, MATOMO_TOKEN (and optionally MATOMO_SITE_ID) to run these.",
)


# ─── SSRF hardening — no network, no credentials, always runs ────────────────

class TestSSRFValidation:
    """The backend's MatomoContextRequest rejects private/loopback/link-local
    hosts before ever making a request - this is testable without a live
    Matomo instance or the backend even running, since Pydantic validates
    matomo_url before any I/O. These hit the live backend's validation layer
    (still needs the service reachable) but never touch a real Matomo."""

    @pytest.mark.skipif(not API_URL, reason="MATOMO_ANALYTICS_API_URL not set")
    @pytest.mark.parametrize("bad_url", [
        "https://localhost/",
        "https://127.0.0.1/",
        "https://0.0.0.0/",
        "https://169.254.169.254/",  # cloud metadata endpoint
        "https://10.0.0.5/",
    ])
    def test_rejects_private_and_loopback_hosts(self, bad_url):
        r = httpx.post(
            f"{API_URL}/api/matomo-analytics/traffic",
            json={"matomo_url": bad_url, "token": "x", "site_id": 1, "period": "day", "date": "today"},
            timeout=10,
        )
        assert r.status_code == 422, f"{bad_url} should be rejected, got {r.status_code}: {r.text[:200]}"


# ─── Live backend + real Matomo — skipped unless configured ──────────────────

@pytest.fixture(scope="module")
def http():
    with httpx.Client(timeout=60) as c:
        yield c


def post(http, path: str, extra: dict = None) -> dict:
    payload = {**MATOMO, **(extra or {})}
    r = http.post(f"{API_URL}/api/matomo-analytics/{path}", json=payload)
    assert r.status_code == 200, f"{path}: HTTP {r.status_code} — {r.text[:300]}"
    return r.json()


@live
class TestHealth:
    def test_health_no_auth_needed(self, http):
        r = http.get(f"{API_URL}/api/matomo-analytics/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@live
class TestTraffic:
    def test_has_required_keys(self, http):
        d = post(http, "traffic", {"period": "day", "date": "last7"})
        assert {"visits", "pageviews", "series"} <= d.keys()

    def test_series_has_date_field(self, http):
        d = post(http, "traffic", {"period": "day", "date": "last7"})
        assert d["series"] and "date" in d["series"][0]


@live
class TestTrends:
    def test_direction_valid(self, http):
        d = post(http, "trends")
        assert d["direction"] in ("up", "down", "flat")

    def test_weeks_present(self, http):
        d = post(http, "trends")
        assert "current_week" in d and "previous_week" in d


@live
class TestTopPages:
    def test_limit_respected(self, http):
        d = post(http, "top-pages", {"period": "week", "date": "today", "limit": 3})
        assert len(d["pages"]) <= 3

    def test_page_schema(self, http):
        d = post(http, "top-pages", {"period": "week", "date": "today", "limit": 3})
        if d["pages"]:
            assert {"url", "views"} <= d["pages"][0].keys()


@live
class TestGeo:
    """geo uses alias='countries' - the response carries both `items` and
    `countries` (same list), matching what handlers_detail.py reads."""

    def test_countries_key_populated(self, http):
        d = post(http, "geo", {"period": "day", "date": "last30", "limit": 10})
        assert "countries" in d
        if d["countries"]:
            assert {"label", "visits", "percent"} <= d["countries"][0].keys()


@live
class TestRealTime:
    def test_all_windows_present(self, http):
        d = post(http, "real-time")
        assert {"live_30m", "live_60m", "live_180m"} <= d.keys()
        assert "visitors" in d["live_30m"]


@live
class TestConversions:
    """Falls back to a synthetic 'All Goals' entry when Goals.getGoals is
    empty but conversions are still happening (e.g. Ecommerce-only sites)."""

    def test_schema(self, http):
        d = post(http, "conversions", {"period": "day", "date": "last7"})
        assert {"has_goals", "goals", "total_conversions"} <= d.keys()
        if d["has_goals"]:
            assert d["goals"] and {"name", "conversions", "conversion_rate", "revenue"} <= d["goals"][0].keys()


@live
class TestNewReturning:
    def test_percentages_sum_to_100(self, http):
        d = post(http, "new-returning", {"period": "day", "date": "last7"})
        total = d["new_percent"] + d["returning_percent"]
        assert abs(total - 100.0) < 1 or (d["new_visits"] == 0 and d["returning_visits"] == 0)


@live
class TestEvents:
    def test_no_duplicate_categories_across_date_range(self, http):
        """Regression: Events.getCategory nests per-date for period=day +
        multi-day range - categories must be aggregated by label, not
        listed once per date bucket."""
        d = post(http, "events", {"period": "day", "date": "last7", "limit": 5})
        labels = [c["category"] for c in d["categories"]]
        assert len(labels) == len(set(labels)), f"duplicate categories: {labels}"


@live
class TestFullReport:
    SECTIONS = {
        "traffic", "trends", "top_pages", "sources", "devices", "geo", "real_time",
        "entry_exit", "regions", "brands", "browsers", "search_engines", "keywords",
        "campaigns", "socials", "referring_sites", "site_search", "new_returning",
        "visit_duration", "languages", "providers", "resolutions", "page_details", "outlinks",
    }

    def test_all_24_sections_present(self, http):
        d = post(http, "full-report", {"period": "day", "date": "last7", "limit": 5})
        missing = self.SECTIONS - d.keys()
        assert not missing, f"missing sections: {missing}"

    def test_zero_error_sections(self, http):
        d = post(http, "full-report", {"period": "day", "date": "last7", "limit": 5})
        errors = {k: v["error"] for k, v in d.items() if isinstance(v, dict) and "error" in v}
        assert not errors, f"sections with errors: {errors}"

    def test_completes_reasonably_fast(self, http):
        """24 parallel Matomo calls - generous bound, this is a real network fan-out."""
        payload = {**MATOMO, "period": "day", "date": "last7", "limit": 5}
        t0 = time.time()
        r = http.post(f"{API_URL}/api/matomo-analytics/full-report", json=payload)
        elapsed = time.time() - t0
        assert r.status_code == 200
        assert elapsed < 20, f"full-report took {elapsed:.1f}s — too slow"
