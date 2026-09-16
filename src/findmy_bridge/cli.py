"""CLI entry point for the Find My → HA MQTT bridge."""

from __future__ import annotations

import argparse
import os
import signal
import time

from ha_mqtt_bridge.app_helpers import configure_logging

from .config import load
from .runtime import Bridge


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="findmy-mqtt-bridge")
    ap.add_argument(
        "-c", "--config",
        default=os.environ.get("FINDMY_CONFIG", "config.yaml"),
        help="path to config.yaml (default: $FINDMY_CONFIG or ./config.yaml)",
    )
    ap.add_argument("--once", action="store_true", help="run a single poll and exit")
    ap.add_argument("--clear", action="store_true",
                    help="remove all published discovery configs (entities) and exit")
    args = ap.parse_args(argv)

    cfg = load(args.config)
    log = configure_logging("findmy-mqtt-bridge", cfg.log_level)
    log.info("starting findmy-mqtt-bridge (cache=%s broker=%s:%d)",
             cfg.cache_path, cfg.mqtt.host, cfg.mqtt.port)

    bridge = Bridge(cfg)

    if args.clear:
        bridge.pub.start()
        bridge.pub.wait_until_connected(15.0)
        bridge.clear()
        time.sleep(float(os.environ.get("FINDMY_ONCE_DRAIN", "4")))
        bridge.pub.stop()
        return 0

    if args.once:
        bridge.start()
        bridge.poll_once()
        # Let paho's network thread flush the queued QoS-1 discovery/state
        # messages before we disconnect (otherwise --once drops most of them).
        time.sleep(float(os.environ.get("FINDMY_ONCE_DRAIN", "4")))
        bridge.pub.stop()
        return 0

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: bridge.stop())
    bridge.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
