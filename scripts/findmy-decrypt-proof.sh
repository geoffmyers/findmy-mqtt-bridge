#!/bin/bash
# PROOF (macOS 14.x): extract the Find My cache key(s) via a one-time GUI
# "Always Allow", then ChaCha20-Poly1305-decrypt Items.data / Devices.data and
# print a SAFE summary (names + ~100 m-rounded coords). Never prints keys or
# precise location. $LOGINPW comes from the env (set by the remote ssh cmd).
set +e
LK="$HOME/Library/Keychains/login.keychain-db"
D="$HOME/Library/Caches/com.apple.findmy.fmipcore"

security unlock-keychain -p "$LOGINPW" "$LK" 2>/dev/null && echo "keychain: unlocked" || echo "keychain: unlock FAILED"

# One-time venv with `cryptography` (also what the real bridge will use).
VENV="$HOME/.findmy-proof-venv"
if [ ! -x "$VENV/bin/python3" ]; then
  echo "venv: creating + installing cryptography (one-time)..."
  /usr/bin/python3 -m venv "$VENV" 2>&1 | tail -1
  "$VENV/bin/pip" install --quiet --disable-pip-version-check cryptography 2>&1 | tail -2
fi
PY="$VENV/bin/python3"
"$PY" -c 'import cryptography;print("cryptography:",cryptography.__version__)' || { echo "no crypto lib"; exit 1; }

UID_N="$(id -u)"
echo "keys: uid=$UID_N — diagnosing item lookup + ACL, extracting via GUI session..."
# (svce,acct) pairs as seen in dump-keychain.
set -- "BeaconStore:BeaconStoreKey" "FMFDStoreController:FMFDStoreControllerKey" "SPBeaconKeyManager:SPBeaconKeyManagerKey"
KEYS=""
for pair in "$@"; do
  SVCE="${pair%%:*}"; ACCT="${pair##*:}"
  echo "  --- $SVCE / $ACCT ---"
  # 1) Is the item present at all? (attributes only, no ACL prompt.)
  if security find-generic-password -s "$SVCE" -a "$ACCT" "$LK" >/dev/null 2>&1; then
    echo "    found: yes (class=generic-password)"
  else
    echo "    found: NO by -s/-a; trying -l label..."
    security find-generic-password -l "$SVCE" "$LK" >/dev/null 2>&1 && echo "    found via -l label" || echo "    not found via -l either"
  fi
  # 2) Read the secret INSIDE the aqua GUI session so securityd can prompt you.
  #    launchctl asuser needs root -> sudo (password from stdin).
  OUT=$(printf '%s\n' "$LOGINPW" | sudo -S -p '' launchctl asuser "$UID_N" \
          security find-generic-password -w -s "$SVCE" -a "$ACCT" "$LK" 2>/tmp/secerr)
  RC=$?
  if [ $RC -eq 0 ] && [ -n "$OUT" ]; then
    B64=$(printf '%s' "$OUT" | base64 | tr -d '\n')
    KEYS="$KEYS$SVCE:$B64"$'\n'
    echo "    read: OK (secret len=${#OUT})"
  else
    echo "    read: FAILED rc=$RC err=[$(tr -d '\n' </tmp/secerr | cut -c1-160)]"
  fi
done
rm -f /tmp/secerr
export FINDMY_KEYS_B64="$KEYS"

FINDMY_DIR="$D" "$PY" -c '
import os, sys, base64, binascii, plistlib
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305, AESGCM
D = os.environ["FINDMY_DIR"]

