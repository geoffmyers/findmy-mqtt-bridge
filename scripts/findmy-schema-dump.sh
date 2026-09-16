#!/bin/bash
# Dump the full field inventory of one FindMy item + one device (all top-level
# keys + the location/address sub-dicts), redacting precise coordinates. Uses
# the already-deployed extractor binary + venv. Runs ON the guest.
set +e
DIR="$HOME/findmy-mqtt-bridge"
export FINDMY_DIR="$HOME/Library/Caches/com.apple.findmy.fmipcore"
KEYB64=$("$DIR/extractor/fmip_keydump" 2>/dev/null | awk '/service=FMIPDataManager/ && /DATA_B64=/{sub(/.*DATA_B64=/,"");print;exit}')
[ -z "$KEYB64" ] && { echo "no FMIPDataManager key"; exit 1; }
export FINDMY_FMIP_KEY_B64="$KEYB64"

"$DIR/.venv/bin/python3" - <<'PY'
import os, base64
from findmy_bridge.decrypt import symmetric_key, decrypt_records
D = os.environ["FINDMY_DIR"]
sk = symmetric_key(base64.b64decode(os.environ["FINDMY_FMIP_KEY_B64"]))

def dec(fn):
    return decrypt_records(os.path.join(D, fn), sk)

def red(k, v):
    if k in ("latitude", "longitude") and isinstance(v, (int, float)):
        return round(float(v), 1)
    if isinstance(v, dict):
        return "{dict: " + ", ".join(sorted(v.keys())) + "}"
    if isinstance(v, (bytes, bytearray)):
        return "<%d bytes>" % len(v)
    if isinstance(v, list):
        return "[list x%d]" % len(v)
    return v

def dump(rec, label):
    print("\n==== %s: %r ====" % (label, rec.get("name") or rec.get("deviceDisplayName")))
    for k in sorted(rec.keys()):
        print("  %-26s = %r" % (k, red(k, rec[k])))
    for sub in ("location", "address"):
        d = rec.get(sub)
        if isinstance(d, dict):
            print("  -- %s --" % sub)
            for k in sorted(d.keys()):
                print("     %-22s = %r" % (k, red(k, d[k])))

for fn, label in (("Items.data", "ITEM"), ("Devices.data", "DEVICE")):
    recs = dec(fn)
    fix = [r for r in recs if isinstance(r, dict)
           and isinstance(r.get("location"), dict) and r["location"].get("latitude") is not None]
    if fix:
        dump(fix[0], label)
    elif recs:
        dump(recs[0], label + " (no-fix sample)")
PY
