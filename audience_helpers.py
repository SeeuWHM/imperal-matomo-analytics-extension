"""Shared render/error helpers for handlers_audience.py and handlers_channels.py."""
from typing import Union

from imperal_sdk import ui
from imperal_sdk.types import ActionResult


def err(data: dict) -> ActionResult:
    return ActionResult.error(error=data.get("error", "unknown error"))


def table(rows: list[dict], label_col: str = "Label") -> Union[ui.DataTable, ui.Empty]:
    if not rows:
        return ui.Empty(message="No data")
    return ui.DataTable(
        columns=[
            ui.DataColumn(key="label", label=label_col, width="55%"),
            ui.DataColumn(key="visits", label="Visits", width="22%"),
            ui.DataColumn(key="pct", label="Share", width="23%"),
        ],
        rows=[
            {"label": r.get("label", "-"),
             "visits": f"{r.get('visits', 0):,}",
             "pct": f"{r.get('percent', 0)}%"}
            for r in rows[:15]
        ],
    )


def top(items: list[dict]) -> tuple[str, float]:
    """Return (label, percent) of the first item."""
    if items:
        return items[0].get("label", "n/a"), items[0].get("percent", 0)
    return "n/a", 0
