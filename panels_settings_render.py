"""Settings panel render helpers (sites list + non-secret settings form).
Split out of panels_render.py to stay under the 300-line file limit."""
from __future__ import annotations

from imperal_sdk import ui

from app import ext, matomo_ready, active_site_label


def sites_list(s: dict) -> ui.UINode:
    """Manage which Matomo site_ids are tracked as named projects."""
    sites = s.get("sites") or []
    active = active_site_label(s)
    rows = [{"label": site.get("label", "-"), "site_id": str(site.get("site_id", "-")),
             "scope": site.get("segment") or "whole site",
             "default": "★ default" if site.get("label") == active else ""}
            for site in sites]
    table = ui.DataTable(
        columns=[
            ui.DataColumn(key="label", label="Site / project", width="30%"),
            ui.DataColumn(key="site_id", label="Matomo site_id", width="15%"),
            ui.DataColumn(key="scope", label="Scope", width="35%"),
            ui.DataColumn(key="default", label="", width="20%"),
        ],
        rows=rows,
    ) if rows else ui.Empty(message="No sites yet - add one below.")

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

    active_site = next((site for site in sites if site.get("label") == active), None)
    domains = (active_site or {}).get("known_domains") or []
    domain_form = None
    if len(domains) > 1:
        segment = (active_site or {}).get("segment") or ""
        current = segment[len("pageUrl=^"):] if segment.startswith("pageUrl=^") else "All domains"
        domain_form = ui.Form(
            action="view_domain",
            submit_label="View domain",
            defaults={"site_id": active_site["site_id"]},
            children=[
                ui.Select(
                    options=[{"value": "All domains", "label": "All domains"}]
                            + [{"value": d, "label": d} for d in domains],
                    value=current,
                    param_name="domain",
                ),
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
    if switch_form:
        children.append(switch_form)
    if domain_form:
        children.append(domain_form)
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
