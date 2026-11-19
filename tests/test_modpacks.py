import hashlib
import io
import json
import sys
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.downloader import DownloadManager
from app.core.modpack_manager import ModpackManager
from app.core.process_manager import ProcessManager
from app.core.security import create_session_token, get_current_user
from app.main import app


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: True
    c = TestClient(app)
    c.cookies.set("dockraft_session", create_session_token())
    yield c
    app.dependency_overrides.clear()


def _build_mrpack_bytes(
    *,
    name: str = "Test Pack",
    version_id: str = "1.0.0",
    dependencies: dict = None,
    files: list = None,
    extra_entries: dict = None,
) -> bytes:
    buf = io.BytesIO()
    manifest = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": version_id,
        "name": name,
        "dependencies": dependencies or {"minecraft": "1.21.1", "fabric-loader": "0.20.1"},
        "files": files or [],
    }
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("modrinth.index.json", json.dumps(manifest))
        for k, v in (extra_entries or {}).items():
            zf.writestr(k, v)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_modpack_search_filters_loaders_and_server_side():
    captured_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "project_id": "5FFgwNNP",
                        "slug": "cobblemon-fabric",
                        "title": "Cobblemon Official Modpack [Fabric]",
                        "description": "Play Cobblemon cleanly",
                        "author": "Cobblemon",
                        "icon_url": "https://cdn.modrinth.com/icon.png",
                        "downloads": 11000000,
                        "follows": 90000,
                        "categories": ["adventure", "fabric", "optimization"],
                        "versions": ["1.20.1", "1.21.1"],
                        "latest_version": "YQpPe5Iu",
                        "server_side": "required",
                    },
                    {
                        "project_id": "ignored1",
                        "slug": "datapack-only",
                        "title": "Unsupported Loader Pack",
                        "categories": ["datapack"],
                        "versions": ["1.21.1"],
                        "server_side": "required",
                    },
                ],
                "total_hits": 2,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    mgr = ModpackManager()

    with patch(
        "app.core.modpack_manager.httpx.AsyncClient",
        side_effect=lambda **kw: real_client(transport=transport, headers=kw.get("headers")),
    ):
        res = await mgr.search_projects(query="cobblemon", project_type="modpack", loader="fabric")

    facets = json.loads(captured_params["facets"])
    assert ["project_type:modpack"] in facets
    assert ["server_side:required", "server_side:optional"] in facets
    assert ["categories:fabric"] in facets
    assert len(res["hits"]) == 1
    assert res["hits"][0]["slug"] == "cobblemon-fabric"
    assert res["hits"][0]["loaders"] == ["fabric"]
    assert res["hits"][0]["url"] == "https://modrinth.com/modpack/cobblemon-fabric"


@pytest.mark.parametrize(
    "dep_key,expected_loader,loader_ver",
    [
        ("fabric-loader", "fabric", "0.20.1"),
        ("neoforge", "neoforge", "21.1.264"),
        ("forge", "forge", "47.2.20"),
        ("quilt-loader", "quilt", "0.26.4"),
    ],
)
def test_parse_mrpack_manifest_loaders_and_client_skip(tmp_path, dep_key, expected_loader, loader_ver):
    pack_path = tmp_path / f"{expected_loader}.mrpack"
    raw = _build_mrpack_bytes(
        name=f"Pack {expected_loader}",
        dependencies={"minecraft": "1.21.1", dep_key: loader_ver},
        files=[
            {"path": "mods/cobblemon.jar", "env": {"client": "required", "server": "required"}, "downloads": ["https://cdn.modrinth.com/c.jar"]},
            {"path": "mods/optional.jar", "env": {"client": "required", "server": "optional"}, "downloads": ["https://cdn.modrinth.com/o.jar"]},
            {"path": "mods/iris-client-only.jar", "env": {"client": "required", "server": "unsupported"}, "downloads": ["https://cdn.modrinth.com/i.jar"]},
        ],
    )
    pack_path.write_bytes(raw)

    parsed = ModpackManager.parse_mrpack_manifest(pack_path)
    assert parsed["mc_version"] == "1.21.1"
    assert parsed["loader_type"] == expected_loader
    assert parsed["loader_version"] == loader_ver
    assert len(parsed["server_files"]) == 2
    assert parsed["skipped_client_files"] == 1
    assert all(f["path"] != "mods/iris-client-only.jar" for f in parsed["server_files"])


def test_extract_mrpack_overrides_precedence_and_zipslip_protection(tmp_path):
    mgr = ModpackManager()
    data_dir = tmp_path / "server"
    data_dir.mkdir()
    (data_dir / "dockraft_config.json").write_text('{"keep": true}', encoding="utf-8")

    # 1. Precedence + protected internal file preservation + client-overrides skip
    pack_ok = tmp_path / "ok.mrpack"
    pack_ok.write_bytes(
        _build_mrpack_bytes(
            extra_entries={
                "overrides/config/cobblemon.json": '{"shinyRate": 8192}',
                "overrides/config/common.txt": "from-overrides",
                "server-overrides/config/common.txt": "from-server-overrides",
                "client-overrides/options.txt": "should-not-extract",
                "overrides/dockraft_config.json": '{"evil": true}',
            }
        )
    )
    written = mgr._extract_mrpack_overrides(pack_ok, data_dir)
    assert written == 3
    assert (data_dir / "config" / "cobblemon.json").read_text(encoding="utf-8") == '{"shinyRate": 8192}'
    assert (data_dir / "config" / "common.txt").read_text(encoding="utf-8") == "from-server-overrides"
    assert not (data_dir / "options.txt").exists()
    assert (data_dir / "dockraft_config.json").read_text(encoding="utf-8") == '{"keep": true}'

    # 2. ZipSlip attempt must fail loudly
    pack_evil = tmp_path / "evil.mrpack"
    pack_evil.write_bytes(
        _build_mrpack_bytes(extra_entries={"overrides/../../outside.txt": "pwn"})
    )
    with pytest.raises(ValueError):
        mgr._extract_mrpack_overrides(pack_evil, data_dir)


@pytest.mark.asyncio
async def test_download_verified_file_sha512_and_ssrf_blocks(tmp_path):
    mgr = ModpackManager()

    with pytest.raises(ValueError):
        mgr._validate_download_url("http://cdn.modrinth.com/mod.jar")
    with pytest.raises(ValueError):
        mgr._validate_download_url("https://localhost/mod.jar")
    with pytest.raises(ValueError):
        mgr._validate_download_url("https://127.0.0.1/mod.jar")
    with pytest.raises(ValueError):
        mgr._validate_download_url("https://169.254.169.254/latest/meta-data")

    payload = b"cobblemon-mod-bytes"
    valid_sha512 = hashlib.sha512(payload).hexdigest()
    transport = httpx.MockTransport(lambda req: httpx.Response(200, headers={"content-length": str(len(payload))}, content=payload))

    dest = tmp_path / "mods" / "cobblemon.jar"
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RuntimeError):
            await mgr._download_verified_file(client, ["https://cdn.modrinth.com/mod.jar"], dest, expected_sha512="0" * 128)
        assert not dest.exists()

        out = await mgr._download_verified_file(client, ["https://cdn.modrinth.com/mod.jar"], dest, expected_sha512=valid_sha512)
        assert out == dest
        assert dest.read_bytes() == payload


