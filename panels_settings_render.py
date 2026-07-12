"""Settings panel render helpers (sites list + non-secret settings form).
Split out of panels_render.py to stay under the 300-line file limit."""
from __future__ import annotations

from imperal_sdk import ui

from app import ext, matomo_ready


def sites_list(s: dict) -> ui.UINode:
    """Manage which Matomo site_ids are tracked as named projects."""
    sites = s.get("sites") or []
    rows = [{"label": site.get("label", "-"), "site_id": str(site.get("site_id", "-"))}
            for site in sites]
    table = ui.DataTable(
        columns=[
            ui.DataColumn(key="label", label="Site / project", width="60%"),
            ui.DataColumn(key="site_id", label="Matomo site_id", width="40%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No sites yet - add one below.")

    add_form = ui.Form(
        action="add_site",
        submit_label="Add site",
        children=[
            ui.Input(placeholder="Label - e.g. Main Website, Blog, Docs", param_name="label"),
            ui.Input(placeholder="Matomo site_id - e.g. 1", param_name="site_id"),
        ],
    )
    remove_form = ui.Form(
        action="remove_site",
        submit_label="Remove site",
        children=[
            ui.Input(placeholder="Label to remove", param_name="label"),
        ],
    ) if rows else None

    children = [table, add_form]
    if remove_form:
        children.append(remove_form)
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
    form = ui.Form(
        action="save_settings",
        submit_label="Save settings",
        children=[
            ui.Input(placeholder="Segment (optional) - pageUrl=^https://blog.example.com",
                     value=s.get("matomo_segment", ""), param_name="matomo_segment"),
            ui.Input(placeholder="UTM source Dimension ID (optional) - e.g. 8",
                     value=str(s.get("utm_source_dim_id") or ""), param_name="utm_source_dim_id"),
        ],
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
        ui.Divider(),
        form,
        ui.Text(content="Leave a field blank to keep the current value.",
                variant="caption"),
    ])
