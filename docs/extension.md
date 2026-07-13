# Matomo Analytics Connector — Full Documentation

**Version:** 5.2.2 | **app_id:** `imperal-matomo-analytics-extension` | **Tool name:** `analytics`
**Git:** `github.com/SeeuWHM/imperal-matomo-analytics-extension` (branch `main`, latest commit `4923175`)
**Live deploy status (as of writing):** `draft` — `reject_reason` on file is a **stale** message
("Does not meet quality standards") left over from an earlier, already-fixed review pass
(`593585d6`, 14/18 checks). Resubmit for marketplace review; don't trust the reject_reason text
as current.

**2026-07-13 (v5.1.0):** the backend's per-site request contract changed from a single
`site_id`/`segment` to a universal `targets: [{label, site_id, segment}]` list - every route
(not just a new "compare" one) now serves either one site or a side-by-side comparison of several,
fanned out concurrently server-side. `call_mos()` unwraps a single target back to the old flat
shape, so this was invisible to every pre-existing handler; `sites=[...]` opts a chat function into
the raw per-target list. Also fixed a real bug found while verifying this: `/geo` was silently
returning zero countries whenever Matomo answered with its per-date nested shape (`period=day` +
a multi-day `date` like `last7`) - it had its own extra `isinstance(rows, list)` guard that
discarded that shape instead of letting `normalize_breakdown` flatten it like every other
breakdown route already does correctly.

**2026-07-13 (v5.2.0):** fixed `view_domain` - it was find-or-creating a `sites` entry per domain,
which polluted the project/site_id selector with fake per-domain "sites" instead of showing just
the real Matomo projects. It now only ever updates the existing project's own `segment` in place;
`add_site` remains the only function that grows `sites`. Also exposed 4 new IPC functions
(`organic_keywords`, `site_search`, `page_details`, `entry_exit`) as lightweight, individually
callable content-strategy signals - previously only reachable via chat, or bundled inside the
slow `full_report`.

**2026-07-13 (v5.2.2):** fixed the left sidebar failing to render in production - `ensure_known_domains`
(added in v5.2.1) called `save_settings` from inside a panel render, which panels apparently aren't
allowed to do. It's now read-only (enriches the in-memory dict for that render, never writes) and
wrapped in a blanket try/except as defense-in-depth. Also fixed `main.py`'s hot-reload module list,
which was missing `response_models` and `compare_render` - either could have kept serving a stale
cached version across deploys instead of picking up the new one.

This file supersedes the root `README.md`, which still describes the pre-refactor architecture
(shared backend + `X-API-Key`, single `Site ID` field, `panels_main.py` that no longer exists,
version 4.0.6). Treat this document as the source of truth.

---

## Architecture

```
User (panel / chat)
    │
    ▼
Extension (this repo) — 39 @chat.function tools + 17 @ext.expose IPC + 4 @ext.skeleton + 1 @ext.schedule
    │  api_client.call_mos(ctx, endpoint, extra, site="", sites=None) — resolves each label to
    │  {label, site_id, segment}, sends targets:[...] (1 or many, same shape either way)
    │  POST https://api.webhostmost.com/api/matomo-analytics/<endpoint>
    ▼
matomo-analytics-api  (FastAPI, api-server, systemd unit `matomo-analytics-api`, :8105,
                        proxied publicly at api.webhostmost.com/api/matomo-analytics/* via
                        /etc/nginx/sites-enabled/api-gateway.conf)
    │  no auth header checked on incoming requests — matomo_url/token travel in the POST body
    │  per-request SSRF validation on matomo_url (blocks localhost/private/loopback/link-local)
    │  every route fans targets out concurrently (asyncio.gather) and returns
    │  MultiResult{results:[{label, site_id, error, data}, ...]} - no separate "compare" routes
    ▼
User's own Matomo instance — REST API (module=API, token_auth=<user's token>)
```

**`call_mos()` return shape** (`api_client.py`): asking for exactly one target (the default -
just `site`, or `sites` with one label) returns `results[0]["data"]` unwrapped, i.e. the exact
flat shape every pre-existing handler already expects (`data.get("visits")`, `data.get("countries")`,
...) - zero code changes needed anywhere that doesn't want a comparison. Asking for 2+ labels via
`sites=[...]` returns the raw `{"results": [...]}` envelope instead; the caller renders it (see
`compare_render.py`'s `compare_table()`, wired onto `traffic`/`top_pages`/`trends`/`sources`/
`devices`/`geo`/`real_time`/`entry_exit`). Comparing "domains" that share one Matomo `site_id`
works the same way - each entry in `sites=[...]` resolves through the normal per-site `segment`.

