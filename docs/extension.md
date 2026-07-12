# Matomo Analytics Connector — Full Documentation

**Version:** 5.0.0 | **app_id:** `imperal-matomo-analytics-extension` | **Tool name:** `analytics`
**Git:** `github.com/SeeuWHM/imperal-matomo-analytics-extension` (branch `main`, latest commit `dd2fd70`)
**Live deploy status (as of writing):** `draft` — `reject_reason` on file is a **stale** message
("Does not meet quality standards") left over from an earlier, already-fixed review pass
(`593585d6`, 14/18 checks). The manifest actually deployed right now (`updated_at
2026-07-12T22:29:02`) is version 5.0.0 with 42 tools including `site_domains`/`set_active_site` —
i.e. current. Resubmit for marketplace review; don't trust the reject_reason text as current.

This file supersedes the root `README.md`, which still describes the pre-refactor architecture
(shared backend + `X-API-Key`, single `Site ID` field, `panels_main.py` that no longer exists,
version 4.0.6). Treat this document as the source of truth.

---

## Architecture

```
User (panel / chat)
    │
    ▼
Extension (this repo) — 38 @chat.function tools + 13 @ext.expose IPC + 4 @ext.skeleton + 1 @ext.schedule
    │  api_client.call_mos(ctx, endpoint, extra, site="") — resolves site_id + per-site segment
    │  POST https://api.webhostmost.com/api/matomo-analytics/<endpoint>
    ▼
matomo-analytics-api  (FastAPI, api-server, systemd unit `matomo-analytics-api`, :8105,
                        proxied publicly at api.webhostmost.com/api/matomo-analytics/* via
                        /etc/nginx/sites-enabled/api-gateway.conf)
    │  no auth header checked on incoming requests — matomo_url/token travel in the POST body
    │  per-request SSRF validation on matomo_url (blocks localhost/private/loopback/link-local)
    ▼
User's own Matomo instance — REST API (module=API, token_auth=<user's token>)
```

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
  - `sites: list[{label: str, site_id: int, segment?: str}]` — the multi-site/multi-project list.
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
api_client.py               call_mos(ctx, endpoint, extra, timeout, site="") — the only place
                            that talks HTTP to the backend
params.py                   all chat-function Pydantic param models + shared help-text constants
response_models.py          all chat-function Pydantic response models (data_model= contracts)
skeleton.py                 4 @ext.skeleton providers (see below)
handlers_traffic.py         traffic, top_pages, trends (chat) + IPC: traffic, trends, top_pages,
                            growing_pages, ai_referrers, matomo_config
handlers_settings.py        save_settings, add_site, remove_site, list_sites, set_active_site,
                            site_domains
handlers_detail.py          real_time, sources, devices, geo, entry_exit (chat) + matching IPC
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
                            slot="right"); _site_selector() compact switcher
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
`panels_render.py` at 278).

---

## Chat functions (38) — full inventory

`site` param (present on almost every read function): a label from `list_sites`; omit for the
user's `active_site`. Params below are the actual Pydantic fields, not paraphrased.

### Traffic & trends — `handlers_traffic.py`
| Function | action_type | Params | Returns |
|---|---|---|---|
| `traffic` | read | `period, date, site` (`TrafficParams`) | `TrafficOverviewRecord` (visits, pageviews, unique_visitors, bounce_rate, avg_time_on_site, series) |
| `top_pages` | read | `period, date, limit(1-100), site` (`TopPagesParams`) | `PageListResponse` |
| `trends` | read | `site` (`TrendsParams`) — compares last 7 full days vs the 7 before | `TrendSummaryResponse` |

### Site / project management — `handlers_settings.py`
| Function | action_type | Params | Notes |
|---|---|---|---|
| `save_settings` | write | `matomo_segment, utm_source_dim_id` (`SaveSettingsParams`) | blank field = keep current value; never touches matomo_url/token |
| `add_site` | write | `label(1-60), site_id(≥1), segment(optional,≤500)` (`AddSiteParams`) | replaces existing entry with same label; first site added becomes `active_site` automatically |
| `remove_site` | destructive | `label` (`RemoveSiteParams`) | reassigns `active_site` to the next remaining site if the removed one was active |
| `list_sites` | read | none | includes `active: bool` per site |
| `set_active_site` | write | `label` (`SetActiveSiteParams`) | `refresh_panels=["sidebar","workspace","analytics_hub"]` |
| `site_domains` | read | `site` (`SiteDomainsParams`) | ground-truth `main_url` + `urls[]` + `suggested_segments[]` from Matomo's SitesManager |

