#!/usr/bin/env bash
# install.sh — idempotent installer for findmy-mqtt-bridge.
#
# Run this ON the machine that will actually run the bridge: a macOS VM (or
# real Mac) that is signed in to Find My and has SIP + AMFI disabled (see
# README.md -> Requirements). It builds the Python venv, compiles and
# ad-hoc-signs the key-extractor helper, and installs the two LaunchAgents
# (the bridge itself, and a "keepawake" watcher that keeps Find My fetching
# on a headless machine).
#
#   ./install.sh              # install / update, then bootstrap the agents
#   ./install.sh --uninstall  # stop and remove the agents (leaves config.yaml
#                              # and .env in place)
set -euo pipefail

BRIDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_LABEL="com.example.findmy-bridge"
KEEPAWAKE_LABEL="com.example.findmy-keepawake"
BRIDGE_PLIST_DST="${HOME}/Library/LaunchAgents/${BRIDGE_LABEL}.plist"
KEEPAWAKE_PLIST_DST="${HOME}/Library/LaunchAgents/${KEEPAWAKE_LABEL}.plist"
CONFIG_FILE="${BRIDGE_DIR}/config.yaml"
ENV_FILE="${BRIDGE_DIR}/.env"

uninstall() {
    echo "uninstalling ${BRIDGE_LABEL} and ${KEEPAWAKE_LABEL}…"
    launchctl bootout "gui/$(id -u)" "${BRIDGE_PLIST_DST}" 2>/dev/null || true
    launchctl bootout "gui/$(id -u)" "${KEEPAWAKE_PLIST_DST}" 2>/dev/null || true
    rm -f "${BRIDGE_PLIST_DST}" "${KEEPAWAKE_PLIST_DST}"
    echo "removed ${BRIDGE_PLIST_DST} and ${KEEPAWAKE_PLIST_DST}"
    echo "(left ${CONFIG_FILE} and ${ENV_FILE} in place — delete manually if desired)"
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "missing: $1"; exit 1; }
}

main() {
    if [[ "${1:-}" == "--uninstall" ]]; then
        uninstall
        return 0
    fi

    require_cmd python3
    require_cmd swiftc
    require_cmd codesign

    if [[ ! -f "${CONFIG_FILE}" ]]; then
        echo "==> ${CONFIG_FILE} not found; copying from config.example.yaml"
        # The example assumes a clone at ~/findmy-mqtt-bridge; point it here.
        sed "s|~/findmy-mqtt-bridge/|${BRIDGE_DIR}/|g" \
            "${BRIDGE_DIR}/config.example.yaml" > "${CONFIG_FILE}"
        echo "==> EDIT ${CONFIG_FILE} (at least mqtt.host) and re-run install.sh"
        exit 0
    fi

    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "missing: ${ENV_FILE}"
        echo "create it with MQTT_USERNAME and MQTT_PASSWORD, e.g.:"
        echo "    printf 'MQTT_USERNAME=...\\nMQTT_PASSWORD=...\\n' > ${ENV_FILE}"
        echo "    chmod 600 ${ENV_FILE}"
        exit 1
    fi
    chmod 600 "${ENV_FILE}"

    echo "==> creating venv + installing dependencies"
    python3 -m venv "${BRIDGE_DIR}/.venv"
    "${BRIDGE_DIR}/.venv/bin/pip" install -q --upgrade pip
    if [[ -d "${BRIDGE_DIR}/_shared/ha-mqtt-bridge-toolkit" ]]; then
        # Published layout: the toolkit is vendored alongside this project.
        "${BRIDGE_DIR}/.venv/bin/pip" install -q -e "${BRIDGE_DIR}/_shared/ha-mqtt-bridge-toolkit[yaml]"
    fi
    "${BRIDGE_DIR}/.venv/bin/pip" install -q -e "${BRIDGE_DIR}[dev]"

    echo "==> building + ad-hoc-signing the key-extractor helper"
    (
        cd "${BRIDGE_DIR}/extractor" \
            && swiftc fmip_keydump.swift -o fmip_keydump \
            && codesign -f -s - --entitlements entitlements.plist fmip_keydump
    )

    echo "==> installing LaunchAgents to ${HOME}/Library/LaunchAgents"
    mkdir -p "${HOME}/Library/LaunchAgents" "${BRIDGE_DIR}/logs"
    sed "s|__BRIDGE_DIR__|${BRIDGE_DIR}|g" "${BRIDGE_DIR}/launchd/${BRIDGE_LABEL}.plist" > "${BRIDGE_PLIST_DST}"
    sed "s|__BRIDGE_DIR__|${BRIDGE_DIR}|g" "${BRIDGE_DIR}/launchd/${KEEPAWAKE_LABEL}.plist" > "${KEEPAWAKE_PLIST_DST}"
    chmod +x "${BRIDGE_DIR}/launchd/run-bridge.sh" "${BRIDGE_DIR}/launchd/findmy-keepawake.sh"

    echo "==> bootstrapping LaunchAgents"
    launchctl bootout "gui/$(id -u)" "${BRIDGE_PLIST_DST}" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "${BRIDGE_PLIST_DST}"
    launchctl kickstart -k "gui/$(id -u)/${BRIDGE_LABEL}"

    launchctl bootout "gui/$(id -u)" "${KEEPAWAKE_PLIST_DST}" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "${KEEPAWAKE_PLIST_DST}"
    launchctl kickstart -k "gui/$(id -u)/${KEEPAWAKE_LABEL}"

    echo
    echo "==> installed. logs at: ${BRIDGE_DIR}/logs/"
    echo "==> the Find My cache is only decryptable with SIP + AMFI disabled —"
    echo "    see README.md -> Requirements if you have not done that yet."
}

main "$@"
