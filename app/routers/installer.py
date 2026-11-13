import sys
import re
import logging
import asyncio
from typing import Dict, Any, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.core.security import get_current_user
from app.core.process_manager import process_manager as _default_process_manager
from app.core.downloader import downloader as _default_downloader
from app.core.java_manager import JavaManager
from app.core.backup_manager import backup_manager as _default_backup_manager
from app.core.activity_manager import activity_manager as _default_activity_manager

logger = logging.getLogger("dockraft.installer")

router = APIRouter(tags=["installer"])

_background_tasks: set = set()


def _track_task(coro) -> asyncio.Task:
    """Spawns an asyncio background task while holding a strong reference to prevent GC."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    if hasattr(task, "add_done_callback"):
        task.add_done_callback(_background_tasks.discard)
    return task


def _deps():
    """Resolves core dependencies through app.main when loaded, preserving test monkeypatches."""
    main_mod = sys.modules.get("app.main")
    pm = getattr(main_mod, "process_manager", _default_process_manager)
    dl = getattr(main_mod, "downloader", _default_downloader)
    bm = getattr(main_mod, "backup_manager", _default_backup_manager)
    am = getattr(main_mod, "activity_manager", _default_activity_manager)
    is_inst = getattr(main_mod, "_is_server_installed", lambda: pm.is_installed())
    return pm, dl, bm, am, is_inst


class InstallRequest(BaseModel):
    server_type: str  # paper, purpur, vanilla, fabric, bedrock, forge
    version: str
    server_name: Optional[str] = "Mi Servidor Dockraft"
    java_path: Optional[str] = None
    min_ram: Optional[str] = "1G"
    max_ram: Optional[str] = "2G"
    aikar_flags: Optional[bool] = True
    cpu_cores: Optional[int] = 2
    disk_limit_gb: Optional[float] = 10.0
    force: Optional[bool] = False


class UpdateRequest(BaseModel):
    version: str
    build: Optional[Union[int, str]] = None


async def resolve_server_download(
    server_type: str,
    version: str,
    build: Optional[Union[int, str]] = None,
    unsupported_detail: str = "Unsupported server type",
) -> Dict[str, Any]:
    """Resolves download_url, target_file, is_zip, and build for a given server_type and version."""
    _, downloader, _, _, _ = _deps()
    target_file = "server.jar"
    is_zip = False
    resolved_build = build
    expected_sha256: Optional[str] = None
    expected_sha1: Optional[str] = None
    allowed_hosts: Optional[set] = None

    if server_type in ["paper", "folia", "velocity"]:
        if build is not None:
            info = await downloader.get_paper_build(server_type, version, build)
        else:
            info = await downloader.get_paper_latest_build(server_type, version)
        download_url = info["download_url"]
        resolved_build = info.get("build")
        expected_sha256 = info.get("sha256")
        allowed_hosts = {"papermc.io"}
    elif server_type == "purpur":
        if build is not None:
            info = await downloader.get_purpur_build(version, build)
        else:
            info = await downloader.get_purpur_latest_build(version)
        download_url = info["download_url"]
        resolved_build = info.get("build")
        allowed_hosts = {"purpurmc.org"}
    elif server_type == "vanilla":
        versions = await downloader.get_vanilla_versions()
        match = next((v for v in versions if v["id"] == version), None)
        if not match:
            raise HTTPException(status_code=404, detail="Version manifest not found")
        v_info = await downloader.get_vanilla_download_info(match["url"])
        download_url = str(v_info["url"])
        expected_sha1 = v_info.get("sha1")
        allowed_hosts = {"mojang.com"}
    elif server_type == "fabric":
        download_url = await downloader.get_fabric_download_url(version)
        allowed_hosts = {"fabricmc.net"}
    elif server_type == "bedrock":
        platform = "win" if sys.platform == "win32" else "linux"
        download_url = await downloader.get_bedrock_download_url(version, platform=platform)
        target_file = "bedrock-server.zip"
        is_zip = True
        allowed_hosts = {"minecraft.net", "azureedge.net", "minecraft-cdn.net"}
    elif server_type == "forge":
        download_url = await downloader.get_forge_download_url(version)
        target_file = "forge-installer.jar"
        allowed_hosts = {"minecraftforge.net"}
    else:
        raise HTTPException(status_code=400, detail=unsupported_detail)

    return {
        "download_url": download_url,
        "target_file": target_file,
        "is_zip": is_zip,
        "build": resolved_build,
        "expected_sha256": expected_sha256,
        "expected_sha1": expected_sha1,
        "allowed_hosts": allowed_hosts,
    }


def get_version_changelog_info(server_type: str, version_id: str, channel: str = "stable") -> Dict[str, Any]:
    """Generates official changelog URLs, engine notes, and upgrade advice for any Minecraft server version."""
    st = (server_type or "").lower().strip()
    vid = (version_id or "").strip()

    m = re.search(r"([0-9]+(?:\.[0-9]+)+(?:-[a-zA-Z0-9\.\-]+)?)", vid)
    clean_ver = m.group(1) if m else vid

    if st == "bedrock":
        if channel in ("preview", "beta"):
            official_url = "https://feedback.minecraft.net/hc/en-us/sections/360001185332-Beta-and-Preview-Information-and-Changelogs"
            official_label = "Novedades Oficiales de Betas y Previews (Bedrock)"
        else:
            official_url = "https://feedback.minecraft.net/hc/en-us/sections/360001186971-Release-Changelogs"
            official_label = "Página Oficial y Cambios de Bedrock"
        wiki_url = f"https://minecraft.wiki/w/Bedrock_Edition_{clean_ver}"
    elif st == "paper":
        official_url = "https://papermc.io/downloads/paper"
        official_label = "Página Oficial y Descargas de PaperMC"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "folia":
        official_url = "https://papermc.io/downloads/folia"
        official_label = "Página Oficial y Descargas de Folia"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "velocity":
        official_url = "https://papermc.io/downloads/velocity"
        official_label = "Página Oficial y Descargas de Velocity"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "purpur":
        official_url = f"https://purpurmc.org/downloads?version={clean_ver}" if clean_ver else "https://purpurmc.org/downloads"
        official_label = "Página Oficial y Descargas de Purpur"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "fabric":
        official_url = "https://fabricmc.net/"
        official_label = "Portal Oficial de FabricMC"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "forge":
        official_url = "https://files.minecraftforge.net/net/minecraftforge/forge/"
        official_label = "Portal Oficial de Minecraft Forge"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    else:
        official_url = "https://www.minecraft.net/articles"
        official_label = "Artículos Oficiales de Lanzamiento en Minecraft.net"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"

    wiki_label = f"Wiki de Minecraft ({clean_ver})"

    is_stable = channel == "stable"
    if is_stable:
        advice_title = "Compilación Estable (Recomendada para Producción)"
        advice_text = (
            f"La versión {clean_ver} es una compilación Estable oficial. Es la opción recomendada "
            "si buscas máxima compatibilidad con plugins/mods, estabilidad para tus jugadores y cero riesgos de fallos experimentales."
        )
    else:
        ch_label = "Beta / Snapshot" if channel in ("beta", "snapshot", "pre") else "Experimental"
        advice_title = f"Compilación {ch_label} (Preliminar de Desarrollo)"
        advice_text = (
            f"La versión {clean_ver} incluye las mecánicas y bloques más recientes antes de su lanzamiento final, "
            "pero puede contener bugs, inestabilidad o incompatibilidad temporal con plugins. Te conviene quedarte en Estable "
            "si tu comunidad está activa, o probar esta versión si tienes un entorno de prueba o deseas explorar las novedades. "
            "Dockraft generará una copia de seguridad preventiva antes de instalar."
        )

    return {
        "clean_version": clean_ver,
        "official_url": official_url,
        "official_label": official_label,
        "wiki_url": wiki_url,
        "wiki_label": wiki_label,
        "changelog_url": official_url,
        "engine_url": wiki_url,
        "engine_label": wiki_label,
        "advice_title": advice_title,
        "advice_text": advice_text,
        "is_stable": is_stable,
    }


@router.get("/api/installer/versions", dependencies=[Depends(get_current_user)])
async def get_installer_versions(type: str = Query("paper")):
    _, downloader, _, _, _ = _deps()
    try:
        if type in ["paper", "folia", "velocity"]:
            versions = await downloader.get_paper_versions(type)
            return {"type": type, "versions": versions}
        elif type == "purpur":
            versions = await downloader.get_purpur_versions()
            return {"type": type, "versions": versions}
        elif type == "vanilla":
            versions = await downloader.get_vanilla_versions()
            return {"type": type, "versions": [v["id"] for v in versions]}
        elif type == "fabric":
            versions = await downloader.get_fabric_versions()
            return {"type": type, "versions": versions}
        elif type == "bedrock":
            versions = await downloader.get_bedrock_versions()
            return {"type": "bedrock", "versions": versions}
        elif type == "forge":
            versions = await downloader.get_forge_versions()
            return {"type": "forge", "versions": versions}
        else:
            raise HTTPException(status_code=400, detail="Invalid server type")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching versions: {str(e)}")


@router.get("/api/installer/progress", dependencies=[Depends(get_current_user)])
async def get_install_progress():
    _, downloader, _, _, _ = _deps()
    data = downloader.active_download or {"status": "idle", "percent": 0}
    if data.get("status") == "completed":
        downloader.active_download = {"status": "idle", "percent": 100}
    return data


@router.post("/api/installer/install", dependencies=[Depends(get_current_user)])
async def install_server(req: InstallRequest):
    process_manager, downloader, _, _, is_server_installed = _deps()
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de instalar o cambiar de versión")

    if is_server_installed() and not req.force:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un servidor instalado en este directorio. Desbloquea la reinstalación para confirmar la sobrescritura.",
        )

    try:
        if req.server_type != "bedrock":
            if not req.java_path or req.java_path == "java":
                req.java_path = await asyncio.to_thread(JavaManager.get_best_java_path, req.version)

        dl_info = await resolve_server_download(req.server_type, req.version)
        download_url = dl_info["download_url"]
        target_file = dl_info["target_file"]
        is_zip = dl_info["is_zip"]
        server_build = dl_info["build"]
        expected_sha256 = dl_info.get("expected_sha256")
        expected_sha1 = dl_info.get("expected_sha1")
        allowed_hosts = dl_info.get("allowed_hosts")

        if req.server_type == "forge":
            java_bin = req.java_path or "java"

            async def forge_install_pipeline():
                try:
                    installer_path = await downloader.download_file(
                        download_url,
                        target_file,
                        expected_sha256=expected_sha256,
                        expected_sha1=expected_sha1,
                        allowed_hosts=allowed_hosts,
                    )
                    res = await downloader.install_forge_server(installer_path, java_bin=java_bin)
                    settings.save_runtime_config({
                        "server_file": res.get("server_file", "run.sh")
                    })
                except Exception as ex:
                    logger.error("[Dockraft] Forge install pipeline error: %s", ex)

            _track_task(forge_install_pipeline())
        else:
            _track_task(
                downloader.download_file(
                    download_url,
                    target_file,
                    is_zip=is_zip,
                    expected_sha256=expected_sha256,
                    expected_sha1=expected_sha1,
                    allowed_hosts=allowed_hosts,
                )
            )

        resolved_server_file = (
            ("bedrock_server.exe" if sys.platform == "win32" else "bedrock_server")
            if req.server_type == "bedrock"
            else ("run.sh" if req.server_type == "forge" else "server.jar")
        )

        cfg_to_save = {
            "server_type": req.server_type,
            "server_version": req.version,
            "server_file": resolved_server_file,
            "server_name": req.server_name or "Mi Servidor Dockraft",
            "java_path": req.java_path or "java",
            "min_ram": req.min_ram or "1G",
            "max_ram": req.max_ram or "2G",
            "aikar_flags": req.aikar_flags if req.aikar_flags is not None else True,
            "cpu_cores": req.cpu_cores if req.cpu_cores is not None else 2,
            "disk_limit_gb": req.disk_limit_gb if req.disk_limit_gb is not None else 10.0,
        }
        if server_build is not None:
            try:
                cfg_to_save["server_build"] = int(server_build)
            except (ValueError, TypeError):
                pass

        settings.save_runtime_config(cfg_to_save)
        return {"status": "started", "target_file": target_file, "download_url": download_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/installer/update-info", dependencies=[Depends(get_current_user)])
async def get_update_info():
    """Returns update status and classified versions for the currently installed server type."""
    _, downloader, _, _, is_server_installed = _deps()
    if not is_server_installed():
        return {
            "is_installed": False,
            "server_type": None,
            "current_version": None,
            "current_channel": "unknown",
            "latest_stable": "",
            "latest_preview": "",
            "update_available": False,
            "preview_available": False,
            "available_versions": [],
            "versions": [],
        }

    cfg = settings.runtime_config
    server_type = cfg.get("server_type", "paper")
    current_version = cfg.get("server_version", "")
    current_build = cfg.get("server_build")
    server_file = cfg.get("server_file")

    if not current_version or current_version.lower() in ["importado", "desconocida", "unknown"]:
        detected_ver = downloader.detect_server_version(server_file=server_file)
        if detected_ver:
            current_version = detected_ver
            settings.save_runtime_config({"server_version": detected_ver})
        else:
            current_version = "importado"

    if current_build is None and server_type in ["paper", "folia", "velocity", "purpur"]:
        detected_build = downloader.detect_server_build(server_file=server_file)
        if detected_build:
            current_build = detected_build
            settings.save_runtime_config({"server_build": detected_build})

    latest_stable = ""
    latest_preview = ""
    version_items = []

    try:
        if server_type == "bedrock":
            b_vers = await downloader.get_bedrock_versions()
            for bv in b_vers:
                m = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)+)", bv)
                vid = m.group(1) if m else bv
                is_prev = "preview" in bv.lower() or "beta" in bv.lower()
                ch = "preview" if is_prev else "stable"
                lbl = f"{vid} (Estable)" if not is_prev else f"{vid} (Preview / Beta)"
                version_items.append({"id": bv, "label": lbl, "channel": ch})
                if not is_prev and not latest_stable:
                    latest_stable = vid
                elif is_prev and not latest_preview:
                    latest_preview = vid

        elif server_type == "vanilla":
            latest_info = await downloader.get_vanilla_latest()
            latest_stable = latest_info.get("release", "")
            latest_preview = latest_info.get("snapshot", "")

            raw_versions = await downloader.get_vanilla_versions()
            for v in raw_versions:
                vid = v["id"]
                vtype = v.get("type", "")
                if vtype == "release":
                    ch = "stable"
                    lbl = f"{vid} (Estable)"
                elif "-pre" in vid or "pre-release" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Pre-Release)"
                elif "-rc" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Release Candidate)"
                else:
                    ch = "snapshot"
                    lbl = f"{vid} (Snapshot)"
                version_items.append({"id": vid, "label": lbl, "channel": ch})

        elif server_type == "fabric":
            fabric_items = await downloader.get_fabric_version_items()
            for f in fabric_items:
                vid = f["id"]
                is_st = f.get("stable", False)
                if is_st:
                    ch = "stable"
                    lbl = f"{vid} (Estable)"
                    if not latest_stable:
                        latest_stable = vid
                elif "-pre" in vid or "-rc" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Pre-Release)"
                    if not latest_preview:
                        latest_preview = vid
                else:
                    ch = "snapshot"
                    lbl = f"{vid} (Snapshot)"
                    if not latest_preview:
                        latest_preview = vid
                version_items.append({"id": vid, "label": lbl, "channel": ch})

        elif server_type in ["paper", "folia", "velocity"]:
            classified = await downloader.get_paper_classified_versions(server_type)
            version_items = classified.get("versions", [])
            latest_stable = classified.get("latest_stable", "")
            latest_preview = classified.get("latest_preview", "")

        elif server_type == "purpur":
            purpur_versions = await downloader.get_purpur_versions()
            for pv in purpur_versions:
                is_pre = "-pre" in pv or "-rc" in pv
                ch = "pre" if is_pre else "stable"
                lbl = f"{pv} (Pre-Release)" if is_pre else f"{pv} (Estable)"
                version_items.append({"id": pv, "label": lbl, "channel": ch})
                if ch == "stable" and not latest_stable:
                    latest_stable = pv
                elif ch != "stable" and not latest_preview:
                    latest_preview = pv

        elif server_type == "forge":
            forge_list = await downloader.get_forge_versions()
            for fv in forge_list:
                vid = fv["mc_version"]
                is_rec = fv.get("is_recommended", False)
                ch = "stable" if is_rec else "preview"
                version_items.append({"id": vid, "label": fv["label"], "channel": ch})
                if is_rec and not latest_stable:
                    latest_stable = vid
                elif not is_rec and not latest_preview:
                    latest_preview = vid

    except Exception as e:
        logger.error("[UpdateInfo] Error querying versions for %s: %s", server_type, e)

    curr_l = current_version.lower()
    if server_type == "bedrock":
        current_channel = "preview" if ("preview" in curr_l or "beta" in curr_l) else "stable"
    elif "-pre" in curr_l or "pre-release" in curr_l:
        current_channel = "pre"
    elif "-rc" in curr_l:
        current_channel = "rc"
    elif "snapshot" in curr_l or re.search(r"^[0-9]{2}w[0-9]{2}[a-z]$", curr_l):
        current_channel = "snapshot"
    else:
        matching_ver = next((v for v in version_items if v.get("id") == current_version), None)
        if matching_ver and matching_ver.get("channel") in ("preview", "pre", "snapshot"):
            current_channel = matching_ver.get("channel")
        else:
            current_channel = "stable"

    curr_m = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)+)", current_version)
    curr_clean = curr_m.group(1) if curr_m else current_version

    latest_build = None
    build_update_available = False
    try:
        target_v = current_version if (current_version and current_version != "importado") else latest_stable
        if target_v and server_type in ["paper", "folia", "velocity"]:
            b_info = await downloader.get_paper_latest_build(server_type, target_v)
            if b_info and b_info.get("build"):
                latest_build = int(b_info["build"])
        elif target_v and server_type == "purpur":
            b_info = await downloader.get_purpur_latest_build(target_v)
            if b_info and b_info.get("build"):
                latest_build = int(b_info["build"])
    except Exception as ex:
        logger.warning("[UpdateInfo] Warning querying latest build for %s: %s", server_type, ex)

    if current_build is not None and latest_build is not None:
        try:
            if int(latest_build) > int(current_build):
                build_update_available = True
        except (ValueError, TypeError):
            pass

    update_available = False
    if current_version == "importado":
        update_available = bool(latest_stable)
    elif current_channel == "stable":
        if latest_stable and curr_clean and latest_stable != curr_clean:
            update_available = True
        elif build_update_available:
            update_available = True
    else:
        if latest_preview and current_version != latest_preview:
            update_available = True
        elif build_update_available:
            update_available = True

    preview_available = bool(latest_preview and latest_preview != current_version and latest_preview != latest_stable)

    enriched_versions = []
    for it in version_items:
        cinfo = get_version_changelog_info(server_type, it["id"], it.get("channel", "stable"))
        enriched = dict(it)
        enriched.update(cinfo)
        enriched_versions.append(enriched)

    latest_stable_info = get_version_changelog_info(server_type, latest_stable, "stable") if latest_stable else None
    latest_preview_info = get_version_changelog_info(server_type, latest_preview, "preview") if latest_preview else None
    current_version_info = get_version_changelog_info(server_type, current_version, current_channel) if current_version else None

    return {
        "is_installed": True,
        "server_type": server_type,
        "current_version": current_version,
        "current_build": current_build,
        "current_channel": current_channel,
        "latest_stable": latest_stable,
        "latest_preview": latest_preview,
        "latest_build": latest_build,
        "build_update_available": build_update_available,
        "latest_stable_info": latest_stable_info,
        "latest_preview_info": latest_preview_info,
        "current_version_info": current_version_info,
        "update_available": update_available,
        "preview_available": preview_available,
        "available_versions": [it["label"] for it in enriched_versions],
        "versions": enriched_versions,
    }


@router.get("/api/installer/builds", dependencies=[Depends(get_current_user)])
async def get_installer_builds(version: Optional[str] = None):
    """Retrieves available builds for the current server type and specified version."""
    _, downloader, _, _, is_server_installed = _deps()
    if not is_server_installed():
        raise HTTPException(status_code=400, detail="No hay servidor instalado")
    cfg = settings.runtime_config
    server_type = cfg.get("server_type", "paper")
    current_ver = cfg.get("server_version", "")
    current_build = cfg.get("server_build")
    target_ver = version or current_ver

    builds = []
    latest_build = None
    try:
        if server_type in ["paper", "folia", "velocity"]:
            builds = await downloader.get_paper_build_list(server_type, target_ver)
            if builds:
                latest_build = builds[0]["id"]
        elif server_type == "purpur":
            builds = await downloader.get_purpur_build_list(target_ver)
            if builds:
                latest_build = builds[0]["id"]
    except Exception as e:
        logger.error("[BuildsAPI] Error fetching builds for %s %s: %s", server_type, target_ver, e)

    return {
        "server_type": server_type,
        "version": target_ver,
        "current_build": current_build,
        "latest_build": latest_build,
        "builds": builds,
    }


@router.post("/api/installer/update", dependencies=[Depends(get_current_user)])
async def update_server(req: UpdateRequest):
    """Safely updates the existing server to a new version of the same software."""
    process_manager, downloader, backup_manager, activity_manager, is_server_installed = _deps()
    if not is_server_installed():
        raise HTTPException(status_code=400, detail="No hay ningún servidor instalado para actualizar")

    cfg = settings.runtime_config
    server_type = cfg.get("server_type", "paper")
    old_server_file = cfg.get("server_file")

    try:
        dl_info = await resolve_server_download(
            server_type,
            req.version,
            build=req.build,
            unsupported_detail="Tipo de servidor no soportado para actualización",
        )
        download_url = dl_info["download_url"]
        target_file = dl_info["target_file"]
        is_zip = dl_info["is_zip"]
        new_build = dl_info["build"]
        expected_sha256 = dl_info.get("expected_sha256")
        expected_sha1 = dl_info.get("expected_sha1")
        allowed_hosts = dl_info.get("allowed_hosts")

        was_running = process_manager.get_status() != "OFFLINE"

        async def safe_update_pipeline():
            try:
                if was_running:
                    msg = "[Dockraft] Deteniendo servidor de forma segura para aplicar actualización..."
                    process_manager._append_log(msg)
                    await process_manager.broadcast_message({"type": "log", "data": msg})
                    await process_manager.send_command("save-all", echo=False)
                    await process_manager.stop_server()
                    for _ in range(45):
                        await asyncio.sleep(1)
                        if process_manager.get_status() == "OFFLINE":
                            break
                    if process_manager.get_status() != "OFFLINE":
                        kill_msg = "[Dockraft] El servidor tardó más de 45s en cerrar; forzando detención para proceder con la actualización de forma segura..."
                        process_manager._append_log(kill_msg)
                        await process_manager.broadcast_message({"type": "log", "data": kill_msg})
                        await process_manager.kill_server()

                build_suffix = f"-b{new_build}" if new_build else ""
                tag_name = f"pre-update-{req.version}{build_suffix}"
                msg = f"[Dockraft] Generando copia de seguridad preventiva ({tag_name})..."
                process_manager._append_log(msg)
                await process_manager.broadcast_message({"type": "log", "data": msg})
                pre_backup = backup_manager.create_backup(
                    scope="full",
                    tag=tag_name,
                    compression=True,
                )
                if pre_backup.get("status") == "error":
                    err_msg = f"[Dockraft] Error al crear copia preventiva: {pre_backup.get('message')}. Abortando actualización para seguridad de datos."
                    process_manager._append_log(err_msg)
                    await process_manager.broadcast_message({"type": "log", "data": err_msg})
                    if was_running:
                        await process_manager.start_server()
                    return

                build_label = f" (Build #{new_build})" if new_build else ""
                msg = f"[Dockraft] Descargando actualización {req.version}{build_label} y verificando integridad anti-corrupción..."
                process_manager._append_log(msg)
                await process_manager.broadcast_message({"type": "log", "data": msg})

                if server_type == "forge":
                    java_path = cfg.get("java_path") or JavaManager.get_best_java_path(req.version)
                    installer_path = await downloader.download_file(
                        download_url,
                        target_file,
                        preserve_existing_configs=True,
                        verify_integrity=True,
                        expected_sha256=expected_sha256,
                        expected_sha1=expected_sha1,
                        allowed_hosts=allowed_hosts,
                    )
                    res = await downloader.install_forge_server(installer_path, java_bin=java_path)
                    settings.save_runtime_config({
                        "server_file": res.get("server_file", "run.sh"),
                        "server_version": req.version,
                    })
                else:
                    await downloader.download_file(
                        download_url,
                        target_file,
                        is_zip=is_zip,
                        preserve_existing_configs=True,
                        verify_integrity=True,
                        expected_sha256=expected_sha256,
                        expected_sha1=expected_sha1,
                        allowed_hosts=allowed_hosts,
                    )
                    if old_server_file and old_server_file != target_file and not is_zip:
                        old_path = settings.data_dir / old_server_file
                        if old_path.exists():
                            try:
                                old_path.unlink()
                            except Exception:
                                pass

                    upd_cfg = {
                        "server_file": target_file if not is_zip else old_server_file or "bedrock_server",
                        "server_version": req.version,
                    }
                    if new_build is not None:
                        try:
                            upd_cfg["server_build"] = int(new_build)
                        except (ValueError, TypeError):
                            pass
                    settings.save_runtime_config(upd_cfg)

                build_label = f" (Build #{new_build})" if new_build else ""
                activity_manager.log(
                    category="update",
                    action="Servidor actualizado",
                    details=f"Actualizado con éxito a versión {req.version}{build_label} ({server_type.upper()}). Respaldo preventivo: {pre_backup.get('filename')}",
                    user="admin",
                    status="success",
                )

                succ_msg = f"[Dockraft] ¡Servidor actualizado exitosamente a la versión {req.version}{build_label}!"
                process_manager._append_log(succ_msg)
                await process_manager.broadcast_message({"type": "log", "data": succ_msg})

                if was_running:
                    restart_msg = "[Dockraft] Reiniciando servidor automáticamente con la nueva versión..."
                    process_manager._append_log(restart_msg)
                    await process_manager.broadcast_message({"type": "log", "data": restart_msg})
                    await asyncio.sleep(1.5)
                    await process_manager.start_server()

            except Exception as ex:
                err_msg = f"[Dockraft] Error en la actualización a {req.version}: {str(ex)}"
                process_manager._append_log(err_msg)
                await process_manager.broadcast_message({"type": "log", "data": err_msg})
                activity_manager.log(
                    category="update",
                    action="Error en actualización",
                    details=f"Fallo al actualizar a {req.version}: {str(ex)}",
                    user="admin",
                    status="error",
                )
                if was_running and process_manager.get_status() == "OFFLINE":
                    await process_manager.start_server()

        _track_task(safe_update_pipeline())

        return {
            "status": "started",
            "server_type": server_type,
            "target_version": req.version,
            "download_url": download_url,
            "auto_stopping": was_running,
        }

    except HTTPException:
        raise
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise HTTPException(status_code=404, detail="Version not found")
        if "HTTPStatusError" in type(e).__name__:
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

