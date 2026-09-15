import pytest
from fastapi.testclient import TestClient
from app.main import app, get_current_user
from app.core.metrics_manager import metrics_manager

@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: True
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_metrics_sample_recording():
    metrics_manager.reset()
    sample = metrics_manager.record_sample()

    assert "disk_used_mb" in sample
    assert "disk_limit_mb" in sample
    assert "disk_percent" in sample
    assert sample["disk_percent"] >= 0.0
    assert len(metrics_manager.get_history()) == 1

def test_metrics_history_and_summary(client):
    metrics_manager.record_sample()
    res = client.get("/api/metrics/history")
    assert res.status_code == 200
    data = res.json()

    assert "history" in data
    assert "summary" in data
    assert isinstance(data["history"], list)

    summary = data["summary"]
    assert "disk_used_mb" in summary
    assert "disk_limit_mb" in summary
    assert "disk_free_mb" in summary
    assert "disk_percent" in summary
    assert "disk_limit_gb" in summary
    assert "tps" in summary

def test_metrics_reset(client):
    metrics_manager.record_sample()
    assert len(metrics_manager.get_history()) > 0

    res = client.post("/api/metrics/reset")
    assert res.status_code == 200
    assert res.json()["status"] == "reset"
    assert len(metrics_manager.get_history()) == 0
