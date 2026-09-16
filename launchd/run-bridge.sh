#!/bin/bash
# LaunchAgent wrapper: source the (secret) .env, then exec the bridge. Kept
# separate from the plist so broker credentials never live in the plist.
set -a
DIR="$(cd "$(dirname "$0")/.." && pwd)"   # the project: this script is in launchd/
[ -f "$DIR/.env" ] && . "$DIR/.env"
set +a
cd "$DIR" || exit 1
exec "$DIR/.venv/bin/findmy-mqtt-bridge" -c "$DIR/config.yaml"
