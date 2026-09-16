"""Apple Find My → Home Assistant MQTT bridge.

Runs on the macOS VM (SIP+AMFI disabled). Every poll it runs the signed
extractor to obtain the FMIPDataManager key, decrypts the Find My cache
(ChaCha20-Poly1305), normalizes each device/item, and publishes an HA MQTT
device_tracker (+ battery / last-seen sensors) via the shared bridge toolkit.
See ARCHITECTURE.md for the design.
"""

__version__ = "0.1.0"
