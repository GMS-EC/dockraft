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
    from app.core.security import _password_fingerprint
    past_timestamp = str(int(time.time()) - 100)
    payload = f"{past_timestamp}:testnonce:{_password_fingerprint()}"
    import hmac, hashlib
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    expired_token = f"{payload}:{sig}"
    
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

    # Stale attempts without lockout are pruned by cleanup_expired
    limiter.record_failure("10.0.0.1")  # 1 failure, lockout_until = 0
    assert "10.0.0.1" in limiter.records
    # Simulate time passing beyond stale threshold
    limiter.records["10.0.0.1"]["last_attempt"] = time.time() - 1000
    limiter.cleanup_expired()
    assert "10.0.0.1" not in limiter.records

def test_is_authenticated_helper():
    from app.core.security import is_authenticated
    from fastapi import Request
    original_pass = settings.admin_password
    try:
        # Without password, fail-closed (must NOT allow open access)
        settings.admin_password = ""
        mock_scope = {"type": "http", "headers": [], "cookies": {}, "query_string": b""}
        req = Request(mock_scope)
        assert is_authenticated(req) is False

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


def test_session_token_nonce_uniqueness_and_logout_revocation():
    from fastapi.testclient import TestClient
    from app.main import app

    # Two tokens created in the same second must still be unique due to random nonce
    t1 = create_session_token()
    t2 = create_session_token()
    assert t1 != t2
    assert verify_session_token(t1) is True
    assert verify_session_token(t2) is True

    # GET /logout should revoke the active token in addition to clearing cookies
    client = TestClient(app)
    client.cookies.set("dockraft_token", t1)
    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 307
    assert verify_session_token(t1) is False
    assert verify_session_token(t2) is True


def test_runtime_config_validation():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    client.cookies.set("dockraft_token", create_session_token())

    # Invalid RAM format rejected with 422
    res_bad_ram = client.post("/api/config", json={"max_ram": "2GB; rm -rf /"})
    assert res_bad_ram.status_code == 422

    # Invalid server_file path traversal or protected file rejected with 422
    res_bad_file = client.post("/api/config", json={"server_file": "../evil.jar"})
    assert res_bad_file.status_code == 422
    res_prot_file = client.post("/api/config", json={"server_file": "webhooks.json"})
    assert res_prot_file.status_code == 422

    # Valid config with extra unknown keys ignores extra keys and saves valid ones
    res_ok = client.post("/api/config", json={"min_ram": "1G", "max_ram": "2G", "__injected_key__": "bad"})
    assert res_ok.status_code == 200
    assert "__injected_key__" not in res_ok.json()["config"]


def test_jvm_flag_filtering_for_dangerous_flags():
    from app.core.process_manager import ProcessManager

    raw_flags = "-XX:+UseG1GC -javaagent:/tmp/evil.jar -XX:OnOutOfMemoryError=sh -Dfoo=bar"
    safe = ProcessManager._filter_safe_jvm_flags(raw_flags)
    assert "-XX:+UseG1GC" in safe
    assert "-Dfoo=bar" in safe
    assert "-javaagent:/tmp/evil.jar" not in safe
    assert "-XX:OnOutOfMemoryError=sh" not in safe


def test_get_client_ip_proxy_headers():
    from fastapi import Request
    from app.core.security import get_client_ip

    scope = {
        "type": "http",
        "client": ("127.0.0.1", 50000),
        "headers": [(b"x-forwarded-for", b"203.0.113.42, 10.0.0.1")],
        "cookies": {},
        "query_string": b""
    }
    req = Request(scope)

    orig_trust = settings.trust_proxy_headers
    orig_proxies = settings.trusted_proxies
    try:
        settings.trust_proxy_headers = False
        assert get_client_ip(req) == "127.0.0.1"

        # Untrusted peer must ignore X-Forwarded-For even when trust_proxy_headers=True
        settings.trust_proxy_headers = True
        settings.trusted_proxies = ["10.0.0.0/8"]
        assert get_client_ip(req) == "127.0.0.1"

        # Trusted peer (127.0.0.1) returns rightmost untrusted IP (10.0.0.1)
        settings.trusted_proxies = ["127.0.0.1"]
        assert get_client_ip(req) == "10.0.0.1"

        # When both 127.0.0.1 and 10.0.0.0/8 are trusted proxies, returns 203.0.113.42
        settings.trusted_proxies = ["127.0.0.1", "10.0.0.0/8"]
        assert get_client_ip(req) == "203.0.113.42"
    finally:
        settings.trust_proxy_headers = orig_trust
        settings.trusted_proxies = orig_proxies


