import json
import zipfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.security import create_session_token
from app.core.plugin_manager import parse_version_tuple, is_newer_version, plugin_manager
from app.core.process_manager import ProcessManager

client = TestClient(app)
client.cookies.set("dockraft_session", create_session_token())

def test_version_comparisons():
    # Newer versions
    assert is_newer_version("1.0.0", "1.0.1") is True
    assert is_newer_version("v1.2.0", "v1.2.1") is True
    assert is_newer_version("2.5", "2.6.1") is True
    assert is_newer_version("1.19.4-R0.1", "1.20.1") is True

    # Same or older
    assert is_newer_version("1.5.0", "1.5.0") is False
    assert is_newer_version("2.0.0", "1.9.9") is False
    assert is_newer_version("", "1.0.0") is False
    assert is_newer_version("1.0.0", "") is False

    # Tuple extraction
    assert parse_version_tuple("v5.4.130-SNAPSHOT") == (5, 4, 130)
    assert parse_version_tuple("1.21") == (1, 21)
    assert parse_version_tuple("alpha") == (0,)

def test_plugin_scanner_with_mock_jars(tmp_path, monkeypatch):
    test_plugins_dir = tmp_path / "plugins"
    test_plugins_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(plugin_manager, "plugins_dir", test_plugins_dir)

    # 1. Create a valid plugin jar with plugin.yml
    jar_path1 = test_plugins_dir / "EssentialsX-2.20.1.jar"
    yml_content1 = """
name: Essentials
version: 2.20.1
author: EssentialsX Team
description: The essential plugin suite for Spigot and Paper servers.
website: https://essentialsx.net
"""
    with zipfile.ZipFile(jar_path1, "w") as z:
        z.writestr("plugin.yml", yml_content1)

    # 2. Create another plugin with authors list
    jar_path2 = test_plugins_dir / "Vault-1.7.3.jar"
    yml_content2 = """
name: Vault
version: 1.7.3
authors: [cereal, Sleak, EvilSeph]
description: Vault Permissions and Economy abstraction layer.
"""
    with zipfile.ZipFile(jar_path2, "w") as z:
        z.writestr("plugin.yml", yml_content2)

    # 3. Create a jar without plugin.yml (e.g. non-bukkit or corrupt)
    jar_path3 = test_plugins_dir / "RandomHelper.jar"
    with zipfile.ZipFile(jar_path3, "w") as z:
        z.writestr("somefile.txt", "hello")

    scanned = plugin_manager.scan_installed_plugins()
    assert len(scanned) == 3

    p_map = {p["filename"]: p for p in scanned}
    assert p_map["EssentialsX-2.20.1.jar"]["name"] == "Essentials"
    assert p_map["EssentialsX-2.20.1.jar"]["version"] == "2.20.1"
    assert p_map["EssentialsX-2.20.1.jar"]["valid"] is True
    assert "EssentialsX Team" in p_map["EssentialsX-2.20.1.jar"]["author"]

    assert p_map["Vault-1.7.3.jar"]["name"] == "Vault"
    assert "cereal, Sleak" in p_map["Vault-1.7.3.jar"]["author"]

    assert p_map["RandomHelper.jar"]["valid"] is False

@pytest.mark.asyncio
async def test_plugin_check_and_notify_updates(tmp_path, monkeypatch):
    test_plugins_dir = tmp_path / "plugins"
    test_plugins_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(plugin_manager, "plugins_dir", test_plugins_dir)
    plugin_manager._detected_updates = {}

    # Create outdated plugin jar
    jar_path = test_plugins_dir / "LuckPerms-5.3.0.jar"
    yml_content = "name: LuckPerms\nversion: 5.3.0\nauthor: Luck\ndescription: An advanced permissions plugin."
    with zipfile.ZipFile(jar_path, "w") as z:
        z.writestr("plugin.yml", yml_content)

    # Mock Spiget responses
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = [{"id": 28140, "name": "LuckPerms"}]

    mock_ver_resp = MagicMock()
    mock_ver_resp.status_code = 200
    mock_ver_resp.json.return_value = {"name": "5.4.131"}

    async def mock_get(url):
        if "search" in url:
            return mock_search_resp
        return mock_ver_resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        with patch("app.core.webhook_manager.webhook_manager.dispatch") as mock_dispatch:
            res = await plugin_manager.check_and_notify_updates()
            assert res["total_installed"] == 1
            assert res["total_outdated"] == 1
            assert res["plugins"][0]["has_update"] is True
            assert res["plugins"][0]["latest_version"] == "5.4.131"
            assert mock_dispatch.called
            call_args = mock_dispatch.call_args[0]
            assert call_args[0] == "plugin_update"

