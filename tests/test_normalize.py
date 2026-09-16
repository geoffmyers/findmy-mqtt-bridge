from findmy_bridge.normalize import DEVICE, ITEM, normalize


def test_normalize_item(raw_item):
    r = normalize(raw_item, ITEM)
    assert r is not None
    assert r.uuid == "11111111-1111-1111-1111-111111111111"
    assert r.name == "Keys"
    assert r.kind == ITEM
    assert r.has_fix is True
    assert r.location["latitude"] == 40.0000
    assert r.location["horizontalAccuracy"] == 12.33
    assert r.battery_text == "Full"
    assert r.battery_percent is None
    assert r.model == "b389"  # productType.type
    assert r.last_seen_iso and r.last_seen_iso.endswith("Z")
    assert r.raw is raw_item  # full payload retained for the Details sensor


def test_normalize_item_falls_back_to_role_name_for_model():
    raw = {"identifier": "U", "name": "n", "role": {"name": "Wallet"}, "location": {}}
    assert normalize(raw, ITEM).model == "Wallet"


def test_normalize_item_exposes_emoji_and_role_name(raw_item):
    r = normalize(raw_item, ITEM)
    assert r.emoji == "\U0001f511"  # 🔑
    assert r.role_name == "Keys"


def test_normalize_item_without_role_has_no_emoji():
    r = normalize({"identifier": "U", "name": "n", "location": {}}, ITEM)
    assert r.emoji is None
    assert r.role_name is None


def test_normalize_device_has_no_emoji(raw_device):
    r = normalize(raw_device, DEVICE)
    assert r.emoji is None
    assert r.role_name is None


def test_normalize_device(raw_device):
    r = normalize(raw_device, DEVICE)
    assert r.uuid == "22222222-2222-2222-2222-222222222222"
    assert r.name == "iPhone 13 Pro Max"
    assert r.kind == DEVICE
    assert r.battery_percent == 96
    assert r.battery_text == "Unknown"  # device batteryStatus string
    assert r.model == "iPhone14,3"
    assert r.address["locality"] == "Example City"


def test_normalize_nofix_item(raw_item_nofix):
    r = normalize(raw_item_nofix, ITEM)
    assert r is not None
    assert r.has_fix is False
    assert r.battery_text == "Unknown"  # batteryStatus 0


def test_normalize_without_identifier_returns_none():
    assert normalize({"name": "x", "location": {}}, ITEM) is None
    assert normalize({"deviceDisplayName": "x"}, DEVICE) is None


def test_normalize_name_falls_back_to_uuid():
    assert normalize({"identifier": "ABC", "location": {}}, ITEM).name == "ABC"