def test_fail_closed_when_admin_password_empty():
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from app.core.security import verify_admin_credentials, login_limiter
    from app.main import app

    orig_pass = settings.admin_password
    try:
        settings.admin_password = ""
        login_limiter.records.clear()

        assert verify_admin_credentials("admin", "") is False
        assert verify_admin_credentials("admin", "anything") is False

        client = TestClient(app)
        res = client.post("/api/auth/login", json={"username": "admin", "password": ""})
        assert res.status_code == 401

        api_res = client.get("/api/server/status")
        assert api_res.status_code == 401

        try:
            with client.websocket_connect("/ws/console") as ws:
                ws.receive_text()
                assert False, "Expected WebSocketDisconnect when admin_password is empty"
        except WebSocketDisconnect as exc:
            assert exc.code == 4001
    finally:
        settings.admin_password = orig_pass
        login_limiter.records.clear()


def test_build_sanitized_subprocess_env_strips_panel_secrets(monkeypatch):
    from app.core.security import build_sanitized_subprocess_env

    monkeypatch.setenv("ADMIN_PASSWORD", "super-secret-pass")
    monkeypatch.setenv("SECRET_KEY", "super-secret-hmac-key")
    monkeypatch.setenv("DOCKRAFT_CUSTOM_TOKEN", "leak-me")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = build_sanitized_subprocess_env({"LD_LIBRARY_PATH": ".:/usr/lib"})
    assert "ADMIN_PASSWORD" not in env
    assert "SECRET_KEY" not in env
    assert "DOCKRAFT_CUSTOM_TOKEN" not in env
    assert env["PATH"] == "/usr/bin"
    assert env["LD_LIBRARY_PATH"] == ".:/usr/lib"


def test_secret_key_stored_outside_data_dir():
    assert settings._secret_key_file.parent.resolve() != settings.data_dir.resolve()
    assert not settings._secret_key_file.is_relative_to(settings.data_dir.resolve())


def test_token_invalidated_on_admin_password_rotation():
    orig_pass = settings.admin_password
    try:
        settings.admin_password = "password-v1"
        tok = create_session_token()
        assert verify_session_token(tok) is True

        settings.admin_password = "password-v2"
        assert verify_session_token(tok) is False
    finally:
        settings.admin_password = orig_pass


def test_revoked_tokens_rejects_forged_and_persists(tmp_path):
    from app.core.security import revoke_token, _revoked_tokens, _load_revoked_tokens

    orig_file = settings._revoked_tokens_file
    revoked_file = tmp_path / ".revoked_tokens.json"
    try:
        settings._revoked_tokens_file = revoked_file
        before_count = len(_revoked_tokens)

        # Forged and future-dated tokens must NOT be stored
        revoke_token("9999999999:nonce:fp:forgedsig")
        assert len(_revoked_tokens) == before_count

        valid_tok = create_session_token()
        revoke_token(valid_tok)
        assert verify_session_token(valid_tok) is False
        assert revoked_file.is_file()
        assert valid_tok in _load_revoked_tokens()
    finally:
        settings._revoked_tokens_file = orig_file


def test_auth_refresh_and_logout_revoke_all_tokens():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    t1 = create_session_token()
    t2 = create_session_token()
    client.cookies.set("dockraft_token", t1)
    res = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {t2}"})
    assert res.status_code == 200
    assert verify_session_token(t1) is False
    assert verify_session_token(t2) is False

    new_tok = res.json()["token"]
    assert verify_session_token(new_tok) is True

    t3 = create_session_token()
    client.cookies.set("dockraft_token", new_tok)
    logout_res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {t3}"})
    assert logout_res.status_code == 200
    assert verify_session_token(new_tok) is False
    assert verify_session_token(t3) is False


