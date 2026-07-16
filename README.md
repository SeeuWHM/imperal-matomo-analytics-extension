# Matomo Analytics Connector

Traffic analytics dashboard for Imperal Cloud. Connect one or more Matomo instances (and even
track a single subdomain like a blog separately via a segment), get a full dashboard with
visits, trends, top pages, sources, devices, geo, audience insights and AI anomaly detection.

**Full technical documentation (frontend + backend, verified against the live deploy):**
[`docs/extension.md`](docs/extension.md) — read that file for architecture, the complete
39-function chat inventory, panels, secrets/settings model, backend routes, and known gaps.

## Quick facts

- **Version:** 5.2.6 · **app_id:** `imperal-matomo-analytics-extension` · **Tool:** `analytics`
- Matomo URL + Auth Token are entered via the platform's own Secrets panel (EXT-SECRETS-V1,
  per-user), not stored by the extension itself.
- Multiple sites/projects supported — including two "projects" sharing one Matomo `site_id` via
  a per-site segment (e.g. `label="Blog", site_id=2, segment="pageUrl=^https://blog.example.com"`).
  A domain-level dropdown (`view_domain`) switches between a site's real domains one click at a
  time, using a `known_domains` cache populated from Matomo's own SitesManager at `add_site` time.
- `traffic`/`top_pages`/`trends`/`sources`/`devices`/`geo`/`real_time`/`entry_exit` accept
  `sites=[...]` (2+ labels) for a side-by-side comparison in one call - the backend fans targets
  out concurrently itself, no separate "compare" endpoint.
- Backend is a separate FastAPI service (`matomo-analytics-api`, api-server:8105, **not in this
  repo** — edited directly on the server) that does the actual Matomo REST API calls and SSRF
  hardening; the extension only resolves site/segment and renders results.

## Development

```bash
source /home/ignat/Nextcloud/MCP-Configs/Imperal-Extensions-MCP/SeeU-Extensions/.venv-ext/bin/activate
python -m pytest tests/ -v
/home/ignat/.local/share/uv/tools/imperal-mcp/bin/imperal build .
/home/ignat/.local/share/uv/tools/imperal-mcp/bin/imperal validate .
```

All files kept ≤300 lines to satisfy the deploy validator.

## License

AGPL-3.0 (matches imperal-sdk).
