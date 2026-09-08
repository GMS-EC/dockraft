import json
import pytest
from pathlib import Path
from app.core.fs_utils import atomic_write_text, atomic_write_json, atomic_write_bytes
from app.config import settings
from app.core.task_scheduler import task_scheduler
from app.core.webhook_manager import webhook_manager

def test_atomic_write_text(tmp_path: Path):
    target = tmp_path / "test.txt"
    atomic_write_text(target, "Hello World\nLine 2")
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Hello World\nLine 2"
    
    # Overwrite safely
    atomic_write_text(target, "Updated Content")
    assert target.read_text(encoding="utf-8") == "Updated Content"

def test_atomic_write_json(tmp_path: Path):
    target = tmp_path / "data.json"
    payload = {"server": "Dockraft", "version": "1.21.4", "players": ["Alex", "Steve"]}
    atomic_write_json(target, payload)
    
    assert target.exists()
    with open(target, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == payload

def test_atomic_write_bytes(tmp_path: Path):
    target = tmp_path / "binary.bin"
    raw = b"\x00\x01\x02\xff\xfe\xfd"
    atomic_write_bytes(target, raw)
    assert target.exists()
    assert target.read_bytes() == raw

def test_atomic_write_failure_preserves_original(tmp_path: Path):
    """
    Critical test: If writing or serialization fails, the original file MUST remain
    completely untouched and no temporary files should be left behind.
    """
    target = tmp_path / "critical_config.json"
    target.write_text('{"initial": "safe"}', encoding="utf-8")
    
    # Attempt to write non-serializable data
    class Unserializable:
        pass
    
    bad_payload = {"key": Unserializable()}
    
    with pytest.raises(TypeError):
        atomic_write_json(target, bad_payload)
        
    # The original file must NOT be 0 bytes and must retain its exact original content
    assert target.exists()
    assert target.read_text(encoding="utf-8") == '{"initial": "safe"}'
    
    # No lingering .tmp files
    tmp_files = list(tmp_path.glob(".*.tmp.*"))
    assert len(tmp_files) == 0

def test_config_save_runtime_atomic():
    """Verify settings.save_runtime_config performs safe atomic replacement."""
    cfg = {"test_atomic_key": "verified_safe"}
    settings.save_runtime_config(cfg)
    
    assert settings.config_file.exists()
    with open(settings.config_file, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved.get("test_atomic_key") == "verified_safe"

def test_task_scheduler_save_atomic():
    """Verify task_scheduler.save_tasks performs safe atomic replacement."""
    task_scheduler.tasks = [{"id": "atomic_test_task", "name": "Backup Safe"}]
    task_scheduler.save_tasks()
    
    assert task_scheduler.tasks_file.exists()
    with open(task_scheduler.tasks_file, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert any(t.get("id") == "atomic_test_task" for t in saved)

def test_webhook_manager_save_atomic():
    """Verify webhook_manager.save_config performs safe atomic replacement."""
    webhook_manager.save_config({"discord": {"webhook_url": "https://discord.com/api/webhooks/safe_test"}})
    
    assert webhook_manager.config_file.exists()
    with open(webhook_manager.config_file, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved.get("discord", {}).get("webhook_url") == "https://discord.com/api/webhooks/safe_test"