def describe(b):
    kinds = []
    try:
        bytes.fromhex(b.decode("ascii")); kinds.append("hex(%d->%d)" % (len(b), len(b)//2))
    except Exception: pass
    try:
        d = base64.b64decode(b, validate=True); kinds.append("b64(->%d)" % len(d))
    except Exception: pass
    if b[:6] == b"bplist": kinds.append("bplist")
    return "len=%d head=%s kinds=[%s]" % (len(b), binascii.hexlify(b[:4]).decode(), ",".join(kinds) or "raw")

def candidates(blob):
    # Every plausible interpretation of the keychain secret -> raw key bytes.
    out, seen = [], set()
    def add(tag, kb):
        if isinstance(kb, (bytes, bytearray)) and len(kb) in (16, 32) and bytes(kb) not in seen:
            seen.add(bytes(kb)); out.append((tag, bytes(kb)))
    add("raw", blob)
    add("raw[:32]", blob[:32]); add("raw[-32:]", blob[-32:])
    add("raw[:16]", blob[:16])
    try: add("hex", bytes.fromhex(blob.decode("ascii")))
    except Exception: pass
    try:
        db = base64.b64decode(blob, validate=True)
        add("b64", db); add("b64[:32]", db[:32]); add("b64[-32:]", db[-32:])
    except Exception: pass
    try:
        p = plistlib.loads(blob)
        if isinstance(p, dict):
            print("      key-blob is plist fields=", list(p.keys()))
            for k, v in p.items():
                if isinstance(v, (bytes, bytearray)): add("plist:"+k, bytes(v))
                if isinstance(v, str):
                    try: add("plist-hex:"+k, bytes.fromhex(v))
                    except Exception: pass
                    try: add("plist-b64:"+k, base64.b64decode(v))
                    except Exception: pass
    except Exception: pass
    return out

keys = {}
for line in os.environ.get("FINDMY_KEYS_B64","").splitlines():
    if ":" not in line: continue
    label, b64 = line.split(":", 1)
    try:
        blob = base64.b64decode(b64)
        keys[label] = blob
        print("  key %-20s %s" % (label, describe(blob)))
    except Exception as e:
        print("  keydecode fail", label, e)

def show(recs, fname, tag):
    items = recs if isinstance(recs, list) else (recs.get("payload") if isinstance(recs, dict) else [])
    print("  %s DECRYPTED via %s -> %d records" % (fname, tag, len(items or [])))
    n = 0
    for e in (items or [])[:120]:
        if not isinstance(e, dict): continue
        nm = e.get("name") or e.get("deviceDisplayName") or "?"
        loc = e.get("location") or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if lat is not None:
            n += 1
            print("    - %-28s %.3f,%.3f acc=%s" % (str(nm)[:28], lat, lon, loc.get("horizontalAccuracy")))
        else:
            print("    - %-28s (no fix)" % str(nm)[:28])
    print("  ->", n, "record(s) with a location fix")

def try_decrypt(fname):
    path = os.path.join(D, fname)
    if not os.path.exists(path): print(fname, "MISSING"); return
    with open(path, "rb") as f: outer = plistlib.load(f)
    print("  outer-plist keys:", list(outer.keys()) if isinstance(outer, dict) else type(outer).__name__)
    enc = outer.get("encryptedData"); sig = outer.get("signature")
    if not enc: print(fname, "has no encryptedData"); return
    print("  encryptedData len=%d  signature len=%s" % (len(enc), len(sig) if sig else None))
    aads = [None, b"", sig] if sig else [None, b""]
    # Try 12-byte-nonce-prefix (ChaCha & AES-GCM) and 16-byte-nonce-prefix.
    layouts = [("n12", enc[:12], enc[12:]), ("n16", enc[:16], enc[16:])]
    for label, blob in keys.items():
        for ktag, sk in candidates(blob):
            for algname, alg in (("chacha", ChaCha20Poly1305), ("aesgcm", AESGCM)):
                for lname, nonce, data in layouts:
                    if algname == "chacha" and len(nonce) != 12: continue
                    for aad in aads:
                        try:
                            pt = alg(sk).decrypt(nonce, data, aad)
                        except Exception:
                            continue
                        tag = "%s/%s %s %s aad=%s" % (label, ktag, algname, lname,
                              "none" if aad is None else len(aad))
                        try:
                            recs = plistlib.loads(pt)
                        except Exception:
                            print("  %s decrypted %d bytes (not plist) via %s; head=%s" % (
                                fname, len(pt), tag, binascii.hexlify(pt[:8]).decode())); return
                        show(recs, fname, tag); return
    print(fname, "NOT DECRYPTED by any key/candidate/layout")

for fn in ("Items.data", "Devices.data"):
    print("====", fn, "====")
    try_decrypt(fn)
'
echo "===== DONE ====="
