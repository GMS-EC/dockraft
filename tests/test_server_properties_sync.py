import io
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.downloader import downloader
from app.core.process_manager import process_manager
from app.core.security import create_session_token
from app.core.server_properties import (
    ensure_initial_server_properties,
    parse_properties_text,
    read_instance_mc_port,
    sync_property_aliases,
    update_server_properties_port,
)
from app.main import app


def _make_bedrock_props_text(
    *,
    server_name: str = "Dedicated Server",
    allow_list: str = "true",
    port: str = "19132",
    portv6: str = "19133",
    udp_ports: str = "19132",
) -> str:
    return (
        f"server-name={server_name}\n"
        "gamemode=survival\n"
        "difficulty=easy\n"
        f"allow-list={allow_list}\n"
        f"server-port={port}\n"
        f"server-portv6={portv6}\n"
        "transport=nethernet\n"
        f"server-udp-ports={udp_ports}\n"
    )


def test_fresh_bedrock_zip_aligns_mc_port_and_disables_allow_list(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MC_PORT", raising=False)
    inst_dir = tmp_path / "inst_bedrock"
    data_dir = inst_dir / "data"
    data_dir.mkdir(parents=True)
    (inst_dir / ".env").write_text("PORT=8000\nMC_PORT=25565\n", encoding="utf-8")
    (data_dir / "server.properties").write_text(_make_bedrock_props_text(), encoding="utf-8")

    ensure_initial_server_properties(
        data_dir,
        server_type="bedrock",
        server_name="Mi Bedrock LAN",
        instance_dir=inst_dir,
        sync_initial_defaults=True,
    )

    props = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props["server-port"] == "25565"
    assert props["server-udp-ports"] == "25565"
    assert props["server-portv6"] == "26565"
    assert props["allow-list"] == "false"
    sync_property_aliases(props)
    assert props["white-list"] == "false"
    assert props["server-name"] == "Mi Bedrock LAN"
    assert props["motd"] == "Mi Bedrock LAN"
    assert props["transport"] == "nethernet"


def test_fresh_bedrock_docker_mode_preserves_19132_and_disables_allow_list(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MC_PORT", raising=False)
    inst_dir = tmp_path / "docker_inst"
    data_dir = inst_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "server.properties").write_text(_make_bedrock_props_text(), encoding="utf-8")

    ensure_initial_server_properties(
        data_dir,
        server_type="bedrock",
        server_name="Docker Bedrock",
        instance_dir=inst_dir,
        sync_initial_defaults=True,
    )

    props = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props["server-port"] == "19132"
    assert props["server-udp-ports"] == "19132"
    assert props["server-portv6"] == "19133"
    assert props["allow-list"] == "false"


def test_fresh_java_initial_config_defaults_and_custom_port(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MC_PORT", raising=False)
    inst_dir = tmp_path / "inst_java"
    data_dir = inst_dir / "data"
    data_dir.mkdir(parents=True)
    (inst_dir / ".env").write_text("PORT=8001\nMC_PORT=25570\n", encoding="utf-8")

    ensure_initial_server_properties(
        data_dir,
        server_type="paper",
        server_name="Survival Paper",
        instance_dir=inst_dir,
        sync_initial_defaults=True,
    )

    props = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props["server-port"] == "25570"
    assert props["white-list"] == "false"
    assert props["enforce-whitelist"] == "false"
    assert props["motd"] == "Survival Paper"
    assert props["server-name"] == "Survival Paper"


def test_update_preserves_user_allow_list_and_reconciles_port(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MC_PORT", raising=False)
    inst_dir = tmp_path / "inst_update"
    data_dir = inst_dir / "data"
    data_dir.mkdir(parents=True)
    (inst_dir / ".env").write_text("MC_PORT=25566\n", encoding="utf-8")
    (data_dir / "server.properties").write_text(
        _make_bedrock_props_text(server_name="Mi Servidor Privado", allow_list="true"),
        encoding="utf-8",
    )

    ensure_initial_server_properties(
        data_dir,
        server_type="bedrock",
        server_name="Otro Nombre",
        instance_dir=inst_dir,
        sync_initial_defaults=False,
    )

    props = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props["allow-list"] == "true"
    assert props["server-name"] == "Mi Servidor Privado"
    assert props["server-port"] == "25566"
    assert props["server-udp-ports"] == "25566"


@pytest.mark.asyncio
async def test_process_manager_start_server_reconciles_port_before_launch(tmp_path: Path, monkeypatch):
    inst_dir = tmp_path / "inst_start"
    data_dir = inst_dir / "data"
    data_dir.mkdir(parents=True)
    (inst_dir / ".env").write_text("MC_PORT=25568\n", encoding="utf-8")
    (data_dir / "bedrock_server.exe").write_text("stub", encoding="utf-8")
    (data_dir / "bedrock_server").write_text("stub", encoding="utf-8")
    (data_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    (data_dir / "server.properties").write_text(
        _make_bedrock_props_text(allow_list="false", port="19132", udp_ports="19132"),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "instance_dir", inst_dir)
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setitem(settings.runtime_config, "server_type", "bedrock")
    monkeypatch.setitem(settings.runtime_config, "server_file", "bedrock_server")
    monkeypatch.setattr(process_manager, "process", None)
    monkeypatch.setattr(process_manager, "status", "OFFLINE")

    class _EmptyReader:
        async def readline(self):
            return b""

    class _FakeProc:
        def __init__(self):
            self.pid = 999999
            self.stdin = None
            self.stdout = _EmptyReader()
            self.returncode = 0

        async def wait(self):
            return 0

    async def _fake_exec(*_args, **_kwargs):
        return _FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)

    res = await process_manager.start_server()
    assert res["status"] == "success"

    for task in (process_manager._reader_task, process_manager._supervisor_task, process_manager._tps_poller_task):
        if task and not task.done():
            task.cancel()
    process_manager.process = None
    process_manager.status = "OFFLINE"

    props = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props["server-port"] == "25568"
    assert props["server-udp-ports"] == "25568"


def test_api_save_properties_syncs_bedrock_udp_and_env_mc_port(tmp_path: Path, monkeypatch):
    inst_dir = tmp_path / "inst_api"
    data_dir = inst_dir / "data"
    data_dir.mkdir(parents=True)
    (inst_dir / ".env").write_text("PORT=8000\nMC_PORT=25565\n", encoding="utf-8")
    (data_dir / "server.properties").write_text(
        _make_bedrock_props_text(allow_list="false", port="25565", udp_ports="25565"),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "instance_dir", inst_dir)
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setitem(settings.runtime_config, "server_type", "bedrock")

    client = TestClient(app)
    client.cookies.set("dockraft_session", create_session_token())

    res = client.post(
        "/api/server/properties",
        json={
            "server-name": "Bedrock API",
            "server-port": "25571",
            "server-portv6": "26571",
            "server-udp-ports": "25565",
            "allow-list": "false",
        },
    )
    assert res.status_code == 200
    assert read_instance_mc_port(inst_dir) == 25571

    props = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props["server-port"] == "25571"
    assert props["server-udp-ports"] == "25571"

    res_raw = client.post(
        "/api/server/properties/raw",
        json={"content": "server-port=25572\nmotd=Raw Test\n"},
    )
    assert res_raw.status_code == 200
    assert read_instance_mc_port(inst_dir) == 25572


def test_launcher_update_mc_server_port_and_restart_on_port_change(tmp_path: Path, monkeypatch):
    import launcher

    inst_dir = tmp_path / "inst_launcher"
    data_dir = inst_dir / "data"
    data_dir.mkdir(parents=True)
    (inst_dir / ".env").write_text("HOST=127.0.0.1\nPORT=8000\nMC_PORT=25565\n", encoding="utf-8")
    (data_dir / "server.properties").write_text(
        _make_bedrock_props_text(allow_list="false", port="19132", udp_ports="19132"),
        encoding="utf-8",
    )

    prev = launcher._update_mc_server_port(inst_dir, 25575)
    assert prev == 19132
    props = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props["server-port"] == "25575"
    assert props["server-udp-ports"] == "25575"
    assert props["server-portv6"] == "26575"

    calls = []
    monkeypatch.setattr(launcher, "_ACTIVE_INSTANCE_DIR", inst_dir.resolve())
    monkeypatch.setattr(launcher, "_is_port_open", lambda _p: True)

    def _fake_action(web_port, target, action="status"):
        calls.append((web_port, Path(target).resolve(), action))
        return True, "restarted" if action == "restart" else "RUNNING"

    monkeypatch.setattr(launcher, "_request_instance_mc_action", _fake_action)

    outcome, _msg = launcher._apply_port_change_sync_and_restart(
        inst_dir, old_web=8000, new_web=8000, old_mc=25565, new_mc=25575, prev_prop_port=19132
    )
    assert outcome == "restarted"
    assert calls == [(8000, inst_dir.resolve(), "restart")]

    # Offline MC server should not report error or restart failure
    monkeypatch.setattr(launcher, "_request_instance_mc_action", lambda *_a, **_kw: (True, "offline"))
    outcome_off, _ = launcher._apply_port_change_sync_and_restart(
        inst_dir, old_web=8000, new_web=8000, old_mc=25565, new_mc=25575, prev_prop_port=25565
    )
    assert outcome_off == "saved_offline"

    # Web port change on child instance should stop old panel, respawn on new_web, and restore running MC server
    child_dir = tmp_path / "inst_child"
    child_dir.mkdir(parents=True)
    child_calls = []
    monkeypatch.setattr(launcher, "_request_instance_mc_action", lambda wp, td, act="status": (
        child_calls.append(("action", wp, act)) or (True, "RUNNING" if act == "status" else "success")
    ))
    monkeypatch.setattr(launcher, "_stop_instance", lambda td, wp: child_calls.append(("stop", wp)) or (True, "ok"))
    monkeypatch.setattr(launcher, "_spawn_instance_background", lambda td, wp: child_calls.append(("spawn", wp)))
    monkeypatch.setattr(launcher, "_wait_for_port", lambda _h, _p, timeout=12.0: True)

    outcome_web, _ = launcher._apply_port_change_sync_and_restart(
        child_dir, old_web=8001, new_web=8002, old_mc=25566, new_mc=25566, prev_prop_port=25566
    )
    assert outcome_web == "restarted"
    assert child_calls == [
        ("action", 8001, "status"),
        ("stop", 8001),
        ("spawn", 8002),
        ("action", 8002, "start"),
    ]


@pytest.mark.asyncio
async def test_downloader_zip_install_vs_update_config_sync(tmp_path: Path, monkeypatch):
    inst_dir = tmp_path / "inst_dl"
    data_dir = inst_dir / "data"
    data_dir.mkdir(parents=True)
    (inst_dir / ".env").write_text("MC_PORT=25580\n", encoding="utf-8")

    monkeypatch.delenv("MC_PORT", raising=False)
    monkeypatch.setattr(settings, "instance_dir", inst_dir)
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setitem(settings.runtime_config, "server_type", "bedrock")
    monkeypatch.setitem(settings.runtime_config, "server_name", "Bedrock Zip")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bedrock_server", "binary-stub")
        zf.writestr("server.properties", _make_bedrock_props_text(allow_list="true", port="19132", udp_ports="19132"))
    zip_bytes = buf.getvalue()

    class _StreamResp:
        status_code = 200
        headers = {"content-length": str(len(zip_bytes))}
        url = httpx.URL("https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-1.26.63.1.zip")

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, chunk_size=65536):
            yield zip_bytes

    class _StreamCtx:
        async def __aenter__(self):
            return _StreamResp()

        async def __aexit__(self, *args):
            return False

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, _method, _url):
            return _StreamCtx()

    monkeypatch.setattr("app.core.downloader.httpx.AsyncClient", _FakeClient)

    # Fresh install
    await downloader.download_file(
        "https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-1.26.63.1.zip",
        "bedrock-server.zip",
        is_zip=True,
        preserve_existing_configs=False,
        verify_integrity=False,
    )
    props_fresh = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props_fresh["allow-list"] == "false"
    assert props_fresh["server-port"] == "25580"
    assert props_fresh["server-udp-ports"] == "25580"
    assert "eula=true" in (data_dir / "eula.txt").read_text(encoding="utf-8")

    # User enables allow-list manually, then performs a Bedrock version update (preserve_existing_configs=True)
    update_server_properties_port(data_dir / "server.properties", 25580, server_type="bedrock")
    text_user = (data_dir / "server.properties").read_text(encoding="utf-8").replace("allow-list=false", "allow-list=true")
    (data_dir / "server.properties").write_text(text_user, encoding="utf-8")

    await downloader.download_file(
        "https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-1.26.63.1.zip",
        "bedrock-server.zip",
        is_zip=True,
        preserve_existing_configs=True,
        verify_integrity=False,
    )
    props_updated = parse_properties_text((data_dir / "server.properties").read_text(encoding="utf-8"))
    assert props_updated["allow-list"] == "true"
    assert props_updated["server-port"] == "25580"
