"""Tests for panels_render.error_banner / _clean_error_detail — the guard
against silently rendering a failed backend call as legitimate zero data.

Real-world trigger (2026-07-21): the user's Matomo instance was locked out
("Too many failed logins"), so every /api/matomo-analytics/* call the
backend made came back as an HTML error page wrapped in a Python exception
string. call_mos()/call_mos_cached() turn that into {"error": "<the raw
string>"}. Before error_banner existed, every panel just read individual
fields with .get(x, 0) from that dict, producing a dashboard that loaded
FAST (no timeout, no crash) and showed all-zero stats - indistinguishable
from a real empty-but-successful response. That's the exact bug reported.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from panels_render import error_banner, _clean_error_detail


def test_clean_error_detail_extracts_h2_from_matomo_html_page():
    raw = (
        "Matomo API error 500: <!DOCTYPE html><html><head><title>Matomo &rsaquo; "
        "Error</title></head><body><div class=\"content\"><h2>Too many failed "
        "logins. Please wait and try logging in again later.</h2><p>...</p></div>"
        "</body></html>"
    )
    assert _clean_error_detail(raw) == "Too many failed logins. Please wait and try logging in again later."


def test_clean_error_detail_falls_back_to_plain_text():
    assert _clean_error_detail("Matomo not configured - open Settings and add your URL + Auth Token.") == \
        "Matomo not configured - open Settings and add your URL + Auth Token."


def test_clean_error_detail_handles_empty():
    assert _clean_error_detail("") == "Unknown error"


def test_error_banner_none_when_everything_clean():
    banner = error_banner({"Traffic": {"visits": 10}, "Trends": {"change_percent": 5}})
    assert banner is None


def test_error_banner_none_for_genuinely_empty_but_unerrored_payload():
    """{} with no "error" key is a real empty result (e.g. brand-new site,
    zero visits yet) - must NOT be flagged as a failure."""
    banner = error_banner({"Traffic": {}, "Trends": {}})
    assert banner is None


def test_error_banner_fires_on_any_section_with_error_key():
    banner = error_banner({
        "Traffic": {"error": "Matomo API error 500: locked out"},
        "Trends": {"change_percent": 5},
    })
    assert banner is not None
    d = banner.to_dict()
    assert d["type"] == "Alert"
    assert "Traffic" in d["props"]["message"] or "Traffic" in str(d["props"].get("title", ""))


def test_error_banner_names_every_failed_section():
    banner = error_banner({
        "Traffic": {"error": "boom"},
        "Sources": {"error": "boom"},
        "Devices": {"visits": 1},
    })
    assert banner is not None
    text = str(banner.to_dict())
    assert "Traffic" in text
    assert "Sources" in text
    assert "Devices" not in text
