"""Decrypt the Find My cache (``*.data``) with the FMIPDataManager key.

The key blob (a keychain generic-password) is a bplist whose ``symmetricKey`` is
the 32-byte ChaCha20-Poly1305 key. Each cache file is a bplist
``{signature, encryptedData}`` with ``encryptedData = nonce(12) ‖ ct ‖ tag(16)``
and AAD ``None``. Plaintext is a nested bplist list of records.
"""

from __future__ import annotations

import base64
import plistlib

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


def symmetric_key(blob: bytes) -> bytes:
    """Extract the 32-byte symmetricKey from the FMIPDataManager key blob."""
    try:
        p = plistlib.loads(blob)
    except Exception:
        if len(blob) == 32:
            return blob
        raise ValueError("key blob is neither a plist nor 32 raw bytes")
    v = p.get("symmetricKey") if isinstance(p, dict) else None
    if isinstance(v, dict):  # nested {key: {data: <b64|bytes>}}
        kd = v.get("key", {}).get("data")
        v = base64.b64decode(kd) if isinstance(kd, str) else kd
    if isinstance(v, str):
        v = base64.b64decode(v)
    if not isinstance(v, (bytes, bytearray)) or len(v) != 32:
        raise ValueError("symmetricKey missing or not 32 bytes in key blob")
    return bytes(v)


def decrypt_records(path: str, key: bytes) -> list[dict]:
    """Decrypt one cache file to its list of raw record dicts (``[]`` if the
    file has no encrypted payload)."""
    with open(path, "rb") as f:
        outer = plistlib.load(f)
    enc = outer.get("encryptedData")
    if not enc:
        return []
    plaintext = ChaCha20Poly1305(key).decrypt(enc[:12], enc[12:], None)
    recs = plistlib.loads(plaintext)
    if isinstance(recs, list):
        return [r for r in recs if isinstance(r, dict)]
    if isinstance(recs, dict) and isinstance(recs.get("payload"), list):
        return [r for r in recs["payload"] if isinstance(r, dict)]
    return []
