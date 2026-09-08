import time
import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.core.security import (
    create_session_token,
    verify_session_token,
    get_session_max_age,
    get_token_age
)

@pytest.fixture
def client():
    return TestClient(app)

def test_default_session_timeout():
    """Verify that the default session timeout is 60 minutes (3600 seconds)."""
    orig = settings.runtime_config.get("session_timeout_minutes")
    try:
        settings.runtime_config["session_timeout_minutes"] = 60
        assert get_session_max_age() == 3600
    finally:
        if orig is not None:
            settings.runtime_config["session_timeout_minutes"] = orig

def test_verify_session_token_expired():
    """Verify that tokens older than the session timeout are rejected."""
    orig = settings.runtime_config.get("session_timeout_minutes")
    try:
        settings.runtime_config["session_timeout_minutes"] = 60  # 3600s
        
        # Valid token (just created)
        fresh_token = create_session_token()
        assert verify_session_token(fresh_token) is True
        
        # Expired token (created 3700 seconds ago)
        past_time = str(int(time.time()) - 3700)
        sig = hmac.new(settings.secret_key.encode(), past_time.encode(), hashlib.sha256).hexdigest()
        expired_token = f"{past_time}:{sig}"
        assert verify_session_token(expired_token) is False
        
        # Token age helper
        assert get_token_age(expired_token) >= 3700
    finally:
        if orig is not None:
            settings.runtime_config["session_timeout_minutes"] = orig

def test_custom_session_timeout():
    """Verify that updating runtime_config immediately updates session max age."""
    orig = settings.runtime_config.get("session_timeout_minutes")
    try:
        settings.runtime_config["session_timeout_minutes"] = 10  # 10 minutes = 600s
        assert get_session_max_age() == 600
        
        # Token created 700 seconds ago is expired
        past_time = str(int(time.time()) - 700)
        sig = hmac.new(settings.secret_key.encode(), past_time.encode(), hashlib.sha256).hexdigest()
        token = f"{past_time}:{sig}"
        assert verify_session_token(token) is False
        
        # Token created 300 seconds ago is still valid
        recent_time = str(int(time.time()) - 300)
        sig2 = hmac.new(settings.secret_key.encode(), recent_time.encode(), hashlib.sha256).hexdigest()
        token2 = f"{recent_time}:{sig2}"
        assert verify_session_token(token2) is True
    finally:
        if orig is not None:
            settings.runtime_config["session_timeout_minutes"] = orig

def test_auth_status_includes_timeout(client):
    """Verify that /api/auth/status returns the session_timeout_minutes."""
    orig_pass = settings.admin_password
    try:
        settings.admin_password = "SecretPassword2026!"
        token = create_session_token()
        res = client.get("/api/auth/status", cookies={"dockraft_token": token})
        assert res.status_code == 200
        data = res.json()
        assert "session_timeout_minutes" in data
        assert data["session_timeout_minutes"] == get_session_max_age() // 60
    finally:
        settings.admin_password = orig_pass

def test_auth_refresh_endpoint(client):
    """Verify the /api/auth/refresh endpoint issues a fresh token and cookie."""
    orig_pass = settings.admin_password
    try:
        settings.admin_password = "SecretPassword2026!"
        
        # Unauthenticated refresh fails with 401
        res = client.post("/api/auth/refresh")
        assert res.status_code == 401
        
        # Authenticated refresh succeeds
        token = create_session_token()
        res = client.post("/api/auth/refresh", cookies={"dockraft_token": token})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "token" in data
        assert verify_session_token(data["token"]) is True
        assert "dockraft_token" in res.cookies
    finally:
        settings.admin_password = orig_pass

def test_expired_token_rejected_on_api(client):
    """Verify that an expired token results in a 401 Unauthorized response on protected APIs."""
    orig_pass = settings.admin_password
    try:
        settings.admin_password = "SecretPassword2026!"
        
        # Token older than 7 days or custom timeout
        past_time = str(int(time.time()) - 999999)
        sig = hmac.new(settings.secret_key.encode(), past_time.encode(), hashlib.sha256).hexdigest()
        expired_token = f"{past_time}:{sig}"
        
        res = client.get("/api/server/status", cookies={"dockraft_token": expired_token})
        assert res.status_code == 401
    finally:
        settings.admin_password = orig_pass

def test_login_page_expired_param(client):
    """Verify that /login?expired=1 renders the login page and clears expired cookies."""
    orig_pass = settings.admin_password
    try:
        settings.admin_password = "SecretPassword2026!"
        res = client.get("/login?expired=1", follow_redirects=False)
        assert res.status_code == 200
        assert "Sesión Caducada" in res.text
    finally:
        settings.admin_password = orig_pass
