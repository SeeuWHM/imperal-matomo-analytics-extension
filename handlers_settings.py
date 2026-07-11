"""Handlers for saving user settings via the right-side Form."""
# No `from __future__ import annotations` - see note in handlers_traffic.py.

from imperal_sdk.types import ActionResult

from app import chat, save_settings
from params import SaveSettingsParams


@chat.function(
    "save_settings",
    description="Save the Analytics extension settings (server + Matomo credentials).",
    action_type="write",
    chain_callable=True,
    effects=["update:settings"],
    event="analytics.settings.saved",
)
async def fn_save_settings(ctx, params: SaveSettingsParams) -> ActionResult:
    """Persist form values. Blank fields keep their current value -
    that lets users update one field at a time without retyping secrets."""
    updates: dict = {}
    if params.matomo_url:
        updates["matomo_url"] = params.matomo_url.strip()
    if params.matomo_token:
        updates["matomo_token"] = params.matomo_token.strip()
    if params.matomo_site_id:
        updates["matomo_site_id"] = int(params.matomo_site_id)
    if params.matomo_segment is not None:
        updates["matomo_segment"] = params.matomo_segment.strip()
    if params.blog_url is not None:
        updates["blog_url"] = params.blog_url.strip().rstrip("/")
    if params.blog_site_id is not None:
        updates["blog_site_id"] = int(params.blog_site_id)
    if params.utm_source_dim_id is not None:
        updates["utm_source_dim_id"] = int(params.utm_source_dim_id)

    await save_settings(ctx, updates)
    return ActionResult.success(
        data={"saved_keys": list(updates.keys())},
        summary=f"Saved {len(updates)} field(s)",
    )
