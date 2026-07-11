"""Chat functions for audience, channel, and engagement analytics.

All new endpoints introduced in analytics_audience on the MOS server:
regions, brands, browsers, search-engines, keywords, campaigns, socials,
referring-sites, site-search, new-returning, visit-duration, languages,
providers, resolutions, page-details, outlinks, full-report.
"""
# No `from __future__ import annotations` - V6 validator needs real annotations.

from typing import Union

from pydantic import BaseModel, Field
from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat, ext, save_result
from api_client import call_mos, HEAVY_TIMEOUT
from params import _DATE_HELP, _PERIOD_HELP


# ─── Shared params model ──────────────────────────────────────────────────────

class _AudienceParams(BaseModel):
    period: str = Field(default="week", description=_PERIOD_HELP)
    date: str   = Field(default="today", description=_DATE_HELP)
    limit: int  = Field(default=20, ge=1, le=100)


class _AIReferrersParams(BaseModel):
    period: str = Field(default="month", description=_PERIOD_HELP)
    date: str   = Field(default="today", description=_DATE_HELP)


class _ConversionsParams(BaseModel):
    period: str = Field(default="month", description=_PERIOD_HELP)
    date: str   = Field(default="today", description=_DATE_HELP)


# ─── Error helper ─────────────────────────────────────────────────────────────

def _err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _table(rows: list[dict], label_col: str = "Label") -> Union[ui.DataTable, ui.Empty]:
    if not rows:
        return ui.Empty(message="No data")
    return ui.DataTable(
        columns=[
            ui.DataColumn(key="label", label=label_col, width="55%"),
            ui.DataColumn(key="visits", label="Visits", width="22%"),
            ui.DataColumn(key="pct", label="Share", width="23%"),
        ],
        rows=[
            {"label": r.get("label", "-"),
             "visits": f"{r.get('visits', 0):,}",
             "pct": f"{r.get('percent', 0)}%"}
            for r in rows[:15]
        ],
    )


def _top(items: list[dict]) -> tuple[str, float]:
    """Return (label, percent) of the first item."""
    if items:
        return items[0].get("label", "n/a"), items[0].get("percent", 0)
    return "n/a", 0


# ─── ai_referrers ─────────────────────────────────────────────────────────────

@chat.function("ai_referrers",
               description=(
                   "Which AI assistants and LLMs send traffic — ChatGPT, Perplexity, Claude, "
                   "Gemini, DeepSeek, Grok, Copilot. Combines referrer detection + UTM tracking. "
                   "Default period=month for meaningful data. "
                   "Use for: с каких нейросетей трафик, ChatGPT traffic, AI referrers, "
                   "нейронки шлют трафик, which AI sends visitors, LLM traffic."
               ),
               action_type="read", event="analytics.action.result")
async def fn_ai_referrers(ctx, params: _AIReferrersParams) -> ActionResult:
    """Handler: fn_ai_referrers."""
    data = await call_mos(ctx, "/api/analytics/ai-referrers", {
        "period": params.period, "date": params.date,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "ai_referrers", "AI referrers", data)
    sources = data.get("sources") or []
    total = data.get("total_visits", 0)
    top = sources[0] if sources else {}
    rows = [
        {
            "source": s.get("source", "-"),
            "visits": f"{s.get('visits', 0):,}",
            "change": f"{s.get('change_pct', 0):+.1f}%",
        }
        for s in sources
    ]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="source", label="AI Source", width="45%"),
            ui.DataColumn(key="visits", label="Visits",    width="25%"),
            ui.DataColumn(key="change", label="vs prev",   width="30%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No AI referrer traffic detected this period")
    return ActionResult.success(
        data=data,
        summary=f"{total:,} visits from AI — top: {top.get('source', 'none')} ({top.get('visits', 0):,})",
        ui=ui_node,
    )


# ─── conversions ─────────────────────────────────────────────────────────────

@chat.function("conversions",
               description=(
                   "Goal conversions from Matomo: purchases (cart complete), checkouts started, "
                   "conversion rate. Use for: конверсии, покупки, заказы, сколько купили, "
                   "checkout, воронка продаж, purchase funnel, how many orders."
               ),
               action_type="read", event="analytics.action.result")