**Not in git** — the backend (`matomo-analytics-api`) lives only on `api-server`
(`/home/ext_server_webhostmost_com/matomo-analytics-api/`), edited via
`mcp__api-server__write_file` + `service_control restart`, same pattern as `web-tools-api`.
There is no repo for it; this doc is the only record of its routes.

**Design principle (why the extension has "no Matomo logic" of its own):** the extension is a
thin chat/panel layer. All actual Matomo API calls, response normalization, and SSRF hardening
live in the backend. The extension only: resolves which site/segment to ask for, forwards the
call, and renders whatever comes back.

---

## Secrets & settings model

- **`matomo_url`**, **`matomo_token`** — declared via `ext.secret(...)` in `app.py` with
  `write_mode="user"` (default `scope="user"`, i.e. per-user, not a shared app secret). Per
  **EXT-SECRETS-V1**, the platform auto-registers a `panel_id="secrets"` tab for these — the
  extension never renders its own credential form. `settings_form()` (`panels_settings_render.py`)
  links directly to it via `ui.Navigate(path=f"/ext/{ext.app_id}/secrets")`.
- Everything else lives in `ctx.store`, collection `analytics_settings` (single doc per user,
  looked up via `query(limit=1)` — see `app.py` docstring for why not a fixed doc id):
  - `matomo_segment: str` — account-wide fallback segment (used when a site has no segment of
    its own).
  - `utm_source_dim_id: int` — Custom Dimension ID for `utm_source`, 0 = disabled.
  - `sites: list[{label: str, site_id: int, segment?: str, known_domains?: list[str]}]` — the
    multi-site/multi-project list. `known_domains` is a best-effort cache of that site_id's real
    URLs (from `SitesManager`, fetched once at `add_site` time) - it's what powers the domain-level
    dropdown, and is never required for the entry to work.
  - `active_site: str` — label of the default site for chat/dashboard when no `site` is named.
- **Legacy migration**: if `sites` is empty but a pre-multisite `matomo_site_id` field exists in
  the stored doc, `load_settings()` folds it into `sites` as `{"label": "Основной сайт",
  "site_id": <that id>}` — this is why a site can appear that the user never explicitly added.

### Multi-site + per-site segment (the core feature)

Each entry in `sites` is `{label, site_id, segment?}`. Two entries can share the same `site_id`
while each tracking a different **segment** — this is how "the blog" becomes trackable
separately even though `blog.example.com` is just one of many URL aliases under one Matomo
`idSite`, not its own site. `app.resolve_site(s, site="")` resolves a label to its full entry
(falls back to `active_site`, then the first configured site, then `site_id=1` with no segment).
`api_client.call_mos()` uses the resolved entry's own `segment` if set, else the account-wide
`matomo_segment`, else none.

`site_domains(site)` calls Matomo's own `SitesManager.getSiteFromId` +
`SitesManager.getSiteUrlsFromId` (ground truth, not inferred from traffic) and returns
`suggested_segments: [{domain, segment: "pageUrl=^<domain>"}]` for every configured URL — meant
to be pasted straight into `add_site(label, site_id, segment=...)`.

### Domain-level switcher (`view_domain`, `_domain_selector`)

Two genuinely different levels, kept structurally separate on purpose:

- **`sites` = real Matomo projects (site_ids)** - e.g. "WHM Front Websites" and "Client Zone",
  picked via `set_active_site`/`_site_selector`. This list should only ever grow when the user
  deliberately runs `add_site` (a new project, or a permanently-named sub-project sharing a
  site_id via its own `segment`).
- **domains within the active project** - the URL aliases Matomo already knows about under that
  *same* site_id (`known_domains`, cached from `SitesManager` at `add_site` time - persisted there,
  since `add_site` is a write action). For any site added before this cache existed (or whose
  lookup failed at the time), `api_client.ensure_known_domains()` fetches it live so the dropdown
  still appears - called from all 3 panels, but **read-only**: panels must stay side-effect-free,
  so it enriches the in-memory settings for that render only and never calls `save_settings`
  (v5.2.1 persisted from inside a panel render - broke the sidebar in production; v5.2.2 fixed by
  making it read-only + wrapping it in a blanket try/except so a lookup failure can never take the
  panel down). Once the active site has 2+ known domains, `panels_side.py` (sidebar),
  `panels_center.py` (`analytics_hub` dashboard - the primary view), and
  `panels_settings_render.py` (settings form) all show a second `ui.Select` for exactly this -
  picking a domain (or "All domains", always the first option) submits
  to `view_domain(site_id, domain)`.

