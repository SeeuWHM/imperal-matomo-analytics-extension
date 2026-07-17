# Matomo Analytics Connector

[![Imperal SDK](https://img.shields.io/badge/imperal--sdk-5.9.9-blue)](https://pypi.org/project/imperal-sdk/)
[![Version](https://img.shields.io/badge/version-5.2.7-green)](https://github.com/SeeuWHM/imperal-matomo-analytics-extension/releases)
[![License](https://img.shields.io/badge/license-LGPL--2.1-orange)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Imperal%20Cloud-purple)](https://panel.imperal.io)

**Traffic analytics dashboard extension for [Imperal Cloud](https://panel.imperal.io).**

Connect one or more [Matomo](https://matomo.org/) instances and get a full dashboard with visits,
trends, top pages, sources, devices, geo, audience insights, and AI anomaly detection — straight
from natural language or the panel.

**Full technical documentation** (architecture, complete 39-function chat inventory, IPC surface,
panels, secrets/settings model, backend routes, known gaps):
[`docs/extension.md`](docs/extension.md).

---

## What It Does

Talk to it naturally:

```
"how's traffic looking on webhostmost.com this week"
"compare visits between my two sites"
"where is my traffic coming from"
"any anomalies today?"
"which pages are growing fastest?"
"how many people are on the site right now"
```

Or open the dashboard from the panel — live counter, 30-day chart, top pages, sources, devices,
one click away.

---

## Capabilities

### Tools (39 `@chat.function` + 17 `@ext.expose` IPC + 4 skeleton + 1 scheduled job)

**Traffic & trends:** `traffic` (visits/pageviews/unique visitors/bounce rate/avg time + series),
`top_pages`, `trends` (last 7 days vs the 7 before) — all three accept `sites=[...]` for a
side-by-side comparison instead of a single answer.

**Real-time & breakdowns:** `real_time` (live 30/60/180-min visitors), `sources`
(Direct/Search/Websites/Social), `devices` (desktop/mobile/tablet), `geo` (countries),
`entry_exit` (landing + exit pages) — all also accept `sites=[...]`.

**Audience:** `ai_referrers` (ChatGPT/Perplexity/Claude traffic), `conversions` (synthesizes an
"All Goals" entry for Ecommerce-only accounts with no named goals), `events`, `utm_sources`,
`new_vs_returning`, `visit_duration`.

**Channels:** `regions`, `device_brands`, `browsers` (+ `os_families`), `search_engines`,
`organic_keywords`, `campaigns`.

**Demographics & content signals:** `social_networks`, `referring_sites`, `site_search` (keywords +
no-result keywords — a zero-result search term is proof of content demand that doesn't exist yet),
`languages`, `providers` (ISP), `screen_resolutions`, `page_details` (time-on-page + bounce per
URL), `outlinks`.

**Insights:** `insights` (free — bounce-rate + growing/dying-page heuristics), `daily_report`
(uses AI tokens, runs in background), `anomaly_check` (free, vs last 7 days).

**Reports:** `full_report` — background, fetches all 24 backend sections concurrently.

**Site / project management:** `add_site`, `remove_site`, `list_sites`, `set_active_site`,
`site_domains` (ground-truth URLs + suggested segments straight from Matomo's own SitesManager),
`view_domain`, `save_settings`.

**Cross-extension IPC (17):** other extensions (e.g. an article-writing extension) pull
`organic_keywords`, `site_search`, `page_details`, `entry_exit`, `traffic`, `trends`, `top_pages`,
`growing_pages`, `real_time`, `sources`, `devices`, `geo`, `insights`, `daily_summary`,
`full_report`, and a token-safe `matomo_config` (never leaks `matomo_url`/`matomo_token`) via
`ctx.extensions.call("analytics", "<name>", ...)`.

**Scheduled:** `daily_summary` (`@ext.schedule`, cron `0 9 * * *`) — scans every configured site
and pushes an in-app notification if there are critical insights or 3+ warnings.

---

## Multi-site & segment tracking

Multiple sites/projects are supported — including two "projects" sharing one Matomo `site_id` via
a per-project **segment** (e.g. `label="Blog", site_id=2,
segment="pageUrl=^https://blog.example.com"`), so a subdomain that's really just one of many URL
aliases under a single Matomo `idSite` can be tracked and compared as if it were its own site.

Two levels are kept structurally separate on purpose:

- **`sites`** — real Matomo projects (site_ids), picked via `set_active_site`. Only grows when the
  user runs `add_site`.
- **domains within the active project** — the URL aliases Matomo already knows about under that
  same site_id (`known_domains`, cached from Matomo's `SitesManager` at `add_site` time). Once the
  active site has 2+ known domains, a `view_domain` domain-switcher dropdown appears in the
  sidebar, dashboard, and settings form — picking a domain updates that project's own `segment` in
  place (never adds a new `sites` entry); "All domains" clears it.

`traffic`/`top_pages`/`trends`/`sources`/`devices`/`geo`/`real_time`/`entry_exit` all accept
`sites=[...]` (2+ labels) for a side-by-side comparison in one call — the backend fans the targets
out concurrently itself, there's no separate "compare" endpoint.

---

## Architecture

```
imperal-matomo-analytics-extension/
├── main.py                    # entry point; hot-reload module list; @ext.schedule
│                               #   daily_summary; @ext.on_install; @ext.health_check
├── app.py                     # Extension + ChatExtension init; ext.secret() x2 (matomo_url,
│                               #   matomo_token); load_settings/save_settings; resolve_site()
├── api_client.py               # call_mos() — the only place that talks HTTP to the backend
├── compare_render.py           # compare_table()/compare_summary() — shared comparison renderer
├── params.py                   # chat-function Pydantic param models + shared help-text
├── response_models.py          # chat-function Pydantic response models (data_model= contracts)
├── skeleton.py                 # 4 @ext.skeleton providers (LLM context cache)
├── handlers_traffic.py         # traffic, top_pages, trends + IPC
├── handlers_settings.py        # save_settings, add_site, remove_site, list_sites,
│                               #   set_active_site, site_domains, view_domain
├── handlers_detail.py          # real_time, sources, devices, geo, entry_exit + IPC
├── handlers_insights.py        # insights, daily_report, anomaly_check + IPC
├── handlers_audience.py        # ai_referrers, conversions, events, utm_sources,
│                               #   new_vs_returning, visit_duration
├── handlers_channels.py        # regions, device_brands, browsers, search_engines,
│                               #   organic_keywords, campaigns
├── handlers_demographics.py    # social_networks, referring_sites, site_search, languages,
│                               #   providers, screen_resolutions, page_details, outlinks
├── handlers_reports.py         # full_report + IPC
├── audience_helpers.py         # shared err()/table()/top() helpers
├── panels_center.py            # @ext.panel("analytics_hub", slot="center") — dashboard overlay
├── panels_side.py               # @ext.panel("sidebar", slot="left") + @ext.panel("workspace",
│                               #   slot="right"); site/domain switchers
├── panels_render.py            # pure render helpers (kpi_stats, chart, tables, result dispatch)
├── panels_settings_render.py   # settings form (secrets-panel link, segment field, site list)
└── icon.svg                    # official Matomo mark
```

Backend is a separate FastAPI service (`matomo-analytics-api`, api-server:8105) that makes the
actual Matomo REST API calls, normalizes Matomo's response quirks, and handles SSRF hardening on
the user-supplied Matomo URL — not in this repo. This extension only resolves which site/segment
to ask for, forwards the call, and renders whatever comes back.

---

## Secrets & settings

Matomo URL and Auth Token are entered via the platform's own Secrets panel (EXT-SECRETS-V1,
per-user, `write_mode="user"`) — the extension never renders its own credential form and never
persists them outside `ctx.secrets`. Everything else (per-site list, active site, account-wide
segment, UTM custom-dimension id) lives in `ctx.store`.

---

## Development

```bash
source /home/ignat/Nextcloud/MCP-Configs/Imperal-Extensions-MCP/SeeU-Extensions/.venv-ext/bin/activate
python -m pytest tests/ -v
/home/ignat/.local/share/uv/tools/imperal-mcp/bin/imperal build .
/home/ignat/.local/share/uv/tools/imperal-mcp/bin/imperal validate .
```

All files kept ≤300 lines to satisfy the deploy validator.

---

## Built with

- [imperal-sdk](https://github.com/imperalcloud/imperal-sdk) 5.9.9
- [Imperal Cloud](https://panel.imperal.io)
