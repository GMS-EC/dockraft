import pytest
import zipfile
import io
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.core.backup_manager import backup_manager

from app.core.security import create_session_token

client = TestClient(app)
client.cookies.set("dockraft_session", create_session_token())

def test_backup_create_list_restore_delete(tmp_path):
    # Setup a dummy server file
    dummy_file = settings.data_dir / "test_file.txt"
    dummy_file.write_text("hello minecraft world", encoding="utf-8")

    # 1. Create backup via API
    res = client.post("/api/backups/create", json={"tag": "test"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    filename = data["filename"]
    assert filename.startswith("backup_manual_") or filename.startswith("backup_test_") or "backup_" in filename

    # 2. List backups
    res_list = client.get("/api/backups/list")
    assert res_list.status_code == 200
    items = res_list.json()
    assert any(b["filename"] == filename for b in items)

    # 3. Download backup
    res_dl = client.get(f"/api/backups/download/{filename}")
    assert res_dl.status_code == 200
    assert len(res_dl.content) > 0

    # 4. Modify test file and restore
    dummy_file.write_text("corrupted content", encoding="utf-8")
    res_rest = client.post("/api/backups/restore", json={"filename": filename})
    assert res_rest.status_code == 200
    assert dummy_file.read_text(encoding="utf-8") == "hello minecraft world"

    # 5. Delete backup
    res_del = client.delete(f"/api/backups/{filename}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # Clean up dummy file
    if dummy_file.exists():
        dummy_file.unlink()

def test_backup_selective_scopes_and_targets(tmp_path):
    # Setup test files and folders
    world_dir = settings.data_dir / "world"
    world_dir.mkdir(parents=True, exist_ok=True)
    (world_dir / "level.dat").write_text("level data", encoding="utf-8")
    
    plugins_dir = settings.data_dir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    (plugins_dir / "plugin.jar").write_text("fake jar", encoding="utf-8")

    props_file = settings.data_dir / "server.properties"
    props_file.write_text("server-port=25565\n", encoding="utf-8")

    # Test GET targets
    res_targets = client.get("/api/backups/targets")
    assert res_targets.status_code == 200
    targets = res_targets.json()
    target_names = [t["name"] for t in targets]
    assert "world" in target_names
    assert "plugins" in target_names

    # Test create worlds-only backup
    res_w = client.post("/api/backups/create", json={"tag": "test", "scope": "worlds"})
    assert res_w.status_code == 200
    data_w = res_w.json()
    assert "worlds" in data_w["filename"]
    assert data_w["scope"] == "worlds"

    # Test create custom backup selecting only plugins
    res_c = client.post("/api/backups/create", json={"tag": "custom", "scope": "custom", "targets": ["plugins"]})
    assert res_c.status_code == 200
    data_c = res_c.json()
    assert "custom" in data_c["filename"]
    assert data_c["scope"] == "custom"

    # Verify list reports correct scope labels
    res_list = client.get("/api/backups/list")
    assert res_list.status_code == 200
    items = res_list.json()
    item_w = next((b for b in items if b["filename"] == data_w["filename"]), None)
    item_c = next((b for b in items if b["filename"] == data_c["filename"]), None)
    assert item_w is not None and item_w["scope"] == "worlds"
    assert item_c is not None and item_c["scope"] == "custom"

    # Clean up backups and test files
    client.delete(f"/api/backups/{data_w['filename']}")
    client.delete(f"/api/backups/{data_c['filename']}")
    if (world_dir / "level.dat").exists():
        (world_dir / "level.dat").unlink()
    try:
        if world_dir.exists():
            world_dir.rmdir()
    except OSError:
        pass
    if (plugins_dir / "plugin.jar").exists():
        (plugins_dir / "plugin.jar").unlink()
    try:
        if plugins_dir.exists():
            plugins_dir.rmdir()
    except OSError:
        pass

def test_backup_config_endpoints():
    res = client.get("/api/backups/config")
    assert res.status_code == 200
    cfg = res.json()
    assert "auto_backup" in cfg
    assert "backup_interval_hours" in cfg
    assert "backup_max_count" in cfg

    # Update config
    res_save = client.post("/api/backups/config", json={
        "auto_backup": True,
        "backup_interval_hours": 12,
        "backup_max_count": 7
    })
    assert res_save.status_code == 200
    updated = res_save.json()["config"]
    assert updated["auto_backup"] is True
    assert updated["backup_interval_hours"] == 12
    assert updated["backup_max_count"] == 7

def test_server_import_from_zip(tmp_path):
    # Build an in-memory zip representing a paper server
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("paper-1.21.4.jar", "fake-jar-data")
        zf.writestr("server.properties", "motd=ImportedServer\nserver-port=25565\n")
    zip_buffer.seek(0)

    res = client.post(
        "/api/server/import",
        files={"file": ("my_server.zip", zip_buffer.getvalue(), "application/zip")},
        data={"accept_eula": "true"}
    )
    assert res.status_code == 200
    resp_data = res.json()
    assert resp_data["status"] == "success"
    assert resp_data["server_type"] == "paper"

    # Clean up imported files
    jar = settings.data_dir / "paper-1.21.4.jar"
    if jar.exists():
        jar.unlink()