@pytest.mark.asyncio
async def test_resolve_mod_dependencies_recursive_and_skips_client_deps():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v2/project/cobblemon":
            return httpx.Response(200, json={"id": "cobblemon_id", "title": "Cobblemon", "server_side": "required"})
        if path == "/v2/project/P7dR8mSH/version":
            return httpx.Response(200, json=[{
                "id": "fapi_v1",
                "project_id": "P7dR8mSH",
                "version_number": "0.110.0+1.21.1",
                "files": [{"filename": "fabric-api-0.110.0.jar", "url": "https://cdn.modrinth.com/fapi.jar", "primary": True, "size": 1000, "hashes": {"sha512": "a" * 128}}],
                "dependencies": [
                    {"project_id": "clientonly_id", "dependency_type": "required"},
                    {"project_id": "corelib_id", "dependency_type": "required"},
                ],
            }])
        if path == "/v2/project/P7dR8mSH":
            return httpx.Response(200, json={"id": "P7dR8mSH", "title": "Fabric API", "server_side": "required"})
        if path == "/v2/project/clientonly_id/version":
            return httpx.Response(200, json=[{
                "id": "co_v1",
                "project_id": "clientonly_id",
                "version_number": "1.0",
                "files": [{"filename": "client-ui.jar", "url": "https://cdn.modrinth.com/co.jar", "primary": True, "size": 500, "hashes": {}}],
                "dependencies": [],
            }])
        if path == "/v2/project/clientonly_id":
            return httpx.Response(200, json={"id": "clientonly_id", "title": "Client HUD", "server_side": "unsupported"})
        if path == "/v2/project/corelib_id/version":
            return httpx.Response(200, json=[{
                "id": "cl_v1",
                "project_id": "corelib_id",
                "version_number": "2.0",
                "files": [{"filename": "corelib-2.0.jar", "url": "https://cdn.modrinth.com/corelib.jar", "primary": True, "size": 750, "hashes": {"sha512": "b" * 128}}],
                "dependencies": [{"project_id": "cobblemon_id", "dependency_type": "required"}],  # cycle check
            }])
        if path == "/v2/project/corelib_id":
            return httpx.Response(200, json={"id": "corelib_id", "title": "CoreLib", "server_side": "optional"})
        return httpx.Response(404)

    mgr = ModpackManager()
    root_ver = {
        "id": "cb_184",
        "project_id": "cobblemon_id",
        "project_title": "Cobblemon",
        "version_number": "1.8.4F",
        "files": [{"filename": "Cobblemon-fabric-1.8.4.jar", "url": "https://cdn.modrinth.com/cb.jar", "primary": True, "size": 5000, "hashes": {"sha512": "c" * 128}}],
        "dependencies": [{"project_id": "P7dR8mSH", "dependency_type": "required"}],
    }

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resolved = await mgr.resolve_mod_dependencies(root_ver, loader="fabric", mc_version="1.21.1", client=client)

    names = [m["filename"] for m in resolved]
    assert names == ["Cobblemon-fabric-1.8.4.jar", "fabric-api-0.110.0.jar", "corelib-2.0.jar"]
    assert "client-ui.jar" not in names


@pytest.mark.asyncio
async def test_modpack_endpoints_install_concurrent_409_and_upload_mrpack(tmp_path, client):
    from contextlib import ExitStack

    with ExitStack() as stack:
        mock_pm = stack.enter_context(patch("app.main.process_manager"))
        mock_dl = stack.enter_context(patch("app.main.downloader"))
        mock_act = stack.enter_context(patch("app.main.activity_manager"))
        mock_mp = stack.enter_context(patch("app.main.modpack_manager"))
        stack.enter_context(patch("app.main._is_server_installed", return_value=False))
        stack.enter_context(patch.object(settings, "data_dir", tmp_path))
        stack.enter_context(patch.object(settings, "config_file", tmp_path / "dockraft_config.json"))
        stack.enter_context(patch("app.routers.installer._background_tasks", set()))

        mock_pm.get_status.return_value = "OFFLINE"
        mock_dl.active_download = {"status": "idle", "percent": 0}
        mock_mp.install_modrinth_modpack = AsyncMock(return_value={"status": "completed"})

        tasks_to_run = []
        def capture_task(coro):
            tasks_to_run.append(coro)
            return MagicMock()

        with patch("asyncio.create_task", side_effect=capture_task):
            res = client.post(
                "/api/installer/modpacks/install",
                json={
                    "project_type": "modpack",
                    "project_id": "cobblemon-fabric",
                    "version_id": "YQpPe5Iu",
                    "server_name": "Cobblemon Amigos",
                    "max_ram": "4G",
                },
            )
            assert res.status_code == 200
            assert res.json()["status"] == "started"

            prog = client.get("/api/installer/progress").json()
            assert prog["status"] == "downloading_modpack"
            assert prog["is_active"] is True
            assert prog["is_downloading"] is True

            # Concurrent install blocked cleanly
            dup = client.post(
                "/api/installer/modpacks/install",
                json={"project_type": "modpack", "project_id": "other", "version_id": "v1"},
            )
            assert dup.status_code == 409

            await tasks_to_run[0]
            mock_mp.install_modrinth_modpack.assert_awaited_once()

            # Test /upload-mrpack rejects invalid extension
            mock_dl.active_download = {"status": "idle", "percent": 0}
            bad_ext = client.post(
                "/api/installer/modpacks/upload-mrpack",
                files={"file": ("notpack.zip", b"123", "application/zip")},
            )
            assert bad_ext.status_code == 400

            # Test /upload-mrpack accepts real .mrpack and runs install_from_mrpack
            mod_bytes = b"mod-jar-binary"
            mod_sha512 = hashlib.sha512(mod_bytes).hexdigest()
            mr_bytes = _build_mrpack_bytes(
                name="Local Cobblemon Pack",
                version_id="1.8.4",
                dependencies={"minecraft": "1.21.1", "fabric-loader": "0.20.1"},
                files=[{
                    "path": "mods/cobblemon.jar",
                    "env": {"server": "required", "client": "required"},
                    "hashes": {"sha512": mod_sha512},
                    "downloads": ["https://cdn.modrinth.com/cb.jar"],
                    "fileSize": len(mod_bytes),
                }],
                extra_entries={"overrides/config/test.cfg": "ok=true"},
            )

            real_mgr = ModpackManager()
            mock_mp.parse_mrpack_manifest.side_effect = real_mgr.parse_mrpack_manifest
            mock_mp.install_from_mrpack = AsyncMock(return_value={"status": "completed"})
            tasks_to_run.clear()

            up_res = client.post(
                "/api/installer/modpacks/upload-mrpack",
                files={"file": ("local-cobblemon.mrpack", mr_bytes, "application/octet-stream")},
                data={"server_name": "Cobblemon Local", "max_ram": "4G"},
            )
            assert up_res.status_code == 200
            up_json = up_res.json()
            assert up_json["loader_type"] == "fabric"
            assert up_json["mc_version"] == "1.21.1"
            assert len(tasks_to_run) == 1
            await tasks_to_run[0]
            mock_mp.install_from_mrpack.assert_awaited_once()
            # Ensure uploaded temp file is cleaned up
            assert not any(p.name.startswith(".upload_") for p in tmp_path.iterdir())


