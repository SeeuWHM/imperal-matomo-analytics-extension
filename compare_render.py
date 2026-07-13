"""Shared renderer for the `sites=[...]` comparison branch - one generic
table, each caller supplies its own per-metric column extractors so this
stays metric-agnostic (traffic's columns differ from geo's, from trends')."""
from __future__ import annotations

from imperal_sdk import ui


def compare_table(results: list[dict], columns: list[tuple[str, str, "callable"]]) -> "ui.DataTable | ui.Empty":
    """results = the raw call_mos() envelope's `results` list -
    [{label, site_id, error, data}, ...]. columns = [(key, header, fn(data)->str), ...]."""
    rows = []
    for r in results:
        row = {"site": r.get("label") or "-"}
        if r.get("error"):
            row["site"] = f"{row['site']} (error)"
            for key, _header, _fn in columns:
                row[key] = "—"
        else:
            data = r.get("data") or {}
            for key, _header, fn in columns:
                try:
                    row[key] = fn(data)
                except Exception:
                    row[key] = "—"
        rows.append(row)
    if not rows:
        return ui.Empty(message="No data")
    width = f"{max(75 // max(len(columns), 1), 15)}%"
    cols = [ui.DataColumn(key="site", label="Site", width="25%")]
    cols += [ui.DataColumn(key=key, label=header, width=width) for key, header, _ in columns]
    return ui.DataTable(columns=cols, rows=rows)


def compare_summary(results: list[dict]) -> str:
    names = ", ".join(r.get("label") or "-" for r in results)
    ok = sum(1 for r in results if not r.get("error"))
    return f"Compared {len(results)} sites ({ok} ok): {names}"
