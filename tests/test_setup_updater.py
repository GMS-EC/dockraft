import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import launcher


def test_is_windows_setup_install_distinguishes_setup_vs_portable_and_linux(tmp_path: Path, monkeypatch):
    # Source run -> False
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert launcher._is_windows_setup_install() is False

    # Linux frozen (AppImage) -> False
    lin_exe = tmp_path / "lin" / "Dockraft"
    lin_exe.parent.mkdir(parents=True)
    lin_exe.write_text("", encoding="utf-8")
    (lin_exe.parent / "_internal").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "executable", str(lin_exe))
    assert launcher._is_windows_setup_install() is False

    # Windows Portable (single exe, no unins*.exe / _internal) -> False
    port_dir = tmp_path / "portable"
    port_dir.mkdir(parents=True)
    port_exe = port_dir / "Dockraft-Windows-Portable-1.6.1.exe"
    port_exe.write_text("MZ", encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(port_exe))
    assert launcher._is_windows_setup_install() is False

    # Windows Setup (onedir + unins000.exe + _internal, no .portable) -> True
    setup_dir = tmp_path / "setup"
    setup_dir.mkdir(parents=True)
    setup_exe = setup_dir / "Dockraft.exe"
    setup_exe.write_text("MZ", encoding="utf-8")
    (setup_dir / "unins000.exe").write_text("MZ", encoding="utf-8")
    (setup_dir / "_internal").mkdir()
    monkeypatch.setattr(sys, "executable", str(setup_exe))
    assert launcher._is_windows_setup_install() is True

    # .portable marker overrides -> False
    (setup_dir / ".portable").write_text("1", encoding="utf-8")
    assert launcher._is_windows_setup_install() is False


def test_fetch_release_update_info_extracts_setup_asset(monkeypatch):
    import urllib.request

    rel_payload = {
        "tag_name": "v1.6.2",
        "html_url": "https://github.com/GMS-EC/dockraft/releases/tag/v1.6.2",
        "assets": [
            {
                "name": "Dockraft-Windows-Portable-1.6.2.exe",
                "browser_download_url": "https://github.com/GMS-EC/dockraft/releases/download/v1.6.2/Dockraft-Windows-Portable-1.6.2.exe",
                "size": 12345,
            },
            {
                "name": "Dockraft-Windows-Setup-1.6.2.exe",
                "browser_download_url": "https://github.com/GMS-EC/dockraft/releases/download/v1.6.2/Dockraft-Windows-Setup-1.6.2.exe",
                "size": 54321,
                "digest": "sha256:abcdef0123456789",
            },
        ],
    }

    class _FakeResp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout=8):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "api.github.com" in url:
            return _FakeResp(json.dumps(rel_payload).encode("utf-8"))
        return _FakeResp(b"## [1.6.2] - 2026-11-15\n")

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    info = launcher._fetch_release_update_info()
    assert info["latest_ver"] == "1.6.2"
    assert info["release_tag_ver"] == "1.6.2"
    assert info["setup_asset_name"] == "Dockraft-Windows-Setup-1.6.2.exe"
    assert info["setup_asset_url"].endswith("Dockraft-Windows-Setup-1.6.2.exe")
    assert info["setup_asset_size"] == 54321
    assert info["setup_asset_sha256"] == "abcdef0123456789"
    assert launcher._fetch_latest_version_info() == (
        "1.6.2",
        "https://github.com/GMS-EC/dockraft/releases/tag/v1.6.2",
    )