@pytest.mark.asyncio
async def test_neoforge_versions_mapping_and_process_manager_launch(tmp_path):
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={"versions": ["20.4.237", "21.1.263", "21.1.264", "21.1.265-beta", "26.3.0.112", "26.3.0.113"]},
        )
    )
    dl = DownloadManager()
    real_async_client = httpx.AsyncClient
    with patch("app.core.downloader.httpx.AsyncClient", side_effect=lambda **kw: real_async_client(transport=transport)):
        vers = await dl.get_neoforge_versions()

    by_mc = {v["mc_version"]: v["neoforge_version"] for v in vers}
    assert by_mc["1.20.4"] == "20.4.237"
    assert by_mc["1.21.1"] == "21.1.264"  # skips 21.1.265-beta because 21.1.264 is non-beta
    assert by_mc["26.3"] == "26.3.0.113"

    pm = ProcessManager()
    pm.status = "OFFLINE"
    pm.process = None

    script_name = "run.bat" if sys.platform == "win32" else "run.sh"
    (tmp_path / script_name).write_text("@echo off\njava @user_jvm_args.txt\npause\n", encoding="utf-8")

    fake_proc = MagicMock()
    fake_proc.returncode = None
    fake_proc.pid = 4321
    fake_proc.stdout = MagicMock()

    with patch.object(settings, "data_dir", tmp_path), \
         patch.object(settings, "instance_dir", tmp_path), \
         patch.object(
             settings,
             "runtime_config",
             {
                 "server_type": "neoforge",
                 "server_version": "1.21.1",
                 "server_file": script_name,
                 "server_name": "NeoForge Test",
                 "java_path": "java",
                 "min_ram": "2G",
                 "max_ram": "4G",
                 "cpu_cores": 2,
                 "aikar_flags": False,
                 "custom_jvm_flags": "",
             },
         ), \
         patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)) as mock_exec, \
         patch.object(pm, "_read_stream", new=AsyncMock()), \
         patch.object(pm, "_process_supervisor", new=AsyncMock()), \
         patch.object(pm, "_tps_poller_loop", new=AsyncMock()):
        res = await pm.start_server()

    assert res["status"] in ("started", "success", "STARTING") or "status" in res
    assert (tmp_path / "user_jvm_args.txt").exists()
    jvm_txt = (tmp_path / "user_jvm_args.txt").read_text(encoding="utf-8")
    assert "-Xms2G" in jvm_txt and "-Xmx4G" in jvm_txt
    cmd_args = mock_exec.call_args[0]
    assert any(script_name in str(a) for a in cmd_args)

    for attr in ("_reader_task", "_supervisor_task", "_tps_poller_task"):
        t = getattr(pm, attr, None)
        if t and not t.done():
            t.cancel()


def test_csp_allows_modrinth_icons(client):
    res = client.get("/login")
    csp = res.headers.get("content-security-policy", "")
    assert "https://cdn.modrinth.com" in csp


