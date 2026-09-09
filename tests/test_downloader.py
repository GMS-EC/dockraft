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


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeAsyncClient:
    def __init__(self, payload, *args, **kwargs):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, *args, **kwargs):
        return _FakeResp(self._payload)


def _paper_build(bid, url, channel="STABLE"):
    return {
        "id": bid,
        "channel": channel,
        "downloads": {
            "server:default": {
                "name": f"paper-1.21.4-{bid}.jar",
                "url": f"https://example.com/paper-1.21.4-{bid}.jar"
            }
        }
    }


@pytest.mark.asyncio
async def test_paper_latest_build_picks_newest(monkeypatch):
    """PaperMC v3 returns builds newest-first; the downloader must NOT use the last element."""
    builds = [
        _paper_build(232, "https://example.com/paper-1.21.4-232.jar"),
        _paper_build(231, "https://example.com/paper-1.21.4-231.jar"),
        _paper_build(1, "https://example.com/paper-1.21.4-1.jar"),
    ]
    monkeypatch.setattr("app.core.downloader.httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(builds))
    info = await downloader.get_paper_latest_build("paper", "1.21.4")
    assert info["download_url"].endswith("-232.jar")
    assert info["build"] == 232


@pytest.mark.asyncio
async def test_paper_latest_build_stable_not_shadowed_by_beta(monkeypatch):
    """A newer beta build must not shadow the newest stable build."""
    builds = [
        _paper_build(300, "https://example.com/beta-300.jar", channel="BETA"),
        _paper_build(232, "https://example.com/paper-1.21.4-232.jar", channel="STABLE"),
        _paper_build(231, "https://example.com/paper-1.21.4-231.jar", channel="STABLE"),
    ]
    monkeypatch.setattr("app.core.downloader.httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(builds))
    info = await downloader.get_paper_latest_build("paper", "1.21.4")
    assert info["download_url"].endswith("-232.jar")
    assert info["build"] == 232
