import pytest
from fastapi.testclient import TestClient
from app.main import app

from app.core.security import create_session_token

client = TestClient(app)
client.cookies.set("dockraft_session", create_session_token())

def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

def test_api_auth_status():
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert "authenticated" in res.json()

def test_api_server_status():
    res = client.get("/api/server/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "memory_mb" in data
    assert "assigned_memory_mb" in data
    assert "memory_percent" in data
    assert "cpu_percent" in data
    assert "disk_used_mb" in data
    assert "disk_limit_mb" in data
    assert "disk_percent" in data
    assert "server_type" in data
    assert "server_version" in data

def test_api_config_endpoints():
    res = client.get("/api/config")
    assert res.status_code == 200
    assert "server_type" in res.json()
    assert "server_name" in res.json()

    # Save a custom server name
    res_save = client.post("/api/config", json={"server_name": "Mi Super Servidor"})
    assert res_save.status_code == 200
    assert res_save.json()["config"]["server_name"] == "Mi Super Servidor"

def test_api_files_list():
    res = client.get("/api/files/list")
    assert res.status_code == 200
    assert "items" in res.json()

def test_api_properties():
    res = client.get("/api/server/properties")
    assert res.status_code == 200
    data = res.json()
    assert "exists" in data
    assert "server_type" in data

def test_save_properties_with_aliases():
    # Test saving Bedrock properties with alias syncing
    bedrock_payload = {
        "server-name": "My Bedrock Realm",
        "server-port": "19132",
        "allow-list": "true",
        "tick-distance": "6"
    }
    res = client.post("/api/server/properties", json=bedrock_payload)
    assert res.status_code == 200

    # Read back and verify aliases synced
    res_get = client.get("/api/server/properties")
    assert res_get.status_code == 200
    props = res_get.json().get("properties", {})
    assert props.get("server-name") == "My Bedrock Realm"
    assert props.get("motd") == "My Bedrock Realm"
    assert props.get("allow-list") == "true"
    assert props.get("white-list") == "true"
    assert props.get("tick-distance") == "6"

def test_api_update_info():
    res = client.get("/api/installer/update-info")
    assert res.status_code == 200
    data = res.json()
    assert "is_installed" in data
    assert "update_available" in data
    assert "available_versions" in data

def test_api_update_requires_installed():
    # If invalid version or manifest not found, it responds with 400 or 404
    res = client.post("/api/installer/update", json={"version": "invalid-version-xyz"})
    assert res.status_code in [400, 404]

def test_api_server_delete():
    from app.config import settings
    dummy_server = settings.data_dir / "server_test.jar"
    dummy_server.write_text("fake-server-binary", encoding="utf-8")
    
    # Backups directory must NOT be deleted
    backups_dir = settings.data_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    dummy_backup = backups_dir / "preserve_test.zip"
    dummy_backup.write_text("backup-data", encoding="utf-8")

    res = client.post("/api/server/delete")
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    # Verify server file deleted and backup preserved
    assert not dummy_server.exists()
    assert dummy_backup.exists()

    # Clean up test backup
    if dummy_backup.exists():
        dummy_backup.unlink()

def test_login_rate_limiting_and_auth_flow():
    from app.config import settings
    from app.core.security import login_limiter
    
    original_pass = settings.admin_password
    original_user = settings.admin_user
    
    try:
        settings.admin_password = "SecretPassword123"
        settings.admin_user = "admin"
        login_limiter.records.clear()

        # 4 wrong attempts -> returns 401
        for i in range(4):
            res = client.post("/api/auth/login", json={"username": "admin", "password": "WrongPassword"})
            assert res.status_code == 401
            assert "Intentos restantes" in res.json()["detail"]

        # 5th attempt -> triggers 429 Too Many Requests
        res_5th = client.post("/api/auth/login", json={"username": "admin", "password": "WrongPassword"})
        assert res_5th.status_code == 429
        assert "Retry-After" in res_5th.headers
        assert "Acceso bloqueado durante 10 minutos" in res_5th.json()["detail"]

        # 6th attempt while locked -> still 429
        res_locked = client.post("/api/auth/login", json={"username": "admin", "password": "SecretPassword123"})
        assert res_locked.status_code == 429
        assert "Retry-After" in res_locked.headers

        # Unlock IP
        login_limiter.records.clear()

        # Correct login now succeeds
        res_ok = client.post("/api/auth/login", json={"username": "admin", "password": "SecretPassword123"})
        assert res_ok.status_code == 200
        assert res_ok.json()["status"] == "success"
        assert "dockraft_token" in res_ok.cookies
    finally:
        settings.admin_password = original_pass
        settings.admin_user = original_user
        login_limiter.records.clear()

def test_page_routes_and_template_rendering():
    from app.config import settings
    from app.core.security import create_session_token
    original_pass = settings.admin_password
    try:
        settings.admin_password = "SecretPassword123"
        client.cookies.clear()

        # 1. Unauthenticated root request redirects to /login
        res_root_unauth = client.get("/", follow_redirects=False)
        assert res_root_unauth.status_code == 307
        assert res_root_unauth.headers["location"] == "/login"

        # 2. Login page renders login.html template
        res_login_page = client.get("/login")
        assert res_login_page.status_code == 200
        assert "Dockraft" in res_login_page.text
        assert "login-card" in res_login_page.text
        assert "login-password" in res_login_page.text

        # 3. Authenticated user visiting /login redirects to /
        token = create_session_token()
        client.cookies.set("dockraft_token", token)
        res_login_auth = client.get("/login", follow_redirects=False)
        assert res_login_auth.status_code == 307
        assert res_login_auth.headers["location"] == "/"

        # 4. Authenticated user visiting / renders index.html with components & footer
        res_root_auth = client.get("/")
        assert res_root_auth.status_code == 200
        assert "Dockraft" in res_root_auth.text
        assert "main-container" in res_root_auth.text
        assert "app-footer" in res_root_auth.text
        assert "https://gmsec.cc" in res_root_auth.text

        # 5. Logout endpoint
        res_logout = client.get("/logout", follow_redirects=False)
        assert res_logout.status_code == 307
        assert res_logout.headers["location"] == "/login"
    finally:
        settings.admin_password = original_pass
        client.cookies.clear()
