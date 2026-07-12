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


class TrafficParams(BaseModel):
    period: Period = Field(default="day", description=_PERIOD_HELP)
    date: str = Field(default="last7", description=_DATE_HELP)


class TopPagesParams(BaseModel):
    period: Period = Field(default="month", description=_PERIOD_HELP)
    date: str = Field(default="today", description=_DATE_HELP)
    limit: int = Field(default=10, ge=1, le=100)


class TrendsParams(BaseModel):
    """No params - compares the last 7 full days to the 7 before that."""
    pass


class SaveSettingsParams(BaseModel):
    """Form payload - user's Matomo + backend connection settings."""
    backend_url: str = ""
    backend_api_key: str = ""
    matomo_url: str = ""
    matomo_token: str = ""
    matomo_site_id: int = 1
    matomo_segment: str = ""
    blog_url: str = ""          # e.g. https://blog.example.com
    blog_site_id: int = 0       # Matomo site ID for blog (0 = same as main site_id)
    utm_source_dim_id: int = 0  # Custom Dimension ID for utm_source (0 = disabled)
