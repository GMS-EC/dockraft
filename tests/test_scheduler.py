import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.task_scheduler import task_scheduler

from app.core.security import create_session_token

client = TestClient(app)
client.cookies.set("dockraft_session", create_session_token())

def test_task_scheduler_crud():
    # 1. Create task with interval
    res = client.post("/api/tasks", json={
        "name": "Test Interval Task",
        "action": "restart",
        "schedule_type": "interval",
        "interval_value": 2,
        "interval_unit": "hours",
        "enabled": True
    })
    assert res.status_code == 200
    task_data = res.json()
    task_id = task_data["id"]
    assert task_data["name"] == "Test Interval Task"
    assert task_data["next_run"] is not None

    # 2. List tasks
    res_list = client.get("/api/tasks")
    assert res_list.status_code == 200
    tasks = res_list.json()
    assert any(t["id"] == task_id for t in tasks)

    # 3. Get task
    res_get = client.get(f"/api/tasks/{task_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == task_id

    # 4. Toggle task
    res_toggle = client.post(f"/api/tasks/{task_id}/toggle", json={"enabled": False})
    assert res_toggle.status_code == 200
    assert res_toggle.json()["enabled"] is False
    assert res_toggle.json()["next_run"] is None

    # 5. Update task to Cron
    res_update = client.put(f"/api/tasks/{task_id}", json={
        "name": "Updated Cron Task",
        "schedule_type": "cron",
        "cron_expression": "0 3 * * *",
        "enabled": True
    })
    assert res_update.status_code == 200
    updated = res_update.json()
    assert updated["schedule_type"] == "cron"
    assert updated["cron_expression"] == "0 3 * * *"
    assert updated["next_run"] is not None

    # 6. Delete task
    res_del = client.delete(f"/api/tasks/{task_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # Verify deleted
    res_get_deleted = client.get(f"/api/tasks/{task_id}")
    assert res_get_deleted.status_code == 404
