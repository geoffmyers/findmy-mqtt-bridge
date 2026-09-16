# Architecture

## Overview

The bridge is two cooperating pieces that share nothing but the filesystem:

1. **The extractor** (`extractor/fmip_keydump.swift`) — a small, ad-hoc-signed
   Swift binary that reads one keychain item and prints its bytes.
2. **The bridge** (`src/findmy_bridge/`) — a pure-Python process that runs the
   extractor, decrypts the Find My cache with the key it returns, and
   publishes the result to MQTT with Home Assistant discovery.

```
                     ┌─────────────────────────────┐
                     │   extractor/fmip_keydump     │  ad-hoc signed,
                     │   (Swift, Security.framework)│  keychain-access-groups
                     └───────────────┬─────────────┘  entitlement
                                     │ stdout: "KEY service=FMIPDataManager
                                     │          len=NN DATA_B64=<base64 bplist>"
                                     ▼
  ~/Library/Caches/           keyprovider.KeyProvider
  com.apple.findmy.fmipcore/        │ caches the 32-byte symmetricKey
  {Items,Devices}.data              ▼
        │                    decrypt.decrypt_records()
        └───────────────────►  ChaCha20-Poly1305, AAD=None
                                     │ list[dict] (raw Apple record shape)
                                     ▼
                              normalize.normalize()
                                     │ Record (uuid, name, kind, raw + helpers)
                                     ▼
                    entities.build_discovery() / build_state()
                                     │ HA MQTT Discovery configs + state/attrs
                                     ▼
                          ha_mqtt_bridge.ThreadedPublisher
                                     │
                                     ▼
                              MQTT broker → Home Assistant
```

`runtime.Bridge` is the poll loop that wires these together: extract → decrypt
→ normalize → filter → publish, once per `poll_interval_seconds`, with a
key-refresh-and-retry if a decrypt fails (the key is expected to be stable
across reboots, so a decrypt failure almost always means the extractor read a
stale or wrong key blob, not that the cache is corrupt).

## Why an external extractor process

The FMIPDataManager key lives in the **data-protection keychain**, gated to
the access group `0000000000.com.apple.findmy` — an Apple-reserved group that
`SecItemCopyMatching` only grants to a process that either ships an Apple
entitlement (which nothing outside Apple can obtain) or runs with **AMFI
entitlement validation disabled**, so an ad-hoc self-signed binary can simply
*claim* the group in its own entitlements and macOS will believe it.

