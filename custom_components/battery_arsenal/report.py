"""Report rendering: Markdown and CSV from an inventory snapshot."""

from __future__ import annotations

import csv
import io

from homeassistant.util import dt as dt_util

from .coordinator import InventoryData
from .storage import ReplacementHistory


def render_markdown(data: InventoryData, history: ReplacementHistory | None) -> str:
    """Render the inventory as a Markdown report."""
    lines: list[str] = []
    now = dt_util.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# Battery Arsenal report\n")
    lines.append(f"_Generated {now}_\n")

    device_count = sum(len(a.devices) for a in data.types.values())
    top = data.most_common
    top_txt = f"{top.battery_type} ({top.cells} cells)" if top else "n/a"
    lines.append(
        f"**{data.total_cells} consumable cells** across **{len(data.types)} types** "
        f"in **{device_count} devices**. Most common: {top_txt}.\n"
    )

    # Totals by type.
    lines.append("## Totals by type\n")
    if data.types:
        lines.append("| Type | Cells | Devices | Share |")
        lines.append("| --- | ---: | ---: | ---: |")
        for agg in sorted(data.types.values(), key=lambda a: a.cells, reverse=True):
            share = (
                round(100 * agg.cells / data.total_cells, 1)
                if data.total_cells
                else 0
            )
            lines.append(
                f"| {agg.battery_type} | {agg.cells} | {len(agg.devices)} | {share}% |"
            )
    else:
        lines.append("_No consumable batteries found._")
    lines.append("")

    # Devices grouped by type.
    lines.append("## Devices by type\n")
    for agg in sorted(data.types.values(), key=lambda a: a.cells, reverse=True):
        lines.append(f"### {agg.battery_type}\n")
        for r in agg.devices:
            area = f" — {r.area}" if r.area else ""
            lines.append(f"- {r.name}{area} ({r.quantity}×)")
        lines.append("")

    # Non consumable.
    lines.append("## Non-consumable devices\n")
    if data.non_consumable:
        for r in data.non_consumable:
            area = f" — {r.area}" if r.area else ""
            lines.append(f"- {r.name}{area} ({r.battery_type})")
    else:
        lines.append("_None._")
    lines.append("")

    # Unmapped.
    lines.append("## Unmapped devices (no known type)\n")
    if data.unmapped:
        for r in data.unmapped:
            area = f" — {r.area}" if r.area else ""
            lines.append(f"- {r.name}{area}")
    else:
        lines.append("_None._")
    lines.append("")

    if data.untracked:
        lines.append("## Untracked battery devices (not in Battery Notes)\n")
        for r in data.untracked:
            area = f" — {r.area}" if r.area else ""
            lines.append(f"- {r.name}{area}")
        lines.append("")

    # Restock (phase 2).
    rates = history.annual_rate_by_type() if history else {}
    if rates:
        lines.append("## Restock\n")
        lines.append("| Type | Cells/year | Suggested stock |")
        lines.append("| --- | ---: | ---: |")
        for btype in sorted(rates, key=lambda b: rates[b], reverse=True):
            rate = rates[btype]
            lines.append(f"| {btype} | {rate} | {history.suggested_stock(rate)} |")
        lines.append("")

    return "\n".join(lines)


def render_csv(data: InventoryData) -> str:
    """Render the per-device inventory as CSV."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["category", "battery_type", "quantity", "device", "area", "manufacturer", "model"]
    )
    rows = (
        [r for a in data.types.values() for r in a.devices]
        + data.non_consumable
        + data.unmapped
        + data.untracked
    )
    for r in rows:
        writer.writerow(
            [
                r.category,
                r.battery_type or "",
                r.quantity,
                r.name,
                r.area or "",
                r.manufacturer or "",
                r.model or "",
            ]
        )
    return buffer.getvalue()
