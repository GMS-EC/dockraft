import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.webhook_manager import webhook_manager

from app.core.security import create_session_token

client = TestClient(app)
client.cookies.set("dockraft_session", create_session_token())

def test_webhook_config_load_and_save():
    # Load config via API
    res = client.get("/api/webhooks/config")
    assert res.status_code == 200
    cfg = res.json()
    assert "discord" in cfg
    assert "telegram" in cfg
    assert "email" in cfg
    assert "events" in cfg

    # Save new config
    payload = {
        "discord": {
            "enabled": True,
            "webhook_url": "https://discord.com/api/webhooks/123/fake-token"
        },
        "telegram": {
            "enabled": True,
            "bot_token": "123456:fake_token",
            "chat_id": "-100123456789"
        },
        "email": {
            "enabled": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "alert@example.com",
            "smtp_password": "secret_password",
            "smtp_use_tls": True,
            "from_email": "alerts@example.com",
            "to_emails": "admin@example.com"
        },
        "events": {
            "server_start": True,
            "server_stop": True,
            "server_crash": True,
            "backup_created": True,
            "task_executed": True,
            "player_join": False,
            "player_leave": False
        }
    }
    res_save = client.post("/api/webhooks/config", json=payload)
    assert res_save.status_code == 200
    saved = res_save.json()["config"]
    assert saved["discord"]["enabled"] is True
    assert saved["discord"]["webhook_url"] == "https://discord.com/api/webhooks/123/fake-token"
    assert saved["telegram"]["bot_token"] == "123456:fake_token"
    assert saved["email"]["smtp_host"] == "smtp.example.com"
    assert saved["events"]["server_start"] is True

@pytest.mark.asyncio
async def test_webhook_discord_dispatch_mock():
    # Test discord sending with mocked httpx.AsyncClient
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.text = ""
        mock_post.return_value = mock_resp

        webhook_manager.config["discord"]["webhook_url"] = "https://discord.com/api/webhooks/test"
        await webhook_manager.send_discord("Test Title", "Test Message", color=0x2ea043)
        assert mock_post.called

@pytest.mark.asyncio
async def test_webhook_telegram_dispatch_mock():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"ok": true}'
        mock_post.return_value = mock_resp

        webhook_manager.config["telegram"]["bot_token"] = "fake:bot"
        webhook_manager.config["telegram"]["chat_id"] = "123456"
        await webhook_manager.send_telegram("TG Title", "TG Message")
        assert mock_post.called

def test_webhook_test_endpoint_failure_when_unconfigured():
    # Test with empty webhook URL
    webhook_manager.config["discord"]["webhook_url"] = ""
    res = client.post("/api/webhooks/test/discord")
    assert res.status_code == 400
    assert "Discord" in res.json()["detail"] or "URL" in res.json()["detail"]

def test_webhook_test_endpoint_unknown_channel():
    res = client.post("/api/webhooks/test/unknown_service")
    assert res.status_code == 400
    assert "desconocido" in res.json()["detail"].lower()

def test_backup_retention_only_config_save():
    # Verify that saving only backup_max_count works seamlessly
    res = client.post("/api/backups/config", json={"backup_max_count": 8})
    assert res.status_code == 200
    cfg = res.json()["config"]
    assert cfg["backup_max_count"] == 8