`view_domain` **never adds a new `sites` entry** - it updates the matching project's own `segment`
in place (preferring the currently active entry if several share that site_id) and clears it for
"All domains". Getting this backwards once made every domain look like its own top-level "site" in
the project selector - fixed 2026-07-13; `add_site` is the only function that grows `sites`.

---

## File structure

```
main.py                    entry point; sys.modules hot-reload list (must list every module
                            below); @ext.schedule("daily_summary", cron="0 9 * * *") loops all
                            configured sites; @ext.on_install; @ext.health_check
app.py                     Extension + ChatExtension init; ext.secret() x2; SERVER_URL constant
                            (api.webhostmost.com, overridable via MATOMO_BACKEND_URL env);
                            load_settings/save_settings; matomo_ready(); resolve_site()/
                            resolve_site_id(); active_site_label(); sites_with_active()
api_client.py               call_mos(ctx, endpoint, extra, timeout, site="", sites=None) — the
                            only place that talks HTTP to the backend; site_info_for(ctx, site_id,
                            segment) — direct site-id lookup used by add_site (before that entry
                            is resolvable by label)
compare_render.py           compare_table()/compare_summary() — generic per-site comparison table
                            shared by every sites=[...] render branch
params.py                   all chat-function Pydantic param models + shared help-text constants
response_models.py          all chat-function Pydantic response models (data_model= contracts)
skeleton.py                 4 @ext.skeleton providers (see below)
handlers_traffic.py         traffic, top_pages, trends (chat, all 3 accept sites=[...]) + IPC:
                            traffic, trends, top_pages, growing_pages, ai_referrers, matomo_config
handlers_settings.py        save_settings, add_site, remove_site, list_sites, set_active_site,
                            site_domains, view_domain
handlers_detail.py          real_time, sources, devices, geo, entry_exit (chat, all accept
                            sites=[...]) + IPC (entry_exit added v5.2.0):
                            sites=[...]) + matching IPC
handlers_insights.py        insights, daily_report (background, uses AI), anomaly_check (chat)
                            + IPC: insights, daily_summary
handlers_audience.py        ai_referrers, conversions, events, utm_sources, new_vs_returning,
                            visit_duration
handlers_channels.py        regions, device_brands, browsers, search_engines, organic_keywords,
                            campaigns
handlers_demographics.py    social_networks, referring_sites, site_search, languages, providers,
                            screen_resolutions, page_details, outlinks
handlers_reports.py         full_report (chat, background) + IPC: full_report
audience_helpers.py         shared err()/table()/top() helpers for handlers_audience.py
panels_center.py            @ext.panel("analytics_hub", slot="center") — full dashboard overlay
panels_side.py              @ext.panel("sidebar", slot="left") + @ext.panel("workspace",
                            slot="right"); _site_selector() + _domain_selector() switchers
panels_render.py            pure render helpers shared by the panels above (kpi_stats, chart,
                            pages_table, breakdown_table, entry_exit_table, result_zone,
                            _render_result_body — the big per-action switch)
panels_settings_render.py   sites_list() + settings_form() (secrets-panel button, segment field,
                            site switcher, matomo_segment/utm_source_dim_id form)
icon.svg                    official Matomo mark (Simple Icons path), fill #3152A0
imperal.json                manifest — regenerate with `imperal build .` (see below), NOT by hand
tests/test_handlers.py      unit tests, MockContext + MockSecretStore, no network
tests/test_matomo_analytics_api.py   backend tests: always-run SSRF validation + skip-safe live
                            integration (needs MATOMO_ANALYTICS_API_URL/MATOMO_URL/MATOMO_TOKEN)
tests/test_webbee_agent.py  Matomo-only agent-routing smoke tests
```

All files are ≤300 lines (platform hard limit; verified `wc -l` at time of writing, max is
`handlers_settings.py` at 245).

---

## Chat functions (39) — full inventory

