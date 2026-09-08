import os
import tempfile
import zipfile
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.activity_manager import ActivityManager
from app.core.downloader import verify_file_integrity
from app.core.security import get_current_user, create_session_token
from app.main import app

@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: True
    c = TestClient(app)
    c.cookies.set("dockraft_session", create_session_token())
    yield c
    app.dependency_overrides.clear()

@pytest.fixture
def temp_activity_mgr(tmp_path):
    log_file = tmp_path / "test_activity_logs.json"
    mgr = ActivityManager(log_file=str(log_file), max_entries=10)
    return mgr

def test_activity_manager_logging_and_filtering(temp_activity_mgr):
    mgr = temp_activity_mgr

    # Log several actions across categories
    mgr.log("console", "Comando ejecutado", "list", user="admin", status="success")
    mgr.log("console", "Comando ejecutado", "op Steve", user="admin", status="success")
    mgr.log("server", "Inicio de servidor", "Servidor iniciado en puerto 25565", user="system", status="success")
    mgr.log("backup", "Copia creada", "backup_manual_123.zip", user="admin", status="success")
    mgr.log("update", "Actualización aplicada", "Actualizado a 1.21.4", user="admin", status="success")

    # Verify counts
    res_all = mgr.get_logs()
    assert res_all["total"] == 5
    assert res_all["counts"]["console"] == 2
    assert res_all["counts"]["server"] == 1
    assert res_all["counts"]["backup"] == 1

    # Filter by category
    res_console = mgr.get_logs(category="console")
    assert res_console["total"] == 2
    assert all(item["category"] == "console" for item in res_console["logs"])

    # Search filter
    res_search = mgr.get_logs(search="Steve")
    assert res_search["total"] == 1
    assert "Steve" in res_search["logs"][0]["details"]

def test_activity_manager_ring_buffer(temp_activity_mgr):
    mgr = temp_activity_mgr # max_entries = 10
    for i in range(15):
        mgr.log("console", "cmd", f"say message {i}")

    res = mgr.get_logs()
    assert res["total"] == 10
    # Newest should be 'say message 14'
    assert res["logs"][0]["details"] == "say message 14"

def test_activity_manager_exports_and_clear(temp_activity_mgr):
    mgr = temp_activity_mgr
    mgr.log("console", "Comando", "whitelist add Alex", user="marcus", status="success")
    mgr.log("backup", "Respaldo", "pre-update.zip", user="system", status="info")

    csv_data = mgr.export_logs(format_type="csv")
    assert "whitelist add Alex" in csv_data
    assert "timestamp,category,action" in csv_data

    json_data = mgr.export_logs(format_type="json")
    assert "pre-update.zip" in json_data

    txt_data = mgr.export_logs(format_type="txt")
    assert "DOCKRAFT - REGISTRO DE AUDITORÍA" in txt_data

    # Clear logs
    mgr.clear_logs()
    assert mgr.get_logs()["total"] == 0

