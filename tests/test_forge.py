import pytest
from app.core.downloader import downloader

@pytest.mark.asyncio
async def test_forge_versions():
    versions = await downloader.get_forge_versions()
    assert len(versions) > 0
    # Forge should have versions like 1.20.1, 1.16.5, etc.
    mc_versions = [v["mc_version"] for v in versions]
    assert any("1.20" in v or "1.19" in v or "1.16" in v for v in mc_versions)
    
    first = versions[0]
    assert "mc_version" in first
    assert "forge_build" in first
    assert "label" in first

@pytest.mark.asyncio
async def test_forge_download_url():
    # Pick 1.20.1
    url = await downloader.get_forge_download_url("1.20.1")
    assert "maven.minecraftforge.net" in url
    assert "1.20.1" in url
    assert url.endswith("-installer.jar")