`site` param (present on almost every read function): a label from `list_sites`; omit for the
user's `active_site`. `sites` param (v5.1.0, on `traffic`/`top_pages`/`trends`/`sources`/`devices`/
`geo`/`real_time`/`entry_exit`): a list of 2+ labels - triggers a comparison render instead of a
single answer, and replaces `site` when given. Params below are the actual Pydantic fields, not
paraphrased.

### Traffic & trends — `handlers_traffic.py`
| Function | action_type | Params | Returns |
|---|---|---|---|
| `traffic` | read | `period, date, site, sites` (`TrafficParams`) | `TrafficOverviewRecord` (visits, pageviews, unique_visitors, bounce_rate, avg_time_on_site, series) — or a comparison table if `sites` has 2+ labels |
| `top_pages` | read | `period, date, limit(1-100), site, sites` (`TopPagesParams`) | `PageListResponse` (or comparison) |
| `trends` | read | `site, sites` (`TrendsParams`) — compares last 7 full days vs the 7 before | `TrendSummaryResponse` (or comparison) |

### Site / project management — `handlers_settings.py`
| Function | action_type | Params | Notes |
|---|---|---|---|
| `save_settings` | write | `matomo_segment, utm_source_dim_id` (`SaveSettingsParams`) | blank field = keep current value; never touches matomo_url/token |
| `add_site` | write | `label(1-60), site_id(≥1), segment(optional,≤500)` (`AddSiteParams`) | replaces existing entry with same label; first site added becomes `active_site` automatically; best-effort caches `known_domains` via `site_info_for` |
| `remove_site` | destructive | `label` (`RemoveSiteParams`) | reassigns `active_site` to the next remaining site if the removed one was active |
| `list_sites` | read | none | includes `active: bool` per site |
| `set_active_site` | write | `label` (`SetActiveSiteParams`) | `refresh_panels=["sidebar","workspace","analytics_hub"]` |
| `site_domains` | read | `site` (`SiteDomainsParams`) | ground-truth `main_url` + `urls[]` + `suggested_segments[]` from Matomo's SitesManager |
| `view_domain` | write | `site_id, domain` (`ViewDomainParams`) | updates that site_id's own entry's `segment` in place (never adds a new site); `domain="All domains"` clears it |

### Real-time / breakdown detail — `handlers_detail.py`
| Function | Params | Notes |
|---|---|---|
| `real_time` | `site, sites` | live_30m/60m/180m visitor counts (or comparison) |
| `sources` | `period, date, limit, site, sites` | Direct/Search/Websites/Social merged (or comparison) |
| `devices` | `period, date, limit, site, sites` | desktop/mobile/tablet split (or comparison) |
| `geo` | `period, date, limit, site, sites` | countries (or comparison) - fixed in v5.1.0: was silently empty whenever Matomo returned its per-date nested shape (`period=day` + multi-day `date`) |
| `entry_exit` | `period, date, limit, site, sites` | landing pages + exit pages (or comparison) |

### Insights — `handlers_insights.py`
| Function | Notes |
|---|---|
| `insights` | free, no AI tokens; bounce-rate + growing/dying-page heuristics |
| `daily_report` | **uses AI tokens**, runs in background, result delivered async to chat |
| `anomaly_check` | free, compares vs last 7 days |

### Audience — `handlers_audience.py`
`ai_referrers`, `conversions`, `events`, `utm_sources`, `new_vs_returning`, `visit_duration` — all
take `AudienceParams`/`AIReferrersParams`/`ConversionsParams` (`period, date, [limit], site`).
`conversions` synthesizes an "All Goals" entry when Matomo has conversions but no named goals
(e.g. Ecommerce-only accounts).

### Channels — `handlers_channels.py`
`regions`, `device_brands`, `browsers` (also returns `os_families`), `search_engines`,
`organic_keywords`, `campaigns` — all `TopPagesParams`-shaped (`period, date, limit, site`).

### Demographics — `handlers_demographics.py`
`social_networks`, `referring_sites`, `site_search` (keywords + no-result keywords), `languages`,
`providers` (ISP), `screen_resolutions`, `page_details` (time-on-page + bounce per URL),
`outlinks`.

### Reports — `handlers_reports.py`
`full_report` — background, fetches all 24 backend sections via `asyncio.gather`, ~90s timeout
budget (`HEAVY_TIMEOUT` in `api_client.py`).

---

## Cross-extension IPC (`@ext.expose`, 17 functions)

