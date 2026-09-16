"""Config loading for the Find My bridge (declarative YAML + ${ENV} substitution)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ha_mqtt_bridge.config_helpers import load_yaml_with_env


@dataclass
class MqttConfig:
    host: str
    port: int = 8883
    tls: bool = True
    username: str | None = None
    password: str | None = None
    base_topic: str = "findmy"
    discovery_prefix: str = "homeassistant"
    client_id: str = "findmy-bridge"
    ca_file: str | None = None


@dataclass
class Filters:
    exclude: list[str] = field(default_factory=list)  # UUIDs or names to skip
    name_overrides: dict[str, str] = field(default_factory=dict)  # uuid -> display name


@dataclass
class Config:
    mqtt: MqttConfig
    filters: Filters = field(default_factory=Filters)
    poll_interval_seconds: int = 30
    cache_dir: str = "~/Library/Caches/com.apple.findmy.fmipcore"
    extractor_bin: str = "~/findmy-mqtt-bridge/extractor/fmip_keydump"
    health_path: str | None = "/tmp/findmy-bridge-healthy"
    log_level: str = "INFO"
    item_battery_labels: dict[int, str] | None = None

    @property
    def cache_path(self) -> str:
        return os.path.expanduser(self.cache_dir)

    @property
    def extractor_path(self) -> str:
        return os.path.expanduser(self.extractor_bin)


def load(path: str | Path) -> Config:
    raw = load_yaml_with_env(path) or {}
    mqtt_raw = raw.get("mqtt") or {}
    if "host" not in mqtt_raw:
        raise ValueError("config.mqtt.host is required")
    filt_raw = raw.get("filters") or {}
    labels_raw = raw.get("item_battery_labels")
    labels = {int(k): str(v) for k, v in labels_raw.items()} if labels_raw else None
    return Config(
        mqtt=MqttConfig(**mqtt_raw),
        filters=Filters(
            exclude=list(filt_raw.get("exclude") or []),
            name_overrides=dict(filt_raw.get("name_overrides") or {}),
        ),
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 30)),
        cache_dir=raw.get("cache_dir", Config.cache_dir),
        extractor_bin=raw.get("extractor_bin", Config.extractor_bin),
        health_path=raw.get("health_path", Config.health_path),
        log_level=raw.get("log_level", "INFO"),
        item_battery_labels=labels,
    )
