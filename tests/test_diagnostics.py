"""
Tests for DiagnosticManager and /api/diagnostics endpoints.
Uses monkey-patching to inject log content directly, without hitting the filesystem.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import create_session_token
from app.core.diagnostic_manager import DiagnosticManager

client = TestClient(app)
client.cookies.set("dockraft_session", create_session_token())

# ─── Sample Log Fixtures ──────────────────────────────────────────────────────

SAMPLE_OOM_LOG = """
[14:20:01 INFO]: Starting minecraft server version 1.21
[14:20:05 ERROR]: Encountered an unexpected exception
java.lang.OutOfMemoryError: Java heap space
\tat java.base/java.util.Arrays.copyOf(Arrays.java:3537)
\tat net.minecraft.server.MinecraftServer.w(MinecraftServer.java:820)
[14:20:06 ERROR]: This crash report has been saved to: crash-reports/crash-2026-09-07.txt
"""

SAMPLE_PORT_CONFLICT_LOG = """
[18:00:01 INFO]: Loading server.properties
[18:00:02 WARN]: **** FAILED TO BIND TO PORT!
[18:00:02 WARN]: The exception was: java.net.BindException: Address already in use
[18:00:02 WARN]: Perhaps a server is already running on that port?
"""

SAMPLE_JAVA_MISMATCH_LOG = """
Error: LinkageError occurred while loading main class net.minecraft.bundler.Main
java.lang.UnsupportedClassVersionError: net/minecraft/bundler/Main has been compiled by a more recent version of the Java Runtime (class file version 65.0), this version of the Java Runtime only recognizes class file versions up to 61.0
"""

SAMPLE_EULA_LOG = """
[10:00:00 INFO]: You need to agree to the EULA in order to run the server. Go to eula.txt for more info.
"""

SAMPLE_CLEAN_LOG = """
[12:00:00 INFO]: Starting Minecraft server on *:25565
[12:00:10 INFO]: Done (10.420s)! For help, type "help"
[12:05:00 INFO]: Player Steve joined the game
"""

# ─── Unit Tests: DiagnosticManager.analyze_diagnostics() ────────────────────

def _analyze_with_text(text: str) -> dict:
    """Helper: creates a DiagnosticManager and runs analysis on injected text."""
    dm = DiagnosticManager()
    with patch.object(dm, "get_latest_crash_report", return_value=None):
        with patch.object(dm, "get_recent_log_tail", return_value=text):
            return dm.analyze_diagnostics()


def test_diagnostic_detects_out_of_memory():
    result = _analyze_with_text(SAMPLE_OOM_LOG)
    assert result["has_issue"] is True
    assert result.get("category") == "memory"
    assert "Memoria RAM" in result["title"] or "OutOfMemory" in result["title"]
    assert result.get("severity") == "critical"


def test_diagnostic_detects_port_conflict():
    result = _analyze_with_text(SAMPLE_PORT_CONFLICT_LOG)
    assert result["has_issue"] is True
    assert result.get("category") == "network"
    assert "Puerto" in result["title"]
    assert result.get("severity") == "critical"


def test_diagnostic_detects_java_mismatch():
    result = _analyze_with_text(SAMPLE_JAVA_MISMATCH_LOG)
    assert result["has_issue"] is True
    assert result.get("category") == "java"
    assert "Java" in result["title"]
    assert result.get("severity") == "critical"


def test_diagnostic_detects_eula():
    result = _analyze_with_text(SAMPLE_EULA_LOG)
    assert result["has_issue"] is True
    assert result.get("category") == "eula"
    assert "EULA" in result["title"] or "Licencia" in result["title"]


def test_diagnostic_clean_log_no_issues():
    result = _analyze_with_text(SAMPLE_CLEAN_LOG)
    assert result["has_issue"] is False
    assert "title" in result


# ─── Integration Tests: /api/diagnostics endpoints ───────────────────────────

def test_api_diagnostics_analyze_returns_correct_schema():
    """Endpoint must respond 200 with has_issue and title fields."""
    res = client.get("/api/diagnostics/analyze")
    assert res.status_code == 200
    data = res.json()
    assert "has_issue" in data
    assert "title" in data


def test_api_diagnostics_analyze_with_oom_log():
    """Mock filesystem to simulate OOM and verify API returns has_issue: true."""
    from app.core import diagnostic_manager as dm_module
    with patch.object(dm_module.diagnostic_manager, "get_latest_crash_report", return_value=None):
        with patch.object(dm_module.diagnostic_manager, "get_recent_log_tail", return_value=SAMPLE_OOM_LOG):
            res = client.get("/api/diagnostics/analyze")
            assert res.status_code == 200
            data = res.json()
            assert data["has_issue"] is True
            assert data.get("category") == "memory"


def test_api_diagnostics_analyze_clean_log():
    """Mock filesystem with clean log, endpoint must return has_issue: false."""
    from app.core import diagnostic_manager as dm_module
    with patch.object(dm_module.diagnostic_manager, "get_latest_crash_report", return_value=None):
        with patch.object(dm_module.diagnostic_manager, "get_recent_log_tail", return_value=SAMPLE_CLEAN_LOG):
            res = client.get("/api/diagnostics/analyze")
            assert res.status_code == 200
            data = res.json()
            assert data["has_issue"] is False


@pytest.mark.asyncio
async def test_share_to_mclogs_success():
    """DiagnosticManager.share_to_mclogs() must return success=True and url when API succeeds."""
    dm = DiagnosticManager()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "id": "abc123",
        "url": "https://mclo.gs/abc123",
        "raw": "https://api.mclo.gs/1/raw/abc123"
    }

    with patch("httpx.AsyncClient.__aenter__") as mock_ctx:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_ctx.return_value = mock_client

        result = await dm.share_to_mclogs("Test Minecraft log content here")
        assert result["success"] is True
        assert result["url"] == "https://mclo.gs/abc123"


@pytest.mark.asyncio
async def test_share_to_mclogs_api_failure():
    """DiagnosticManager.share_to_mclogs() must return success=False when API returns error."""
    dm = DiagnosticManager()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": False, "error": "Log is too large"}

    with patch("httpx.AsyncClient.__aenter__") as mock_ctx:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_ctx.return_value = mock_client

        result = await dm.share_to_mclogs("Test content")
        assert result["success"] is False
        assert "error" in result


# ─── TPS Integration ─────────────────────────────────────────────────────────

def test_server_status_includes_tps():
    """GET /api/server/status must include a tps object with a status field."""
    res = client.get("/api/server/status")
    assert res.status_code == 200
    data = res.json()
    assert "tps" in data
    assert isinstance(data["tps"], dict)
    assert "status" in data["tps"]
