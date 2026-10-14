import pytest
import asyncio
from unittest.mock import patch
import app.main
from app.config import settings
from app.core.downloader import downloader

@pytest.mark.asyncio
async def test_paper_classified_versions_live():
    res = await downloader.get_paper_classified_versions("paper")
    assert "versions" in res
    assert res["latest_stable"] in ["26.2", "26.3"]
    
    # 26.3 must be in versions list
    v26_3 = next((v for v in res["versions"] if v["id"] == "26.3"), None)
    assert v26_3 is not None

    # 26.2 must be stable
    v26_2 = next((v for v in res["versions"] if v["id"] == "26.2"), None)
    assert v26_2 is not None
    assert v26_2["channel"] == "stable"
    assert "Estable" in v26_2["label"]

@pytest.mark.asyncio
async def test_update_info_paper_on_latest_version():
    res = await downloader.get_paper_classified_versions("paper")
    latest_st = res["latest_stable"]
    with patch.object(settings, "runtime_config", {
        "server_type": "paper",
        "server_version": latest_st,
        "server_build": 999999,
        "server_file": "server.jar"
    }), patch("app.main._is_server_installed", return_value=True):
        info = await app.main.get_update_info()
        assert info["server_type"] == "paper"
        assert info["current_version"] == latest_st
        assert info["current_channel"] == "stable"
        assert info["latest_stable"] == latest_st
        # Because build is 999999, it is not outdated
        assert info["build_update_available"] is False
        assert info["update_available"] is False

@pytest.mark.asyncio
async def test_update_info_paper_build_update_available():
    res = await downloader.get_paper_classified_versions("paper")
    latest_st = res["latest_stable"]
    with patch.object(settings, "runtime_config", {
        "server_type": "paper",
        "server_version": latest_st,
        "server_build": 1,  # Outdated build 1
        "server_file": "server.jar"
    }), patch("app.main._is_server_installed", return_value=True):
        info = await app.main.get_update_info()
        assert info["server_type"] == "paper"
        assert info["current_version"] == latest_st
        assert info["current_build"] == 1
        if info.get("latest_build") and info["latest_build"] > 1:
            assert info["build_update_available"] is True
            assert info["update_available"] is True

@pytest.mark.asyncio
async def test_update_info_paper_on_older_version():
    with patch.object(settings, "runtime_config", {
        "server_type": "paper",
        "server_version": "26.1",
        "server_file": "server.jar"
    }), patch("app.main._is_server_installed", return_value=True):
        info = await app.main.get_update_info()
        assert info["server_type"] == "paper"
        assert info["current_version"] == "26.1"
        assert info["update_available"] is True

def test_detect_server_build_from_log(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    latest_log = logs_dir / "latest.log"
    latest_log.write_text(
        "[14:21:48 INFO]: [bootstrap] Loading Paper 26.3-186-main@b5eb5e0 (2026-10-14T18:20:35Z) for Minecraft 26.3\n"
        "[14:21:55 INFO]: This server is running Paper version 26.3-186-main@b5eb5e0 (Implementing API version 26.3.build.186-stable)\n",
        encoding="utf-8"
    )
    detected_build = downloader.detect_server_build(data_dir=tmp_path)
    assert detected_build == 186

