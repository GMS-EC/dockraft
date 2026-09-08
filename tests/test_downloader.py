import pytest
import pytest_asyncio
from app.core.downloader import downloader

@pytest.mark.asyncio
async def test_paper_versions():
    versions = await downloader.get_paper_versions("paper")
    assert isinstance(versions, list)
    assert len(versions) > 0
    # Common version should be present
    assert any("1.20" in v or "1.21" in v for v in versions)

@pytest.mark.asyncio
async def test_purpur_versions():
    versions = await downloader.get_purpur_versions()
    assert isinstance(versions, list)
    assert len(versions) > 0
    assert any("1.20" in v or "1.21" in v for v in versions)

@pytest.mark.asyncio
async def test_vanilla_versions():
    versions = await downloader.get_vanilla_versions()
    assert isinstance(versions, list)
    assert len(versions) > 0
    assert any(v["id"].startswith("1.") for v in versions)

@pytest.mark.asyncio
async def test_fabric_versions():
    versions = await downloader.get_fabric_versions()
    assert isinstance(versions, list)
    assert len(versions) > 0

@pytest.mark.asyncio
async def test_bedrock_versions():
    versions = await downloader.get_bedrock_versions()
    assert isinstance(versions, list)
    assert len(versions) == 2
    assert any("Estable" in v for v in versions)
    assert any("Preview" in v or "Beta" in v for v in versions)

@pytest.mark.asyncio
async def test_bedrock_download_url():
    versions = await downloader.get_bedrock_versions()
    url_linux = await downloader.get_bedrock_download_url(versions[0], platform="linux")
    assert "https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-" in url_linux
    url_preview = await downloader.get_bedrock_download_url(versions[1], platform="linux")
    assert "bin-linux-preview" in url_preview
