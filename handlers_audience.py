"""Chat functions for AI referrers, conversions, events, UTM, and engagement
(new vs returning, visit duration). Channel/demographic breakdowns live in
handlers_channels.py + handlers_demographics.py; the full-report aggregate
lives in handlers_reports.py — split apart to stay under the 300-line limit."""
# No `from __future__ import annotations` - V6 validator needs real annotations.

from imperal_sdk import ui
from imperal_sdk.types import ActionResult

from app import chat, save_result
from api_client import call_mos
from params import AudienceParams, AIReferrersParams, ConversionsParams
from response_models import (
    AIReferrersResponse, ConversionsResponse, EventsResponse, UTMSourcesResponse,
    NewReturningResponse, BreakdownResponse,
)
from audience_helpers import err, table, top


# ─── ai_referrers ─────────────────────────────────────────────────────────────

@chat.function("ai_referrers",
               description=(
                   "Which AI assistants and LLMs send traffic — ChatGPT, Perplexity, Claude, "
                   "Gemini, DeepSeek, Grok, Copilot. Combines referrer detection + UTM tracking. "
                   "Default period=month for meaningful data. "
                   "Use for: с каких нейросетей трафик, ChatGPT traffic, AI referrers, "
                   "нейронки шлют трафик, which AI sends visitors, LLM traffic."
               ),
               action_type="read", event="analytics.action.result", data_model=AIReferrersResponse)
async def fn_ai_referrers(ctx, params: AIReferrersParams) -> ActionResult:
    """Handler: fn_ai_referrers."""
    data = await call_mos(ctx, "/api/matomo-analytics/ai-referrers", {
        "period": params.period, "date": params.date,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "ai_referrers", "AI referrers", data)
    sources = data.get("sources") or []
    total = data.get("total_visits", 0)
    top_source = sources[0] if sources else {}
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
        summary=f"{total:,} visits from AI — top: {top_source.get('source', 'none')} ({top_source.get('visits', 0):,})",
        ui=ui_node,
    )


# ─── conversions ─────────────────────────────────────────────────────────────

@chat.function("conversions",
               description=(
                   "Goal conversions from Matomo: purchases (cart complete), checkouts started, "
                   "conversion rate. Use for: конверсии, покупки, заказы, сколько купили, "
                   "checkout, воронка продаж, purchase funnel, how many orders."
               ),
               action_type="read", event="analytics.action.result", data_model=ConversionsResponse)
async def fn_conversions(ctx, params: ConversionsParams) -> ActionResult:
    """Handler: fn_conversions."""
    data = await call_mos(ctx, "/api/matomo-analytics/conversions", {
        "period": params.period, "date": params.date,
    }, site=params.site)
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

    top_goal = goals[0] if goals else {}
    return ActionResult.success(
        data=data,
        summary=f"{total:,} total conversions | top goal: {top_goal.get('name','')} ({top_goal.get('conversions',0):,})",
        ui=ui_node,
    )


# ─── events ───────────────────────────────────────────────────────────────────

@chat.function("events",
               description=(
                   "Custom tracking events: engagement (scrolls, clicks) and ecommerce events "
                   "(begin_checkout). Use for: события, события аналитики, engagement events, "
                   "scroll depth, ecommerce events, what is being tracked."
               ),
               action_type="read", event="analytics.action.result", data_model=EventsResponse)
async def fn_events(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_events."""
    data = await call_mos(ctx, "/api/matomo-analytics/events", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
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
               action_type="read", event="analytics.action.result", data_model=UTMSourcesResponse)
async def fn_utm_sources(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_utm_sources."""
    data = await call_mos(ctx, "/api/matomo-analytics/utm-sources", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return ActionResult.error(error=data.get("error", "unknown error"))
    await save_result(ctx, "utm_sources", "UTM Sources", data)

    sources = data.get("utm_sources") or []
    ai_visits = data.get("ai_utm_visits", 0)
    top_source = sources[0] if sources else {}

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
        summary=f"Top UTM source: {top_source.get('label','none')} ({top_source.get('visits',0):,} visits) | AI UTM: {ai_visits:,}",
        ui=ui_node,
    )


# ─── new_vs_returning ─────────────────────────────────────────────────────────

@chat.function("new_vs_returning",
               description="New visitors vs returning visitors ratio and counts. "
                           "Use for: новые vs возвращающиеся, лояльность аудитории, "
                           "сколько новых пользователей, retention, returning users percentage.",
               action_type="read", event="analytics.action.result", data_model=NewReturningResponse)
async def fn_new_vs_returning(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_new_vs_returning."""
    data = await call_mos(ctx, "/api/matomo-analytics/new-returning", {
        "period": params.period, "date": params.date,
    }, site=params.site)
    if "error" in data:
        return err(data)
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
               action_type="read", event="analytics.action.result", data_model=BreakdownResponse)
async def fn_visit_duration(ctx, params: AudienceParams) -> ActionResult:
    """Handler: fn_visit_duration."""
    data = await call_mos(ctx, "/api/matomo-analytics/visit-duration", {
        "period": params.period, "date": params.date, "limit": params.limit,
    }, site=params.site)
    if "error" in data:
        return err(data)
    await save_result(ctx, "visit_duration", "Visit duration", data)
    buckets = data.get("buckets") or []
    lbl, pct = top(buckets)
    return ActionResult.success(
        data=data,
        summary=f"Most common duration: {lbl} ({pct}% of sessions)",
        ui=table(buckets, "Duration"),
    )