async def fn_conversions(ctx, params: _ConversionsParams) -> ActionResult:
    """Handler: fn_conversions."""
    data = await call_mos(ctx, "/api/analytics/conversions", {
        "period": params.period, "date": params.date,
    })
    if "error" in data:
        return ActionResult.error(error=data.get("error", "unknown error"))
    await save_result(ctx, "conversions", "Conversions", data)

    if not data.get("has_goals"):
        return ActionResult.success(
            data=data,
            summary="No goals configured in Matomo — set up goals to track conversions",
            ui=ui.Alert(
                message=data.get("message", "Configure goals in Matomo to track conversions."),
                type="warning",
            ),
        )

    goals = data.get("goals") or []
    total = data.get("total_conversions", 0)
    rows = [
        {
            "goal":  g.get("name", "-")[:35],
            "conv":  f"{g.get('conversions', 0):,}",
            "rate":  g.get("conversion_rate", "0%"),
            "rev":   f"${g.get('revenue', 0):.0f}" if g.get("revenue") else "—",
        }
        for g in goals[:10]
    ]
    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="goal", label="Goal",       width="40%"),
            ui.DataColumn(key="conv", label="Conversions", width="20%"),
            ui.DataColumn(key="rate", label="Rate",        width="20%"),
            ui.DataColumn(key="rev",  label="Revenue",     width="20%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No conversion data")

    top = goals[0] if goals else {}
    return ActionResult.success(
        data=data,
        summary=f"{total:,} total conversions | top goal: {top.get('name','')} ({top.get('conversions',0):,})",
        ui=ui_node,
    )


# ─── events ───────────────────────────────────────────────────────────────────

@chat.function("events",
               description=(
                   "Custom tracking events: engagement (scrolls, clicks) and ecommerce events "
                   "(begin_checkout). Use for: события, события аналитики, engagement events, "
                   "scroll depth, ecommerce events, what is being tracked."
               ),
               action_type="read", event="analytics.action.result")