def test_verify_file_integrity_accepts_fabric_bootstrap_size_and_rejects_tiny(tmp_path):
    from app.core.downloader import verify_file_integrity

    # Valid ~180 KB archive (Fabric server launcher bootstrap JAR size)
    fabric_jar = tmp_path / "fabric-server-launch.jar"
    with zipfile.ZipFile(str(fabric_jar), "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        zf.writestr("fabric-server-launch.properties", "launch.mainClass=net.fabricmc.loader.impl.launch.knot.KnotServer\n")
        zf.writestr("payload.bin", b"\x01" * (180 * 1024))
    assert verify_file_integrity(fabric_jar, expected_type="jar") is True

    # Tiny 104-byte error page / truncated download still fails
    tiny_jar = tmp_path / "tiny.jar"
    tiny_jar.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    with pytest.raises(ValueError, match="incompleto o truncado"):
        verify_file_integrity(tiny_jar, expected_type="jar")


@pytest.mark.asyncio
async def test_resolve_mod_stack_deduplicates_deps_filters_beta_and_detects_conflicts():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v2/projects":
            return httpx.Response(
                200,
                json=[
                    {"id": "cobblemon_id", "title": "Cobblemon", "slug": "cobblemon", "server_side": "required"},
                    {"id": "lithium_id", "title": "Lithium", "slug": "lithium", "server_side": "required"},
                    {"id": "betaonly_id", "title": "BetaOnlyMod", "slug": "betaonly", "server_side": "required"},
                    {"id": "conflict_id", "title": "ConflictMod", "slug": "conflictmod", "server_side": "required"},
                ],
            )
        if path == "/v2/project/cobblemon_id/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "cb_rel",
                        "project_id": "cobblemon_id",
                        "version_number": "1.8.4",
                        "version_type": "release",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "Cobblemon-1.8.4.jar", "url": "https://cdn.modrinth.com/cb.jar", "primary": True, "size": 4000, "hashes": {"sha512": "1" * 128}}],
                        "dependencies": [{"project_id": "fapi_id", "dependency_type": "required"}],
                    }
                ],
            )
        if path == "/v2/project/lithium_id/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "li_rel",
                        "project_id": "lithium_id",
                        "version_number": "0.14.0",
                        "version_type": "release",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "lithium-0.14.0.jar", "url": "https://cdn.modrinth.com/li.jar", "primary": True, "size": 1500, "hashes": {"sha512": "2" * 128}}],
                        "dependencies": [{"project_id": "fapi_id", "dependency_type": "required"}],
                    }
                ],
            )
        if path == "/v2/project/fapi_id/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "fapi_beta",
                        "project_id": "fapi_id",
                        "version_number": "0.111.0-beta",
                        "version_type": "beta",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "fabric-api-0.111.0-beta.jar", "url": "https://cdn.modrinth.com/fapi-beta.jar", "primary": True, "size": 1200, "hashes": {"sha512": "9" * 128}}],
                        "dependencies": [],
                    },
                    {
                        "id": "fapi_rel",
                        "project_id": "fapi_id",
                        "version_number": "0.110.0",
                        "version_type": "release",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "fabric-api-0.110.0.jar", "url": "https://cdn.modrinth.com/fapi.jar", "primary": True, "size": 1100, "hashes": {"sha512": "3" * 128}}],
                        "dependencies": [],
                    },
                ],
            )
        if path == "/v2/project/fapi_id":
            return httpx.Response(200, json={"id": "fapi_id", "title": "Fabric API", "server_side": "required"})
        if path == "/v2/version/fapi_rel":
            return httpx.Response(200, json={"id": "fapi_rel", "project_id": "fapi_id", "dependencies": []})
        if path == "/v2/project/betaonly_id/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "bo_beta",
                        "project_id": "betaonly_id",
                        "version_number": "2.0.0-beta.1",
                        "version_type": "beta",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "betaonly-2.0.jar", "url": "https://cdn.modrinth.com/bo.jar", "primary": True, "size": 900, "hashes": {"sha512": "4" * 128}}],
                        "dependencies": [],
                    }
                ],
            )
        if path == "/v2/project/conflict_id/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "cf_rel",
                        "project_id": "conflict_id",
                        "version_number": "1.0.0",
                        "version_type": "release",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "conflict-1.0.jar", "url": "https://cdn.modrinth.com/cf.jar", "primary": True, "size": 800, "hashes": {"sha512": "5" * 128}}],
                        "dependencies": [{"project_id": "lithium_id", "dependency_type": "incompatible"}],
                    }
                ],
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    mgr = ModpackManager()

    with patch(
        "app.core.modpack_manager.httpx.AsyncClient",
        side_effect=lambda **kw: real_client(transport=transport, headers=kw.get("headers")),
    ):
        # 1. Multi-mod stack with shared dependency (Fabric API) and strict stable filtering
        plan = await mgr.resolve_mod_stack(["cobblemon_id", "lithium_id"], loader="fabric", mc_version="1.21.1", allow_beta=False)
        assert plan["can_install"] is True
        assert len(plan["selected_mods"]) == 2
        assert len(plan["auto_dependencies"]) == 1
        assert plan["auto_dependencies"][0]["project_id"] == "fapi_id"
        assert plan["auto_dependencies"][0]["filename"] == "fabric-api-0.110.0.jar"
        assert plan["total_files"] == 3
        assert plan["conflicts"] == []
        assert plan["recommended_ram"]["min_recommended_gb"] >= 2
        assert "max_ram" in plan["recommended_ram"]

        # Verify smart RAM estimation tiers for modpacks and heavy loaders
        ram_fabric = mgr._estimate_recommended_ram(loader="fabric", project_type="modpack", pack_size_bytes=5 * 1024 * 1024)
        assert ram_fabric["min_recommended_gb"] == 4
        assert ram_fabric["max_ram"] == "4G"

        ram_forge = mgr._estimate_recommended_ram(loader="neoforge", project_type="modpack", pack_size_bytes=20 * 1024 * 1024)
        assert ram_forge["min_recommended_gb"] == 4
        assert ram_forge["recommended_gb"] == 6
        assert ram_forge["max_ram"] == "6G"

        ram_explicit = mgr._estimate_recommended_ram(
            loader="fabric",
            project_type="modpack",
            pack_size_bytes=4 * 1024 * 1024,
            description_text="Server requires at least 6GB of RAM recommended for smooth gameplay.",
        )
        assert ram_explicit["recommended_gb"] == 6
        assert ram_explicit["max_ram"] == "6G"

        # 2. Beta-only mod blocked when allow_beta=False, allowed when allow_beta=True
        plan_no_beta = await mgr.resolve_mod_stack(["cobblemon_id", "betaonly_id"], loader="fabric", mc_version="1.21.1", allow_beta=False)
        assert plan_no_beta["can_install"] is False
        assert len(plan_no_beta["missing"]) == 1
        assert plan_no_beta["missing"][0]["beta_only"] is True

        plan_with_beta = await mgr.resolve_mod_stack(["cobblemon_id", "betaonly_id"], loader="fabric", mc_version="1.21.1", allow_beta=True)
        assert plan_with_beta["can_install"] is True
        assert len(plan_with_beta["selected_mods"]) == 2

        # 3. Incompatible mods detected
        plan_conflict = await mgr.resolve_mod_stack(["lithium_id", "conflict_id"], loader="fabric", mc_version="1.21.1", allow_beta=False)
        assert plan_conflict["can_install"] is False
        assert len(plan_conflict["conflicts"]) == 1
        assert "Lithium" in plan_conflict["conflicts"][0]["reason"]


