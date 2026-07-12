# Imperal Analytics

Traffic analytics dashboard for Imperal Cloud. Connect any Matomo instance, get a full-screen dashboard with visits, trends, and top pages.

## What it does

- **Central dashboard** — 4 stat cards (Today / Yesterday / Last 7d / Week Δ%), 7-day visits chart, top-10 pages table.
- **Quick actions (left panel)** — one-click refresh, today's traffic, week trends, top pages for the month.
- **Chat** — ask Webbee things like *"top 5 pages this month"*, *"compare traffic vs last week"*, *"how many visits today"*.
- **IPC** — other extensions can call `ctx.extensions.call("analytics", "traffic" | "trends" | "top_pages", ...)` to pull metrics into their own dashboards (e.g. a Daily Report extension).

## How it works

```
User → Imperal Panel
       │
       ▼
[ analytics extension ]         ← this repo, runs inside Imperal Cloud
       │
       │ HTTPS + X-API-Key
       ▼
[ mos.lexa-lox.xyz ]             ← shared FastAPI server (outside this repo)
       │
       │ token_auth + segment
       ▼
[ user's Matomo instance ]       ← any Matomo, user supplies URL/token in Settings
```

The extension itself is small and contains **no Matomo logic** — it just renders a dashboard and forwards requests to a shared server. The server does the actual Matomo API talking. If AI quota runs out, the dashboard still works (the chat goes away, panels keep rendering).

**Why the split?** Scripts, not tokens. The server is pure Python + HTTP. It runs even without an LLM. The extension is the UI.

## Install

1. Marketplace → search *Analytics* → Install.
2. Settings panel (right side):
   - **Server URL:** `https://mos.lexa-lox.xyz` (default)
   - **Server API Key:** save it as the Imperal app secret `MATOMO_BACKEND_API_KEY`
   - **Backend URL:** save it as the Imperal app secret `MATOMO_BACKEND_URL`
   - **Matomo URL:** e.g. `https://analytics.example.com`
   - **Auth Token:** from Matomo → Personal → Security → Auth tokens
   - **Site ID:** integer (default 1)
   - **Segment (optional):** e.g. `pageUrl=^https://blog.example.com`

## Development

```bash
pip install -e .[dev]
imperal validate
pytest
```

### Files

```
main.py              entry point (hot-reload wrapper)
app.py               Extension + ChatExtension instances, config helpers
api_client.py        HTTP client → mos.lexa-lox.xyz
params.py            Pydantic models
handlers_traffic.py  chat functions (traffic, trends, top_pages) + IPC
panels_main.py       @ext.panel("dashboard", slot="main") — central workspace
panels_side.py       @ext.panel("sidebar", slot="left") + settings (slot="right")
imperal.json         manifest
tests/               unit tests with MockContext
```

All files kept ≤ 300 lines to satisfy the deploy validator.

## License

AGPL-3.0 (matches imperal-sdk).
