from pathlib import Path
from fastapi.testclient import TestClient

from app.config import settings
from app.core.security import create_session_token
from app.main import app


def test_get_instance_label_priority(monkeypatch, tmp_path):
    orig_inst_name = settings.instance_name
    orig_inst_dir = settings.instance_dir
    orig_server_name = settings.runtime_config.get("server_name")

    try:
        # 1. Explicit INSTANCE_NAME takes top priority
        settings.instance_name = "Cobblemon-Norte"
        settings.runtime_config["server_name"] = "Otro Nombre"
        assert settings.get_instance_label() == "Cobblemon-Norte"

        # 2. Without INSTANCE_NAME, non-default server_name is used
        settings.instance_name = ""
        settings.runtime_config["server_name"] = "Survival Técnico"
        assert settings.get_instance_label() == "Survival Técnico"

        # 3. With default server_name inside desktop instancias/<slug>, folder name is used
        inst_dir = tmp_path / "instancias" / "instancia-2"
        inst_dir.mkdir(parents=True)
        settings.instance_dir = inst_dir
        settings.runtime_config["server_name"] = "Mi Servidor Dockraft"
        assert settings.get_instance_label() == "instancia-2"

        # 4. Outside instancias/ with default name falls back cleanly
        settings.instance_dir = tmp_path
        assert settings.get_instance_label() == "Mi Servidor Dockraft"
    finally:
        settings.instance_name = orig_inst_name
        settings.instance_dir = orig_inst_dir
        if orig_server_name is not None:
            settings.runtime_config["server_name"] = orig_server_name


def test_login_and_dashboard_render_instance_identifier(monkeypatch):
    orig_inst_name = settings.instance_name
    orig_admin_pwd = settings.admin_password
    try:
        settings.admin_password = "test-admin-password"
        settings.instance_name = 'Instancia-<Alfa> & "2"'

        client = TestClient(app)

        login_res = client.get("/login")
        assert login_res.status_code == 200
        assert 'id="login-instance-badge"' in login_res.text
        assert "Instancia-&lt;Alfa&gt; &amp; &#34;2&#34;" in login_res.text
        assert "<title>Instancia-&lt;Alfa&gt;" in login_res.text

        tok = create_session_token()
        client.cookies.set("dockraft_token", tok)

        home_res = client.get("/")
        assert home_res.status_code == 200
        assert 'id="sidebar-instance-name"' in home_res.text
        assert 'data-locked="true"' in home_res.text
        assert "Instancia-&lt;Alfa&gt; &amp; &#34;2&#34;" in home_res.text

        status_res = client.get("/api/server/status")
        assert status_res.status_code == 200
        assert status_res.json()["instance_name"] == 'Instancia-<Alfa> & "2"'
    finally:
        settings.instance_name = orig_inst_name
        settings.admin_password = orig_admin_pwd


def test_docker_entrypoint_uses_lf_and_nonroot_privilege_drop():
    ep = Path("docker-entrypoint.sh")
    raw = ep.read_bytes()
    assert b"\r\n" not in raw, "docker-entrypoint.sh must use LF line endings"
    text = raw.decode("utf-8")
    assert "setpriv --reuid=" in text
    assert "PUID=1000" in text
    assert "exec \"$@\"" in text