async def fn_events(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_events."""
    data = await call_mos(ctx, "/api/analytics/events", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return ActionResult.error(error=data.get("error", "unknown error"))
    await save_result(ctx, "events", "Events", data)

    cats = data.get("categories") or []
    total = data.get("total_events", 0)
    rows = []
    for c in cats[:10]:
        actions = ", ".join(a["action"] for a in c.get("actions", [])[:3])
        rows.append({
            "category": c.get("category", "-"),
            "events":   f"{c.get('events', 0):,}",
            "actions":  actions or "—",
        })

    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="category", label="Category", width="30%"),
            ui.DataColumn(key="events",   label="Events",   width="20%"),
            ui.DataColumn(key="actions",  label="Actions",  width="50%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No events tracked")

    return ActionResult.success(
        data=data,
        summary=f"{total:,} total events across {len(cats)} categories",
        ui=ui_node,
    )


# ─── utm_sources ──────────────────────────────────────────────────────────────

@chat.function("utm_sources",
               description=(
                   "UTM source breakdown from custom dimensions — shows which sources "
                   "sent tagged traffic including AI sources with UTM parameters. "
                   "Use for: utm источники, utm_source, tagged traffic, платный трафик, "
                   "ChatGPT referral with UTM, campaign sources."
               ),
               action_type="read", event="analytics.action.result")
async def fn_utm_sources(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_utm_sources."""
    data = await call_mos(ctx, "/api/analytics/utm-sources", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return ActionResult.error(error=data.get("error", "unknown error"))
    await save_result(ctx, "utm_sources", "UTM Sources", data)

    sources = data.get("utm_sources") or []
    ai_visits = data.get("ai_utm_visits", 0)
    top = sources[0] if sources else {}

    rows = [
        {
            "source": s.get("label", "-")[:35],
            "visits": f"{s.get('visits', 0):,}",
            "pct":    f"{s.get('percent', 0)}%",
            "ai":     "🤖" if s.get("is_ai") else "",
        }
        for s in sources[:15]
    ]

    ui_node = ui.DataTable(
        columns=[
            ui.DataColumn(key="source", label="UTM Source", width="48%"),
            ui.DataColumn(key="visits", label="Visits",     width="20%"),
            ui.DataColumn(key="pct",    label="%",          width="20%"),
            ui.DataColumn(key="ai",     label="AI",         width="12%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No UTM-tagged traffic found")

    return ActionResult.success(
        data=data,
        summary=f"Top UTM source: {top.get('label','none')} ({top.get('visits',0):,} visits) | AI UTM: {ai_visits:,}",
        ui=ui_node,
    )


# ─── regions ──────────────────────────────────────────────────────────────────

@chat.function("regions",
               description="Visitor breakdown by city and region.",
               action_type="read", event="analytics.action.result")
async def fn_regions(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_regions."""
    data = await call_mos(ctx, "/api/analytics/regions", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "regions", "Regions", data)
    regions = data.get("regions") or []
    lbl, pct = _top(regions)
    return ActionResult.success(
        data=data,
        summary=f"Top region: {lbl} ({pct}%)",
        ui=ui.Section(title="Top Regions", children=[_table(regions, "Region")]),
    )


# ─── device_brands ────────────────────────────────────────────────────────────

@chat.function("device_brands",
               description="Phone and tablet brands (Apple, Samsung, etc.).",
               action_type="read", event="analytics.action.result")
async def fn_device_brands(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_device_brands."""
    data = await call_mos(ctx, "/api/analytics/brands", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "device_brands", "Device brands", data)
    brands = data.get("brands") or []
    lbl, pct = _top(brands)
    return ActionResult.success(
        data=data,
        summary=f"Top brand: {lbl} ({pct}%)",
        ui=ui.Section(title="Device Brands", children=[_table(brands, "Brand")]),
    )


# ─── browsers ─────────────────────────────────────────────────────────────────

@chat.function("browsers",
               description="Browser breakdown (Chrome, Firefox, Safari, Edge, Opera) AND OS breakdown "
                           "(Windows, macOS, Linux, Android, iOS). "
                           "Use for: сравни браузеры, какие браузеры используют, Chrome vs Safari, "
                           "browser compatibility, ОС пользователей, работает ли на всех браузерах.",
               action_type="read", event="analytics.action.result")
async def fn_browsers(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_browsers."""
    data = await call_mos(ctx, "/api/analytics/browsers", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "browsers", "Browsers & OS", data)
    browsers = data.get("browsers") or []
    os_fams  = data.get("os_families") or []
    lbl, pct = _top(browsers)
    return ActionResult.success(
        data=data,
        summary=f"Top browser: {lbl} ({pct}%)",
        ui=ui.Section(title="Browsers & OS", children=[
            _table(browsers, "Browser"),
            _table(os_fams, "OS"),
        ]),
    )


# ─── search_engines ───────────────────────────────────────────────────────────

@chat.function("search_engines",
               description="Which search engines send organic traffic.",
               action_type="read", event="analytics.action.result")
async def fn_search_engines(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_search_engines."""
    data = await call_mos(ctx, "/api/analytics/search-engines", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "search_engines", "Search engines", data)
    items = data.get("search_engines") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top search engine: {lbl} ({pct}%)",
        ui=_table(items, "Search Engine"),
    )


# ─── organic_keywords ─────────────────────────────────────────────────────────

@chat.function("organic_keywords",
               description="Organic search keywords (may show 'not provided' if encrypted).",
               action_type="read", event="analytics.action.result")
async def fn_organic_keywords(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_organic_keywords."""
    data = await call_mos(ctx, "/api/analytics/keywords", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "organic_keywords", "Organic keywords", data)
    items = data.get("keywords") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top keyword: {lbl} ({pct}%)",
        ui=_table(items, "Keyword"),
    )


# ─── campaigns ────────────────────────────────────────────────────────────────

@chat.function("campaigns",
               description="UTM campaign performance.",
               action_type="read", event="analytics.action.result")
async def fn_campaigns(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_campaigns."""
    data = await call_mos(ctx, "/api/analytics/campaigns", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "campaigns", "Campaigns", data)
    items = data.get("campaigns") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top campaign: {lbl} ({pct}%)",
        ui=_table(items, "Campaign"),
    )


# ─── social_networks ──────────────────────────────────────────────────────────

@chat.function("social_networks",
               description="Social network traffic breakdown.",
               action_type="read", event="analytics.action.result")
async def fn_social_networks(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_social_networks."""
    data = await call_mos(ctx, "/api/analytics/socials", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "social_networks", "Social networks", data)
    items = data.get("socials") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top social: {lbl} ({pct}%)",
        ui=_table(items, "Network"),
    )


# ─── referring_sites ──────────────────────────────────────────────────────────

@chat.function("referring_sites",
               description="Referral websites sending visitors.",
               action_type="read", event="analytics.action.result")
async def fn_referring_sites(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_referring_sites."""
    data = await call_mos(ctx, "/api/analytics/referring-sites", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "referring_sites", "Referring sites", data)
    items = data.get("referring_sites") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top referrer: {lbl} ({pct}%)",
        ui=_table(items, "Referrer"),
    )


# ─── site_search ──────────────────────────────────────────────────────────────

@chat.function("site_search",
               description="Internal site search terms including zero-result queries.",
               action_type="read", event="analytics.action.result")
async def fn_site_search(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_site_search."""
    data = await call_mos(ctx, "/api/analytics/site-search", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "site_search", "Site search", data)
    keywords  = data.get("keywords") or []
    no_result = data.get("no_results") or []
    lbl, pct = _top(keywords)
    return ActionResult.success(
        data=data,
        summary=f"Top search: '{lbl}' | {len(no_result)} zero-result terms",
        ui=ui.Section(title="Site Search", children=[
            _table(keywords, "Search Term"),
            _table(no_result, "No-Result Term"),
        ]),
    )


# ─── new_vs_returning ─────────────────────────────────────────────────────────

@chat.function("new_vs_returning",
               description="New visitors vs returning visitors ratio and counts. "
                           "Use for: новые vs возвращающиеся, лояльность аудитории, "
                           "сколько новых пользователей, retention, returning users percentage.",
               action_type="read", event="analytics.action.result")
async def fn_new_vs_returning(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_new_vs_returning."""
    data = await call_mos(ctx, "/api/analytics/new-returning", {
        "period": params.period, "date": params.date,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "new_vs_returning", "New vs returning", data)
    new_pct = data.get("new_percent", 0)
    ret_pct = data.get("returning_percent", 0)
    return ActionResult.success(
        data=data,
        summary=f"New: {new_pct}% | Returning: {ret_pct}%",
        ui=ui.Stats(children=[
            ui.Stat(label="New visitors", value=f"{data.get('new_visits', 0):,}",
                    color="green", icon="UserPlus"),
            ui.Stat(label="Returning", value=f"{data.get('returning_visits', 0):,}",
                    color="blue", icon="RefreshCw"),
        ]),
    )


# ─── visit_duration ───────────────────────────────────────────────────────────

@chat.function("visit_duration",
               description="Session duration distribution buckets.",
               action_type="read", event="analytics.action.result")
async def fn_visit_duration(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_visit_duration."""
    data = await call_mos(ctx, "/api/analytics/visit-duration", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "visit_duration", "Visit duration", data)
    buckets = data.get("buckets") or []
    lbl, pct = _top(buckets)
    return ActionResult.success(
        data=data,
        summary=f"Most common duration: {lbl} ({pct}% of sessions)",
        ui=_table(buckets, "Duration"),
    )


# ─── languages ────────────────────────────────────────────────────────────────

@chat.function("languages",
               description="Visitor browser language preferences.",
               action_type="read", event="analytics.action.result")
async def fn_languages(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_languages."""
    data = await call_mos(ctx, "/api/analytics/languages", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "languages", "Languages", data)
    items = data.get("languages") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top language: {lbl} ({pct}%)",
        ui=_table(items, "Language"),
    )


# ─── providers ────────────────────────────────────────────────────────────────

@chat.function("providers",
               description="ISP and network providers of visitors.",
               action_type="read", event="analytics.action.result")
async def fn_providers(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_providers."""
    data = await call_mos(ctx, "/api/analytics/providers", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "providers", "Providers", data)
    items = data.get("providers") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top provider: {lbl} ({pct}%)",
        ui=_table(items, "Provider"),
    )


# ─── screen_resolutions ───────────────────────────────────────────────────────

@chat.function("screen_resolutions",
               description="Screen resolution distribution: 1920x1080, 1366x768, mobile resolutions, etc. "
                           "Use for: разрешения экранов, с каких экранов заходят, "
                           "1080p vs 720p, мобильные разрешения, screen size breakdown.",
               action_type="read", event="analytics.action.result")
async def fn_screen_resolutions(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_screen_resolutions."""
    data = await call_mos(ctx, "/api/analytics/resolutions", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "screen_resolutions", "Screen resolutions", data)
    items = data.get("resolutions") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top resolution: {lbl} ({pct}%)",
        ui=_table(items, "Resolution"),
    )


# ─── page_details ─────────────────────────────────────────────────────────────

@chat.function("page_details",
               description="All pages with time-on-page, bounce rate, and avg actions.",
               action_type="read", event="analytics.action.result")
async def fn_page_details(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_page_details."""
    data = await call_mos(ctx, "/api/analytics/page-details", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "page_details", "Page details", data)
    pages = data.get("pages") or []
    top = pages[0] if pages else {}
    rows = [
        {
            "url": p.get("url", "/"),
            "visits": f"{p.get('visits', 0):,}",
            "avg_time": str(p.get("avg_time_on_page", 0)),
            "bounce": p.get("bounce_rate", "0%"),
        }
        for p in pages[:15]
    ]
    table = ui.DataTable(
        columns=[
            ui.DataColumn(key="url",      label="Page",       width="45%"),
            ui.DataColumn(key="visits",   label="Visits",     width="18%"),
            ui.DataColumn(key="avg_time", label="Avg Time",   width="18%"),
            ui.DataColumn(key="bounce",   label="Bounce",     width="19%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No page data")
    return ActionResult.success(
        data=data,
        summary=f"Top page: {top.get('url', 'n/a')} ({top.get('visits', 0):,} visits)",
        ui=table,
    )


# ─── outlinks ─────────────────────────────────────────────────────────────────

@chat.function("outlinks",
               description="Outbound link clicks tracked by Matomo.",
               action_type="read", event="analytics.action.result")
async def fn_outlinks(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_outlinks."""
    data = await call_mos(ctx, "/api/analytics/outlinks", {
        "period": params.period, "date": params.date, "limit": params.limit,
    })
    if "error" in data:
        return _err(data)
    await save_result(ctx, "outlinks", "Outlinks", data)
    items = data.get("outlinks") or []
    lbl, pct = _top(items)
    return ActionResult.success(
        data=data,
        summary=f"Top outlink: {lbl} ({pct}% of clicks)",
        ui=_table(items, "URL"),
    )


# ─── full_report ──────────────────────────────────────────────────────────────

@chat.function("full_report",
               description="Fetch ALL analytics data in one call — traffic, geo, devices, referrers, engagement, AI referrers, audience. Runs in background, result delivered to chat.",
               action_type="read", event="analytics.action.result",
               background=True, long_running=False)
async def fn_full_report(ctx, params: _AudienceParams) -> ActionResult:
    """Handler: fn_full_report."""
    await ctx.progress(10, "Fetching all analytics data from Matomo...")
    data = await call_mos(ctx, "/api/analytics/full-report", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, timeout=HEAVY_TIMEOUT)
    if "error" in data:
        return _err(data)
    await ctx.progress(75, "Processing results...")

    # Persist each section individually so other functions can read them
    for key, label in [
        ("traffic", "Traffic"), ("top_pages", "Top pages"),
        ("sources", "Sources"), ("devices", "Devices"), ("geo", "Countries"),
        ("entry_exit", "Entry/Exit"), ("regions", "Regions"),
        ("brands", "Device brands"), ("browsers", "Browsers"),
        ("search_engines", "Search engines"), ("keywords", "Keywords"),
        ("campaigns", "Campaigns"), ("socials", "Social networks"),
        ("referring_sites", "Referring sites"), ("site_search", "Site search"),
        ("new_returning", "New vs returning"), ("visit_duration", "Visit duration"),
        ("languages", "Languages"), ("providers", "Providers"),
        ("resolutions", "Screen resolutions"), ("page_details", "Page details"),
        ("outlinks", "Outlinks"),
    ]:
        section = data.get(key)
        if section and "error" not in section:
            await save_result(ctx, key, label, section)

    # Build a compact summary from key metrics
    traffic     = data.get("traffic") or {}
    new_ret     = data.get("new_returning") or {}
    sources     = data.get("sources") or {}
    top_src     = (sources.get("sources") or [{}])[0]
    geo         = data.get("geo") or {}
    top_country = (geo.get("countries") or [{}])[0]

    visits   = traffic.get("visits", 0)
    brate    = traffic.get("bounce_rate", "n/a")
    new_pct  = new_ret.get("new_percent", 0)
    src_lbl  = top_src.get("label", "n/a")
    src_pct  = top_src.get("percent", 0)
    cntry    = top_country.get("label", "n/a")

    errors   = [k for k, v in data.items() if isinstance(v, dict) and "error" in v]
    err_note = f" ({len(errors)} sections unavailable)" if errors else ""

    summary = (
        f"Full report{err_note}: {visits:,} visits, bounce {brate}, "
        f"{new_pct}% new visitors. "
        f"Top source: {src_lbl} ({src_pct}%). Top country: {cntry}."
    )

    await ctx.progress(95, "Building report...")
    return ActionResult.success(
        data=data,
        summary=summary,
        ui=ui.Stats(children=[
            ui.Stat(label="Visits",    value=f"{visits:,}",     icon="BarChart2"),
            ui.Stat(label="Bounce",    value=str(brate),        icon="TrendingDown"),
            ui.Stat(label="New",       value=f"{new_pct}%",     icon="UserPlus", color="green"),
            ui.Stat(label="Top src",   value=src_lbl,           icon="Globe"),
        ]),
    )


# ─── IPC — expose for cross-extension use ────────────────────────────────────

@ext.expose("full_report")
async def ipc_full_report(ctx, period: str = "week", date: str = "today",
                          limit: int = 20) -> ActionResult:
    """Handler: ipc_full_report."""
    data = await call_mos(ctx, "/api/analytics/full-report", {
        "period": period, "date": date, "limit": limit,
    })
    if "error" in data:
        return ActionResult.error(error=data.get("error", "unknown error"))
    return ActionResult.success(data=data)
