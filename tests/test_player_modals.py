import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import app, get_current_user
from app.core.player_manager import player_manager
from app.core.process_manager import process_manager

@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: True
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_kick_all_players_offline():
    """Verify kick-all behavior when server is offline."""
    orig_status = process_manager.get_status
    try:
        process_manager.get_status = lambda: "OFFLINE"
        process_manager.online_players.clear()
        
        res = asyncio.run(player_manager.kick_all_players("Mantenimiento programado"))
        assert res["status"] == "warning"
        assert "fuera de línea" in res["message"].lower() or "offline" in res["message"].lower()
    finally:
        process_manager.get_status = orig_status

def test_kick_all_players_online():
    """Verify kick-all sends commands and clears online players when server is running."""
    orig_status = process_manager.get_status
    orig_send = process_manager.send_command
    try:
        process_manager.get_status = lambda: "RUNNING"
        commands_sent = []
        async def mock_send(cmd):
            commands_sent.append(cmd)
            return True
        process_manager.send_command = mock_send

        process_manager.online_players.clear()
        process_manager.online_players.add("TestSteve")
        process_manager.online_players.add("TestAlex")
        
        res = asyncio.run(player_manager.kick_all_players("Reinicio de servidor por mantenimiento"))
        assert res["status"] == "success"
        assert res["count"] == 2
        assert len(process_manager.online_players) == 0
        assert any("kick TestSteve" in c or "kick @a" in c for c in commands_sent)
    finally:
        process_manager.get_status = orig_status
        process_manager.send_command = orig_send

def test_http_kick_all_endpoint(client):
    """Verify POST /api/players/kick-all endpoint."""
    orig_status = process_manager.get_status
    orig_send = process_manager.send_command
    try:
        process_manager.get_status = lambda: "RUNNING"
        process_manager.send_command = lambda cmd: asyncio.sleep(0)
        process_manager.online_players.add("Gamer123")
        
        http_res = client.post("/api/players/kick-all", json={"reason": "Mantenimiento del servidor"})
        assert http_res.status_code == 200
        data = http_res.json()
        assert data["status"] == "success"
        assert "expulsado a todos" in data["message"]
    finally:
        process_manager.get_status = orig_status
        process_manager.send_command = orig_send

def test_ban_player_offline_and_reason_reflection(client):
    """Verify offline ban persists the reason in banned-players.json."""
    orig_status = process_manager.get_status
    try:
        process_manager.get_status = lambda: "OFFLINE"
        
        ban_res = client.post("/api/players/ban", json={"player": "BadActor", "reason": "Uso de Hacks / Trampas"})
        assert ban_res.status_code == 200
        assert ban_res.json()["status"] == "success"

        # Verify banned list reflects reason
        list_res = client.get("/api/players/list")
        assert list_res.status_code == 200
        banned = list_res.json()["banned"]
        bad_actor_entry = next((b for b in banned if b["name"].lower() == "badactor"), None)
        assert bad_actor_entry is not None
        assert bad_actor_entry["reason"] == "Uso de Hacks / Trampas"

        # Clean up test ban
        pardon_res = client.post("/api/players/pardon", json={"player": "BadActor"})
        assert pardon_res.status_code == 200
    finally:
        process_manager.get_status = orig_status

def test_ban_player_online_sends_command(client):
    """Verify online ban dispatches console command with reason."""
    orig_status = process_manager.get_status
    orig_send = process_manager.send_command
    try:
        process_manager.get_status = lambda: "RUNNING"
        commands_sent = []
        async def mock_send(cmd):
            commands_sent.append(cmd)
            return True
        process_manager.send_command = mock_send

        ban_online_res = client.post("/api/players/ban", json={"player": "TrollPlayer", "reason": "Griefing masivo"})
        assert ban_online_res.status_code == 200
        assert any("ban TrollPlayer Griefing masivo" in c for c in commands_sent)
    finally:
        process_manager.get_status = orig_status
        process_manager.send_command = orig_send