def test_downloader_integrity_verification(tmp_path):
    # 1. Non-existent file
    with pytest.raises(ValueError, match="no existe"):
        verify_file_integrity(str(tmp_path / "non_existent.jar"))

    # 2. Too small file (< 512 KB for jar)
    tiny_jar = tmp_path / "tiny.jar"
    tiny_jar.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    with pytest.raises(ValueError, match="incompleto o truncado"):
        verify_file_integrity(str(tiny_jar), expected_type="paper")

    # 3. Corrupted ZIP (magic bytes OK, but truncated archive)
    corrupt_jar = tmp_path / "corrupt.jar"
    corrupt_jar.write_bytes(b"PK\x03\x04" + b"\x00" * 600000)
    with pytest.raises(ValueError, match="corrupto o dañado"):
        verify_file_integrity(str(corrupt_jar), expected_type="paper")

    # 4. Valid ZIP / JAR (using random bytes so compressed file exceeds 512 KB)
    valid_jar = tmp_path / "valid.jar"
    with zipfile.ZipFile(str(valid_jar), "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        zf.writestr("content.bin", os.urandom(600000))
    assert verify_file_integrity(str(valid_jar), expected_type="paper") is True

def test_api_activity_endpoints(client):
    # Auth is provided via authenticated client fixture
    res = client.get("/api/activity/logs")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert "counts" in data

    # Export
    res_export = client.get("/api/activity/export?format=csv")
    assert res_export.status_code == 200
    assert "text/csv" in res_export.headers.get("content-type", "")

@pytest.mark.asyncio
async def test_update_server_workflow_with_safe_shutdown_and_backup(tmp_path, client):

    with patch("app.main.process_manager") as mock_pm, \
         patch("app.main.backup_manager") as mock_bm, \
         patch("app.main.downloader") as mock_dl, \
         patch("app.main.activity_manager") as mock_act, \
         patch("app.main._is_server_installed", return_value=True), \
         patch.object(settings, "runtime_config", {"server_type": "paper", "server_version": "1.21.3"}):

        status_val = "RUNNING"
        def get_stat():
            return status_val

        mock_pm.get_status.side_effect = get_stat
        mock_pm.is_running.return_value = True

        async def fake_send_cmd(*args, **kwargs): return True
        async def fake_stop():
            nonlocal status_val
            status_val = "OFFLINE"
            return True
        async def fake_start():
            nonlocal status_val
            status_val = "RUNNING"
            return True
        async def fake_backup(*args, **kwargs): return {"filename": "pre-update-1.21.4.zip"}
        async def fake_dl(*args, **kwargs): return tmp_path / "server.jar"
        async def fake_broadcast(*args, **kwargs): pass
        async def fake_paper_build(proj, ver): return {"download_url": "https://example.com/paper-1.21.4.jar"}

        mock_pm.send_command.side_effect = fake_send_cmd
        mock_pm.stop_server.side_effect = fake_stop
        mock_pm.start_server.side_effect = fake_start
        mock_pm.broadcast_message.side_effect = fake_broadcast
        mock_bm.create_backup.side_effect = fake_backup
        mock_dl.download_file.side_effect = fake_dl
        mock_dl.get_paper_latest_build.side_effect = fake_paper_build

        tasks_to_run = []
        def capture_task(coro):
            tasks_to_run.append(coro)
            return MagicMock()

        with patch("asyncio.create_task", side_effect=capture_task), \
             patch("asyncio.sleep", return_value=None):
            res = client.post("/api/installer/update", json={"version": "1.21.4"})
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "started"
            assert data["auto_stopping"] is True

            # Run the captured background safe_update_pipeline
            assert len(tasks_to_run) == 1
            await tasks_to_run[0]

            # Verify safe shutdown: save-all command sent, stop_server called
            mock_pm.send_command.assert_called_with("save-all", echo=False)
            mock_pm.stop_server.assert_called_once()

            # Verify automatic safety backup was created
            mock_bm.create_backup.assert_called_once()
            assert "pre-update-1.21.4" in mock_bm.create_backup.call_args[1].get("tag")

            # Verify integrity verified download was initiated
            mock_dl.download_file.assert_called_once()
            assert mock_dl.download_file.call_args[1].get("verify_integrity") is True

            # Verify server was auto-restarted
            mock_pm.start_server.assert_called_once()

            # Verify activity logged
            assert any(call[1].get("category") == "update" or "update" in str(call) for call in mock_act.log.call_args_list)

def test_activity_manager_7_day_retention(temp_activity_mgr):
    import time
    mgr = temp_activity_mgr
    now = time.time()

    # Add an entry from 10 days ago (expired)
    old_entry = mgr.log("console", "Old Command", "help", status="success")
    old_entry["created_at"] = now - (10 * 86400)

    # Add an entry from 8 days ago (expired)
    old_entry_2 = mgr.log("server", "Old Event", "restart", status="info")
    old_entry_2["created_at"] = now - (8 * 86400)

    # Add an entry from 2 days ago (retained)
    recent_entry = mgr.log("console", "Recent Command", "list", status="success")
    recent_entry["created_at"] = now - (2 * 86400)

    # Add an entry from today (retained)
    mgr.log("console", "Today Command", "say hello", status="success")

    # Query logs; expired entries should be pruned automatically
    res = mgr.get_logs()
    assert res["total"] == 2
    actions = [e["action"] for e in res["logs"]]
    assert "Today Command" in actions
    assert "Recent Command" in actions
    assert "Old Command" not in actions
    assert "Old Event" not in actions

@pytest.mark.asyncio
async def test_send_command_offline_logging():
    from app.core.process_manager import process_manager
    from app.core.activity_manager import activity_manager

    # Ensure process is None
    process_manager.process = None
    process_manager.status = "OFFLINE"

    with patch.object(activity_manager, "log") as mock_log, \
         patch.object(process_manager, "broadcast_message") as mock_broadcast:
        res = await process_manager.send_command("list", echo=True)
        assert res["status"] == "error"
        assert "Server is not running" in res["message"]

        # Verify it logged to activity_manager
        mock_log.assert_called_once_with(
            category="console",
            action="Comando no ejecutado",
            details="list",
            user="admin",
            status="warning"
        )
