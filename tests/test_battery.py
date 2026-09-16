from findmy_bridge.battery import device_battery_percent, item_battery_text


def test_device_percent_maps_float_to_int():
    assert device_battery_percent(0.96) == 96
    assert device_battery_percent(1.0) == 100
    assert device_battery_percent(0.0) == 0


def test_device_percent_rejects_bad_values():
    assert device_battery_percent(None) is None
    assert device_battery_percent(1.5) is None
    assert device_battery_percent(-0.1) is None
    assert device_battery_percent("0.5") is None
    assert device_battery_percent(True) is None  # bool is not a battery level


def test_item_status_maps_known_enum():
    assert item_battery_text(5) == "Full"
    assert item_battery_text(4) == "Good"
    assert item_battery_text(0) == "Unknown"


def test_item_status_passes_through_unknown_int_and_rejects_nonint():
    assert item_battery_text(99) == "99"
    assert item_battery_text("x") is None
    assert item_battery_text(None) is None
    assert item_battery_text(True) is None


def test_item_status_respects_custom_labels():
    assert item_battery_text(5, {5: "Charged"}) == "Charged"