Other extensions call these via `ctx.extensions.call("analytics", "<name>", ...)` — never the raw
Matomo credentials. `matomo_config` deliberately returns only `{configured, sites, active_site,
matomo_segment}`, no `matomo_url`/`matomo_token` (regression-tested:
`test_ipc_matomo_config_does_not_leak_token`).

`real_time, sources, devices, geo, entry_exit` (`handlers_detail.py`) · `traffic, trends,
top_pages, growing_pages, ai_referrers, matomo_config` (`handlers_traffic.py`) · `insights,
daily_summary` (`handlers_insights.py`) · `full_report` (`handlers_reports.py`) ·
`organic_keywords` (`handlers_channels.py`) · `site_search, page_details`
(`handlers_demographics.py`).

**Content-strategy signals (v5.2.0)**: `organic_keywords`, `site_search`, `page_details`, and
`entry_exit` were added specifically so a content/article-writing extension can pull them directly
and cheaply, without paying for the ~90s `full_report` fan-out (which already contained this data,
just bundled and slow). `site_search`'s `no_results` is the sharpest one - a zero-result on-site
search term is a visitor proving there's demand for content that doesn't exist yet.

`growing_pages` computes real month-over-month page growth (no longer hardcoded to 0, no longer
filtered to `/blog`).

---

## Panels

| Panel id | Slot | File | States |
|---|---|---|---|
| `sidebar` | left | `panels_side.py` | offline (not configured) · online (live/today/yesterday stats + `_site_selector()` if 2+ sites + `_domain_selector()` if the active site has 2+ `known_domains` + "Open Dashboard" button, auto-opens center panel on load) |
| `workspace` | right | `panels_side.py` | not-configured (settings form) · loaded (result_zone for last chat result + KPIs + 7 detail Sections including embedded settings) |
| `analytics_hub` | center overlay | `panels_center.py` | `view="close"` empty · `view="settings"` (settings_form) · default (7-metric KPI row, 30-day chart, top pages, sources, devices; site badge + `_domain_selector()` shown once applicable, imported from `panels_side.py`) |

`_render_result_body()` in `panels_render.py` is the single dispatch point that turns a chat
result's `action` name into a rendered body for `result_zone` — every chat function's result
needs a case here or it falls back to a generic "Result ready." empty state. Current cases cover
all 39 functions except the pure site-management ones (`add_site`/`remove_site`/`list_sites`/
`set_active_site`/`view_domain` don't render a body themselves — their `refresh_panels`/`event`
triggers a panel re-render instead of a result card). The 8 `sites=[...]`-enabled functions render
their comparison via `compare_render.compare_table()` directly in the handler's own `ui=`, not
through this dispatch point.

---

## Skeleton (LLM context cache, `skeleton.py`)

| Name | TTL | Content |
|---|---|---|
| `traffic_overview` | 300s | last 7 days visits/pageviews/bounce/avg time + WoW % (separate `/trends` call) |
| `top_pages` | 600s | top 10 pages this week |
| `realtime` | 60s | 30/60/180-min visitor counts |
| `matomo_config` | 600s | `configured, sites, active_site, utm_source_dim_id` |

All fall back to `{"response": {"configured": false, "instruction": "..."}}`-shaped payloads on
error rather than raising, per skeleton's degrade-to-zeros contract.

---

## Backend — `matomo-analytics-api` (api-server, NOT in git)

FastAPI app, `app/main.py` entry (`uvicorn app.main:app --port 8105`), router prefix
`/api/matomo-analytics`. Structure: `app/routes/analytics.py` (all routes), `app/core/schemas.py`
(Pydantic request/response models), `app/core/matomo_client.py` (`MatomoClient.call(base_url,
token, method, params)` — POSTs `module=API&format=JSON&token_auth=...&method=...`),
`app/core/normalizers.py` (generic row/aggregation helpers shared across routes).

**Fixed 2026-07-13**: `/real-time`'s 3 `Live.getCounters` calls never forwarded `segment` (every
other route already did) - so switching the domain-level dropdown correctly re-scoped every other
metric but "Live" always stayed pinned to the whole site_id. Verified live: an unmatchable segment
now correctly returns 0/0/0 instead of the whole-site count. A full pass over every `client.call()`
in this file (parenthesis-matched, not just grep) confirms this was the only route missing it -
`SitesManager.getSiteFromId`/`getSiteUrlsFromId` (site metadata) and `Goals.getGoals` (goal
definitions, not data) are correctly segment-less by nature.

