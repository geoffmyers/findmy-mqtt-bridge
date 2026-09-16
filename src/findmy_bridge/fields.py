"""Declarative field → HA mapping for Find My records.

Everything a device/item reports is surfaced:
  * location + reverse-geocoded address + core identity → device_tracker attrs
  * high-value fields → dedicated diagnostic sensors / binary_sensors
  * the full raw long-tail → a "Details" sensor's attributes (nothing dropped)

Pure functions + data tables; consumed by entities.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .normalize import DEVICE, ITEM, Record

BOTH = (ITEM, DEVICE)

# Sentinel "no data" values Apple uses for these numeric location fields.
_NEG_SENTINEL = {"altitude", "vertical_accuracy", "floor_level"}


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if k in _NEG_SENTINEL and isinstance(v, (int, float)) and v < 0:
            continue
        out[k] = v
    return out


def tracker_attributes(record: Record) -> dict[str, Any]:
    """device_tracker json_attributes: GPS (drives HA zone resolution) + the
    reverse-geocoded address broken out + core identity."""
    loc, addr = record.location, record.address
    return _clean({
        # GPS — latitude/longitude/gps_accuracy drive HA's native zone resolution
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "gps_accuracy": loc.get("horizontalAccuracy"),
        "vertical_accuracy": loc.get("verticalAccuracy"),
        "altitude": loc.get("altitude"),
        "floor_level": loc.get("floorLevel"),
        "position_type": loc.get("positionType"),
        "is_inaccurate": loc.get("isInaccurate"),
        "is_old": loc.get("isOld"),
        "location_finished": loc.get("locationFinished"),
        "last_seen": record.last_seen_iso,
        "source_type": "gps",
        # identity
        "device_model": record.model,
        "raw_device_model": record.raw.get("rawDeviceModel"),
        "device_class": record.raw.get("deviceClass"),
        "serial_number": record.raw.get("serialNumber"),
        "emoji": record.emoji,          # items: user-assigned Find My emoji (🔑)
        "role_name": record.role_name,  # items: user-assigned role label ("Keys")
        # reverse-geocoded address
        "place_name": addr.get("mapItemFullAddress") or addr.get("label"),
        "street_address": addr.get("streetAddress"),
        "street_name": addr.get("streetName"),
        "thoroughfare": addr.get("fullThroroughfare"),
        "city": addr.get("locality"),
        "county": addr.get("subAdministrativeArea"),
        "state": addr.get("administrativeArea"),
        "state_code": addr.get("stateCode"),
        "country": addr.get("country"),
        "country_code": addr.get("countryCode"),
    })


@dataclass(frozen=True)
class SensorSpec:
    key: str
    name: str
    value: Callable[[Record], Any]
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    icon: str | None = None
    kinds: tuple = BOTH


# Battery is handled specially by entities.py (% for devices vs text for items);
# these are the remaining standalone diagnostic sensors.
SENSORS: list[SensorSpec] = [
    SensorSpec("last_seen", "Last Seen", lambda r: r.last_seen_iso,
               device_class="timestamp", icon="mdi:clock-outline"),
    SensorSpec("accuracy", "Accuracy", lambda r: r.location.get("horizontalAccuracy"),
               device_class="distance", unit="m", state_class="measurement", icon="mdi:crosshairs-gps"),
    SensorSpec("altitude", "Altitude", lambda r: r.location.get("altitude"),
               device_class="distance", unit="m", state_class="measurement", icon="mdi:altimeter"),
    SensorSpec("position_type", "Position Type", lambda r: r.location.get("positionType"),
               icon="mdi:map-marker-question"),
    SensorSpec("place", "Place", lambda r: (r.address.get("mapItemFullAddress") or r.address.get("label")),
               icon="mdi:map-marker"),
    SensorSpec("model", "Model", lambda r: r.model, icon="mdi:information-outline"),
    SensorSpec("emoji", "Emoji", lambda r: r.emoji, kinds=(ITEM,), icon="mdi:emoticon"),
    SensorSpec("role_name", "Role", lambda r: r.role_name, kinds=(ITEM,), icon="mdi:tag-text"),
    SensorSpec("battery_status", "Battery Status", lambda r: r.raw.get("batteryStatus"),
               kinds=(DEVICE,), icon="mdi:battery-charging"),
    SensorSpec("device_class", "Device Class", lambda r: r.raw.get("deviceClass"),
               kinds=(DEVICE,), icon="mdi:devices"),
    SensorSpec("serial_number", "Serial Number", lambda r: r.raw.get("serialNumber"),
               kinds=(ITEM,), icon="mdi:barcode"),
    SensorSpec("firmware", "Firmware", lambda r: r.raw.get("systemVersion"),
               kinds=(ITEM,), icon="mdi:chip"),
]


@dataclass(frozen=True)
class BinarySpec:
    key: str
    name: str
    value: Callable[[Record], Any]  # truthy → ON
    device_class: str | None = None
    icon: str | None = None
    kinds: tuple = BOTH


BINARY_SENSORS: list[BinarySpec] = [
    BinarySpec("low_power", "Low Power Mode", lambda r: r.raw.get("lowPowerMode"),
               kinds=(DEVICE,), icon="mdi:battery-alert"),
    BinarySpec("with_you", "With You", lambda r: r.raw.get("deviceWithYou"),
               kinds=(DEVICE,), icon="mdi:account-check"),
    BinarySpec("lost_mode", "Lost Mode", lambda r: r.raw.get("lostModeEnabled"),
               device_class="safety", kinds=(DEVICE,), icon="mdi:map-marker-alert"),
    BinarySpec("activation_locked", "Activation Locked", lambda r: r.raw.get("activationLocked"),
               device_class="lock", kinds=(DEVICE,), icon="mdi:lock"),
    BinarySpec("inaccurate", "Location Inaccurate", lambda r: r.location.get("isInaccurate"),
               icon="mdi:map-marker-question"),
    BinarySpec("stale", "Location Stale", lambda r: r.location.get("isOld"),
               icon="mdi:map-marker-off"),
]

# Raw keys already surfaced elsewhere (tracker attrs / dedicated entities) —
# excluded from the catch-all Details sensor to avoid pure duplication. The
# Details sensor carries EVERYTHING else so no field is lost.
_DETAILS_SKIP = {"location", "address", "crowdSourcedLocation", "name", "identifier", "id"}


def details_attributes(record: Record) -> dict[str, Any]:
    """All remaining raw fields (the long tail) as native HA attributes. Bytes
    values are hex-encoded so they serialize; nested dicts/lists pass through."""
    out: dict[str, Any] = {}
    for k, v in record.raw.items():
        if k in _DETAILS_SKIP:
            continue
        if isinstance(v, (bytes, bytearray)):
            out[k] = v.hex()
        else:
            out[k] = v
    return out