That is the whole reason this project exists as a separate compiled helper
instead of one Python `keyring` call: Python cannot embed a code-signing
entitlement, but a tiny Swift binary, ad-hoc-signed with the right
`entitlements.plist`, can. See [Requirements](README.md#requirements) for why
this also means SIP has to be off.

The bridge re-runs the extractor rather than caching the key to disk between
process restarts, on the theory that a compromise of the bridge's own storage
should not also compromise the key — the blast radius of a leaked key is "an
attacker can decrypt cached location history until the next key rotation",
not "an attacker has a standing credential."

## The decryption

`extractor/fmip_keydump.swift` prints one line per matching keychain item:

```
KEY service=FMIPDataManager len=171 DATA_B64=<base64>
```

`keyprovider.KeyProvider` runs the binary, parses that line, base64-decodes
it, and hands the blob to `decrypt.symmetric_key()`, which unwraps Apple's
bplist framing to get the raw 32-byte ChaCha20-Poly1305 key. Each cache file
(`Items.data`, `Devices.data`, …) is itself a bplist
`{signature, encryptedData}`, where `encryptedData` is
`nonce(12) ‖ ciphertext ‖ tag(16)` with **no additional authenticated data**.
`decrypt.decrypt_records()` does the ChaCha20-Poly1305 open and
`plistlib.loads()`s the plaintext, which is a list of Apple's own record
dicts — unmodified, so every field FindMy reports survives.

## Normalization: keep everything, compute a few conveniences

`normalize.Record` wraps a raw dict without discarding anything:

- `raw` is the untouched Apple record.
- `location`, `address`, `role` are safe accessors (empty dict if the raw
  field is missing or the wrong type) instead of `KeyError`-prone lookups.
- `has_fix`, `last_seen_iso`, `emoji`, `role_name`, `model` are small computed
  properties used by more than one entity.
- `battery_percent` (devices, 0–100 int from a 0.0–1.0 float) and
  `battery_text` (items, from `battery.item_battery_text` — Apple's
  `batteryStatus` int enum is undocumented, so the mapping is a best-effort
  default overridable via `item_battery_labels` in config) are computed once
  in `normalize()` rather than in every consumer.

Devices and items use different raw field names for the same concepts
(`id` vs `identifier`, `deviceDisplayName` vs `name`, `batteryLevel` float vs
`batteryStatus` int) — `normalize()` is the one place that branches on `kind`
to reconcile them into the same `Record` shape.

## From `Record` to Home Assistant entities

`fields.py` is a declarative table, not a big `if/elif`: each `SensorSpec` /
`BinarySpec` is `(key, name, value_fn, device_class, unit, icon, kinds)`, and
`entities.py` walks the table to build one HA discovery config per applicable
entry (`kinds=(ITEM,)` / `(DEVICE,)` / both skips entities that don't apply to
a given record kind, e.g. `low_power` only exists for devices).

One HA **device** is created per tracked item/device, all sharing a
`via_device` pointing at a synthetic **"FindMy Proxy (macOS VM)"** hub device
— the natural Home Assistant grouping for "things this integration knows
about." Per tracked thing:

- **`device_tracker`** (`source_type: gps`) — carries GPS + the
  reverse-geocoded address + identity fields as `json_attributes_topic`
  attributes, and **deliberately has no `state_topic`**. Home Assistant
  resolves `home` / `not_home` / a named zone from the `latitude`/`longitude`
  attributes on its own; publishing a computed state string here would
  *override* that resolution and can desync from the zone HA actually thinks
  you're in (an early build did this and always showed "home").
- A **Battery** sensor (`%` for devices, the text label for items), plus
  whichever of `SENSORS` / `BINARY_SENSORS` apply to that kind.
- A **Details** sensor whose attributes are every raw field *not* already
  surfaced elsewhere (`fields.details_attributes()`, which explicitly skips
  `location`/`address`/`name`/`identifier`/`id` to avoid duplication) — so a
  field Apple adds tomorrow shows up in Home Assistant today, in the Details
  sensor, even though nobody wrote a dedicated sensor for it yet.

`runtime.Bridge.poll_once()` diffs against `self._known` (already-published
unique IDs) and `self._last` (last-published body per topic) so discovery
configs are only (re)published once per entity and unchanged state is never
re-sent — Home Assistant's `last_updated` for an entity then genuinely tracks
"when did FindMy report something new," not "when did the bridge poll."

## Filters

`config.yaml`'s `filters.exclude` (a list of UUIDs or display names) and
`filters.name_overrides` (`{uuid: "Friendly Name"}`) are applied once, right
after normalization and before anything is published — so an excluded item
never gets an HA device at all, rather than being published and then hidden.

## Keeping the source fresh: `findmy-keepawake`

None of the above works if the on-disk cache the extractor reads never gets
new data. `FindMy.app` **wedges** — stops fetching updates entirely — after
running unattended for a while, especially headless, and neither `open -a`
nor `osascript quit` can revive a wedged instance (the latter hangs on a
headless display). `launchd/findmy-keepawake.sh` is a small watcher LaunchAgent
that:

1. Keeps the machine awake (`caffeinate -dis`) and makes sure FindMy is
   running at all.
2. Watches the newest mtime across the cache files. If that age exceeds
   `STALE_AFTER` (default 60s) — meaning FindMy has stopped fetching even
   though it's still "running" — it hard-kills (`pkill -9`) and relaunches
   FindMy.

Staleness-based relaunching, rather than a blind timer, means a healthy
FindMy is left alone (few relaunches, no stolen window focus if you're
connected over screen sharing) and a wedge self-heals within one check
interval. The bridge exposes the newest cache mtime as its own sensor
(`sensor.<hub>_cache_updated`) so you can watch this end to end.

## Layout

| Path | Role |
|---|---|
| `extractor/fmip_keydump.swift` | Ad-hoc-signed helper: reads the `FMIPDataManager` keychain item, prints it as base64. |
| `extractor/entitlements.plist` | The one entitlement (`keychain-access-groups: 0000000000.com.apple.findmy`) that makes the above possible with AMFI off. |
| `src/findmy_bridge/keyprovider.py` | Runs the extractor, parses its output, caches the 32-byte key. |
| `src/findmy_bridge/decrypt.py` | ChaCha20-Poly1305 decrypt of one cache file → list of raw record dicts. |
| `src/findmy_bridge/normalize.py` | Raw dict → `Record`, reconciling item/device field-name differences. |
| `src/findmy_bridge/battery.py` | The two battery encodings (device float, item int enum) → a common shape. |
| `src/findmy_bridge/fields.py` | Declarative field → HA sensor/binary_sensor tables + the tracker/Details attribute builders. |
| `src/findmy_bridge/entities.py` | `Record` → HA MQTT discovery configs and state/attribute publishes. |
| `src/findmy_bridge/runtime.py` | `Bridge`: the poll loop, publish-dedup, and `--clear`. |
| `src/findmy_bridge/config.py` | YAML config loading with `${ENV_VAR}` substitution. |
| `src/findmy_bridge/cli.py` | `findmy-mqtt-bridge` entry point (`run` / `--once` / `--clear`). |
| `launchd/run-bridge.sh`, `launchd/findmy-keepawake.sh` | The two LaunchAgent program scripts. |
| `install.sh` | Idempotent installer: venv, build+sign the extractor, install both LaunchAgents. |
| `scripts/` | Diagnostics used while building this (recon, SIP/AMFI precheck, schema dump, cache-refresh experiments) — none of them run as part of normal operation. |

## Dependencies

- `_shared/ha-mqtt-bridge-toolkit/` (vendored into this repository at
  publish time) — the MQTT publisher, HA discovery payload builders, topic
  slugging, and `${ENV_VAR}`-aware YAML config loading shared with this
  project's sibling bridges. See [Credits](README.md#credits).
- `cryptography` — ChaCha20-Poly1305.
- `paho-mqtt` — the MQTT client underneath `ha_mqtt_bridge.ThreadedPublisher`.
