#!/usr/bin/env python3
"""Decrypt Apple Find My fmipcore cache files with the FMIPDataManager key.

The key (a keychain generic-password blob, base64 in env FINDMY_FMIP_KEY_B64) is
a bplist whose `symmetricKey` field is the 32-byte ChaCha20-Poly1305 key. Each
cache `.data` file is a bplist {signature, encryptedData} where
encryptedData = nonce(12) || ciphertext || tag(16), decrypted with AAD=None
(scheme per the community findmy-cache-decryptor). Plaintext is a nested bplist
of records. Prints a safe summary (coords rounded to ~100 m); never prints keys.

Usage:  FINDMY_FMIP_KEY_B64=<b64> python3 decrypt_cache.py <fmipcore_dir> [file...]
"""
import base64
import os
import plistlib
import sys

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

FILES = ["Items.data", "Devices.data", "FamilyMembers.data", "SafeLocations.data", "Owner.data"]


def symmetric_key(blob: bytes) -> bytes:
    """Extract the 32-byte symmetricKey from the keychain key blob."""
    try:
        p = plistlib.loads(blob)
    except Exception:
        if len(blob) == 32:
            return blob
        raise SystemExit("key blob is not a plist and not 32 raw bytes")
    v = p.get("symmetricKey") if isinstance(p, dict) else None
    if isinstance(v, dict):  # nested {key: {data: <b64/bytes>}}
        kd = v.get("key", {}).get("data")
        v = base64.b64decode(kd) if isinstance(kd, str) else kd
    if isinstance(v, str):
        v = base64.b64decode(v)
    if not isinstance(v, (bytes, bytearray)) or len(v) != 32:
        raise SystemExit(f"symmetricKey not found / wrong size in key blob (fields={list(p.keys())})")
    return bytes(v)


def decrypt_file(path: str, key: bytes):
    with open(path, "rb") as f:
        outer = plistlib.load(f)
    enc = outer.get("encryptedData")
    if not enc:
        return None
    pt = ChaCha20Poly1305(key).decrypt(enc[:12], enc[12:], None)
    return plistlib.loads(pt)


def summarize(name: str, recs):
    items = recs if isinstance(recs, list) else (recs.get("payload") if isinstance(recs, dict) else [])
    n = 0
    print(f"== {name}: {len(items or [])} records ==")
    for e in (items or []):
        if not isinstance(e, dict):
            continue
        nm = e.get("name") or e.get("deviceDisplayName") or "?"
        loc = e.get("location")
        if not isinstance(loc, dict):
            loc = {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        batt = e.get("batteryLevel", e.get("batteryStatus"))
        if lat is not None:
            n += 1
            print(f"   - {str(nm)[:30]:30} {lat:.3f},{lon:.3f} acc={loc.get('horizontalAccuracy')} batt={batt}")
        else:
            print(f"   - {str(nm)[:30]:30} (no fix)")
    print(f"   -> {n} with a location fix")


def _scalar(v):
    """Redact coordinates; keep other scalars for schema inspection."""
    if isinstance(v, (dict, list)):
        return f"<{type(v).__name__}:{sorted(v.keys()) if isinstance(v, dict) else len(v)}>"
    return v


def dump_schema(name, recs):
    items = recs if isinstance(recs, list) else (recs.get("payload") if isinstance(recs, dict) else [])
    print(f"\n#### SCHEMA {name} (first record) ####")
    for e in (items or []):
        if not isinstance(e, dict):
            continue
        print("  keys:", sorted(e.keys()))
        loc = e.get("location")
        if isinstance(loc, dict):
            print("  location.keys:", sorted(loc.keys()))
        for k in ("batteryLevel", "batteryStatus", "deviceModel", "rawDeviceModel",
                  "productType", "modelDisplayName", "role", "isInaccurate",
                  "deviceDisplayName", "groupIdentifier"):
            if k in e:
                print(f"  {k} = {_scalar(e[k])!r}")
        addr = e.get("address")
        if isinstance(addr, dict):
            print("  address.keys:", sorted(addr.keys()))
        break


def main():
    d = sys.argv[1]
    names = sys.argv[2:] or FILES
    blob = base64.b64decode(os.environ["FINDMY_FMIP_KEY_B64"])
    key = symmetric_key(blob)
    print(f"symmetricKey ok (32 bytes)")
    dump = bool(os.environ.get("FINDMY_DUMP_SCHEMA"))
    for name in names:
        path = os.path.join(d, name)
        if not os.path.exists(path):
            continue
        try:
            recs = decrypt_file(path, key)
        except Exception as e:
            print(f"== {name}: DECRYPT FAILED: {type(e).__name__}: {e} ==")
            continue
        if recs is not None:
            summarize(name, recs)
            if dump:
                dump_schema(name, recs)


if __name__ == "__main__":
    main()
