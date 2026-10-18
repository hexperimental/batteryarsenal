"""Tests for report rendering against a fixed inventory snapshot."""

from custom_components.battery_arsenal.coordinator import (
    DeviceRecord,
    InventoryData,
    TypeAggregate,
)
from custom_components.battery_arsenal.const import (
    CATEGORY_CONSUMABLE,
    CATEGORY_NON_CONSUMABLE,
    CATEGORY_UNMAPPED,
)
from custom_components.battery_arsenal.report import render_csv, render_markdown


def _snapshot() -> InventoryData:
    aa1 = DeviceRecord(
        "d1", "Hallway sensor", "Hallway", "Aqara", "T1", "AA", 2, CATEGORY_CONSUMABLE, "sensor.d1"
    )
    aa2 = DeviceRecord(
        "d2", "Remote", "Living room", "Logitech", "Harmony", "AA", 2, CATEGORY_CONSUMABLE, "sensor.d2"
    )
    cr = DeviceRecord(
        "d3", "Door sensor", "Front door", "Aqara", "DW2", "CR2032", 1, CATEGORY_CONSUMABLE, "sensor.d3"
    )
    data = InventoryData()
    data.types["AA"] = TypeAggregate("AA", cells=4, devices=[aa1, aa2])
    data.types["CR2032"] = TypeAggregate("CR2032", cells=1, devices=[cr])
    data.total_cells = 5
    data.records = [aa1, aa2, cr]
    data.non_consumable = [
        DeviceRecord(
            "d4", "Thermostat", "Hall", "Google", "Nest", "RECHARGEABLE", 1, CATEGORY_NON_CONSUMABLE, "sensor.d4"
        )
    ]
    data.unmapped = [
        DeviceRecord("d5", "Mystery", None, None, None, None, 1, CATEGORY_UNMAPPED, "sensor.d5")
    ]
    return data


def test_render_markdown():
    md = render_markdown(_snapshot(), None)
    assert "# Battery Arsenal report" in md
    assert "5 consumable cells" in md
    assert "2 types" in md
    assert "Most common: AA (4 cells)" in md
    assert "| AA | 4 | 2 | 80.0% |" in md
    assert "### CR2032" in md
    assert "Thermostat" in md
    assert "Mystery" in md


def test_render_csv():
    csv_text = render_csv(_snapshot())
    lines = csv_text.strip().splitlines()
    assert lines[0] == "category,battery_type,quantity,device,area,manufacturer,model"
    # 3 consumable + 1 non-consumable + 1 unmapped = 5 rows + header
    assert len(lines) == 6
    assert "consumable,AA,2,Hallway sensor,Hallway,Aqara,T1" in csv_text
    assert "unmapped,,1,Mystery,,," in csv_text
