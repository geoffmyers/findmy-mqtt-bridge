"""Obtain the FMIPDataManager key by running the ad-hoc-signed extractor.

The extractor (``extractor/fmip_keydump.swift``, compiled + signed at deploy)
prints lines like ``KEY service=FMIPDataManager len=171 DATA_B64=<b64>``. The key
is stable across reboots, so we extract once and cache the 32-byte symmetricKey,
re-extracting only if a decrypt later fails.
"""

from __future__ import annotations

import base64
import logging
import re
import subprocess

from .decrypt import symmetric_key

log = logging.getLogger(__name__)

_KEY_RE = re.compile(r"^KEY service=(?P<svc>\S+) len=\d+ DATA_B64=(?P<b64>\S+)$")


class KeyExtractionError(RuntimeError):
    pass


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
