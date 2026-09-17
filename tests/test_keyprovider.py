"""macOS-version detection and the macOS-15+ error path in KeyProvider.

Apple moved the Find My cache key behind additional protection starting in
macOS 15 (see README.md -> Requirements): this project's extractor still
runs there, but finds no FMIPDataManager key in its output. Without a
version check that looks exactly like every other "extractor found
nothing" failure (wrong binary, missing entitlement, SIP/AMFI still on) —
so the version check exists purely to turn a generic error into an
actionable one.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from findmy_bridge.keyprovider import KeyExtractionError, KeyProvider, macos_major_version


class _FakeCompletedProcess:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


# --- macos_major_version() ---------------------------------------------


def test_macos_major_version_from_mac_ver():
    with patch("findmy_bridge.keyprovider.platform.mac_ver", return_value=("14.8", ("", "", ""), "")):
        assert macos_major_version() == 14


def test_macos_major_version_15_from_mac_ver():
    with patch("findmy_bridge.keyprovider.platform.mac_ver", return_value=("15.1", ("", "", ""), "")):
        assert macos_major_version() == 15


def test_macos_major_version_falls_back_to_sw_vers_when_mac_ver_empty():
    # Seen on some sandboxed/venv Pythons: platform.mac_ver() returns "".
    with (
        patch("findmy_bridge.keyprovider.platform.mac_ver", return_value=("", ("", "", ""), "")),
        patch(
            "findmy_bridge.keyprovider.subprocess.run",
            return_value=_FakeCompletedProcess(stdout="15.2\n"),
        ) as run,
    ):
        assert macos_major_version() == 15
    run.assert_called_once_with(
        ["sw_vers", "-productVersion"], capture_output=True, text=True, timeout=5.0
    )


def test_macos_major_version_none_when_both_sources_empty():
    with (
        patch("findmy_bridge.keyprovider.platform.mac_ver", return_value=("", ("", "", ""), "")),
        patch("findmy_bridge.keyprovider.subprocess.run", return_value=_FakeCompletedProcess(stdout="")),
    ):
        assert macos_major_version() is None


def test_macos_major_version_none_when_sw_vers_missing():
    # Not on macOS at all (e.g. the CI container): sw_vers isn't installed.
    with (
        patch("findmy_bridge.keyprovider.platform.mac_ver", return_value=("", ("", "", ""), "")),
        patch("findmy_bridge.keyprovider.subprocess.run", side_effect=OSError("no such file")),
    ):
        assert macos_major_version() is None


def test_macos_major_version_none_on_unparseable_string():
    with patch("findmy_bridge.keyprovider.platform.mac_ver", return_value=("not-a-version", ("", "", ""), "")):
        assert macos_major_version() is None


# --- KeyProvider._run() macOS-15+ error path -----------------------------


def _extractor_result_with_no_key() -> _FakeCompletedProcess:
    # The extractor ran (rc=0) but its output has no matching KEY line —
    # exactly what happens on macOS 15+, where the key extraction itself is
    # blocked and the extractor has nothing to print.
    return _FakeCompletedProcess(stdout="", stderr="", returncode=0)


def test_get_raises_specific_error_on_macos_15_plus(tmp_path):
    provider = KeyProvider(extractor_bin=str(tmp_path / "fmip_keydump"))
    with (
        patch("findmy_bridge.keyprovider.subprocess.run", return_value=_extractor_result_with_no_key()),
        patch("findmy_bridge.keyprovider.macos_major_version", return_value=15),
    ):
        with pytest.raises(KeyExtractionError) as exc_info:
            provider.get()
    message = str(exc_info.value)
    assert "macOS 15" in message
    assert "not supported" in message
    assert "14.4-14.8" in message
    assert "README.md" in message


def test_get_raises_generic_error_on_supported_macos(tmp_path):
    provider = KeyProvider(extractor_bin=str(tmp_path / "fmip_keydump"))
    with (
        patch("findmy_bridge.keyprovider.subprocess.run", return_value=_extractor_result_with_no_key()),
        patch("findmy_bridge.keyprovider.macos_major_version", return_value=14),
    ):
        with pytest.raises(KeyExtractionError) as exc_info:
            provider.get()
    message = str(exc_info.value)
    assert "macOS 15" not in message
    assert "not supported" not in message


def test_get_raises_generic_error_when_version_unknown(tmp_path):
    provider = KeyProvider(extractor_bin=str(tmp_path / "fmip_keydump"))
    with (
        patch("findmy_bridge.keyprovider.subprocess.run", return_value=_extractor_result_with_no_key()),
        patch("findmy_bridge.keyprovider.macos_major_version", return_value=None),
    ):
        with pytest.raises(KeyExtractionError) as exc_info:
            provider.get()
    assert "not supported" not in str(exc_info.value)


def test_get_succeeds_when_key_present_regardless_of_version(tmp_path):
    key_line = (
        "KEY service=FMIPDataManager len=32 "
        "DATA_B64=" + __import__("base64").b64encode(b"x" * 32).decode()
    )
    provider = KeyProvider(extractor_bin=str(tmp_path / "fmip_keydump"))
    with (
        patch(
            "findmy_bridge.keyprovider.subprocess.run",
            return_value=_FakeCompletedProcess(stdout=key_line + "\n"),
        ),
        patch("findmy_bridge.keyprovider.macos_major_version", return_value=15),
    ):
        key = provider.get()
    assert isinstance(key, bytes)


def test_run_propagates_subprocess_errors_without_version_check(tmp_path):
    # The extractor binary itself failing to launch (missing/not executable)
    # is a distinct failure mode from "ran but found no key" — must not be
    # swallowed or reclassified by the version check.
    provider = KeyProvider(extractor_bin=str(tmp_path / "does-not-exist"))
    with patch(
        "findmy_bridge.keyprovider.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="fmip_keydump", timeout=30.0),
    ):
        with pytest.raises(KeyExtractionError, match="extractor failed to run"):
            provider.get()
