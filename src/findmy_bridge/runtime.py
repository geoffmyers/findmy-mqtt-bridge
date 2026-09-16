"""Poll loop: extract key → decrypt cache → normalize → publish to HA MQTT."""

from __future__ import annotations

import json
import logging
import os
import threading

from ha_mqtt_bridge.paho_publisher import ThreadedPublisher
from ha_mqtt_bridge.time_utils import epoch_to_iso
from ha_mqtt_bridge.topics import slugify

from .config import Config
from .decrypt import decrypt_records
from .entities import (
    build_discovery,
    build_state,
    hub_cache_discovery,
    hub_cache_topic,
    hub_status_discovery,
)
from .keyprovider import KeyExtractionError, KeyProvider
from .normalize import DEVICE, ITEM, Record, normalize

log = logging.getLogger(__name__)

SOURCES = [("Items.data", ITEM), ("Devices.data", DEVICE)]


class DecryptError(RuntimeError):
    pass


def collect(cache_path: str, key: bytes, item_labels: dict[int, str] | None) -> list[Record]:
    """Decrypt + normalize every source file. Raises ``DecryptError`` on a
    decrypt failure (a shared-key problem — caller should refresh the key)."""
    out: list[Record] = []
    for fname, kind in SOURCES:
        path = os.path.join(cache_path, fname)
        if not os.path.exists(path):
            continue
        try:
            raws = decrypt_records(path, key)
        except Exception as e:  # noqa: BLE001 — wrong key surfaces here (InvalidTag)
            raise DecryptError(f"decrypt {fname} failed: {type(e).__name__}: {e}") from e
        for raw in raws:
            rec = normalize(raw, kind, item_labels)
            if rec is not None:
                out.append(rec)
    return out


def apply_filters(records: list[Record], exclude: set[str], overrides: dict[str, str]) -> list[Record]:
    out: list[Record] = []
    for r in records:
        if r.uuid in exclude or r.name in exclude:
            continue
        if r.uuid in overrides:
            r.name = overrides[r.uuid]
        out.append(r)
    return out


class Bridge:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = cfg.mqtt.base_topic
        self.avail_topic = f"{self.base}/bridge/availability"
        self.keys = KeyProvider(cfg.extractor_path)
        self.pub = ThreadedPublisher(
            host=cfg.mqtt.host,
            port=cfg.mqtt.port,
            username=cfg.mqtt.username,
            password=cfg.mqtt.password,
            client_id=cfg.mqtt.client_id,
            tls=cfg.mqtt.tls,
            ca_file=cfg.mqtt.ca_file,
            lwt_topic=self.avail_topic,
            discovery_prefix=cfg.mqtt.discovery_prefix,
            health_path=cfg.health_path,
            retain_state=True,
        )
        self._known: set[str] = set()
        self._last: dict[str, str] = {}  # topic -> last published body (dedup)
        self._stop = threading.Event()

    # ---- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self.pub.start()
        if not self.pub.wait_until_connected(15.0):
            log.warning("MQTT not connected within 15s; will keep retrying in background")
        hub = hub_status_discovery(self.avail_topic)
        self.pub.publish_discovery(component=hub.component, unique_id=hub.unique_id, payload=hub.payload)
        cache = hub_cache_discovery(self.base)
        self.pub.publish_discovery(component=cache.component, unique_id=cache.unique_id, payload=cache.payload)
        self.pub.publish_raw(self.avail_topic, "online", qos=1, retain=True)

    def _publish_cache_mtime(self) -> None:
        """Publish the newest Find My cache-file mtime (when FindMy last fetched)."""
        newest = 0.0
        for fname, _ in SOURCES:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(self.cfg.cache_path, fname)))
            except OSError:
                pass
        if newest <= 0:
            return
        topic = hub_cache_topic(self.base)
        iso = epoch_to_iso(newest)
        if self._last.get(topic) != iso:
            self._last[topic] = iso
            self.pub.publish_state(topic, iso)

    def run(self) -> None:
        self.start()
        try:
            while not self._stop.is_set():
                try:
                    self.poll_once()
                except Exception:  # noqa: BLE001 — one bad poll must not kill the loop
                    log.exception("poll failed")
                self._stop.wait(self.cfg.poll_interval_seconds)
        finally:
            self.pub.stop()

    def stop(self) -> None:
        self._stop.set()

    def clear(self) -> None:
        """Remove every published discovery config (empty retained payload →
        HA deletes the entity), freeing entity_ids for a clean re-register."""
        prefix = self.cfg.mqtt.discovery_prefix
        try:
            key = self.keys.get()
            records = collect(self.cfg.cache_path, key, self.cfg.item_battery_labels)
        except (KeyExtractionError, DecryptError) as e:
            log.error("clear: could not read records: %s", e)
            records = []
        records = apply_filters(
            records, set(self.cfg.filters.exclude), self.cfg.filters.name_overrides
        )
        n = 0
        for r in records:
            for d in build_discovery(self.base, r):
                self.pub.publish_raw(f"{prefix}/{d.component}/{d.unique_id}/config", "", qos=1, retain=True)
                n += 1
            # Also wipe the legacy per-record state topic (pre-zone-resolution
            # builds published home/not_home here; clear stale retained values).
            self.pub.publish_raw(f"{self.base}/{slugify(r.uuid)}/state", "", qos=1, retain=True)
        hub = hub_status_discovery(self.avail_topic)
        self.pub.publish_raw(f"{prefix}/{hub.component}/{hub.unique_id}/config", "", qos=1, retain=True)
        self._known.clear()
        self._last.clear()
        log.info("cleared %d discovery configs (%d records)", n + 1, len(records))

    # ---- one cycle ----------------------------------------------------------
    def poll_once(self) -> None:
        try:
            key = self.keys.get()
        except KeyExtractionError as e:
            log.error("key extraction failed: %s", e)
            return
        try:
            records = collect(self.cfg.cache_path, key, self.cfg.item_battery_labels)
        except DecryptError as e:
            log.warning("%s — refreshing key and retrying", e)
            try:
                key = self.keys.get(force=True)
                records = collect(self.cfg.cache_path, key, self.cfg.item_battery_labels)
            except (KeyExtractionError, DecryptError) as e2:
                log.error("decrypt still failing after key refresh: %s", e2)
                return

        records = apply_filters(
            records, set(self.cfg.filters.exclude), self.cfg.filters.name_overrides
        )
        fixes = 0
        for r in records:
            if r.uuid not in self._known:
                for d in build_discovery(self.base, r):
                    self.pub.publish_discovery(
                        component=d.component, unique_id=d.unique_id, payload=d.payload
                    )
                self._known.add(r.uuid)
            for p in build_state(self.base, r):
                if isinstance(p.payload, dict):
                    body = json.dumps(p.payload, sort_keys=True, default=str)
                    if self._last.get(p.topic) == body:
                        continue
                    self._last[p.topic] = body
                    self.pub.publish_attributes(p.topic, p.payload)
                else:
                    s = str(p.payload)
                    if self._last.get(p.topic) == s:
                        continue
                    self._last[p.topic] = s
                    self.pub.publish_state(p.topic, s)
            if r.has_fix:
                fixes += 1
        self._publish_cache_mtime()
        log.info("published %d records (%d with a fix, %d known entities)",
                 len(records), fixes, len(self._known))
