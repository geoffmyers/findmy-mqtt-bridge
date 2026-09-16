"""Battery decoding for Find My records.

Two encodings, by record kind:

* **Devices** carry ``batteryLevel`` — a float in ``[0.0, 1.0]`` — which maps
  directly to a percentage. (They also carry a ``batteryStatus`` *string* like
  ``"Unknown"`` / ``"Charging"`` which we surface verbatim when present.)
* **Items** (AirTags / accessories) carry ``batteryStatus`` — a small *int*
  enum, higher = healthier (observed values 0/4/5 across the fleet). Apple does
  not publish the enum, so the text mapping is a best-effort default and is
  overridable via config (``filters`` → not applicable; see
  ``Config.item_battery_labels``).

Pure functions; no I/O.
"""

from __future__ import annotations

# Best-effort default text for the item ``batteryStatus`` int enum (higher =
# healthier — a full AirTag reports 5, a fresh-ish one 4, unknown 0). Override
# per-deployment in config if Apple's labels turn out different on your fleet.
DEFAULT_ITEM_BATTERY_LABELS: dict[int, str] = {
    0: "Unknown",
    1: "Critical",
    2: "Low",
    3: "Medium",
    4: "Good",
    5: "Full",
}


def device_battery_percent(battery_level: object) -> int | None:
    """Map a device ``batteryLevel`` float (0.0–1.0) to a 0–100 percent int.

    Returns ``None`` for missing / non-numeric / out-of-range values (Apple
    uses ``0.0`` as a placeholder for "unknown" on some devices, which we keep
    as ``0`` — the caller can choose to suppress it).
    """
    if isinstance(battery_level, bool) or not isinstance(battery_level, (int, float)):
        return None
    if battery_level < 0 or battery_level > 1:
        return None
    return round(battery_level * 100)


def item_battery_text(battery_status: object, labels: dict[int, str] | None = None) -> str | None:
    """Map an item ``batteryStatus`` int enum to a label.

    Unknown/out-of-range ints pass through as their string form so nothing is
    silently dropped. Non-int input returns ``None``.
    """
    table = labels or DEFAULT_ITEM_BATTERY_LABELS
    if isinstance(battery_status, bool) or not isinstance(battery_status, int):
        return None
    return table.get(battery_status, str(battery_status))
