"""Obtain the FMIPDataManager key by running the ad-hoc-signed extractor.

The extractor (``extractor/fmip_keydump.swift``, compiled + signed at deploy)
prints lines like ``KEY service=FMIPDataManager len=171 DATA_B64=<b64>``. The key
is stable across reboots, so we extract once and cache the 32-byte symmetricKey,
re-extracting only if a decrypt later fails.
"""

from __future__ import annotations

import base64
import logging
import platform
import re
import subprocess

from .decrypt import symmetric_key

log = logging.getLogger(__name__)

_KEY_RE = re.compile(r"^KEY service=(?P<svc>\S+) len=\d+ DATA_B64=(?P<b64>\S+)$")


class KeyExtractionError(RuntimeError):
    pass


def macos_major_version() -> int | None:
    """Best-effort major macOS version. Tries ``platform.mac_ver()`` first
    (no subprocess); some sandboxed/venv Pythons return an empty string from
    that, so falls back to ``sw_vers -productVersion``. Returns ``None`` if
    neither source yields a parseable version (e.g. not running on macOS)."""
    version_str = platform.mac_ver()[0]
    if not version_str:
        try:
            proc = subprocess.run(
                ["sw_vers", "-productVersion"],
                capture_output=True, text=True, timeout=5.0,
            )
            version_str = proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            version_str = ""
    if not version_str:
        return None
    try:
        return int(version_str.split(".")[0])
    except (ValueError, IndexError):
        return None


class KeyProvider:
    def __init__(self, extractor_bin: str, service: str = "FMIPDataManager", timeout: float = 30.0):
        self.extractor_bin = extractor_bin
        self.service = service
        self.timeout = timeout
        self._key: bytes | None = None

    def _run(self) -> bytes:
        try:
            proc = subprocess.run(
                [self.extractor_bin], capture_output=True, text=True, timeout=self.timeout
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise KeyExtractionError(f"extractor failed to run: {e}") from e
        for line in proc.stdout.splitlines():
            m = _KEY_RE.match(line.strip())
            if m and m.group("svc") == self.service:
                blob = base64.b64decode(m.group("b64"))
                return symmetric_key(blob)
        major = macos_major_version()
        if major is not None and major >= 15:
            raise KeyExtractionError(
                f"no {self.service} key in extractor output — running on macOS "
                f"{major}, which is not supported. This project's decrypt path "
                "only works on macOS 14.4-14.8 (Sonoma); Apple moved the Find My "
                "cache key behind additional protection starting in macOS 15. "
                "See README.md -> Requirements. "
                f"(rc={proc.returncode}; stderr={proc.stderr.strip()[:200]})"
            )
        raise KeyExtractionError(
            f"no {self.service} key in extractor output (rc={proc.returncode}); "
            f"stderr={proc.stderr.strip()[:200]}"
        )

    def get(self, force: bool = False) -> bytes:
        """Return the cached 32-byte symmetricKey, extracting if needed."""
        if force or self._key is None:
            self._key = self._run()
            log.info("extracted FMIPDataManager symmetricKey (32 bytes)")
        return self._key
