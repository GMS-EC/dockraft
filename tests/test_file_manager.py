import pytest
from pathlib import Path
from fastapi import HTTPException
from app.core.file_manager import file_manager
from app.config import settings

def test_path_traversal_prevention():
    """Ensures attempts to break out of data_dir raise 403 Forbidden."""
    with pytest.raises(HTTPException) as exc_info:
        file_manager._resolve_safe_path("../../../etc/passwd")
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info2:
        file_manager._resolve_safe_path("..\\..\\windows\\system32")
    assert exc_info2.value.status_code == 403

def test_file_crud_operations():
    """Tests writing, reading, listing, and deleting a test file."""
    test_rel = "test_subfolder/greeting.txt"
    content = "Hello Minecraft Docker Dockraft!"

    # Write
    res_write = file_manager.write_file(test_rel, content)
    assert res_write["status"] == "saved"

    # Read
    res_read = file_manager.read_file(test_rel)
    assert res_read["content"] == content

    # List
    list_res = file_manager.list_directory("test_subfolder")
    assert any(item["name"] == "greeting.txt" for item in list_res["items"])

    # Delete
    del_res = file_manager.delete_item(test_rel)
    assert del_res["status"] == "deleted"

    # Clean up folder
    file_manager.delete_item("test_subfolder")

def test_disk_quota_enforcement():
    """Tests that writing files exceeding disk quota raises 400 Bad Request."""
    original_limit = settings.runtime_config.get("disk_limit_gb", 10.0)
    try:
        # Set quota to tiny value (e.g. 0.000001 GB ~ 1 KB)
        settings.runtime_config["disk_limit_gb"] = 0.000001
        
        # Attempt to write larger content
        large_content = "A" * 5000
        with pytest.raises(HTTPException) as exc_info:
            file_manager.write_file("quota_test.txt", large_content)
        assert exc_info.value.status_code == 400
        assert "Límite de espacio en disco superado" in exc_info.value.detail
    finally:
        settings.runtime_config["disk_limit_gb"] = original_limit