def test_download_setup_installer_verifies_pe_size_sha_and_host(tmp_path: Path, monkeypatch):
    import tempfile
    import urllib.request

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    payload = b"MZ\x90\x00" + (b"\x00\x01\x02\x03" * 250)
    digest = hashlib.sha256(payload).hexdigest()

    class _StreamResp:
        def __init__(self, data: bytes, final_url: str):
            self._bio = io.BytesIO(data)
            self._final_url = final_url
            self.headers = {"Content-Length": str(len(data))}

        def geturl(self):
            return self._final_url

        def read(self, n=-1):
            return self._bio.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    progress_events = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=30: _StreamResp(
            payload,
            "https://objects.githubusercontent.com/github-production-release-asset/Dockraft-Windows-Setup-1.6.2.exe",
        ),
    )

    out_path = launcher._download_setup_installer(
        "https://github.com/GMS-EC/dockraft/releases/download/v1.6.2/Dockraft-Windows-Setup-1.6.2.exe",
        "Dockraft-Windows-Setup-1.6.2.exe",
        expected_size=len(payload),
        expected_sha256=digest,
        progress_cb=lambda d, t: progress_events.append((d, t)),
    )
    assert out_path.is_file()
    assert out_path.read_bytes() == payload
    assert progress_events and progress_events[-1] == (len(payload), len(payload))

    # Reject non-GitHub URL
    with pytest.raises(ValueError, match="Untrusted"):
        launcher._download_setup_installer(
            "https://evil.example.com/Dockraft-Windows-Setup-1.6.2.exe",
            "Dockraft-Windows-Setup-1.6.2.exe",
        )

    # Reject HTML / non-PE file
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=30: _StreamResp(b"<html>bad</html>", "https://github.com/a.exe"),
    )
    with pytest.raises(ValueError, match="Windows executable"):
        launcher._download_setup_installer(
            "https://github.com/GMS-EC/dockraft/releases/download/v1.6.2/Dockraft-Windows-Setup-1.6.2.exe",
            "Dockraft-Windows-Setup-1.6.2.exe",
        )

    # Reject SHA-256 mismatch
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=30: _StreamResp(payload, "https://github.com/a.exe"),
    )
    with pytest.raises(ValueError, match="SHA-256"):
        launcher._download_setup_installer(
            "https://github.com/GMS-EC/dockraft/releases/download/v1.6.2/Dockraft-Windows-Setup-1.6.2.exe",
            "Dockraft-Windows-Setup-1.6.2.exe",
            expected_size=len(payload),
            expected_sha256="0" * 64,
        )


def test_stop_all_dockraft_and_launch_installer_stops_running_instances(tmp_path: Path, monkeypatch):
    inst_on = tmp_path / "inst_on"
    inst_off = tmp_path / "inst_off"
    inst_on.mkdir()
    inst_off.mkdir()
    installer_exe = tmp_path / "Dockraft-Windows-Setup-1.6.2.exe"
    installer_exe.write_text("MZ", encoding="utf-8")

    monkeypatch.setattr(
        launcher,
        "_discover_all_instances",
        lambda: [
            {"dir": str(inst_on), "port": 8000, "mc_port": 25565, "name": "Survival"},
            {"dir": str(inst_off), "port": 8001, "mc_port": 25566, "name": "Creative"},
        ],
    )
    monkeypatch.setattr(launcher, "_is_port_open", lambda p: p == 8000)

    stopped = []
    monkeypatch.setattr(launcher, "_stop_instance", lambda d, p: stopped.append((d, p)) or (True, "ok"))
    terminated = []
    monkeypatch.setattr(
        launcher,
        "_terminate_all_other_dockraft_processes",
        lambda stop_mc_servers=False: terminated.append(stop_mc_servers),
    )

    popens = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda argv, **_kw: popens.append(argv))

    fake_server = SimpleNamespace(should_exit=False)
    tray_stopped = []
    fake_tray = SimpleNamespace(stop=lambda: tray_stopped.append(True))

    launcher._stop_all_dockraft_and_launch_installer(
        installer_exe,
        in_process_server=fake_server,
        tray_icon=fake_tray,
    )

    assert stopped == [(inst_on.resolve(), 8000)]
    assert terminated == [True]
    assert popens == [[str(installer_exe)]]
    assert fake_server.should_exit is True
    assert tray_stopped == [True]
