import zipfile
import pytest
from fastapi.testclient import TestClient
from app.main import app, get_current_user
from app.config import settings

@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: True
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_file_create_and_rename(client):
    test_filename = "test_menu_file.txt"
    new_filename = "test_menu_renamed.txt"

    # 1. Create empty file
    res = client.post("/api/files/create", json={"path": test_filename})
    assert res.status_code == 200
    assert res.json()["status"] == "created"
    assert (settings.data_dir / test_filename).exists()

    # Attempt duplicate creation (should fail 400)
    dup_create = client.post("/api/files/create", json={"path": test_filename})
    assert dup_create.status_code == 400

    # 2. Rename file
    rename_res = client.post("/api/files/rename", json={"path": test_filename, "new_name": new_filename})
    assert rename_res.status_code == 200
    assert rename_res.json()["name"] == new_filename
    assert not (settings.data_dir / test_filename).exists()
    assert (settings.data_dir / new_filename).exists()

    # 3. Rename security check: Path traversal should fail
    bad_rename = client.post("/api/files/rename", json={"path": new_filename, "new_name": "../evil.txt"})
    assert bad_rename.status_code in [400, 403]

    # Clean up
    del_res = client.delete(f"/api/files/delete?path={new_filename}")
    assert del_res.status_code == 200
    assert not (settings.data_dir / new_filename).exists()

def test_file_duplicate_and_compress(client):
    source_file = "test_dup_source.json"
    content = '{"greeting": "hello dockraft"}'

    # Create file with content
    res_save = client.post("/api/files/save", json={"path": source_file, "content": content})
    assert res_save.status_code == 200

    # 1. Duplicate item
    dup_res = client.post("/api/files/duplicate", json={"path": source_file})
    assert dup_res.status_code == 200
    dup_name = dup_res.json()["new_name"]
    assert "test_dup_source.copy" in dup_name
    assert (settings.data_dir / dup_name).exists()

    # Verify content preserved
    assert (settings.data_dir / dup_name).read_text(encoding="utf-8") == content

    # 2. Compress to zip
    comp_res = client.post("/api/files/compress", json={"path": source_file})
    assert comp_res.status_code == 200
    archive_name = comp_res.json()["archive_name"]
    assert archive_name.endswith(".zip")
    assert (settings.data_dir / archive_name).exists()

    # 3. Clean up
    client.delete(f"/api/files/delete?path={source_file}")
    client.delete(f"/api/files/delete?path={dup_name}")
    client.delete(f"/api/files/delete?path={archive_name}")
    assert not (settings.data_dir / source_file).exists()
    assert not (settings.data_dir / dup_name).exists()
    assert not (settings.data_dir / archive_name).exists()

def test_bulk_delete(client):
    f1 = "test_bulk_del1.txt"
    f2 = "test_bulk_del2.txt"
    f3 = "test_bulk_del3.txt"

    client.post("/api/files/create", json={"path": f1})
    client.post("/api/files/create", json={"path": f2})
    client.post("/api/files/create", json={"path": f3})

    assert (settings.data_dir / f1).exists()
    assert (settings.data_dir / f2).exists()
    assert (settings.data_dir / f3).exists()

    res = client.post("/api/files/bulk-delete", json={"paths": [f1, f2, f3]})
    assert res.status_code == 200
    data = res.json()
    assert data["deleted_count"] == 3
    assert not (settings.data_dir / f1).exists()
    assert not (settings.data_dir / f2).exists()
    assert not (settings.data_dir / f3).exists()

def test_bulk_compress(client):
    f1 = "test_bcomp1.txt"
    f2 = "test_bcomp2.txt"
    archive = "test_bundle.zip"

    client.post("/api/files/save", json={"path": f1, "content": "file 1 content"})
    client.post("/api/files/save", json={"path": f2, "content": "file 2 content"})

    res = client.post("/api/files/bulk-compress", json={
        "paths": [f1, f2],
        "archive_name": archive
    })
    assert res.status_code == 200
    data = res.json()
    assert data["archive_name"] == archive
    zip_path = settings.data_dir / archive
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert f1 in namelist
        assert f2 in namelist

    # Clean up
    client.delete(f"/api/files/delete?path={f1}")
    client.delete(f"/api/files/delete?path={f2}")
    client.delete(f"/api/files/delete?path={archive}")
    assert not (settings.data_dir / f1).exists()
    assert not (settings.data_dir / f2).exists()
    assert not (settings.data_dir / archive).exists()