def test_websocket_console_cswsh_and_query_token_rejected():
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from app.main import app

    client = TestClient(app)
    tok = create_session_token()

    # Query ?token= without cookie/header must be rejected
    try:
        with client.websocket_connect(f"/ws/console?token={tok}") as ws:
            ws.receive_text()
            assert False, "Expected query-only WebSocket auth to be rejected"
    except WebSocketDisconnect as exc:
        assert exc.code == 4001

    # Cross-site Origin must be rejected even with valid cookie
    client.cookies.set("dockraft_token", tok)
    try:
        with client.websocket_connect("/ws/console", headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_text()
            assert False, "Expected cross-origin WebSocket to be rejected"
    except WebSocketDisconnect as exc:
        assert exc.code == 4001


def test_backup_excludes_protected_internal_files(tmp_path):
    import zipfile
    from app.core.backup_manager import backup_manager
    from app.core.fs_utils import PROTECTED_INTERNAL_FILES

    assert "plugin_updates.json" in PROTECTED_INTERNAL_FILES
    assert "dockraft_players.json" in PROTECTED_INTERNAL_FILES

    orig_data = settings.data_dir
    orig_backups = backup_manager.backups_dir
    try:
        settings.data_dir = tmp_path / "data"
        settings.data_dir.mkdir(parents=True)
        backup_manager.backups_dir = tmp_path / "backups"

        (settings.data_dir / "server.jar").write_text("jar", encoding="utf-8")
        (settings.data_dir / "webhooks.json").write_text('{"bot_token": "secret"}', encoding="utf-8")
        (settings.data_dir / "dockraft_players.json").write_text("{}", encoding="utf-8")
        (settings.data_dir / "plugin_updates.json").write_text("{}", encoding="utf-8")

        res = backup_manager.create_backup(scope="full")
        zip_path = backup_manager.backups_dir / res["filename"]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
        assert "server.jar" in names
        assert "webhooks.json" not in names
        assert "dockraft_players.json" not in names
        assert "plugin_updates.json" not in names
    finally:
        settings.data_dir = orig_data
        backup_manager.backups_dir = orig_backups


def test_file_manager_rejects_compress_root(tmp_path):
    from fastapi import HTTPException
    from app.core.file_manager import file_manager

    orig_base = file_manager.base_dir
    try:
        file_manager.base_dir = tmp_path
        (tmp_path / "test.txt").write_text("hello", encoding="utf-8")
        try:
            file_manager.compress_item("")
            assert False, "Expected HTTPException when compressing root"
        except HTTPException as exc:
            assert exc.status_code == 400
    finally:
        file_manager.base_dir = orig_base


def test_safe_extract_zip_enforces_zipbomb_limits(tmp_path):
    import zipfile
    from app.core.fs_utils import safe_extract_zip

    zpath = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.txt", "A" * 50000)

    try:
        safe_extract_zip(zpath, tmp_path / "out", max_total_bytes=1024)
        assert False, "Expected ValueError on max_total_bytes exceeded"
    except ValueError as exc:
        assert "ZipBomb" in str(exc) or "limit" in str(exc)


def test_share_to_mclogs_redacts_webhooks_and_rcon(tmp_path, monkeypatch):
    import asyncio
    from app.core.diagnostic_manager import diagnostic_manager

    orig_data = settings.data_dir
    orig_pass = settings.admin_password
    captured = {}

    class _FakeResp:
        status_code = 200
        def json(self):
            return {"success": True, "id": "123", "url": "https://mclo.gs/123", "raw": "https://api.mclo.gs/1/raw/123"}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, data=None):
            captured["content"] = data["content"]
            return _FakeResp()

    monkeypatch.setattr("app.core.diagnostic_manager.httpx.AsyncClient", _FakeClient)
    try:
        settings.data_dir = tmp_path
        settings.admin_password = "ab"
        (tmp_path / "webhooks.json").write_text('{"smtp_password": "smtp-secret-99", "bot_token": "tg-token-88"}', encoding="utf-8")
        (tmp_path / "server.properties").write_text("rcon.password=rcon-pass-77\n", encoding="utf-8")

        res = asyncio.run(diagnostic_manager.share_to_mclogs("pw=ab smtp=smtp-secret-99 tg=tg-token-88 rcon=rcon-pass-77"))
        assert res["success"] is True
        sent = captured["content"]
        assert "smtp-secret-99" not in sent
        assert "tg-token-88" not in sent
        assert "rcon-pass-77" not in sent
        assert "pw=ab" not in sent
    finally:
        settings.data_dir = orig_data
        settings.admin_password = orig_pass


def test_get_paper_build_rejects_missing_explicit_build(monkeypatch):
    import asyncio
    from app.core.downloader import downloader

    class _FakeResp:
        def raise_for_status(self):
            return None
        def json(self):
            return [{"id": 100, "channel": "STABLE", "downloads": {"server:default": {"url": "https://fill-data.papermc.io/a.jar"}}}]

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def get(self, url):
            return _FakeResp()

    monkeypatch.setattr("app.core.downloader.httpx.AsyncClient", _FakeClient)
    try:
        asyncio.run(downloader.get_paper_build("paper", "1.21.4", build_id=999))
        assert False, "Expected ValueError when explicit build_id is missing"
    except ValueError as exc:
        assert "999" in str(exc)