### Real-time / breakdown detail — `handlers_detail.py`
| Function | Params | Notes |
|---|---|---|
| `real_time` | `site` | live_30m/60m/180m visitor counts |
| `sources` | `period, date, limit, site` | Direct/Search/Websites/Social merged |
| `devices` | `period, date, limit, site` | desktop/mobile/tablet split |
| `geo` | `period, date, limit, site` | countries |
| `entry_exit` | `period, date, limit, site` | landing pages + exit pages |

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

## Cross-extension IPC (`@ext.expose`, 13 functions)

Other extensions call these via `ctx.extensions.call("analytics", "<name>", ...)` — never the raw
Matomo credentials. `matomo_config` deliberately returns only `{configured, sites, active_site,
matomo_segment}`, no `matomo_url`/`matomo_token` (regression-tested:
`test_ipc_matomo_config_does_not_leak_token`).

`real_time, sources, devices, geo` (`handlers_detail.py`) · `traffic, trends, top_pages,
growing_pages, ai_referrers, matomo_config` (`handlers_traffic.py`) · `insights, daily_summary`
(`handlers_insights.py`) · `full_report` (`handlers_reports.py`).

`growing_pages` computes real month-over-month page growth (no longer hardcoded to 0, no longer
filtered to `/blog`).

---

## Panels

| Panel id | Slot | File | States |
|---|---|---|---|
| `sidebar` | left | `panels_side.py` | offline (not configured) · online (live/today/yesterday stats + `_site_selector()` if 2+ sites + "Open Dashboard" button, auto-opens center panel on load) |
| `workspace` | right | `panels_side.py` | not-configured (settings form) · loaded (result_zone for last chat result + KPIs + 7 detail Sections including embedded settings) |
| `analytics_hub` | center overlay | `panels_center.py` | `view="close"` empty · `view="settings"` (settings_form) · default (7-metric KPI row, 30-day chart, top pages, sources, devices; site badge shown once 2+ sites exist) |

`_render_result_body()` in `panels_render.py` is the single dispatch point that turns a chat
result's `action` name into a rendered body for `result_zone` — every chat function's result
needs a case here or it falls back to a generic "Result ready." empty state. Current cases cover
all 38 functions except the pure site-management ones (`add_site`/`remove_site`/`list_sites`/
`set_active_site` don't render a body themselves — their `refresh_panels`/`event` triggers a
panel re-render instead of a result card).

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

**Security**: `MatomoContextRequest.matomo_url` has a `field_validator` blocking
localhost/`0.0.0.0`/private/loopback/link-local/multicast hosts (literal check + DNS resolution
check). No auth header is checked on the FastAPI side — every request must carry the caller's own
`matomo_url`+`token`, which only the extension (via the user's `ctx.secrets`) has.

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
level.

---

## Tests

Run via the shared venv (no per-extension venv exists):
```
source /home/ignat/Nextcloud/MCP-Configs/Imperal-Extensions-MCP/SeeU-Extensions/.venv-ext/bin/activate
python -m pytest tests/ -v
```
As of `dd2fd70`: **36 passed, 20 skipped** (skips are backend live-integration tests, gated on
`MATOMO_ANALYTICS_API_URL`/`MATOMO_URL`/`MATOMO_TOKEN` env vars — not failures). Covers:
load/save settings, secrets never leaking into `ctx.store`, legacy single-site migration,
`resolve_site`/`resolve_site_id`/`active_site_label`/`sites_with_active`, per-site segment
resolution and precedence over the account-wide segment, add/remove/list/set-active-site
(including active-site reassignment on removal), `site_domains` success + suggested-segment
generation + config-missing error path, `call_mos` site/segment resolution, traffic/top_pages/
trends happy-path + config-missing, the `geo` "countries" key regression, `ipc_matomo_config`
non-leak, and the conversions "no named goals" fallback message.

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
