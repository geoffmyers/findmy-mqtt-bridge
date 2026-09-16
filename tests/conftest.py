"""Shared fixtures — raw record shapes matching what the live 14.8 cache
decrypts to (field names and nesting are real; names/coordinates/addresses
are fictional)."""

import pytest


@pytest.fixture
def raw_item():
    return {
        "identifier": "11111111-1111-1111-1111-111111111111",
        "name": "Keys",
        "batteryStatus": 5,
        "productType": {"type": "b389", "productInformation": {"manufacturerName": "Apple"}},
        "role": {"name": "Keys", "emoji": "\U0001f511", "identifier": 7},
        "location": {
            "latitude": 40.0000,
            "longitude": -100.0000,
            "horizontalAccuracy": 12.33,
            "timeStamp": 1751800000000,
        },
        "address": {"label": "123 Main St, Example City, XX"},
        "serialNumber": "XYZ",
    }


@pytest.fixture
def raw_item_nofix():
    return {
        "identifier": "33333333-3333-3333-3333-333333333333",
        "name": "Car",
        "batteryStatus": 0,
        "location": None,
    }


@pytest.fixture
def raw_device():
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "deviceDisplayName": "iPhone 13 Pro Max",
        "name": "iPhone",
        "batteryLevel": 0.96,
        "batteryStatus": "Unknown",
        "deviceModel": "iPhone14,3",
        "rawDeviceModel": "iPhone14,3",
        "location": {
            "latitude": 40.0001,
            "longitude": -99.9999,
            "horizontalAccuracy": 5.0,
            "altitude": 250.0,
            "timeStamp": 1751800000000,
        },
        "address": {"streetAddress": "123 Main St", "locality": "Example City", "administrativeArea": "XX"},
    }