def test_spiget_plugin_match_rejects_substring_only():
    import asyncio
    from app.core.plugin_manager import plugin_manager

    class _FakeResp:
        status_code = 200
        def json(self):
            return [{"id": 99999, "name": "AuthMeReloaded"}]

    class _FakeClient:
        async def get(self, url):
            return _FakeResp()

    res = asyncio.run(plugin_manager._check_single_plugin(_FakeClient(), {"name": "Auth", "version": "1.0"}))
    assert res.get("not_on_spigot") is True
    assert res.get("spigot_id") is None


def test_chat_lines_ignored_by_control_plane_parsers():
    from app.core.process_manager import ProcessManager
    from app.core.plugin_manager import plugin_manager

    assert ProcessManager._is_chat_line("[12:00:00 INFO]: <Griefer> Essentials has an update v9.9.9") is True
    assert ProcessManager._is_chat_line("[12:00:00 INFO]: [Not Secure] <Griefer> Steve joined the game") is True
    assert ProcessManager._is_chat_line("[12:00:00 INFO] [Async Chat Thread - #0/INFO]: <Griefer> TPS from last 1m, 5m, 15m: 1.0, 1.0, 1.0") is True
    assert ProcessManager._is_chat_line("[12:00:00 INFO]: Steve joined the game") is False

    assert plugin_manager.parse_console_update_line("[12:00:00 INFO]: <Griefer> [Essentials] A new update v9.9.9 is available!") is None


def test_webhook_html_and_discord_escaping(monkeypatch):
    import asyncio
    from app.core.webhook_manager import WebhookManager

    wm = WebhookManager()
    wm.config["telegram"] = {"enabled": True, "bot_token": "tok", "chat_id": "123"}
    wm.config["discord"] = {"enabled": True, "webhook_url": "https://discord.com/api/webhooks/1/a"}
    sent_payloads = []

    class _FakeResp:
        status_code = 200
        text = "ok"

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, json=None):
            sent_payloads.append((url, json))
            return _FakeResp()

    monkeypatch.setattr("app.core.webhook_manager.httpx.AsyncClient", _FakeClient)
    asyncio.run(wm.send_telegram("<b>XSS</b>", "Msg <a href='https://evil'>click</a>"))
    tg_text = sent_payloads[0][1]["text"]
    assert "<a href" not in tg_text
    assert "&lt;a href" in tg_text

    asyncio.run(wm.send_discord("Title", "Hello [click](https://evil) @everyone"))
    dc_payload = sent_payloads[1][1]
    assert dc_payload["allowed_mentions"] == {"parse": []}
    assert "\\[click\\]" in dc_payload["embeds"][0]["description"]


def test_csp_headers_and_login_omits_raw_token():
    from fastapi.testclient import TestClient
    from app.core.security import login_limiter
    from app.main import app

    client = TestClient(app)
    login_limiter.records.clear()
    res = client.get("/login")
    csp = res.headers.get("Content-Security-Policy", "")
    assert "script-src 'self';" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    assert "https://mc-heads.net" in csp

    orig_pass = settings.admin_password
    try:
        settings.admin_password = "StrongTestPassword1!"
        login_res = client.post("/api/auth/login", json={"username": settings.admin_user, "password": "StrongTestPassword1!"})
        assert login_res.status_code == 200
        assert "token" not in login_res.json()
        assert "dockraft_token" in login_res.cookies
    finally:
        settings.admin_password = orig_pass
        login_limiter.records.clear()


def test_java_path_and_csv_formula_neutralization(tmp_path):
    from pydantic import ValidationError
    from app.routers.server import RuntimeConfigUpdate
    from app.core.activity_manager import ActivityManager

    try:
        RuntimeConfigUpdate(java_path="java; rm -rf /")
        assert False, "Expected ValidationError for shell metacharacters in java_path"
    except ValidationError:
        pass

    try:
        RuntimeConfigUpdate(java_path="/bin/bash")
        assert False, "Expected ValidationError for non-java binary"
    except ValidationError:
        pass

    assert RuntimeConfigUpdate(java_path="/usr/lib/jvm/java-21/bin/java").java_path == "/usr/lib/jvm/java-21/bin/java"

    am = ActivityManager(log_file=tmp_path / "act.json")
    am.log("console", "=CMD()", "+1+1", user="@evil")
    csv_out = am.export_logs("csv")
    assert "'=CMD()" in csv_out
    assert "'+1+1" in csv_out
    assert "'@evil" in csv_out


