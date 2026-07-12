"""Handlers for saving user settings, and managing the multi-site list."""
# No `from __future__ import annotations` - see note in handlers_traffic.py.

from imperal_sdk.types import ActionResult

from app import chat, save_settings, load_settings, sites_with_active
from api_client import call_mos
from params import (
    SaveSettingsParams, AddSiteParams, RemoveSiteParams, ListSitesParams,
    SetActiveSiteParams, SiteDomainsParams,
)
from response_models import SavedKeysResponse, SitesListResponse, SiteInfoResponse


@chat.function(
    "save_settings",
    description="Save the Analytics extension's non-credential settings (segment, UTM dimension). "
                "Matomo URL/Auth Token are entered via the Secrets panel, not here.",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
    data_model=SavedKeysResponse,
)
async def fn_save_settings(ctx, params: SaveSettingsParams) -> ActionResult:
    """Persist form values. Blank fields keep their current value -
    that lets users update one field at a time."""
    updates: dict = {}
    if params.matomo_segment is not None:
        updates["matomo_segment"] = params.matomo_segment.strip()
    if params.utm_source_dim_id is not None:
        updates["utm_source_dim_id"] = int(params.utm_source_dim_id)

    await save_settings(ctx, updates)
    return ActionResult.success(
        data={"saved_keys": list(updates.keys())},
        summary=f"Saved {len(updates)} field(s)",
    )


@chat.function(
    "add_site",
    description="Add a site/project to track — each Matomo account can track multiple websites "
                "under different site IDs. Use for: добавь сайт, новый проект, add another site, "
                "track a second project separately, добавить ещё один сайт.",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
    data_model=SitesListResponse,
)
async def fn_add_site(ctx, params: AddSiteParams) -> ActionResult:
    """Add (or replace, if the label already exists) a site/project entry."""
    s = await load_settings(ctx)
    sites = [site for site in (s.get("sites") or []) if site.get("label", "").strip().lower() != params.label.strip().lower()]
    sites.append({"label": params.label.strip(), "site_id": params.site_id})
    updates = {"sites": sites}
    if len(sites) == 1:
        updates["active_site"] = sites[0]["label"]  # first site added becomes the default
    s = await save_settings(ctx, updates)
    return ActionResult.success(
        data={"sites": sites_with_active(s)},
        summary=f"Added site '{params.label}' (Matomo site_id {params.site_id}). {len(sites)} site(s) configured.",
        refresh_panels=["sidebar", "workspace", "analytics_hub"],
    )


@chat.function(
    "remove_site",
    description="Remove a tracked site/project by its label (from list_sites).",
    action_type="destructive",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
    data_model=SitesListResponse,
)
async def fn_remove_site(ctx, params: RemoveSiteParams) -> ActionResult:
    """Remove a site/project entry by label."""
    s = await load_settings(ctx)
    needle = params.label.strip().lower()
    sites = s.get("sites") or []
    remaining = [site for site in sites if site.get("label", "").strip().lower() != needle]
    if len(remaining) == len(sites):
        return ActionResult.error(error=f"No site named '{params.label}' found.")
    updates = {"sites": remaining}
    if remaining and s.get("active_site", "").strip().lower() == needle:
        # save_settings treats "" as "keep current value" - only reassign
        # when there's a real site left to fall back to; resolve_site_id()
        # already ignores a stale active_site label and falls back to
        # sites[0] on its own, so leaving it untouched otherwise is safe.
        updates["active_site"] = remaining[0]["label"]
    s = await save_settings(ctx, updates)
    return ActionResult.success(
        data={"sites": sites_with_active(s)},
        summary=f"Removed site '{params.label}'. {len(remaining)} site(s) remaining.",
        refresh_panels=["sidebar", "workspace", "analytics_hub"],
    )


@chat.function(
    "list_sites",
    description="List all sites/projects configured for this Matomo account. "
                "Use for: какие сайты подключены, список проектов, list my sites.",
    action_type="read",
    data_model=SitesListResponse,
)
async def fn_list_sites(ctx, params: ListSitesParams) -> ActionResult:
    """List configured sites/projects."""
    s = await load_settings(ctx)
    sites = sites_with_active(s)
    if not sites:
        return ActionResult.success(
            data={"sites": []},
            summary="No sites configured yet — use add_site to add one.",
        )
    lines = ", ".join(
        f"{site['label']} (site_id {site['site_id']}){' — default' if site['active'] else ''}"
        for site in sites
    )
    return ActionResult.success(
        data={"sites": sites},
        summary=f"{len(sites)} site(s): {lines}",
    )


@chat.function(
    "set_active_site",
    description="Switch which site/project is the default - used by the sidebar, the dashboard "
                "and chat questions where the user doesn't name a site. Use for: переключи на сайт X, "
                "сделай сайт X основным, switch to site X, make X the default site/project.",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
    data_model=SitesListResponse,
)
async def fn_set_active_site(ctx, params: SetActiveSiteParams) -> ActionResult:
    """Set which configured site is the default for chat/dashboard/sidebar."""
    s = await load_settings(ctx)
    needle = params.label.strip().lower()
    match = next((site for site in (s.get("sites") or [])
                  if site.get("label", "").strip().lower() == needle), None)
    if not match:
        return ActionResult.error(error=f"No site named '{params.label}' found.")
    s = await save_settings(ctx, {"active_site": match["label"]})
    return ActionResult.success(
        data={"sites": sites_with_active(s)},
        summary=f"Default site switched to '{match['label']}'.",
        refresh_panels=["sidebar", "workspace", "analytics_hub"],
    )


@chat.function(
    "site_domains",
    description="Which domains/URLs are actually configured for a site/project in Matomo - the "
                "real main_url and every URL alias from Matomo's own SitesManager, not guessed "
                "from referrer or page traffic. Use for: какие домены привязаны к сайту, "
                "какой домен у сайта, site domains, site URLs, what domains does this site cover.",
    action_type="read",
    data_model=SiteInfoResponse,
)
async def fn_site_domains(ctx, params: SiteDomainsParams) -> ActionResult:
    """Look up the domains Matomo has configured for a site (main_url + aliases)."""
    data = await call_mos(ctx, "/api/matomo-analytics/site-info", {}, site=params.site)
    if "error" in data:
        return ActionResult.error(error=data["error"])
    urls = data.get("urls") or []
    name = data.get("name") or "this site"
    main_url = data.get("main_url") or "unknown"
    summary = f"{name}: main domain {main_url}, {len(urls)} URL(s) configured total."
    return ActionResult.success(data=data, summary=summary)
