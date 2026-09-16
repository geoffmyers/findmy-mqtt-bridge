#!/bin/bash
# Recon: can we reliably read FindMy device/item locations from the on-disk
# cache that FindMy.app maintains? Runs ON the macOS guest via `bash -s`, e.g.:
#   ssh your-user@your-vm-host 'bash -s' < scripts/findmy-recon.sh
# (if your host can't reach the VM directly — a macvlan-bridged VM behind a
# Docker host, for example — pipe it through any box that can SSH to the VM.)
echo "===== HOST / OS ====="
sw_vers 2>/dev/null; echo "whoami=$(whoami)"; scutil --get ComputerName 2>/dev/null

echo; echo "===== iCLOUD SIGN-IN (MobileMeAccounts) ====="
defaults read MobileMeAccounts 2>/dev/null | grep -iE "AccountID|LoggedIn|DisplayName|Description" | head -20 \
  || echo "(no MobileMeAccounts plist — not signed into iCloud?)"

echo; echo "===== FindMy PROCESSES ====="
ps ax -o pid,comm 2>/dev/null | grep -iE "[F]indMy|[s]earchpartyd" || echo "(no FindMy / searchpartyd process)"

D="$HOME/Library/Caches/com.apple.findmy.fmipcore"
echo; echo "===== CACHE DIR: $D ====="
ls -la "$D" 2>/dev/null || echo "MISSING: $D"

for f in Devices Items; do
  p="$D/$f.data"
  echo; echo "----- $f.data -----"
  if [ -f "$p" ]; then
    stat -f 'size=%z bytes  mtime=%Sm' "$p" 2>/dev/null
    file "$p" 2>/dev/null
    echo "first-bytes: $(head -c 80 "$p" 2>/dev/null | tr -d '\n')"
  else
    echo "MISSING: $p"
  fi
done

echo; echo "===== PARSE (python3) ====="
PY=/usr/bin/python3
command -v "$PY" >/dev/null 2>&1 || PY=python3
"$PY" - "$D" <<'PYEOF'
import sys, json, os
d = sys.argv[1]
def load(name):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        return None, f"MISSING {name}"
    try:
        with open(p, "rb") as fh:
            raw = fh.read()
        return json.loads(raw.decode("utf-8", "replace")), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

for name, kind in (("Devices.data","device"), ("Items.data","item")):
    data, err = load(name)
    print(f"\n## {name}")
    if err:
        print("  parse error:", err); continue
    if not isinstance(data, list):
        print("  unexpected top-level type:", type(data).__name__); continue
    print(f"  entries: {len(data)}")
    withloc = 0
    for e in data[:60]:
        nm = e.get("name") or e.get("deviceDisplayName") or "?"
        loc = e.get("location")
        if loc and loc.get("latitude") is not None:
            withloc += 1
            lat = round(loc.get("latitude"), 4); lon = round(loc.get("longitude"), 4)
            acc = loc.get("horizontalAccuracy")
            ts = loc.get("timeStamp") or loc.get("timestamp")
            batt = e.get("batteryLevel", e.get("batteryStatus"))
            print(f"    [{nm}] {lat},{lon} acc={acc} ts={ts} batt={batt}")
        else:
            print(f"    [{nm}] (no location fix)")
    print(f"  -> {withloc} entr{'y' if withloc==1 else 'ies'} WITH a location fix")
PYEOF
echo; echo "===== DONE ====="
