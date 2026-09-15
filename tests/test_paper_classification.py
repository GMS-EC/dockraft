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
    assert res["latest_stable"] == "26.2"
    assert res["latest_preview"] == "26.3"
    
    # 26.3 must be preview / experimental
    v26_3 = next((v for v in res["versions"] if v["id"] == "26.3"), None)
    assert v26_3 is not None
    assert v26_3["channel"] == "preview"
    assert "Experimental" in v26_3["label"]

    # 26.2 must be stable
    v26_2 = next((v for v in res["versions"] if v["id"] == "26.2"), None)
    assert v26_2 is not None
    assert v26_2["channel"] == "stable"
    assert "Estable" in v26_2["label"]

@pytest.mark.asyncio
async def test_update_info_paper_on_26_2():
    with patch.object(settings, "runtime_config", {
        "server_type": "paper",
        "server_version": "26.2",
        "server_file": "server.jar"
    }), patch("app.main._is_server_installed", return_value=True):
        info = await app.main.get_update_info()
        assert info["server_type"] == "paper"
        assert info["current_version"] == "26.2"
        assert info["current_channel"] == "stable"
        assert info["latest_stable"] == "26.2"
        assert info["latest_preview"] == "26.3"
        # 26.2 is latest stable, so update_available must be False
        assert info["update_available"] is False
        # 26.3 is available as preview/experimental
        assert info["preview_available"] is True

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
        assert info["latest_stable"] == "26.2"
        assert info["update_available"] is True
