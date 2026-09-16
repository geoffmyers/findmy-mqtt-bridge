"""Normalize raw decrypted Find My records into a single ``Record`` type that
keeps the full raw payload around (so every field can be surfaced) plus a few
computed conveniences. Pure functions; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ha_mqtt_bridge.time_utils import epoch_ms_to_iso

from .battery import device_battery_percent, item_battery_text

ITEM = "item"
DEVICE = "device"


@dataclass
class Record:
    uuid: str
    name: str
    kind: str  # ITEM | DEVICE
    raw: dict = field(default_factory=dict)
    battery_percent: int | None = None
    battery_text: str | None = None

    # ---- location / address sub-objects (always dicts) ----
    @property
    def location(self) -> dict:
        d = self.raw.get("location")
        return d if isinstance(d, dict) else {}

    @property
    def address(self) -> dict:
        d = self.raw.get("address")
        return d if isinstance(d, dict) else {}

    @property
    def has_fix(self) -> bool:
        return self.location.get("latitude") is not None

    @property
    def last_seen_iso(self) -> str | None:
        return epoch_ms_to_iso(self.location.get("timeStamp")) or None

    @property
    def role(self) -> dict:
        d = self.raw.get("role")
        return d if isinstance(d, dict) else {}

    @property
    def emoji(self) -> str | None:
        """The user-assigned Find My emoji (items only; e.g. 🔑 for a Keys role)."""
        e = self.role.get("emoji")
        return e if isinstance(e, str) and e else None

    @property
    def role_name(self) -> str | None:
        """The user-assigned Find My role label (items only; e.g. "Keys")."""
        n = self.role.get("name")
        return n if isinstance(n, str) and n else None

    @property
    def model(self) -> str | None:
        if self.kind == ITEM:
            pt = self.raw.get("productType")
            if isinstance(pt, dict) and isinstance(pt.get("type"), str):
                return pt["type"]
            return self.role_name
        return (
            self.raw.get("deviceModel")
            or self.raw.get("rawDeviceModel")
            or self.raw.get("modelDisplayName")
        )


def normalize(raw: dict, kind: str, item_battery_labels: dict[int, str] | None = None) -> Record | None:
    """Convert one raw record dict to a ``Record``. Returns ``None`` if the
    record has no stable identifier."""
    if not isinstance(raw, dict):
        return None
    uuid = raw.get("identifier") if kind == ITEM else (raw.get("id") or raw.get("baUUID"))
    if not isinstance(uuid, str) or not uuid:
        return None
    name = raw.get("name") if kind == ITEM else (raw.get("deviceDisplayName") or raw.get("name"))
    name = name if isinstance(name, str) and name.strip() else uuid

    if kind == DEVICE:
        battery_percent = device_battery_percent(raw.get("batteryLevel"))
        bs = raw.get("batteryStatus")
        battery_text = bs if isinstance(bs, str) and bs else None
    else:
        battery_percent = None
        battery_text = item_battery_text(raw.get("batteryStatus"), item_battery_labels)

    return Record(
        uuid=uuid, name=name, kind=kind, raw=raw,
        battery_percent=battery_percent, battery_text=battery_text,
    )
