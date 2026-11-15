import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import create_session_token
from app.core.downloader import DownloadManager, downloader
from app.core.backup_manager import backup_manager
from app.core.process_manager import process_manager
from app.core.task_scheduler import TaskScheduler


client = TestClient(app)
client.cookies.set("dockraft_session", create_session_token())


def test_downloader_progress_property():
    dm = DownloadManager()
    assert dm.progress["is_downloading"] is False
    assert dm.progress["status"] == "idle"
    assert dm.progress["percent"] == 0

    for active_state in ("downloading", "extracting"):
        dm.active_download = {"status": active_state, "percent": 42}
        prog = dm.progress
        assert prog["is_downloading"] is True
        assert prog["status"] == active_state
        assert prog["percent"] == 42

    for inactive_state in ("completed", "idle", "error: network"):
        dm.active_download = {"status": inactive_state, "percent": 100}
        assert dm.progress["is_downloading"] is False


def test_backup_manager_checks_downloader_progress_without_attribute_error(monkeypatch):
    monkeypatch.setattr(downloader, "active_download", {"status": "downloading", "percent": 10})
    with pytest.raises(HTTPException) as exc_info:
        backup_manager.create_backup()
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_task_scheduler_backup_action_uses_downloader_progress(monkeypatch):
    scheduler = TaskScheduler()
    calls = []

    monkeypatch.setattr(process_manager, "is_installed", lambda: True)
    monkeypatch.setattr(process_manager, "get_status", lambda: "OFFLINE")
    monkeypatch.setattr(downloader, "active_download", None)
    monkeypatch.setattr(
        backup_manager,
        "create_backup",
        lambda **kwargs: calls.append(kwargs) or {"status": "success", "filename": "ok.zip"},
    )
    monkeypatch.setattr(backup_manager, "prune_backups", lambda max_count=5: None)
    monkeypatch.setattr(scheduler, "save_tasks", lambda: None)

    task = {
        "id": "t_backup",
        "name": "Backup",
        "action": "backup",
        "enabled": True,
    }
    res = await scheduler.execute_task_action(task)
    assert res["status"] == "success"
    assert len(calls) == 1
    assert "ok.zip" in res["message"]

    monkeypatch.setattr(downloader, "active_download", {"status": "downloading", "percent": 50})
    res_busy = await scheduler.execute_task_action(task)
    assert "Instalación en progreso" in res_busy["message"]
    assert len(calls) == 1


def test_api_responses_have_no_cache_headers():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert "no-store" in res.headers.get("cache-control", "")
    assert res.headers.get("pragma") == "no-cache"
    assert res.headers.get("expires") == "0"

    res_page = client.get("/")
    assert res_page.status_code == 200
    assert "no-store" not in res_page.headers.get("cache-control", "")


def test_file_delete_reflects_immediately_in_listing():
    rel_path = "__dockraft_delete_cache_test.txt"
    create_res = client.post("/api/files/create", json={"path": rel_path})
    assert create_res.status_code == 200

    list_before = client.get("/api/files/list").json()["items"]
    assert any(item["name"] == rel_path for item in list_before)

    del_res = client.delete("/api/files/delete", params={"path": rel_path})
    assert del_res.status_code == 200

    list_after = client.get("/api/files/list").json()["items"]
    assert not any(item["name"] == rel_path for item in list_after)