@pytest.mark.asyncio
async def test_stage_and_apply_modpack_update_preserves_configs_and_migrates_custom_mods(tmp_path):
    old_mod_bytes = b"old-pack-mod-v1"
    old_mod_sha = hashlib.sha512(old_mod_bytes).hexdigest()
    new_mod_bytes = b"new-pack-mod-v2"
    new_mod_sha = hashlib.sha512(new_mod_bytes).hexdigest()

    custom_good_v1 = b"custom-good-mc1201"
    custom_good_v1_sha = hashlib.sha512(custom_good_v1).hexdigest()
    custom_good_v2 = b"custom-good-mc1211"
    custom_good_v2_sha = hashlib.sha512(custom_good_v2).hexdigest()

    custom_legacy = b"custom-legacy-only1201"
    custom_legacy_sha = hashlib.sha512(custom_legacy).hexdigest()

    new_mrpack_bytes = _build_mrpack_bytes(
        name="Cobblemon Official [Fabric]",
        version_id="1.8.4",
        dependencies={"minecraft": "1.21.1", "fabric-loader": "0.20.1"},
        files=[
            {
                "path": "mods/cobblemon-1.8.4.jar",
                "env": {"server": "required", "client": "required"},
                "hashes": {"sha512": new_mod_sha},
                "downloads": ["https://cdn.modrinth.com/data/cb/cobblemon-1.8.4.jar"],
                "fileSize": len(new_mod_bytes),
            }
        ],
        extra_entries={
            "overrides/server.properties": "motd=OverriddenByModpack\n",
            "overrides/config/cobblemon.json": '{"version": "1.8.4"}',
        },
    )
    new_mrpack_sha = hashlib.sha512(new_mrpack_bytes).hexdigest()

    # Setup existing 1.20.1 server installation in tmp_path
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    (mods_dir / "cobblemon-1.5.2.jar").write_bytes(old_mod_bytes)
    (mods_dir / "custom-good-1.0.jar").write_bytes(custom_good_v1)
    (mods_dir / "custom-legacy-1.0.jar").write_bytes(custom_legacy)
    (tmp_path / "server.properties").write_text("motd=MiServidorPersonalizado\nmax-players=25\n", encoding="utf-8")

    mgr = ModpackManager()
    mgr.write_manifest(
        tmp_path,
        {
            "install_mode": "modpack",
            "project_id": "5FFgwNNP",
            "slug": "cobblemon-fabric",
            "name": "Cobblemon Official [Fabric]",
            "version_id": "ver_152",
            "version_number": "1.5.2",
            "mc_version": "1.20.1",
            "loader_type": "fabric",
            "loader_version": "0.18.0",
            "managed_files": [
                {"path": "mods/cobblemon-1.5.2.jar", "sha512": old_mod_sha, "origin": "modpack"}
            ],
        },
    )

    corrupt_mode = {"active": False}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path
        if path == "/v2/project/5FFgwNNP":
            return httpx.Response(
                200,
                json={"id": "5FFgwNNP", "slug": "cobblemon-fabric", "title": "Cobblemon Official [Fabric]", "project_type": "modpack", "loaders": ["fabric"]},
            )
        if path == "/v2/project/5FFgwNNP/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "ver_184",
                        "name": "1.8.4",
                        "version_number": "1.8.4",
                        "version_type": "release",
                        "game_versions": ["1.21.1"],
                        "loaders": ["fabric"],
                        "files": [
                            {
                                "filename": "Cobblemon-1.8.4.mrpack",
                                "url": "https://cdn.modrinth.com/data/5FFgwNNP/Cobblemon-1.8.4.mrpack",
                                "primary": True,
                                "size": len(new_mrpack_bytes),
                                "hashes": {"sha512": new_mrpack_sha},
                            }
                        ],
                    }
                ],
            )
        if url == "https://cdn.modrinth.com/data/5FFgwNNP/Cobblemon-1.8.4.mrpack":
            return httpx.Response(200, content=new_mrpack_bytes)
        if url == "https://cdn.modrinth.com/data/cb/cobblemon-1.8.4.jar":
            return httpx.Response(200, content=b"corrupted" if corrupt_mode["active"] else new_mod_bytes)
        if path == "/v2/version_files/update":
            return httpx.Response(
                200,
                json={
                    custom_good_v1_sha: {
                        "id": "cg_v2",
                        "project_id": "cgood_id",
                        "version_number": "2.0.0",
                        "version_type": "release",
                        "files": [
                            {
                                "filename": "custom-good-2.0.jar",
                                "url": "https://cdn.modrinth.com/data/cg/custom-good-2.0.jar",
                                "primary": True,
                                "size": len(custom_good_v2),
                                "hashes": {"sha512": custom_good_v2_sha},
                            }
                        ],
                    }
                },
            )
        if url == "https://cdn.modrinth.com/data/cg/custom-good-2.0.jar":
            return httpx.Response(200, content=custom_good_v2)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    fake_dl = MagicMock()
    fake_dl.get_fabric_download_url = AsyncMock(
        return_value="https://meta.fabricmc.net/v2/versions/loader/1.21.1/0.20.1/1.0.1/server/jar"
    )
    fake_dl.download_file = AsyncMock(return_value=tmp_path / "server.jar")
    fake_act = MagicMock()

    with patch.object(settings, "data_dir", tmp_path), \
         patch.object(settings, "config_file", tmp_path / "dockraft_config.json"), \
         patch.object(
             settings,
             "runtime_config",
             {
                 "server_type": "fabric",
                 "server_version": "1.20.1",
                 "server_file": "server.jar",
                 "loader_version": "0.18.0",
                 "modpack_id": "5FFgwNNP",
                 "modpack_slug": "cobblemon-fabric",
                 "modpack_name": "Cobblemon Official [Fabric]",
                 "modpack_version_id": "ver_152",
                 "modpack_version_name": "1.5.2",
                 "modpack_type": "modpack",
                 "modpack_source": "modrinth",
             },
         ), \
         patch(
             "app.core.modpack_manager.httpx.AsyncClient",
             side_effect=lambda **kw: real_client(transport=transport, headers=kw.get("headers")),
         ):
        # 1. Corrupted SHA-512 during staging aborts without touching live files
        corrupt_mode["active"] = True
        with pytest.raises((RuntimeError, ValueError), match="SHA-512"):
            await mgr.stage_modpack_update("5FFgwNNP", "ver_184", allow_beta=False)
        assert (mods_dir / "cobblemon-1.5.2.jar").exists()
        assert not (mods_dir / "cobblemon-1.8.4.jar").exists()
        assert not any(p.name.startswith(".modpack_stage_") for p in tmp_path.iterdir())

        # 2. Valid staging + apply swaps modpack files, preserves server.properties, updates compatible custom mod, disables incompatible custom mod
        corrupt_mode["active"] = False
        staged = await mgr.stage_modpack_update("5FFgwNNP", "ver_184", allow_beta=False)
        res = await mgr.apply_staged_modpack_update(
            staged=staged,
            downloader_obj=fake_dl,
            activity_manager_obj=fake_act,
            update_custom_mods=True,
            allow_beta=False,
        )

        assert res["status"] == "completed"
        assert res["mc_version"] == "1.21.1"
        assert not (mods_dir / "cobblemon-1.5.2.jar").exists()
        assert (mods_dir / "cobblemon-1.8.4.jar").read_bytes() == new_mod_bytes
        # Compatible custom mod upgraded
        assert not (mods_dir / "custom-good-1.0.jar").exists()
        assert (mods_dir / "custom-good-2.0.jar").read_bytes() == custom_good_v2
        # Incompatible custom mod disabled safely
        assert not (mods_dir / "custom-legacy-1.0.jar").exists()
        assert (mods_dir / "custom-legacy-1.0.jar.disabled").read_bytes() == custom_legacy
        # User server.properties preserved, modpack config updated
        assert "motd=MiServidorPersonalizado" in (tmp_path / "server.properties").read_text(encoding="utf-8")
        assert json.loads((tmp_path / "config" / "cobblemon.json").read_text(encoding="utf-8"))["version"] == "1.8.4"


