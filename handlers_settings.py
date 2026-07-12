"""Handlers for saving user settings, and managing the multi-site list."""
# No `from __future__ import annotations` - see note in handlers_traffic.py.

from imperal_sdk.types import ActionResult

from app import chat, save_settings, load_settings
from params import SaveSettingsParams, AddSiteParams, RemoveSiteParams, ListSitesParams


@chat.function(
    "save_settings",
    description="Save the Analytics extension's non-credential settings (segment, UTM dimension). "
                "Matomo URL/Auth Token are entered via the Secrets panel, not here.",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
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
                "track my blog separately, добавить ещё один сайт.",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
)
async def fn_add_site(ctx, params: AddSiteParams) -> ActionResult:
    """Add (or replace, if the label already exists) a site/project entry."""
    s = await load_settings(ctx)
    sites = [site for site in (s.get("sites") or []) if site.get("label", "").strip().lower() != params.label.strip().lower()]
    sites.append({"label": params.label.strip(), "site_id": params.site_id})
    await save_settings(ctx, {"sites": sites})
    return ActionResult.success(
        data={"sites": sites},
        summary=f"Added site '{params.label}' (Matomo site_id {params.site_id}). {len(sites)} site(s) configured.",
    )


@chat.function(
    "remove_site",
    description="Remove a tracked site/project by its label (from list_sites).",
    action_type="destructive",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
)
async def fn_remove_site(ctx, params: RemoveSiteParams) -> ActionResult:
    """Remove a site/project entry by label."""
    s = await load_settings(ctx)
    needle = params.label.strip().lower()
    sites = s.get("sites") or []
    remaining = [site for site in sites if site.get("label", "").strip().lower() != needle]
    if len(remaining) == len(sites):
        return ActionResult.error(error=f"No site named '{params.label}' found.")
    await save_settings(ctx, {"sites": remaining})
    return ActionResult.success(
        data={"sites": remaining},
        summary=f"Removed site '{params.label}'. {len(remaining)} site(s) remaining.",
    )


@chat.function(
    "list_sites",
    description="List all sites/projects configured for this Matomo account. "
                "Use for: какие сайты подключены, список проектов, list my sites.",
    action_type="read",
)
async def fn_list_sites(ctx, params: ListSitesParams) -> ActionResult:
    """List configured sites/projects."""
    s = await load_settings(ctx)
    sites = s.get("sites") or []
    if not sites:
        return ActionResult.success(
            data={"sites": []},
            summary="No sites configured yet — use add_site to add one.",
        )
    lines = ", ".join(f"{site['label']} (site_id {site['site_id']})" for site in sites)
    return ActionResult.success(
        data={"sites": sites},
        summary=f"{len(sites)} site(s): {lines}",
    )
