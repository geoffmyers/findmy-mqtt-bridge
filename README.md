<p align="center">
  <img src="docs/icon.svg" width="96" height="96" alt="Find My MQTT Bridge icon">
</p>

# Find My MQTT Bridge

<!-- BADGES:START -->
![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776ab?style=flat-square&logo=python)
[![Licence GPL-3.0-or-later](https://img.shields.io/badge/licence-GPL--3.0--or--later-blue?style=flat-square)](LICENSE.md)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)
<!-- BADGES:END -->

## Table of Contents

- [Description](#description)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Home Assistant](#home-assistant)
- [Permissions and security](#permissions-and-security)
- [Architecture](#architecture)
- [Credits](#credits)
- [Contributing](#contributing)
- [License](#license)

## Description

Apple's Find My app already knows where every device and item on your Apple
ID is — it just keeps that to itself. This bridge runs on a Mac that is
signed in to your Apple ID, decrypts Find My's own on-disk location cache
(the same one the Find My app reads), and republishes every device and item
as a Home Assistant `device_tracker` over MQTT: your iPhone, your AirTags,
anything Find My tracks for you.

It is designed to run unattended on a dedicated, headless macOS VM (or a
spare real Mac) rather than the machine you use day to day — see
[Requirements](#requirements) for why, and [Permissions and security](#permissions-and-security)
for what that trade-off actually buys you.

## Features

- **Every device and item on your account**, not a curated subset: one Home
  Assistant device per thing, grouped under a shared "FindMy Proxy" hub
  device.
- **Native Home Assistant zone resolution.** The bridge publishes raw GPS
  coordinates as `device_tracker` attributes and lets Home Assistant decide
  `home` / `not_home` / a named zone — it never guesses that for you.
- **Nothing is dropped.** Every field Apple's Find My reports — battery,
  accuracy, position type, the user-assigned emoji and role name on an
  AirTag, model, serial number, firmware — becomes either a dedicated sensor
  or an attribute on a catch-all "Details" sensor, so a field Apple adds
  tomorrow is visible in Home Assistant today.
- **A visible health signal.** A `sensor.<hub>_cache_updated` entity exposes
  the moment Find My itself last fetched a location, so you can tell "the
  bridge is running" apart from "Find My has actually refreshed recently."
- **A keep-awake watcher** for running this unattended on a headless machine
  (see [Architecture](ARCHITECTURE.md#keeping-the-source-fresh-findmy-keepawake)) —
  Find My silently stops fetching after a while if left alone, and this
  detects and recovers from that.
- **Deduplicated, retained MQTT publishes** — discovery configs are sent once
  per entity and state is only republished when it actually changes, so a
  Home Assistant entity's "last changed" time means what it says.

## Requirements

- **A Mac (or macOS virtual machine) signed in to the Apple ID whose Find My
  data you want.** This reads your own account's cached data on a machine
  you control; it is not a way to locate anyone else's devices, and it only
  ever sees what the Find My app on that machine can already see.
- **macOS 14.4 through 14.8 (Sonoma).** Apple started encrypting the Find My
  cache in 14.4. This bridge has been validated on 14.8. **macOS 15 and
  later are not supported** — Apple moved the key behind additional
  protection there, and this project's decrypt path does not follow it.
- **SIP and AMFI disabled** on the machine that runs the bridge. Read
  [Permissions and security](#permissions-and-security) before you do this —
  it is a real trade-off, not a checkbox.
- **Python 3.9+**, `swiftc` and `codesign` (both ship with Xcode Command Line
  Tools) to build and ad-hoc-sign the key-extractor helper.
- An MQTT broker with Home Assistant's [MQTT integration](https://www.home-assistant.io/integrations/mqtt/)
  configured, and MQTT discovery enabled (the default).

## Installation

```bash
git clone https://github.com/geoffmyers/findmy-mqtt-bridge.git
cd findmy-mqtt-bridge

cp config.example.yaml config.yaml
$EDITOR config.yaml   # at minimum, set mqtt.host

printf 'MQTT_USERNAME=your-username\nMQTT_PASSWORD=your-password\n' > .env
chmod 600 .env

./install.sh
```

Run this **on the machine that will run the bridge** — the Mac or VM with
SIP/AMFI disabled and Find My signed in (see [Requirements](#requirements)).
`install.sh` creates a Python virtual environment, builds and ad-hoc-signs
the extractor helper, and installs two `launchd` LaunchAgents: the bridge
itself and a keep-awake watcher (see [Architecture](ARCHITECTURE.md)). Both
start automatically and restart on crash. `./install.sh --uninstall` stops
and removes them (your `config.yaml` and `.env` are left in place).

## Usage

Once installed, the bridge runs continuously as a background LaunchAgent —
there is nothing to keep in a terminal. A few commands are useful directly:

```bash
# One poll cycle, then exit — useful for testing a config change.
.venv/bin/findmy-mqtt-bridge --once -c config.yaml

# Remove every discovery config this bridge has published (deletes the
# entities from Home Assistant) and exit. Useful before a clean re-register.
.venv/bin/findmy-mqtt-bridge --clear -c config.yaml

# Watch the logs.
tail -f logs/bridge.out.log logs/keepawake.out.log
```

## Configuration

All configuration is one YAML file (`config.yaml`, gitignored — copy it from
`config.example.yaml`), with broker credentials pulled from environment
variables so they never sit in the file itself.

| Key | Default | Description |
|---|---|---|
| `mqtt.host` | *(required)* | Your MQTT broker hostname. |
| `mqtt.port` | `8883` | Broker port. |
| `mqtt.tls` | `true` | Use TLS. |
| `mqtt.username` / `mqtt.password` | *(from env)* | `${MQTT_USERNAME}` / `${MQTT_PASSWORD}`, resolved from the environment at load time. |
| `mqtt.base_topic` | `findmy` | Topic prefix for state/attribute topics. |
| `mqtt.discovery_prefix` | `homeassistant` | Home Assistant's MQTT discovery prefix. |
| `mqtt.client_id` | `findmy-bridge` | MQTT client ID; change it if two bridges share a broker. |
| `mqtt.ca_file` | *(system CAs)* | CA bundle for a broker with a private certificate. |
| `poll_interval_seconds` | `30` | How often to decrypt the cache and publish. |
| `cache_dir` | `~/Library/Caches/com.apple.findmy.fmipcore` | Where Find My keeps its encrypted cache. |
| `extractor_bin` | `~/findmy-mqtt-bridge/extractor/fmip_keydump` | Path to the built extractor binary (`install.sh` points it at your clone when it creates `config.yaml`). |
| `filters.exclude` | `[]` | UUIDs or display names to skip entirely. |
| `filters.name_overrides` | `{}` | `"<uuid>": "Friendly Name"` overrides. |
| `health_path` | `/tmp/findmy-bridge-healthy` | File whose modification time is refreshed on every publish, for an external liveness check. |
| `log_level` | `INFO` | Python log level. |
| `item_battery_labels` | *(built-in default)* | Override the AirTag `batteryStatus` int → label mapping; see `config.example.yaml`. |

## Home Assistant

Every tracked device and item becomes one Home Assistant device (via MQTT
discovery, so nothing needs configuring on the Home Assistant side beyond
having MQTT set up) under a shared **"FindMy Proxy"** hub device:

| Entity | Notes |
|---|---|
| `device_tracker` | GPS-based; Home Assistant resolves `home`/`not_home`/zone itself from the published coordinates. Attributes carry the reverse-geocoded address, accuracy, altitude, and (for AirTags) the user-assigned emoji and role name. |
| `sensor.*_battery` | Percent for devices, a text label for items (AirTags). |
| `sensor.*_last_seen`, `*_accuracy`, `*_altitude`, `*_position_type`, `*_place`, `*_model` | Both kinds. |
| `sensor.*_emoji`, `*_role_name`, `*_serial_number`, `*_firmware` | Items only. |
| `sensor.*_battery_status`, `*_device_class` | Devices only. |
| `binary_sensor.*_low_power`, `*_with_you`, `*_lost_mode`, `*_activation_locked` | Devices only. |
| `binary_sensor.*_inaccurate`, `*_stale` | Both kinds — flags a fix Apple itself considers unreliable or old. |
| `sensor.*_details` | Every remaining raw field as attributes — a catch-all so nothing Apple reports is ever silently dropped. |
| `binary_sensor.<hub>_bridge_online` | Hub connectivity (the bridge's own MQTT availability / LWT). |
| `sensor.<hub>_cache_updated` | When Find My itself last wrote a fresh fix to the cache — the health signal described in [Features](#features). |

## Permissions and security

Read this before you disable SIP on anything. **Disabling System Integrity
Protection and AMFI's entitlement validation is a full-machine change, not a
setting scoped to Find My** — it removes a real security boundary on the
whole system for as long as it's off, and it is what allows the small
ad-hoc-signed extractor binary in this project to read a keychain item that
Apple otherwise reserves for its own signed binaries (see
[Architecture → Why an external extractor process](ARCHITECTURE.md#why-an-external-extractor-process)
for the mechanics).

- **Run this on a machine dedicated to the purpose** — a virtual machine or a
  spare Mac, not your daily driver, and not one holding anything you would
  not want exposed if that machine were compromised.
- **The bridge only ever reads what the signed-in Find My app on that
  machine can already see:** the devices and items on the Apple ID it is
  signed in to. It has no path to any other account's data — there is no
  "look up someone else" feature to misuse, because the design has no
  concept of any account but the one Find My is already signed in to.
- **What actually leaves the machine** is exactly what gets published to
  your MQTT broker: coordinates, battery, and the other fields listed in
  [Home Assistant](#home-assistant). Nothing is sent anywhere else, and the
  extractor never prints the key material itself to a log — only a redacted
  length.
- **Broker credentials** are read from `${MQTT_USERNAME}`/`${MQTT_PASSWORD}`
  environment variables (`.env`, which `install.sh` `chmod 600`s and which
  is `.gitignore`d) — never hardcoded into `config.yaml`.
- Found a security problem with this project itself? See
  [CONTRIBUTING.md → Security](CONTRIBUTING.md#security).

## Architecture

The bridge is two pieces: a tiny ad-hoc-signed Swift helper that can read one
keychain item, and a pure-Python process that decrypts the cache with that
key, normalizes it, and publishes it over MQTT.

```
extractor (Swift, ad-hoc signed) ──► keychain item (base64)
        │
        ▼
decrypt.py (ChaCha20-Poly1305) ──► normalize.py ──► entities.py ──► MQTT
        ▲
        │
Find My's own encrypted cache on disk
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full pipeline, why an external
extractor process exists at all, and how the keep-awake watcher keeps the
source cache from going stale on a headless machine.

## Credits

- Built on `_shared/ha-mqtt-bridge-toolkit/` (vendored into this
  repository at publish time), a shared MQTT/Home Assistant helper library
  used across this author's home-automation bridges: MQTT discovery
  payload builders, topic slugging, and `${ENV_VAR}`-aware YAML config
  loading.
- Decryption uses the [`cryptography`](https://cryptography.io/) library's
  ChaCha20-Poly1305 implementation.
- MQTT via [`paho-mqtt`](https://eclipse.dev/paho/index.php?page=clients/python/index.php).
- The README icon is the [Font Awesome](https://fontawesome.com/) `location-dot`
  glyph, used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Apple, macOS, Find My and AirTag are trademarks of Apple Inc. This project
  is not affiliated with, endorsed by, or sponsored by Apple.

Written by Geoff Myers.

## Contributing

Bug reports and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md)
for setup, checks and how this repository is published.

## License

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See [LICENSE.md](LICENSE.md) for the full text of the GNU
General Public License.

SPDX-License-Identifier: `GPL-3.0-or-later`
