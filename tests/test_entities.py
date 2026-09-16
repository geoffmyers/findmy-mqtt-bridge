from findmy_bridge.entities import (
    HUB_ID,
    build_discovery,
    build_state,
    hub_status_discovery,
    unique_id,
)
from findmy_bridge.normalize import DEVICE, ITEM, normalize

BASE = "findmy"
DEV_SLUG = "22222222_2222_2222_2222_222222222222"
ITEM_SLUG = "11111111_1111_1111_1111_111111111111"


def test_unique_id_is_uuid_derived(raw_item):
    assert unique_id(normalize(raw_item, ITEM)) == f"findmy_{ITEM_SLUG}"


def test_discovery_has_all_component_types(raw_device):
    ds = build_discovery(BASE, normalize(raw_device, DEVICE))
    uids = [d.unique_id for d in ds]
    comps = [d.component for d in ds]
    assert comps.count("device_tracker") == 1
    assert any(u.endswith("_battery") for u in uids)
    assert any(u.endswith("_details") for u in uids)
    assert any(u.endswith("_last_seen") for u in uids)
    assert any(u.endswith("_low_power") for u in uids)  # device-only binary
    assert "binary_sensor" in comps and "sensor" in comps


def test_tracker_is_gps_without_state_topic(raw_device):
    ds = build_discovery(BASE, normalize(raw_device, DEVICE))
    tracker = next(d for d in ds if d.component == "device_tracker")
    assert tracker.payload["source_type"] == "gps"
    assert "state_topic" not in tracker.payload  # HA resolves the zone from attrs
    assert tracker.payload["json_attributes_topic"] == f"{BASE}/{DEV_SLUG}/attrs"
    assert tracker.payload["device"]["via_device"] == HUB_ID


def test_item_omits_device_only_entities(raw_item):
    uids = [d.unique_id for d in build_discovery(BASE, normalize(raw_item, ITEM))]
    assert not any(u.endswith("_low_power") for u in uids)   # device-only
    assert any(u.endswith("_serial_number") for u in uids)   # item-only
    assert any(u.endswith("_firmware") for u in uids)


def test_item_has_emoji_sensor_device_does_not(raw_item, raw_device):
    item_uids = [d.unique_id for d in build_discovery(BASE, normalize(raw_item, ITEM))]
    dev_uids = [d.unique_id for d in build_discovery(BASE, normalize(raw_device, DEVICE))]
    assert any(u.endswith("_emoji") for u in item_uids)      # item-only
    assert any(u.endswith("_role_name") for u in item_uids)
    assert not any(u.endswith("_emoji") for u in dev_uids)


def test_item_emoji_in_state_and_tracker_attrs(raw_item):
    pubs = {p.topic: p.payload for p in build_state(BASE, normalize(raw_item, ITEM))}
    assert pubs[f"{BASE}/{ITEM_SLUG}/emoji"] == "\U0001f511"
    assert pubs[f"{BASE}/{ITEM_SLUG}/role_name"] == "Keys"
    attrs = pubs[f"{BASE}/{ITEM_SLUG}/attrs"]
    assert attrs["emoji"] == "\U0001f511"
    assert attrs["role_name"] == "Keys"


def test_device_tracker_attrs_omit_emoji(raw_device):
    pubs = {p.topic: p.payload for p in build_state(BASE, normalize(raw_device, DEVICE))}
    attrs = pubs[f"{BASE}/{DEV_SLUG}/attrs"]
    assert "emoji" not in attrs  # None → dropped by _clean


def test_state_tracker_attrs_have_gps_and_address(raw_device):
    pubs = {p.topic: p.payload for p in build_state(BASE, normalize(raw_device, DEVICE))}
    attrs = pubs[f"{BASE}/{DEV_SLUG}/attrs"]
    assert attrs["latitude"] == 40.0001
    assert attrs["gps_accuracy"] == 5.0
    assert attrs["city"] == "Example City"
    assert attrs["state"] == "XX"
    assert attrs["source_type"] == "gps"
    assert all("/state" not in t for t in pubs)  # no device_tracker state topic


def test_state_battery_and_sensors(raw_device, raw_item):
    dev = {p.topic: p.payload for p in build_state(BASE, normalize(raw_device, DEVICE))}
    assert dev[f"{BASE}/{DEV_SLUG}/battery"] == 96
    assert dev[f"{BASE}/{DEV_SLUG}/battery_status"] == "Unknown"
    assert dev[f"{BASE}/{DEV_SLUG}/accuracy"] == 5.0
    itm = {p.topic: p.payload for p in build_state(BASE, normalize(raw_item, ITEM))}
    assert itm[f"{BASE}/{ITEM_SLUG}/battery"] == "Full"


def test_details_sensor_carries_raw_longtail(raw_device):
    pubs = {p.topic: p.payload for p in build_state(BASE, normalize(raw_device, DEVICE))}
    details = pubs[f"{BASE}/{DEV_SLUG}/details"]
    assert isinstance(details, dict)
    assert details["batteryStatus"] == "Unknown"
    assert details["deviceModel"] == "iPhone14,3"
    assert "location" not in details and "address" not in details  # surfaced elsewhere


def test_binary_sensor_on_off():
    raw = {"id": "X", "deviceDisplayName": "d", "lowPowerMode": True, "location": {}}
    pubs = {p.topic: p.payload for p in build_state(BASE, normalize(raw, DEVICE))}
    assert pubs["findmy/x/low_power"] == "ON"


def test_hub_status_is_connectivity_binary_sensor():
    d = hub_status_discovery("findmy/bridge/availability")
    assert d.component == "binary_sensor"
    assert d.payload["device_class"] == "connectivity"
    assert d.payload["device"]["identifiers"] == [HUB_ID]
