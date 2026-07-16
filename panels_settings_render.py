"""Settings panel render helpers (sites list + non-secret settings form).
Split out of panels_render.py to stay under the 300-line file limit."""
from __future__ import annotations

from imperal_sdk import ui

from app import ext, matomo_ready, active_site_label


def sites_list(s: dict) -> ui.UINode:
    """Manage which Matomo site_ids are tracked as named projects.

    Each site is a row with an inline trash action (asks to confirm) instead
    of the old 'type the label and hit Remove' form."""
    sites = s.get("sites") or []
    active = active_site_label(s)

    def _row(site: dict) -> ui.UINode:
        label = site.get("label", "-")
        scope = site.get("segment") or "whole site"
        return ui.ListItem(
            id=label or "-",
            title=label,
            subtitle=f"site_id {site.get('site_id', '-')} · {scope}",
            badge=ui.Badge(label="★ default", color="violet") if label == active else None,
            actions=[{
                "icon": "Trash2",
                "on_click": ui.Call("remove_site", label=label),
                "confirm": f"Remove “{label}” from tracked sites?",
            }],
        )

    listing = (ui.List(items=[_row(site) for site in sites])
               if sites else ui.Empty(message="No sites yet — add one below."))

    add_form = ui.Form(
        action="add_site",
        submit_label="Add site",
        children=[
            ui.Input(placeholder="Label - e.g. Main Website, Site 2", param_name="label"),
            ui.Input(placeholder="Matomo site_id - e.g. 1", param_name="site_id"),
        ],
    )
    switch_form = ui.Form(
        action="set_active_site",
        submit_label="Make default",
        children=[
            ui.Select(
                options=[{"value": site["label"], "label": site["label"]} for site in sites],
                value=active,
                param_name="label",
            ),
        ],
    ) if len(sites) > 1 else None

    children = [listing, add_form]
    if switch_form:
        children.append(switch_form)
    return ui.Stack(children=children)


def settings_form(s: dict) -> ui.UINode:
    ready = matomo_ready(s)
    status = ui.Badge(
        label="Matomo connected" if ready else "Matomo not configured",
        color="green" if ready else "red",
    )
    open_secrets = ui.Button(
        label="Set Matomo URL + Auth Token" if not ready else "Manage Matomo credentials",
        variant="primary" if not ready else "secondary",
        on_click=ui.Navigate(path=f"/ext/{ext.app_id}/secrets"),
    )
    return ui.Stack(children=[
        status,
        ui.Text(
            content=("Matomo URL and Auth Token live in the platform's encrypted Secrets "
                     "vault, never in this extension's own data - click below to set them."),
            variant="caption",
        ),
        open_secrets,
        ui.Divider(),
        ui.Text(content="Sites / projects", variant="caption"),
        sites_list(s),
    ])