**Security**: `MatomoContextRequest.matomo_url` has a `field_validator` blocking
localhost/`0.0.0.0`/private/loopback/link-local/multicast hosts (literal check + DNS resolution
check). No auth header is checked on the FastAPI side — every request must carry the caller's own
`matomo_url`+`token`, which only the extension (via the user's `ctx.secrets`) has.

**Request contract (v5.1.0)**: every route below (except `/health`) takes `targets: [{label,
site_id, segment?}]` instead of a single `site_id`/`segment`, and returns `MultiResult{results:
[{label, site_id, error, data}, ...]}` - one entry per target, fanned out concurrently
(`asyncio.gather`) via a shared `_fan_out()` helper in `analytics.py`. A single-target request
(the common case) is just `targets` with one entry; the extension's `call_mos()` unwraps that back
to a flat dict, so nothing else in this doc changes shape-wise for single-site use. `insights` and
`full_report` pass `req.targets` straight through to the routes they call internally, so they're
multi-target too without any extra plumbing.

**Routes** (31 total, all `POST` except `/health`):
`/health` (GET) · `/traffic` · `/trends` · `/top-pages` · `/sources` · `/devices` · `/geo` ·
`/real-time` · `/search-engines` · `/campaigns` · `/ai-referrers` · **`/site-info`** (added
2026-07-13 — calls `SitesManager.getSiteFromId` + `getSiteUrlsFromId`) · `/insights` ·
`/entry-exit` · `/conversions` · `/events` · `/utm-sources` · `/regions` · `/brands` ·
`/browsers` · `/keywords` · `/socials` · `/referring-sites` · `/site-search` · `/new-returning` ·
`/visit-duration` · `/languages` · `/providers` · `/resolutions` · `/page-details` ·
`/outlinks` · `/full-report`.

**Removed**: `/blog-analytics` — deleted 2026-07-13, was dead code (extension-side blog concept
was already removed in an earlier pass; nothing called this route anymore).

Each route maps to specific Matomo API methods, e.g.: `traffic`→`VisitsSummary.get` +
`VisitsSummary.getVisits`; `top_pages`/`page_details`→`Actions.getPageUrls`;
`entry_exit`→`Actions.getEntryPageUrls`/`getExitPageUrls`; `sources`→`Referrers.getWebsites` +
`getSearchEngines` + `getSocials`; `geo`→`UserCountry.getCountry`; `regions`→
`UserCountry.getRegion`; `devices`→`DevicesDetection.getType`; `brands`→
`DevicesDetection.getBrand`; `browsers`→`DevicesDetection.getBrowsers` + `getOsFamilies`;
`real_time`→`Live.getCounters` (×3 windows); `conversions`→`Goals.get` + `Goals.getGoals`
(per-goal `idGoal` fan-out); `events`→`Events.getCategory` + `Events.getAction` drill-down;
`utm_sources`→`CustomDimensions.getCustomDimension` or `Referrers.getCampaigns` fallback;
`new_vs_returning`→`VisitFrequency.get` (real fields are `nb_visits_new`/`nb_visits_returning` —
there is no plain `nb_visits` on this method); `visit_duration`→
`VisitorInterest.getNumberOfVisitsPerVisitDuration`; `languages`→`UserLanguage.getLanguage`;
`providers`→`Provider.getProvider`; `resolutions`→`Resolution.getResolution`;
`outlinks`→`Actions.getOutlinks`; `site_search`→`Actions.getSiteSearchKeywords` +
`getSiteSearchNoResultKeywords`; `site-info`→`SitesManager.getSiteFromId` +
`getSiteUrlsFromId`.

**Known Matomo quirks handled in normalizers**: `period=day` + a multi-day date range (e.g.
`last7`) nests `VisitsSummary.get`/`Goals.get`/`VisitFrequency.get`/`Events.getCategory`
responses per-date instead of returning one flat object — normalizers detect this
(`all(isinstance(v, dict) ...)`) and aggregate across buckets rather than reading only the first
level. `/geo` used to have its own extra `rows if isinstance(rows, list) else []` guard that
discarded exactly this nested shape instead of letting `normalize_breakdown`/`_rows_from_payload`
flatten it like every other breakdown route already did - fixed 2026-07-13 (verified live: went
from 0 countries to 93/114 real countries for the two test sites on `period=day&date=last7`).

---

## Tests

Run via the shared venv (no per-extension venv exists):
```
source /home/ignat/Nextcloud/MCP-Configs/Imperal-Extensions-MCP/SeeU-Extensions/.venv-ext/bin/activate
python -m pytest tests/ -v
```
As of `4923175`: **54 passed, 20 skipped** (skips are backend live-integration tests, gated on
`MATOMO_ANALYTICS_API_URL`/`MATOMO_URL`/`MATOMO_TOKEN` env vars — not failures). Covers:
load/save settings, secrets never leaking into `ctx.store`, legacy single-site migration,
`resolve_site`/`resolve_site_id`/`active_site_label`/`sites_with_active`, per-site segment
resolution and precedence over the account-wide segment, add/remove/list/set-active-site
(including active-site reassignment on removal), `site_domains` success + suggested-segment
generation + config-missing error path, `call_mos` site/segment resolution, traffic/top_pages/
trends happy-path + config-missing, the `geo` "countries" key regression, `ipc_matomo_config`
non-leak, the conversions "no named goals" fallback message, `call_mos`'s single-target unwrap +
multi-target passthrough (incl. per-target error shape), a comparison-render smoke test, and
`view_domain` (in-place update/prefers-active-entry/all-domains/unknown-site_id-errors +
`add_site`'s best-effort `known_domains` cache).

---

## Building/validating the manifest

`imperal.json` must be regenerated from source, never hand-edited (except one known workaround,
below) — using the SDK CLI, NOT the forbidden raw SDK source checkout:
```
/home/ignat/.local/share/uv/tools/imperal-mcp/bin/imperal build .
/home/ignat/.local/share/uv/tools/imperal-mcp/bin/imperal validate .
```
**Known SDK 5.9.3 quirk**: `imperal build` emits a `scope` field on every `secrets[]` entry that
`imperal validate`'s own schema (`SecretDecl` in `manifest_schema.py`) does not accept — a
mismatch between the SDK's manifest generator and its own validator. Strip it after every build:
```python
import json
d = json.load(open("imperal.json"))
for s in d.get("secrets", []): s.pop("scope", None)
json.dump(d, open("imperal.json", "w"), indent=2, ensure_ascii=False)
```
Also note: `imperal build` intentionally preserves `name`/`description`/`icon`/`category`/`tags`
from the existing `imperal.json` on disk (treated as marketplace-curated fields) — it will NOT
pick up changes to `Extension(display_name=..., description=...)` in `app.py` for those fields.
Edit them directly in `imperal.json` if you rename/re-describe the app.

---

## Known gaps / things worth knowing

- Root `README.md` and `pyproject.toml` (`version = "4.0.6"`, stale `py-modules` list missing
  `handlers_channels`/`handlers_demographics`/`handlers_reports`/`audience_helpers`/
  `panels_settings_render`/`skeleton`) are **not current** — not fixed as part of this doc pass,
  flagged here so nobody trusts them.
  - **Update, same session:** README.md and pyproject.toml were rewritten to match reality
    (version 5.0.0, correct file list, secrets-panel flow, multi-site) right after this doc was
    written — see their current content directly rather than assuming they're still stale.
- Traffic series' per-day `pageviews` is always 0 (pre-existing, unrelated to the 2026-07
  multi-site work): `traffic`'s daily series comes from `VisitsSummary.getVisits`, which is a
  single-metric Matomo method (visits only) — only the top-level summary object (from
  `VisitsSummary.get`) carries a real `pageviews` total. Not fixed; flagged for whoever picks it
  up next.
- Existing users who configured Matomo before the 2026-07-12 secrets refactor will see "Matomo
  not configured" after this version deploys, until they re-enter URL/token via the new Secrets
  panel — old `ctx.store` values for `matomo_url`/`matomo_token` are not read anymore and do not
  auto-migrate (by design — they were never supposed to live outside `ctx.secrets`).
- The Matomo test token used throughout this project's live-verification (`credentials.txt`,
  `146374aef655722813ea4e6c95accacf` against `analytics.webhostmost.com`, sites 1/2) is a real,
  working credential checked into a local (non-git) workspace file — treat it the same as any
  other credential, not for use outside this workspace's own testing.
- A previously different, now-superseded token was committed in plaintext to an old test file and
  removed earlier in this project's history; that token should be considered compromised/rotated
  if it hasn't been already (unrelated to the token above).
