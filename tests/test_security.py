import pytest
import time
from app.core.security import create_session_token, verify_session_token, verify_admin_password
from app.config import settings

def test_session_token_validation():
    token = create_session_token()
    assert verify_session_token(token) is True
    assert verify_session_token("invalid:token") is False
    assert verify_session_token("") is False

def test_token_expiration():
    # Token generated with past timestamp
    past_timestamp = str(int(time.time()) - 100)
    import hmac, hashlib
    sig = hmac.new(settings.secret_key.encode(), past_timestamp.encode(), hashlib.sha256).hexdigest()
    expired_token = f"{past_timestamp}:{sig}"
    
    # Should be valid for max_age=200
    assert verify_session_token(expired_token, max_age_seconds=200) is True
    # Should be expired for max_age=50
    assert verify_session_token(expired_token, max_age_seconds=50) is False

def test_password_verification():
    original_pass = settings.admin_password
    original_user = settings.admin_user
    try:
        settings.admin_password = "SecretPassword123"
        settings.admin_user = "custom_admin"
        assert verify_admin_password("SecretPassword123") is True
        assert verify_admin_password("WrongPassword") is False
    finally:
        settings.admin_password = original_pass
        settings.admin_user = original_user

def test_verify_admin_credentials():
    from app.core.security import verify_admin_credentials
    original_pass = settings.admin_password
    original_user = settings.admin_user
    try:
        settings.admin_user = "admin_dock"
        settings.admin_password = "SuperPassword2026!"
        
        # Valid credentials
        assert verify_admin_credentials("admin_dock", "SuperPassword2026!") is True
        # Invalid username
        assert verify_admin_credentials("wrong_user", "SuperPassword2026!") is False
        # Invalid password
        assert verify_admin_credentials("admin_dock", "wrong_pass") is False
        # Empty username / None
        assert verify_admin_credentials(None, "SuperPassword2026!") is False
    finally:
        settings.admin_password = original_pass
        settings.admin_user = original_user

def test_login_rate_limiter():
    from app.core.security import LoginRateLimiter
    limiter = LoginRateLimiter(max_attempts=5, cooldown_seconds=600)
    test_ip = "192.168.1.50"

    # Initially not locked
    locked, remaining = limiter.is_locked(test_ip)
    assert locked is False
    assert remaining == 0

    # 4 failures: still not locked
    for i in range(4):
        rem_att, cd = limiter.record_failure(test_ip)
        assert cd == 0
        assert rem_att == 5 - (i + 1)
        assert limiter.is_locked(test_ip)[0] is False

    # 5th failure: triggers 600s cooldown
    rem_att, cd = limiter.record_failure(test_ip)
    assert rem_att == 0
    assert cd == 600

    # Now locked
    locked, remaining = limiter.is_locked(test_ip)
    assert locked is True
    assert 590 <= remaining <= 600

    # Success from another IP shouldn't unlock test_ip
    limiter.record_success("192.168.1.99")
    assert limiter.is_locked(test_ip)[0] is True

    # Success from test_ip resets record
    limiter.record_success(test_ip)
    assert limiter.is_locked(test_ip)[0] is False

def test_is_authenticated_helper():
    from app.core.security import is_authenticated
    from fastapi import Request
    original_pass = settings.admin_password
    try:
        # Without password, open access
        settings.admin_password = ""
        mock_scope = {"type": "http", "headers": [], "cookies": {}, "query_string": b""}
        req = Request(mock_scope)
        assert is_authenticated(req) is True

        # With password
        settings.admin_password = "Secret"
        assert is_authenticated(req) is False

        # With valid token cookie
        token = create_session_token()
        cookie_header = f"dockraft_token={token}".encode()
        mock_scope_auth = {
            "type": "http",
            "headers": [(b"cookie", cookie_header)],
            "cookies": {"dockraft_token": token},
            "query_string": b""
        }
        req_auth = Request(mock_scope_auth)
        assert is_authenticated(req_auth) is True
    finally:
        settings.admin_password = original_pass
