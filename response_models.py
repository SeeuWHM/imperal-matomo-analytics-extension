from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class AnalyticsScalarResponse(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class TrafficOverviewRecord(BaseModel):
    visits: int = 0
    pageviews: int = 0
    unique_visitors: Optional[int] = None
    bounce_rate: Optional[float | str] = None
    avg_time_on_site: Optional[float | str] = None
    period: Optional[str] = None
    date: Optional[str] = None


class PageMetricRecord(BaseModel):
    url: str = ""
    title: Optional[str] = None
    views: int = 0
    visits: Optional[int] = None
    bounce_rate: Optional[str | float] = None
    avg_time_on_page: Optional[str | float] = None


class PageListResponse(BaseModel):
    pages: list[PageMetricRecord] = Field(default_factory=list)


class TrendSummaryResponse(BaseModel):
    current_week: int = 0
    previous_week: int = 0
    change_percent: float = 0.0
    direction: str = "flat"


class SimpleBreakdownRecord(BaseModel):
    label: str = ""
    visits: int = 0
    percent: float = 0.0


class BreakdownResponse(BaseModel):
    items: list[SimpleBreakdownRecord] = Field(default_factory=list)


class LiveVisitorsWindow(BaseModel):
    visitors: int = 0


class LiveVisitorsResponse(BaseModel):
    live_30m: Optional[LiveVisitorsWindow] = None
    live_60m: Optional[LiveVisitorsWindow] = None
    live_180m: Optional[LiveVisitorsWindow] = None


class InsightItem(BaseModel):
    severity: str = "info"
    title: str = ""
    detail: str = ""
    action: str = ""


class InsightsResponse(BaseModel):
    count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    insights: list[InsightItem] = Field(default_factory=list)


class DailyReportResponse(BaseModel):
    brief: str = ""
    facts: str = ""


class AlertListResponse(BaseModel):
    count: int = 0
    alerts: list[InsightItem] = Field(default_factory=list)


class AIReferrerRecord(BaseModel):
    source: str = ""
    visits: int = 0
    change_pct: float = 0.0


class AIReferrersResponse(BaseModel):
    total_visits: int = 0
    sources: list[AIReferrerRecord] = Field(default_factory=list)


class GoalRecord(BaseModel):
    name: str = ""
    conversions: int = 0
    conversion_rate: Optional[str] = None
    revenue: Optional[float] = None


class ConversionsResponse(BaseModel):
    has_goals: bool = False
    total_conversions: int = 0
    goals: list[GoalRecord] = Field(default_factory=list)
    message: Optional[str] = None


class EventActionRecord(BaseModel):
    action: str = ""
    events: int = 0


class EventCategoryRecord(BaseModel):
    category: str = ""
    events: int = 0
    actions: list[EventActionRecord] = Field(default_factory=list)


class EventsResponse(BaseModel):
    total_events: int = 0
    categories: list[EventCategoryRecord] = Field(default_factory=list)


class UTMSourceRecord(BaseModel):
    label: str = ""
    visits: int = 0
    percent: Optional[float] = None
    is_ai: bool = False


class UTMSourcesResponse(BaseModel):
    ai_utm_visits: int = 0
    utm_sources: list[UTMSourceRecord] = Field(default_factory=list)


class SimpleListResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class EntryExitResponse(BaseModel):
    entry_pages: list[PageMetricRecord] = Field(default_factory=list)
    exit_pages: list[PageMetricRecord] = Field(default_factory=list)


class NewReturningResponse(BaseModel):
    new_visits: int = 0
    returning_visits: int = 0
    new_percent: float = 0.0
    returning_percent: float = 0.0


class SiteSearchResponse(BaseModel):
    keywords: list[SimpleBreakdownRecord] = Field(default_factory=list)
    no_results: list[SimpleBreakdownRecord] = Field(default_factory=list)


class BrowsersResponse(BaseModel):
    browsers: list[SimpleBreakdownRecord] = Field(default_factory=list)
    os_families: list[SimpleBreakdownRecord] = Field(default_factory=list)


class SiteEntry(BaseModel):
    label: str = ""
    site_id: int = 0
    active: bool = False
    segment: Optional[str] = None
    known_domains: list[str] = Field(default_factory=list)


class SitesListResponse(BaseModel):
    sites: list[SiteEntry] = Field(default_factory=list)


class SavedKeysResponse(BaseModel):
    saved_keys: list[str] = Field(default_factory=list)


class SuggestedSegment(BaseModel):
    domain: str = ""
    segment: str = ""


class SiteInfoResponse(BaseModel):
    name: str = ""
    main_url: str = ""
    urls: list[str] = Field(default_factory=list)
    timezone: Optional[str] = None
    currency: Optional[str] = None
    created_at: Optional[str] = None
    suggested_segments: list[SuggestedSegment] = Field(default_factory=list)
