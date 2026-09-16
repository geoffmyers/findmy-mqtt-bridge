"""Map a normalized ``Record`` to HA MQTT discovery + state/attribute payloads.

One HA *device* per tracked thing (``via_device`` a shared "FindMy Proxy" hub):
  * device_tracker (source_type gps, no state_topic — HA resolves the zone from
    the GPS attributes) carrying location + address + identity attributes
  * a Battery sensor + the diagnostic sensors/binary_sensors in ``fields``
  * a "Details" sensor whose attributes carry the full raw long-tail

Pure functions; the runtime does the publishing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ha_mqtt_bridge.discovery import build_device_block, build_discovery_payload
from ha_mqtt_bridge.topics import slugify

from .fields import (
    BINARY_SENSORS,
    SENSORS,
    details_attributes,
    tracker_attributes,
)
from .normalize import DEVICE, ITEM, Record

HUB_ID = "findmy_proxy_macos_vm"
HUB_NAME = "FindMy Proxy (macOS VM)"


@dataclass
class Discovery:
    component: str
    unique_id: str
    payload: dict


@dataclass
class Publish:
    """A state/attribute update. ``dict`` payload → JSON attributes topic;
    other payloads → plain state topic."""

    topic: str
    payload: object


def unique_id(record: Record) -> str:
    return f"findmy_{slugify(record.uuid)}"


def _base(base: str, record: Record) -> str:
    return f"{base}/{slugify(record.uuid)}"


def _hub_device() -> dict:
    return build_device_block(
        identifiers=[HUB_ID], name=HUB_NAME, manufacturer="Apple", model="Find My"
    )


def _thing_device(record: Record) -> dict:
    return build_device_block(
        identifiers=[unique_id(record)], name=record.name,
        manufacturer="Apple", model=record.model, via_device=HUB_ID,
    )


def _icon(record: Record) -> str:
    return "mdi:tag" if record.kind == ITEM else "mdi:cellphone-marker"


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def build_discovery(base: str, record: Record) -> list[Discovery]:
    b = _base(base, record)
    device = _thing_device(record)
    uid = unique_id(record)
    out: list[Discovery] = []

    # device_tracker — NO state_topic (HA resolves the zone from the GPS attrs).
    out.append(Discovery("device_tracker", uid, {
        "unique_id": uid, "has_entity_name": True, "name": None,
        "json_attributes_topic": f"{b}/attrs", "source_type": "gps",
        "icon": _icon(record), "device": device,
    }))

    # Battery — % for devices, text for items.
    if record.kind == DEVICE:
        batt = build_discovery_payload(
            name="Battery", unique_id=f"{uid}_battery", has_entity_name=True,
            state_topic=f"{b}/battery", device=device, component="sensor",
            device_class="battery", unit_of_measurement="%", state_class="measurement",
            entity_category="diagnostic")
    else:
        batt = build_discovery_payload(
            name="Battery", unique_id=f"{uid}_battery", has_entity_name=True,
            state_topic=f"{b}/battery", device=device, component="sensor",
            icon="mdi:battery", entity_category="diagnostic")
    out.append(Discovery("sensor", f"{uid}_battery", batt))

    for s in SENSORS:
        if record.kind not in s.kinds:
            continue
        out.append(Discovery("sensor", f"{uid}_{s.key}", build_discovery_payload(
            name=s.name, unique_id=f"{uid}_{s.key}", has_entity_name=True,
            state_topic=f"{b}/{s.key}", device=device, component="sensor",
            device_class=s.device_class, unit_of_measurement=s.unit,
            state_class=s.state_class, icon=s.icon, entity_category="diagnostic")))

    for bs in BINARY_SENSORS:
        if record.kind not in bs.kinds:
            continue
        out.append(Discovery("binary_sensor", f"{uid}_{bs.key}", build_discovery_payload(
            name=bs.name, unique_id=f"{uid}_{bs.key}", has_entity_name=True,
            state_topic=f"{b}/{bs.key}", device=device, component="binary_sensor",
            device_class=bs.device_class, icon=bs.icon, entity_category="diagnostic",
            payload_on="ON", payload_off="OFF")))

    # Details — full raw long-tail as attributes (nothing dropped).
    out.append(Discovery("sensor", f"{uid}_details", build_discovery_payload(
        name="Details", unique_id=f"{uid}_details", has_entity_name=True,
        state_topic=f"{b}/details_state", json_attributes_topic=f"{b}/details",
        device=device, component="sensor", icon="mdi:information-outline",
        entity_category="diagnostic")))
    return out


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def build_state(base: str, record: Record) -> list[Publish]:
    b = _base(base, record)
    out: list[Publish] = []

    if record.has_fix:
        out.append(Publish(f"{b}/attrs", tracker_attributes(record)))

    # battery
    if record.battery_percent is not None:
        out.append(Publish(f"{b}/battery", record.battery_percent))
    elif record.battery_text is not None:
        out.append(Publish(f"{b}/battery", record.battery_text))

    for s in SENSORS:
        if record.kind not in s.kinds:
            continue
        v = s.value(record)
        if v is not None:
            out.append(Publish(f"{b}/{s.key}", v))

    for bs in BINARY_SENSORS:
        if record.kind not in bs.kinds:
            continue
        v = bs.value(record)
        if v is not None:
            out.append(Publish(f"{b}/{bs.key}", "ON" if v else "OFF"))

    out.append(Publish(f"{b}/details_state", record.kind))
    out.append(Publish(f"{b}/details", details_attributes(record)))
    return out


def hub_status_discovery(availability_topic: str) -> Discovery:
    """A ``connectivity`` binary_sensor on the hub device reflecting the bridge
    LWT; also materializes the parent hub device."""
    uid = f"{HUB_ID}_status"
    return Discovery("binary_sensor", uid, {
        "name": "Bridge Online", "unique_id": uid, "object_id": "findmy_bridge_online",
        "state_topic": availability_topic, "device_class": "connectivity",
        "payload_on": "online", "payload_off": "offline",
        "entity_category": "diagnostic", "device": _hub_device(),
    })


def hub_cache_topic(base: str) -> str:
    return f"{base}/bridge/cache_updated"


def hub_cache_discovery(base: str) -> Discovery:
    """A timestamp sensor on the hub device showing when the Find My cache files
    were last written — i.e. the last time FindMy actually fetched fresh data
    (distinct from any individual item's ``last_seen``). Surfaces the health of
    the keep-fresh mechanism (the staleness-based FindMy relaunch keepawake)."""
    uid = f"{HUB_ID}_cache_updated"
    return Discovery("sensor", uid, build_discovery_payload(
        name="Cache Updated", unique_id=uid, has_entity_name=True,
        object_id="findmy_cache_updated", state_topic=hub_cache_topic(base),
        device=_hub_device(), component="sensor", device_class="timestamp",
        icon="mdi:database-clock", entity_category="diagnostic"))
