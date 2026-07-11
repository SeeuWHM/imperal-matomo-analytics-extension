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


class EventCategoryRecord(BaseModel):
    category: str = ""
    events: int = 0
    actions: list[EventActionRecord] = Field(default_factory=list)


class EventsResponse(BaseModel):
    total_events: int = 0
    categories: list[EventCategoryRecord] = Field(default_factory=list)


class UTMSourceRecord(BaseModel):
    source: str = ""
    visits: int = 0
    percent: Optional[float] = None


class UTMSourcesResponse(BaseModel):
    ai_utm_visits: int = 0
    utm_sources: list[UTMSourceRecord] = Field(default_factory=list)


class SimpleListResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
