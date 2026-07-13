"""Pydantic models for chat-function parameters.

Fields use Literal types where Matomo has a closed enum - that way the
platform's function schema tells the LLM exactly which values are legal
and Webbee stops hallucinating things like period="10days".

NOTE: no `from __future__ import annotations` here - V6 validator and the
chat.handler need to resolve the Literal types at import time to generate
the function schema.
"""
from typing import Literal

from pydantic import BaseModel, Field


# Accepted Matomo periods. Outside this set Matomo returns 502.
Period = Literal["day", "week", "month", "year", "range"]

_DATE_HELP = (
    "Matomo date string. Presets: today, yesterday, last7, last14, last30, last90, "
    "thisWeek, lastWeek, thisMonth, lastMonth, thisYear. "
    "Custom range: use period='range' and date='YYYY-MM-DD,YYYY-MM-DD' — "
    "e.g. 'с 10 апреля по 20 апреля' → period=range, date=2026-04-10,2026-04-20."
)

_PERIOD_HELP = (
    "Granularity: day, week, month, year, or range (for custom date spans). "
    "Use 'range' when the user specifies a specific start and end date."
)

_SITE_HELP = (
    "Which site/project to report on - a label from list_sites (the name the "
    "user gave when adding it). Omit to use the user's default site."
)

_SITES_HELP = (
    "Compare 2+ sites/domains side by side - a list of labels from list_sites, "
    "e.g. ['Main', 'Blog']. When given, this replaces `site` and the result is "
    "a per-site breakdown instead of a single answer. Omit for a normal, "
    "single-site question."
)


class TrafficParams(BaseModel):
    period: Period = Field(default="day", description=_PERIOD_HELP)
    date: str = Field(default="last7", description=_DATE_HELP)
    site: str = Field(default="", description=_SITE_HELP)
    sites: list[str] | None = Field(default=None, description=_SITES_HELP)


class TopPagesParams(BaseModel):
    period: Period = Field(default="month", description=_PERIOD_HELP)
    date: str = Field(default="today", description=_DATE_HELP)
    limit: int = Field(default=10, ge=1, le=100)
    site: str = Field(default="", description=_SITE_HELP)
    sites: list[str] | None = Field(default=None, description=_SITES_HELP)


class TrendsParams(BaseModel):
    """Compares the last 7 full days to the 7 before that."""
    site: str = Field(default="", description=_SITE_HELP)
    sites: list[str] | None = Field(default=None, description=_SITES_HELP)


class SaveSettingsParams(BaseModel):
    """Form payload for non-secret settings. Matomo URL/Auth Token live in the
    platform's Secrets panel (EXT-SECRETS-V1), not here."""
    matomo_segment: str = ""
    utm_source_dim_id: int = 0  # Custom Dimension ID for utm_source (0 = disabled)


class AddSiteParams(BaseModel):
    label: str = Field(min_length=1, max_length=60, description="Display name for this site/project, e.g. 'Main Website' or 'Site 2'.")
    site_id: int = Field(ge=1, description="The Matomo site ID (idSite) to track under this label.")
    segment: str = Field(
        default="", max_length=500,
        description="Optional Matomo segment to scope this project to part of the site instead of "
                    "the whole thing - e.g. a subdomain that shares a Matomo site_id with other "
                    "content. Use site_domains to see the real domains configured for a site_id, "
                    "then pass segment=\"pageUrl=^<that domain URL>\" (e.g. "
                    "pageUrl=^https://blog.example.com). Leave blank to track the entire site.",
    )


class RemoveSiteParams(BaseModel):
    label: str = Field(min_length=1, description="Label of the site to remove, as shown by list_sites.")


class SetActiveSiteParams(BaseModel):
    label: str = Field(min_length=1, description="Label of the site/project to make the default (from list_sites).")


class ListSitesParams(BaseModel):
    """No input needed."""
    pass


class SiteDomainsParams(BaseModel):
    site: str = Field(default="", description=_SITE_HELP)


class ViewDomainParams(BaseModel):
    site_id: int = Field(ge=1, description="Matomo site_id to pick a domain within (from site_domains/list_sites).")
    domain: str = Field(
        min_length=1, max_length=300,
        description="One of the domains returned by site_domains for this site_id, or "
                    "'All domains' to clear the filter and view the whole site again.",
    )


# ─── Audience / channel breakdown params — shared across handlers_audience.py
# and handlers_channels.py (split apart to stay under the 300-line file limit) ──

class AudienceParams(BaseModel):
    period: str = Field(default="week", description=_PERIOD_HELP)
    date: str   = Field(default="today", description=_DATE_HELP)
    limit: int  = Field(default=20, ge=1, le=100)
    site: str   = Field(default="", description=_SITE_HELP)


class AIReferrersParams(BaseModel):
    period: str = Field(default="month", description=_PERIOD_HELP)
    date: str   = Field(default="today", description=_DATE_HELP)
    site: str   = Field(default="", description=_SITE_HELP)


class ConversionsParams(BaseModel):
    period: str = Field(default="month", description=_PERIOD_HELP)
    date: str   = Field(default="today", description=_DATE_HELP)
    site: str   = Field(default="", description=_SITE_HELP)