@pytest.mark.asyncio
async def test_installed_mods_manager_strict_updates_conflict_toggle_and_delete(tmp_path):
    from app.core.modpack_manager import ModConflictError

    mods_dir = tmp_path / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    lithium_v1 = b"lithium-0.13.0-jar"
    lithium_v1_sha = hashlib.sha512(lithium_v1).hexdigest()
    lithium_v2 = b"lithium-0.14.0-release-jar"
    lithium_v2_sha = hashlib.sha512(lithium_v2).hexdigest()
    (mods_dir / "lithium-0.13.0.jar").write_bytes(lithium_v1)

    mgr = ModpackManager()
    mgr.write_manifest(
        tmp_path,
        {
            "install_mode": "custom_mods",
            "mc_version": "1.21.1",
            "loader_type": "fabric",
            "managed_files": [{"path": "mods/lithium-0.13.0.jar", "sha512": lithium_v1_sha, "origin": "manual", "project_id": "gvQqBUqZ"}],
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        url = str(request.url)
        if path == "/v2/version_files":
            return httpx.Response(
                200,
                json={
                    lithium_v1_sha: {
                        "id": "li_013",
                        "project_id": "gvQqBUqZ",
                        "version_number": "0.13.0",
                        "version_type": "release",
                        "dependencies": [],
                    }
                },
            )
        if path == "/v2/projects":
            return httpx.Response(200, json=[{"id": "gvQqBUqZ", "slug": "lithium", "title": "Lithium", "icon_url": ""}])
        if path == "/v2/version_files/update":
            # Simulates Modrinth returning a beta candidate first
            return httpx.Response(
                200,
                json={
                    lithium_v1_sha: {
                        "id": "li_015_beta",
                        "project_id": "gvQqBUqZ",
                        "version_number": "0.15.0-beta.1",
                        "version_type": "beta",
                        "files": [{"filename": "lithium-0.15.0-beta.jar", "url": "https://cdn.modrinth.com/li-beta.jar", "primary": True, "hashes": {"sha512": "f" * 128}}],
                    }
                },
            )
        if path == "/v2/project/gvQqBUqZ/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "li_015_beta",
                        "project_id": "gvQqBUqZ",
                        "version_number": "0.15.0-beta.1",
                        "version_type": "beta",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "lithium-0.15.0-beta.jar", "url": "https://cdn.modrinth.com/li-beta.jar", "primary": True, "hashes": {"sha512": "f" * 128}}],
                    },
                    {
                        "id": "li_014_rel",
                        "project_id": "gvQqBUqZ",
                        "version_number": "0.14.0",
                        "version_type": "release",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "lithium-0.14.0.jar", "url": "https://cdn.modrinth.com/li-014.jar", "primary": True, "size": len(lithium_v2), "hashes": {"sha512": lithium_v2_sha}}],
                    },
                ],
            )
        if url == "https://cdn.modrinth.com/li-014.jar":
            return httpx.Response(200, content=lithium_v2)
        if path == "/v2/project/badconflict_id":
            return httpx.Response(200, json={"id": "badconflict_id", "title": "IncompatibleMod", "server_side": "required"})
        if path == "/v2/project/badconflict_id/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "bc_v1",
                        "project_id": "badconflict_id",
                        "version_number": "1.0.0",
                        "version_type": "release",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "badconflict.jar", "url": "https://cdn.modrinth.com/bc.jar", "primary": True, "hashes": {"sha512": "e" * 128}}],
                        "dependencies": [{"project_id": "gvQqBUqZ", "dependency_type": "incompatible"}],
                    }
                ],
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    with patch.object(settings, "data_dir", tmp_path), \
         patch.object(settings, "runtime_config", {"server_type": "fabric", "server_version": "1.21.1"}), \
         patch(
             "app.core.modpack_manager.httpx.AsyncClient",
             side_effect=lambda **kw: real_client(transport=transport, headers=kw.get("headers")),
         ):
        # 1. list_installed_mods rejects beta update when allow_beta=False and selects 0.14.0 release
        info = await mgr.list_installed_mods(check_updates=True, allow_beta=False)
        assert info["updates_available_count"] == 1
        mod_entry = info["mods"][0]
        assert mod_entry["latest_version_number"] == "0.14.0"
        assert mod_entry["latest_version_type"] == "release"

        # 2. Adding an incompatible mod raises ModConflictError before downloading
        with pytest.raises(ModConflictError, match="incompatible"):
            await mgr.add_mod_to_installed_server("badconflict_id", allow_beta=False)

        # 3. Stage and apply mod update swaps 0.13.0 -> 0.14.0
        staged = await mgr.stage_mods_update(filenames=["lithium-0.13.0.jar"], allow_beta=False)
        upd_res = mgr.apply_staged_mods_update(staged)
        assert upd_res["count"] == 1
        assert not (mods_dir / "lithium-0.13.0.jar").exists()
        assert (mods_dir / "lithium-0.14.0.jar").read_bytes() == lithium_v2

        # 4. Toggle and delete mod
        t1 = mgr.toggle_mod("lithium-0.14.0.jar")
        assert t1 == {"filename": "lithium-0.14.0.jar.disabled", "enabled": False}
        t2 = mgr.toggle_mod("lithium-0.14.0.jar.disabled")
        assert t2 == {"filename": "lithium-0.14.0.jar", "enabled": True}
        d1 = mgr.delete_mod("lithium-0.14.0.jar")
        assert d1 == {"deleted": "lithium-0.14.0.jar"}
        assert not (mods_dir / "lithium-0.14.0.jar").exists()


@pytest.mark.asyncio
async def test_phase2_modpack_and_mods_api_endpoints(tmp_path, client):
    from contextlib import ExitStack
    from app.core.modpack_manager import ModConflictError

    with ExitStack() as stack:
        mock_pm = stack.enter_context(patch("app.main.process_manager"))
        mock_dl = stack.enter_context(patch("app.main.downloader"))
        mock_bm = stack.enter_context(patch("app.main.backup_manager"))
        mock_act = stack.enter_context(patch("app.main.activity_manager"))
        mock_mp = stack.enter_context(patch("app.main.modpack_manager"))
        stack.enter_context(patch("app.main._is_server_installed", return_value=True))
        stack.enter_context(patch.object(settings, "data_dir", tmp_path))
        stack.enter_context(
            patch.object(
                settings,
                "runtime_config",
                {
                    "server_type": "fabric",
                    "server_version": "1.21.1",
                    "modpack_id": "5FFgwNNP",
                    "modpack_type": "modpack",
                },
            )
        )
        stack.enter_context(patch("app.routers.installer._background_tasks", set()))

        mock_pm.get_status.return_value = "OFFLINE"
        mock_dl.active_download = {"status": "idle", "percent": 0}
        mock_bm.create_backup.return_value = {"status": "success", "filename": "pre.zip"}

        # 1. /api/installer/modpacks/resolve-stack
        mock_mp.resolve_mod_stack = AsyncMock(
            return_value={"can_install": True, "selected_mods": [{"project_id": "cb"}], "auto_dependencies": [], "conflicts": [], "missing": [], "total_files": 1}
        )
        r_stack = client.post(
            "/api/installer/modpacks/resolve-stack",
            json={"project_ids": ["cb"], "loader": "fabric", "mc_version": "1.21.1", "allow_beta": False},
        )
        assert r_stack.status_code == 200
        assert r_stack.json()["can_install"] is True

        # 2. /api/installer/modpacks/update-status
        mock_mp.get_modpack_update_status = AsyncMock(
            return_value={"has_modpack": True, "update_available": True, "latest_version": {"id": "YQpPe5Iu", "name": "1.8.4"}}
        )
        r_ust = client.get("/api/installer/modpacks/update-status?allow_beta=false")
        assert r_ust.status_code == 200
        assert r_ust.json()["update_available"] is True

        # 3. /api/installer/mods/installed
        mock_mp.list_installed_mods = AsyncMock(
            return_value={"server_type": "fabric", "server_version": "1.21.1", "mods": [], "updates_available_count": 0, "conflicts": []}
        )
        r_mods = client.get("/api/installer/mods/installed")
        assert r_mods.status_code == 200

        # 4. /api/installer/mods/add returns 409 on ModConflictError
        mock_mp.add_mod_to_installed_server = AsyncMock(side_effect=ModConflictError("Mod A es incompatible con Mod B"))
        r_add_conflict = client.post("/api/installer/mods/add", json={"project_id": "badmod", "allow_beta": False})
        assert r_add_conflict.status_code == 409
        assert "incompatible" in r_add_conflict.json()["detail"]

        # 5. /api/installer/mods/toggle & DELETE block when server is RUNNING and succeed when OFFLINE
        mock_pm.get_status.return_value = "RUNNING"
        assert client.post("/api/installer/mods/toggle", json={"filename": "a.jar"}).status_code == 400
        assert client.delete("/api/installer/mods/a.jar").status_code == 400

        mock_pm.get_status.return_value = "OFFLINE"
        mock_mp.toggle_mod.return_value = {"filename": "a.jar.disabled", "enabled": False}
        assert client.post("/api/installer/mods/toggle", json={"filename": "a.jar"}).status_code == 200
        mock_mp.delete_mod.return_value = {"deleted": "a.jar"}
        assert client.delete("/api/installer/mods/a.jar").status_code == 200

        # 6. /api/installer/mods/check-compatibility
        mock_mp.check_mods_compatibility_for_target = AsyncMock(
            return_value={"target_mc": "1.21.4", "target_loader": "fabric", "compatible": [], "incompatible": [], "unknown": [], "all_compatible": True}
        )
        r_compat = client.get("/api/installer/mods/check-compatibility?target_mc=1.21.4")
        assert r_compat.status_code == 200
        assert r_compat.json()["all_compatible"] is True


