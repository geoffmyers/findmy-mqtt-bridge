#!/bin/bash
# Build + ad-hoc-sign the entitled extractor, read the FMIPDataManager key, and
# decrypt the Find My cache. Requires SIP disabled + AMFI off (custom OpenCore).
# Runs ON the macOS guest, in its own directory (the transferred extractor/).
set +e
cd "$(dirname "$0")" || exit 1
D="$HOME/Library/Caches/com.apple.findmy.fmipcore"
VENV="$HOME/.findmy-proof-venv"

if [ ! -x "$VENV/bin/python3" ]; then
  /usr/bin/python3 -m venv "$VENV" 2>&1 | tail -1
  "$VENV/bin/pip" install -q --disable-pip-version-check cryptography 2>&1 | tail -1
fi
PY="$VENV/bin/python3"

echo "== build + ad-hoc-sign entitled extractor =="
swiftc fmip_keydump.swift -o fmip_keydump 2>&1 || { echo "swiftc FAILED"; exit 1; }
codesign -f -s - --entitlements entitlements.plist fmip_keydump 2>&1 && echo "codesign: ok" || echo "codesign: FAILED"
codesign -d --entitlements :- fmip_keydump 2>/dev/null | grep -iE "keychain-access" >/dev/null && echo "entitlements: embedded"

echo; echo "== run extractor (key blobs redacted in this log) =="
OUT=$(./fmip_keydump 2>&1)
printf '%s\n' "$OUT" | while IFS= read -r line; do
  case "$line" in
    *DATA_B64=*) pre=${line%%DATA_B64=*}; blob=${line#*DATA_B64=}; echo "${pre}DATA_B64=[${#blob} chars]";;
    *) echo "$line";;
  esac
done

# Use the FMIPDataManager key for the device/item caches.
KEYB64=$(printf '%s\n' "$OUT" | awk '/service=FMIPDataManager/ && /DATA_B64=/ {sub(/.*DATA_B64=/,""); print; exit}')
echo; echo "== decrypt Find My cache =="
if [ -n "$KEYB64" ]; then
  FINDMY_FMIP_KEY_B64="$KEYB64" FINDMY_DUMP_SCHEMA="${FINDMY_DUMP_SCHEMA:-}" "$PY" decrypt_cache.py "$D"
else
  echo "NO FMIPDataManager key blob found — inspect the KEY service=… status lines above."
fi
echo "== DONE =="
