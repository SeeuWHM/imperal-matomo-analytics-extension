"""Handlers for saving user settings, and managing the multi-site list."""
# No `from __future__ import annotations` - see note in handlers_traffic.py.

from imperal_sdk.types import ActionResult

from app import chat, save_settings, load_settings, sites_with_active, active_site_label
from api_client import call_mos, site_info_for
from params import (
    SaveSettingsParams, AddSiteParams, RemoveSiteParams, ListSitesParams,
    SetActiveSiteParams, SiteDomainsParams, ViewDomainParams,
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
    description="Add a site/project to track — either a whole Matomo site, or a specific "
                "subdomain/section that shares a site_id with other content (via segment). "
                "Use for: добавь сайт, новый проект, add another site, track a second project "
                "separately, track just the blog/docs/forum subdomain, добавить ещё один сайт.",
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
    entry = {"label": params.label.strip(), "site_id": params.site_id}
    if params.segment.strip():
        entry["segment"] = params.segment.strip()

    # Best-effort: cache the site_id's real domains so the panel's
    # domain-level dropdown (view_domain) has options without a separate
    # site_domains call. Never blocks add_site if this fails.
    info = await site_info_for(ctx, params.site_id, entry.get("segment"))
    if "error" not in info and info.get("urls"):
        entry["known_domains"] = info["urls"]

    sites.append(entry)
    updates = {"sites": sites}
    if len(sites) == 1:
        updates["active_site"] = sites[0]["label"]  # first site added becomes the default
    s = await save_settings(ctx, updates)
    scope_note = f", segment: {entry['segment']}" if "segment" in entry else ""
    return ActionResult.success(
        data={"sites": sites_with_active(s)},
        summary=f"Added site '{params.label}' (Matomo site_id {params.site_id}{scope_note}). "
                f"{len(sites)} site(s) configured.",
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
                "from referrer or page traffic. Also suggests a ready-to-use segment for each "
                "domain, for tracking one subdomain (e.g. a blog) separately via add_site. "
                "Use for: какие домены привязаны к сайту, какой домен у сайта, site domains, "
                "site URLs, what domains does this site cover, как отследить отдельно поддомен.",
    action_type="read",
    data_model=SiteInfoResponse,
)
async def fn_site_domains(ctx, params: SiteDomainsParams) -> ActionResult:
    """Look up the domains Matomo has configured for a site (main_url + aliases),
    with a ready-to-paste segment suggestion per domain for add_site."""
    data = await call_mos(ctx, "/api/matomo-analytics/site-info", {}, site=params.site)
    if "error" in data:
        return ActionResult.error(error=data["error"])
    urls = data.get("urls") or []
    name = data.get("name") or "this site"
    main_url = data.get("main_url") or "unknown"
    data = {**data, "suggested_segments": [
        {"domain": u, "segment": f"pageUrl=^{u}"} for u in urls
    ]}
    summary = f"{name}: main domain {main_url}, {len(urls)} URL(s) configured total."
    if len(urls) > 1:
        summary += (" To track one of them separately, use add_site with that domain's suggested "
                    "segment.")
    return ActionResult.success(data=data, summary=summary)


@chat.function(
    "view_domain",
    description="Scope the CURRENT site/project down to one domain, when its Matomo site_id "
                "covers several URL aliases (e.g. jump straight to a blog subdomain within the "
                "same project) - pass domain='All domains' to go back to the whole site. This "
                "updates that project's own segment in place, it does NOT add a new site/project "
                "(use add_site for that, to give a sub-project its own permanent label). "
                "Use for: покажи только блог, switch to domain X, view just this subdomain, "
                "смотреть только на этот домен, только для домена.",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
    data_model=SitesListResponse,
)
async def fn_view_domain(ctx, params: ViewDomainParams) -> ActionResult:
    """Update the existing site/project's own segment to scope it to one
    domain - never creates a new sites[] entry (that's what add_site is for,
    when the user deliberately wants a persistent, separately-named
    sub-project). Prefers the currently active entry if several sites share
    this site_id."""
    s = await load_settings(ctx)
    sites = s.get("sites") or []
    active_label = active_site_label(s)
    candidates = [i for i, site in enumerate(sites) if int(site.get("site_id", 0)) == params.site_id]
    if not candidates:
        return ActionResult.error(error=f"No site configured with site_id {params.site_id}.")
    idx = next((i for i in candidates if sites[i].get("label") == active_label), candidates[0])

    all_domains = params.domain.strip().lower() in ("", "all", "all domains")
    updated = dict(sites[idx])
    if all_domains:
        updated.pop("segment", None)
    else:
        updated["segment"] = f"pageUrl=^{params.domain.strip()}"
    sites[idx] = updated

    s = await save_settings(ctx, {"sites": sites, "active_site": updated["label"]})
    scope = "all domains" if all_domains else params.domain.strip()
    return ActionResult.success(
        data={"sites": sites_with_active(s)},
        summary=f"'{updated['label']}' now viewing {scope}.",
        refresh_panels=["sidebar", "workspace", "analytics_hub"],
    )