def _build_fabric_mod_jar_bytes(mod_id: str, depends: dict = None, env: str = "*") -> bytes:
    buf = io.BytesIO()
    fmj = {
        "schemaVersion": 1,
        "id": mod_id,
        "version": "1.0.0",
        "environment": env,
        "depends": depends or {},
    }
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fabric.mod.json", json.dumps(fmj))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_cobbleverse_style_rescue_and_auto_heal_missing_dependencies(tmp_path):
    """Verifies that shared library mods (athena, fusion) mis-tagged as server=unsupported in .mrpack are rescued when required by server mods."""
    cobblefurnies_jar = _build_fabric_mod_jar_bytes("cobblefurnies", depends={"athena": ">=4.0.2", "fabricloader": ">=0.16.0"})
    rechiseled_jar = _build_fabric_mod_jar_bytes("rechiseled", depends={"fusion": ">=1.2.12"})
    athena_jar = _build_fabric_mod_jar_bytes("athena", depends={"minecraft": ">=1.21"}, env="*")
    fusion_jar = _build_fabric_mod_jar_bytes("fusion", depends={"minecraft": ">=1.21"}, env="*")
    sodium_jar = _build_fabric_mod_jar_bytes("sodium", depends={"minecraft": ">=1.21"}, env="client")

    mrpack_bytes = _build_mrpack_bytes(
        name="COBBLEVERSE Test",
        version_id="1.8.0",
        dependencies={"minecraft": "1.21.1", "fabric-loader": "0.19.5"},
        files=[
            {
                "path": "mods/CobbleFurnies-fabric-1.2.jar",
                "env": {"client": "required", "server": "required"},
                "hashes": {"sha512": hashlib.sha512(cobblefurnies_jar).hexdigest()},
                "downloads": ["https://cdn.modrinth.com/data/cf/CobbleFurnies-fabric-1.2.jar"],
                "fileSize": len(cobblefurnies_jar),
            },
            {
                "path": "mods/rechiseled-1.2.6-fabric-mc1.21.jar",
                "env": {"client": "required", "server": "required"},
                "hashes": {"sha512": hashlib.sha512(rechiseled_jar).hexdigest()},
                "downloads": ["https://cdn.modrinth.com/data/rc/rechiseled-1.2.6-fabric-mc1.21.jar"],
                "fileSize": len(rechiseled_jar),
            },
            {
                "path": "mods/athena-fabric-1.21.1-4.0.6.jar",
                "env": {"client": "required", "server": "unsupported"},
                "hashes": {"sha512": hashlib.sha512(athena_jar).hexdigest()},
                "downloads": ["https://cdn.modrinth.com/data/at/athena-fabric-1.21.1-4.0.6.jar"],
                "fileSize": len(athena_jar),
            },
            {
                "path": "mods/fusion-1.3.16-fabric-mc1.21.jar",
                "env": {"client": "required", "server": "unsupported"},
                "hashes": {"sha512": hashlib.sha512(fusion_jar).hexdigest()},
                "downloads": ["https://cdn.modrinth.com/data/fu/fusion-1.3.16-fabric-mc1.21.jar"],
                "fileSize": len(fusion_jar),
            },
            {
                "path": "mods/sodium-fabric-0.8.13+mc1.21.1.jar",
                "env": {"client": "required", "server": "unsupported"},
                "hashes": {"sha512": hashlib.sha512(sodium_jar).hexdigest()},
                "downloads": ["https://cdn.modrinth.com/data/so/sodium-fabric-0.8.13+mc1.21.1.jar"],
                "fileSize": len(sodium_jar),
            },
        ],
    )
    mrpack_path = tmp_path / "cobbleverse.mrpack"
    mrpack_path.write_bytes(mrpack_bytes)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("CobbleFurnies-fabric-1.2.jar"):
            return httpx.Response(200, content=cobblefurnies_jar)
        if url.endswith("rechiseled-1.2.6-fabric-mc1.21.jar"):
            return httpx.Response(200, content=rechiseled_jar)
        if url.endswith("athena-fabric-1.21.1-4.0.6.jar"):
            return httpx.Response(200, content=athena_jar)
        if url.endswith("fusion-1.3.16-fabric-mc1.21.jar"):
            return httpx.Response(200, content=fusion_jar)
        if url.endswith("sodium-fabric-0.8.13+mc1.21.1.jar"):
            return httpx.Response(200, content=sodium_jar)
        if request.url.path == "/v2/search":
            q = request.url.params.get("query", "")
            if q == "athena":
                return httpx.Response(200, json={"hits": [{"project_id": "b1ZV3DIJ", "slug": "athena-ctm", "title": "Athena"}]})
            if q == "fusion":
                return httpx.Response(200, json={"hits": [{"project_id": "p19vrgc2", "slug": "fusion-connected-textures", "title": "Fusion"}]})
        if request.url.path == "/v2/project/b1ZV3DIJ/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "ath_v1",
                        "project_id": "b1ZV3DIJ",
                        "version_type": "release",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "athena-fabric-1.21.1-4.0.6.jar", "url": "https://cdn.modrinth.com/data/at/athena-fabric-1.21.1-4.0.6.jar", "primary": True, "hashes": {"sha512": hashlib.sha512(athena_jar).hexdigest()}}],
                    }
                ],
            )
        if request.url.path == "/v2/project/p19vrgc2/version":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "fus_v1",
                        "project_id": "p19vrgc2",
                        "version_type": "release",
                        "loaders": ["fabric"],
                        "game_versions": ["1.21.1"],
                        "files": [{"filename": "fusion-1.3.16-fabric-mc1.21.jar", "url": "https://cdn.modrinth.com/data/fu/fusion-1.3.16-fabric-mc1.21.jar", "primary": True, "hashes": {"sha512": hashlib.sha512(fusion_jar).hexdigest()}}],
                    }
                ],
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    mgr = ModpackManager()
    fake_dl = MagicMock()
    fake_dl.get_fabric_download_url = AsyncMock(return_value="https://meta.fabricmc.net/v2/versions/loader/1.21.1/0.19.5/1.0.1/server/jar")
    fake_dl.download_file = AsyncMock(return_value=tmp_path / "server.jar")
    fake_act = MagicMock()

    with patch.object(settings, "data_dir", tmp_path), \
         patch.object(settings, "config_file", tmp_path / "dockraft_config.json"), \
         patch.object(settings, "runtime_config", {}), \
         patch(
             "app.core.modpack_manager.httpx.AsyncClient",
             side_effect=lambda **kw: real_client(transport=transport, headers=kw.get("headers")),
         ):
        # 1. Install from .mrpack automatically rescues athena and fusion from client_only_files, while skipping sodium
        res = await mgr.install_from_mrpack(
            mrpack_path=mrpack_path,
            downloader_obj=fake_dl,
            activity_manager_obj=fake_act,
            server_name="COBBLEVERSE",
        )
        assert res["status"] == "completed"
        installed_jars = sorted(p.name for p in (tmp_path / "mods").glob("*.jar"))
        assert "CobbleFurnies-fabric-1.2.jar" in installed_jars
        assert "rechiseled-1.2.6-fabric-mc1.21.jar" in installed_jars
        assert "athena-fabric-1.21.1-4.0.6.jar" in installed_jars
        assert "fusion-1.3.16-fabric-mc1.21.jar" in installed_jars
        assert "sodium-fabric-0.8.13+mc1.21.1.jar" not in installed_jars
        assert mgr._find_missing_mod_ids_in_dir(tmp_path / "mods") == set()

        # 2. Simulate an already-installed server missing athena & fusion -> auto_heal_missing_server_dependencies downloads them from Modrinth
        (tmp_path / "mods" / "athena-fabric-1.21.1-4.0.6.jar").unlink()
        (tmp_path / "mods" / "fusion-1.3.16-fabric-mc1.21.jar").unlink()
        assert mgr._find_missing_mod_ids_in_dir(tmp_path / "mods") == {"athena", "fusion"}

        healed = await mgr.auto_heal_missing_server_dependencies(target_root=tmp_path, loader="fabric", mc_version="1.21.1")
        assert sorted(healed) == ["athena-fabric-1.21.1-4.0.6.jar", "fusion-1.3.16-fabric-mc1.21.jar"]
        assert mgr._find_missing_mod_ids_in_dir(tmp_path / "mods") == set()