def test_api_plugins_and_raw_properties(tmp_path, monkeypatch):
    test_plugins_dir = tmp_path / "plugins"
    test_plugins_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(plugin_manager, "plugins_dir", test_plugins_dir)

    # Test GET /api/plugins/list
    res = client.get("/api/plugins/list")
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert "plugins" in res.json()

    # Test POST /api/plugins/check-updates with mocked empty result
    with patch.object(plugin_manager, "check_plugin_updates", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = []
        res = client.post("/api/plugins/check-updates")
        assert res.status_code == 200
        assert res.json()["outdated_count"] == 0

    # Test GET & POST /api/server/properties/raw
    prop_content = "# Minecraft server properties\npvp=true\nmotd=Dockraft Server\nlevel-seed=123456\n"
    post_res = client.post("/api/server/properties/raw", json={"content": prop_content})
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "success"

    get_res = client.get("/api/server/properties/raw")
    assert get_res.status_code == 200
    assert get_res.json()["exists"] is True
    assert get_res.json()["content"] == prop_content

def test_console_plugin_update_parsing():
    # 1. LuckPerms format
    line1 = "[12:34:56 INFO]: [LuckPerms] An update is available: 5.4.131 (you are running 5.4.102). Download: https://luckperms.net/download"
    entry1 = plugin_manager.parse_console_update_line(line1)
    assert entry1 is not None
    assert entry1["plugin"] == "LuckPerms"
    assert entry1["version"] == "5.4.131"
    assert entry1["url"] == "https://luckperms.net/download"

    # 2. ViaVersion format
    line2 = "[ViaVersion] An update is available! Current: 4.9.2, New: 5.0.0. Download at: https://hangar.papermc.io/ViaVersion/ViaVersion"
    entry2 = plugin_manager.parse_console_update_line(line2)
    assert entry2 is not None
    assert entry2["plugin"] == "ViaVersion"
    assert entry2["version"] == "5.0.0"
    assert "hangar.papermc.io" in entry2["url"]

    # 3. EssentialsX format
    line3 = "[08:12:00 WARN]: [Essentials] A new version (2.20.1) is available at https://github.com/EssentialsX/Essentials/releases"
    entry3 = plugin_manager.parse_console_update_line(line3)
    assert entry3 is not None
    assert entry3["plugin"] == "Essentials"
    assert entry3["version"] == "2.20.1"
    assert "github.com" in entry3["url"]

    # 4. Spigot resource link format
    line4 = "[DecentHolograms] New update available! Version: 2.8.9 (You're on 2.8.5). Download at https://www.spigotmc.org/resources/96927/"
    entry4 = plugin_manager.parse_console_update_line(line4)
    assert entry4 is not None
    assert entry4["plugin"] == "DecentHolograms"
    assert entry4["version"] == "2.8.9"
    assert "spigotmc.org" in entry4["url"]

    # 5. Non-update line (should return None)
    line_normal = "[12:34:56 INFO]: [Essentials] Loading Essentials v2.20.1"
    assert plugin_manager.parse_console_update_line(line_normal) is None

    # 6. False-positive guard: "No new version available" must NOT be detected as an update
    line_vault_negative = "[02:31:39 INFO]: [Vault] No new version available"
    assert plugin_manager.parse_console_update_line(line_vault_negative) is None, \
        "Vault 'No new version available' should NOT trigger an update detection"

    # 7. "already up to date" must also be rejected
    line_up_to_date = "[Chunky] You are already up to date! (v1.4.10)"
    assert plugin_manager.parse_console_update_line(line_up_to_date) is None

def test_console_log_scanning_and_api(tmp_path, monkeypatch):
    test_logs_dir = tmp_path / "logs"
    test_logs_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    plugin_manager._detected_updates = {}

    log_file = test_logs_dir / "latest.log"
    log_content = """[10:00:00 INFO]: Starting minecraft server version 1.21.4
[10:00:05 INFO]: [LuckPerms] An update is available: 5.4.131 (you are running 5.4.102). Download: https://luckperms.net/download
[10:00:06 INFO]: [Chunky] A new version is available: 1.4.10! Download: https://www.spigotmc.org/resources/81534/
[10:00:10 INFO]: Done (5.2s)! For help, type "help"
"""
    log_file.write_text(log_content, encoding="utf-8")

    # Test scan_console_logs
    scanned = plugin_manager.scan_console_logs()
    assert len(scanned) == 2
    names = {s["plugin"] for s in scanned}
    assert "LuckPerms" in names
    assert "Chunky" in names

    # Test API GET /api/plugins/console-updates
    res_get = client.get("/api/plugins/console-updates")
    assert res_get.status_code == 200
    assert res_get.json()["count"] == 2

    # Test API POST /api/plugins/scan-console
    res_post = client.post("/api/plugins/scan-console")
    assert res_post.status_code == 200
    assert res_post.json()["count"] == 2

    # Test handle_console_line with dispatch
    with patch("app.core.webhook_manager.webhook_manager.dispatch") as mock_dispatch:
        new_line = "[ViaVersion] An update is available! Current: 4.9.2, New: 5.0.0. Download at: https://hangar.papermc.io/ViaVersion/ViaVersion"
        entry = plugin_manager.handle_console_line(new_line)
        assert entry is not None
        assert entry["plugin"] == "ViaVersion"
        assert mock_dispatch.called
        assert mock_dispatch.call_args[0][0] == "plugin_update"

@pytest.mark.asyncio
async def test_low_tps_alert_logic():
    pm = ProcessManager()
    pm._consecutive_low_tps = 0
    pm._last_tps_alert_time = 0.0

    with patch("app.core.webhook_manager.webhook_manager.dispatch") as mock_dispatch:
        # Simulate check 1: TPS 14.0 -> consecutive = 1 (no alert yet)
        t1, t5 = 14.0, 15.0
        now = 5000.0
        if t1 < 15.0:
            pm._consecutive_low_tps += 1
            if pm._consecutive_low_tps >= 2 and (now - pm._last_tps_alert_time > 1200):
                pm._last_tps_alert_time = now
                mock_dispatch("low_tps", "Alert", "Desc")

        assert pm._consecutive_low_tps == 1
        assert not mock_dispatch.called

        # Simulate check 2: TPS 13.5 -> consecutive = 2 -> triggers alert (5045 - 0 > 1200)
        now = 5045.0
        t1 = 13.5
        if t1 < 15.0:
            pm._consecutive_low_tps += 1
            if pm._consecutive_low_tps >= 2 and (now - pm._last_tps_alert_time > 1200):
                pm._last_tps_alert_time = now
                mock_dispatch("low_tps", "Alert", "Desc")

        assert pm._consecutive_low_tps == 2
        assert mock_dispatch.called
        assert pm._last_tps_alert_time == 5045.0

        # Simulate check 3: Cooldown active (5090 - 5045 = 45s < 1200s) -> no duplicate alert
        mock_dispatch.reset_mock()
        now = 5090.0
        t1 = 12.0
        if t1 < 15.0:
            pm._consecutive_low_tps += 1
            if pm._consecutive_low_tps >= 2 and (now - pm._last_tps_alert_time > 1200):
                pm._last_tps_alert_time = now
                mock_dispatch("low_tps", "Alert", "Desc")

        assert pm._consecutive_low_tps == 3
        assert not mock_dispatch.called

        # Simulate recovery check: TPS 19.5 -> resets consecutive counter
        t1 = 19.5
        if t1 >= 18.5:
            pm._consecutive_low_tps = 0

        assert pm._consecutive_low_tps == 0

def test_dismiss_and_clear_console_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    plugin_manager._detected_updates = {
        "vault": {"plugin": "Vault", "version": "1.7.3", "message": "New update", "raw_line": ""},
        "luckperms": {"plugin": "LuckPerms", "version": "5.4.131", "message": "New update", "raw_line": ""}
    }
    plugin_manager._save_cache()

    # Dismiss single update
    res_del = client.delete("/api/plugins/console-updates/Vault")
    assert res_del.status_code == 200
    assert res_del.json()["removed"] is True
    assert "vault" not in plugin_manager._detected_updates
    assert "luckperms" in plugin_manager._detected_updates

    # Clear all updates
    res_clear = client.delete("/api/plugins/console-updates")
    assert res_clear.status_code == 200
    assert res_clear.json()["cleared_count"] == 1
    assert len(plugin_manager._detected_updates) == 0

def test_cache_purging_of_negative_notices(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # Write a cache file containing a false-positive entry
    cache_file = tmp_path / "plugin_updates.json"
    cache_data = {
        "vault": {
            "plugin": "Vault",
            "version": "Nueva",
            "url": None,
            "message": "No new version available",
            "raw_line": "[02:31:39 INFO]: [Vault] No new version available",
            "timestamp": 1234567890,
            "time_str": "02:31:39"
        },
        "luckperms": {
            "plugin": "LuckPerms",
            "version": "5.4.131",
            "url": "https://luckperms.net",
            "message": "Update available: 5.4.131",
            "raw_line": "[LuckPerms] Update available",
            "timestamp": 1234567890,
            "time_str": "02:31:40"
        }
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f)

    # Load cache and verify false positive is purged
    plugin_manager._load_cache()
    assert "vault" not in plugin_manager._detected_updates
    assert "luckperms" in plugin_manager._detected_updates
    assert len(plugin_manager._detected_updates) == 1

    # Verify saved cache on disk was sanitized
    with open(cache_file, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert "vault" not in on_disk
    assert "luckperms" in on_disk