def test_inspect_neoforge_mods_toml_extracts_required_dependencies(tmp_path):
    """Verifies NeoForge/Forge mods.toml extraction ignores client-only/optional deps and finds missing required modIds."""
    nf_mod = tmp_path / "cobble-addon-neoforge.jar"
    mods_toml = '''
modLoader="javafml"
loaderVersion="[4,)"
[[mods]]
modId="cobbleaddon"
version="1.0.0"

[[dependencies.cobbleaddon]]
modId="neoforge"
type="required"
side="BOTH"

[[dependencies.cobbleaddon]]
modId="kotlinforforge"
type="required"
side="BOTH"

[[dependencies.cobbleaddon]]
modId="oculus"
type="optional"
side="CLIENT"
'''
    with zipfile.ZipFile(nf_mod, "w") as zf:
        zf.writestr("META-INF/neoforge.mods.toml", mods_toml)

    meta = ModpackManager._inspect_mod_jar_metadata(nf_mod)
    assert "cobbleaddon" in meta["provided_ids"]
    assert "kotlinforforge" in meta["required_ids"]
    assert "neoforge" not in meta["required_ids"]
    assert "oculus" not in meta["required_ids"]
    assert ModpackManager._find_missing_mod_ids_in_dir(tmp_path) == {"kotlinforforge"}


def test_console_websocket_ping_and_live_world_protection_and_diagnostics(tmp_path, client):
    from fastapi import HTTPException
    from app.core.file_manager import FileManager
    from app.core.diagnostic_manager import DiagnosticManager

    # 1. /ws/console responds to client heartbeat {type: "ping"} -> {type: "pong"}
    with patch("app.main.process_manager.get_stats", return_value={"status": "OFFLINE", "is_installed": False}), \
         patch("app.main.process_manager.get_status", return_value="OFFLINE"):
        with client.websocket_connect("/ws/console") as ws:
            init_msg = ws.receive_json()
            assert init_msg["type"] == "init"
            _stats_msg = ws.receive_json()
            ws.send_json({"type": "ping"})
            pong_msg = ws.receive_json()
            assert pong_msg["type"] == "pong"

    # 2. console.js handles background tab freeze & visibilitychange resume silently
    console_js = (tmp_path.parent.parent if False else __import__("pathlib").Path("web/static/js/console.js")).read_text(encoding="utf-8")
    assert "visibilitychange" in console_js
    assert "_pausedInBackground" in console_js
    assert "type: 'ping'" in console_js

    # 3. FileManager blocks deleting or renaming active world while server is RUNNING
    fm = FileManager()
    fm.base_dir = tmp_path
    world_dir = tmp_path / "world"
    world_dir.mkdir(parents=True, exist_ok=True)
    with patch("app.core.process_manager.process_manager.get_status", return_value="RUNNING"):
        with pytest.raises(HTTPException) as exc_del:
            fm.delete_item("world")
        assert exc_del.value.status_code == 409

        with pytest.raises(HTTPException) as exc_ren:
            fm.rename_item("world", "world_bak")
        assert exc_ren.value.status_code == 409

    # 4. DiagnosticManager detects missing ./world save failure clearly
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "latest.log").write_text(
        "[00:45:12] [Server thread/ERROR]: Could not save data net.minecraft.class_3767@1b0caf20\n"
        "java.nio.file.NoSuchFileException: ./world/data/raids.dat\n"
        "[00:45:12] [Server thread/ERROR]: Failed to save level ./world\n",
        encoding="utf-8",
    )
    dm = DiagnosticManager()
    with patch.object(settings, "data_dir", tmp_path):
        diag = dm.analyze_diagnostics()
    assert diag["has_issue"] is True
    assert diag["category"] == "world"




